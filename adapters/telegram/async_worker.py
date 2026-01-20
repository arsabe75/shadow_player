"""
Simplified Telegram async worker using threading and asyncio.
Migrated to Telethon + QR Code Login.
"""
import asyncio
import threading
from typing import Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum
from queue import Queue, Empty

from PySide6.QtCore import QObject, Signal
from telethon import TelegramClient, errors


class TelegramOp(Enum):
    """Telegram operation types."""
    GET_QR_CODE = "get_qr_code"
    WAIT_FOR_QR_SCAN = "wait_for_qr_scan"
    SEND_PASSWORD = "send_password"
    LOGOUT = "logout"
    STOP = "stop"
    GET_CHATS = "get_chats"
    GET_CHAT_HISTORY = "get_chat_history"
    GET_FORUM_TOPICS = "get_forum_topics"
    GET_STREAM_URL = "get_stream_url"





@dataclass
class TelegramTask:
    """A task to execute."""
    operation: TelegramOp
    kwargs: dict
    callback_id: int


class TelegramAsyncWorker(QObject):
    """
    Simplified worker that runs Telegram operations in a background thread.
    """
    
    operation_completed = Signal(int, object)  # callback_id, result
    operation_failed = Signal(int, str)  # callback_id, error_message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_queue = Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callback_counter = 0
        self._callbacks: dict[int, Callable] = {}
        
        # Telethon client
        self._client: Optional[TelegramClient] = None
        self._qr_login_obj = None  # To hold the active QR login request
        
        self.operation_completed.connect(self._handle_result)
        self.operation_failed.connect(self._handle_error)
    
    def start(self):
        """Start the worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the worker thread."""
        self._running = False
        self._task_queue.put(TelegramTask(TelegramOp.STOP, {}, -1))
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
    
    def _run_event_loop(self):
        """Run the async event loop in the worker thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._worker_main())
        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            try:
                loop.run_until_complete(self._cleanup())
            except Exception:
                pass
            loop.close()
    
    async def _cleanup(self):
        """Cleanup client on shutdown."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
    
    async def _worker_main(self):
        """Main worker loop."""
        from adapters.telegram.config import load_telegram_credentials
        from pathlib import Path
        
        # Initialize client
        api_id, api_hash = load_telegram_credentials()
        # Ensure we use the same session path as TDLibClient
        session_dir = Path.home() / ".shadow_player" / "tdlib"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = str(session_dir / "shadow_player")
        
        self._client = TelegramClient(
            session_file,
            api_id=api_id,
            api_hash=api_hash,
            system_version="Desktop",
            device_model="Shadow Player",
            app_version="1.0.0"
        )
        
        # Connect with auto-repair for corrupt sessions
        try:
            await self._client.connect()
        except Exception as e:
            if "no such column" in str(e) or "database is locked" in str(e) or "database disk image is malformed" in str(e):
                print(f"[TelegramWorker] Session file corrupt/incompatible, deleting: {e}")
                # Close possibly open handlers
                try:
                    await self._client.disconnect()
                except:
                    pass
                
                # Delete session file
                session_path = session_dir / "shadow_player.session"
                if session_path.exists():
                    try:
                        session_path.unlink()
                        print("[TelegramWorker] Session file deleted.")
                    except OSError as os_err:
                        print(f"[TelegramWorker] Failed to delete session: {os_err}")

                # Re-init client
                self._client = TelegramClient(
                    session_file,
                    api_id=api_id,
                    api_hash=api_hash,
                    system_version="Desktop",
                    device_model="Shadow Player",
                    app_version="1.0.0"
                )
                await self._client.connect()
            else:
                raise e
        

        
        # Start Proxy
        from adapters.telegram.streaming_proxy import TelegramStreamingProxy
        self._proxy = TelegramStreamingProxy(self._client)
        try:
            await self._proxy.start()
            print(f"[TelegramWorker] Streaming Proxy started at {self._proxy.base_url}")
        except Exception as e:
            print(f"[TelegramWorker] Failed to start proxy: {e}")

        while self._running:
            # Get task from queue WITHOUT blocking to allow event loop to process HTTP requests
            try:
                task = self._task_queue.get_nowait()
            except Empty:
                # Yield control to event loop - this allows aiohttp to process requests
                await asyncio.sleep(0.05)
                continue
            
            if task.operation == TelegramOp.STOP:
                break
            
            # Execute task
            try:
                result = await self._execute_task(task)
                self.operation_completed.emit(task.callback_id, result)
            except Exception as e:
                print(f"Task error: {e}")
                self.operation_failed.emit(task.callback_id, str(e))
    
    async def _execute_task(self, task: TelegramTask) -> Any:
        """Execute a single task."""
        from adapters.telegram.tdlib_client import AuthState
        
        print(f"[TelegramWorker] Executing task: {task.operation}")
        
        # Ensure connected
        if not self._client.is_connected:
             await self._client.connect()
        
        if task.operation == TelegramOp.GET_STREAM_URL:
            if not self._proxy:
                raise RuntimeError("Streaming proxy not initialized - cannot generate stream URL")
            
            message_id = task.kwargs['message_id']
            chat_id = task.kwargs['chat_id']
            
            # Fetch message to get file size
            msgs = await self._client.get_messages(chat_id, ids=[message_id])
            if not msgs or not msgs[0]:
                raise ValueError(f"Message {message_id} not found in chat {chat_id}")
            
            msg = msgs[0]
            size = 0
            if hasattr(msg, 'file') and msg.file:
                size = msg.file.size
            elif msg.document:
                size = msg.document.size
            elif msg.video:
                size = msg.video.size
            
            if size == 0:
                raise ValueError(f"Could not determine file size for message {message_id}")
            
            print(f"[TelegramWorker] Stream URL generated for {message_id}, size: {size}")
            return self._proxy.get_stream_url(message_id, chat_id, size, message_obj=msg)

        if task.operation == TelegramOp.GET_QR_CODE:
            # Check if already authorized
            if await self._client.is_user_authorized():
                return "AUTHORIZED"
            
            # Start QR flow
            self._qr_login_obj = await self._client.qr_login()
            return self._qr_login_obj.url
            
        elif task.operation == TelegramOp.WAIT_FOR_QR_SCAN:
            if not self._qr_login_obj:
                raise ValueError("QR Login not initiated")
            
            try:
                # wait returns user on success, raises error if 2FA needed
                await self._qr_login_obj.wait(120)
                return AuthState.READY
            except errors.SessionPasswordNeededError:
                return AuthState.WAIT_PASSWORD
            except Exception as e:
                # Reset if other error
                self._qr_login_obj = None 
                raise e
            
        elif task.operation == TelegramOp.SEND_PASSWORD:
            password = task.kwargs['password']
            await self._client.sign_in(password=password)
            return AuthState.READY
            
        elif task.operation == TelegramOp.LOGOUT:
            if self._client and self._client.is_connected:
                await self._client.log_out()
            return True

        elif task.operation == TelegramOp.GET_CHATS:
            limit = task.kwargs.get('limit', 100)
            chats = []
            if not self._client.is_connected:
                await self._client.connect()
                
            async for dialog in self._client.iter_dialogs(limit=limit):
                if dialog.is_channel or dialog.is_group:
                    chats.append(dialog.entity)
            return chats

        elif task.operation == TelegramOp.GET_CHAT_HISTORY:
            chat_id = task.kwargs['chat_id']
            limit = task.kwargs.get('limit', 50)
            thread_id = task.kwargs.get('thread_id', None)
            
            from telethon.tl.types import InputMessagesFilterVideo
            
            if not self._client.is_connected:
                await self._client.connect()
                
            videos = []
            
            kwargs = {
                'limit': limit,
                'filter': InputMessagesFilterVideo
            }
            if thread_id:
                kwargs['reply_to'] = thread_id
            
            async for message in self._client.iter_messages(chat_id, **kwargs):
                videos.append(message)
            return videos

        elif task.operation == TelegramOp.GET_FORUM_TOPICS:
            chat_id = task.kwargs['chat_id']
            if not self._client.is_connected:
                 await self._client.connect()
            
            # Fallback strategy: Scan message history for 'TopicCreate' actions
            # Or assume Telethon doesn't support it and return empty with log.
            # Actually, we can use iter_messages with finding service messages that have action=MessageActionTopicCreate
            from telethon.tl.types import MessageActionTopicCreate
            
            topics = []
            try:
                # We need to scan the "forum" channel history for topic creation messages.
                # In forums, the "General" topic (id=1) or main history usually implies topics?
                # Actually, iterate messages and look for topics.
                # This is inefficient but the only way without the Request method.
                # Improving: Just try to get recent active thread service messages?
                
                # Let's limit scan to prevent freezing
                count = 0
                async for message in self._client.iter_messages(chat_id, limit=300):
                     if message.action and isinstance(message.action, MessageActionTopicCreate):
                         # Found a topic
                         topic_id = message.id
                         title = message.action.title
                         # Construct a simple object to mimic the result
                         # using a dynamic class or dict
                         class SimpleTopic:
                             def __init__(self, id, title):
                                 self.id = id
                                 self.title = title
                         
                         topics.append(SimpleTopic(topic_id, title))
            except Exception as e:
                print(f"Fallback topic scan error: {e}")
            
            return topics
        
        return None
    
    def execute(self, operation: TelegramOp, callback: Callable, **kwargs):
        """Queue an operation for execution."""
        self._callback_counter += 1
        callback_id = self._callback_counter
        self._callbacks[callback_id] = callback
        
        task = TelegramTask(operation, kwargs, callback_id)
        self._task_queue.put(task)
    
    def _handle_result(self, callback_id: int, result: Any):
        """Handle successful result."""
        callback = self._callbacks.pop(callback_id, None)
        if callback:
            callback(True, result)
    
    def _handle_error(self, callback_id: int, error_msg: str):
        """Handle error."""
        callback = self._callbacks.pop(callback_id, None)
        if callback:
            callback(False, error_msg)


# Global worker instance
_telegram_worker: Optional[TelegramAsyncWorker] = None


def get_telegram_worker() -> TelegramAsyncWorker:
    """Get or create the global worker."""
    global _telegram_worker
    if _telegram_worker is None:
        _telegram_worker = TelegramAsyncWorker()
        _telegram_worker.start()
    return _telegram_worker


def stop_telegram_worker():
    """Stop the global worker."""
    global _telegram_worker
    if _telegram_worker is not None:
        _telegram_worker.stop()
        _telegram_worker = None
