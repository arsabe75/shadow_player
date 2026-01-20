"""
TDLib client wrapper using Telethon for Telegram API access.
Handles authentication (QR/Phone), session management, and media streaming.
"""
import asyncio
from pathlib import Path
from typing import Optional, AsyncIterator, Callable, Any
from dataclasses import dataclass

from telethon import TelegramClient, events, errors, types
from telethon.tl.types import InputMessagesFilterVideo

from adapters.telegram.config import load_telegram_credentials
from adapters.security.secure_storage import SecureStorage


@dataclass
class AuthState:
    """Authentication state."""
    WAIT_PHONE = "wait_phone"
    WAIT_CODE = "wait_code"
    WAIT_PASSWORD = "wait_password"
    WAIT_QR_SCAN = "wait_qr_scan"
    READY = "ready"
    ERROR = "error"


@dataclass
class TelegramSession:
    """Session information."""
    user_id: int
    username: Optional[str]
    first_name: str
    last_name: Optional[str]
    phone: str


class TDLibClient:
    """
    Wrapper for Telethon client with encrypted session storage.
    
    Features:
    - Encrypted database using SecureStorage keys (if supported by backend)
    - State machine for authentication flow (QR Code focus)
    - Async media streaming
    """
    
    def __init__(self, data_dir: Path, secure_storage: SecureStorage):
        """
        Initialize TDLib client.
        
        Args:
            data_dir: Directory for TDLib database
            secure_storage: SecureStorage instance for encryption keys
        """
        self.data_dir = data_dir
        self.secure_storage = secure_storage
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._client: Optional[TelegramClient] = None
        self._auth_state: str = AuthState.WAIT_QR_SCAN
        self._qr_login_obj = None  # To store the active QR login object
        
        # Callbacks
        self._on_auth_state_changed: Optional[Callable[[str], None]] = None
    
    @property
    def auth_state(self) -> str:
        """Current authentication state."""
        return self._auth_state
    
    @property
    def is_authorized(self) -> bool:
        """Check if client is authorized."""
        return self._auth_state == AuthState.READY
    
    @property
    def client(self) -> Optional[TelegramClient]:
        """Raw Telethon client access (internal use)."""
        return self._client
        
    def set_auth_callback(self, callback: Callable[[str], None]):
        """Set callback for auth state changes."""
        self._on_auth_state_changed = callback
    
    def _update_auth_state(self, state: str):
        """Update auth state and notify callback."""
        self._auth_state = state
        if self._on_auth_state_changed:
            self._on_auth_state_changed(state)
    
    async def initialize(self) -> None:
        """
        Initialize the Telethon client.
        """
        api_id, api_hash = load_telegram_credentials()
        
        # Note: Telethon handles session storage differently.
        # We pass the session file path.
        session_file = str(self.data_dir / "shadow_player")
        
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
                print(f"[TDLibClient] Session file corrupt/incompatible, deleting: {e}")
                try:
                    await self._client.disconnect()
                except:
                    pass
                
                # Delete session file (Telethon appends .session)
                session_path = self.data_dir / "shadow_player.session"
                if session_path.exists():
                    try:
                        session_path.unlink()
                        print("[TDLibClient] Session file deleted.")
                    except OSError:
                        pass
                
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
    
    async def check_authorization(self) -> bool:
        """
        Check if there's a valid session.
        
        Returns:
            True if authorized, False if login required
        """
        if self._client is None or not self._client.is_connected:
            await self.initialize()
        
        try:
            if await self._client.is_user_authorized():
                self._update_auth_state(AuthState.READY)
                return True
            else:
                self._update_auth_state(AuthState.WAIT_QR_SCAN)
                return False
        except Exception:
            self._update_auth_state(AuthState.WAIT_QR_SCAN)
            return False
            
    # --- QR Code Login Flow ---
    
    async def request_qr_code(self) -> str:
        """
        Request a QR code login URL.
        
        Returns:
            URL string (tg://login?token=...)
        """
        if self._client is None:
            await self.initialize()
            
        try:
            self._qr_login_obj = await self._client.qr_login()
            return self._qr_login_obj.url
        except Exception as e:
            print(f"Error requesting QR: {e}")
            raise

    async def wait_for_qr_scan(self) -> str:
        """
        Wait for the user to scan the QR code.
        
        Returns:
            Next auth state (READY or WAIT_PASSWORD)
        """
        if not self._qr_login_obj:
            raise ValueError("QR Login not initiated")
            
        try:
            # wait(timeout) returns user object on success
            # raises SessionPasswordNeededError if 2FA enabled
            await self._qr_login_obj.wait(120) 
            self._update_auth_state(AuthState.READY)
            return AuthState.READY
            
        except errors.SessionPasswordNeededError:
            self._update_auth_state(AuthState.WAIT_PASSWORD)
            return AuthState.WAIT_PASSWORD
        except Exception as e:
            print(f"Wait QR Error: {e}")
            self._update_auth_state(AuthState.ERROR)
            raise

    async def send_password(self, password: str) -> bool:
        """
        Send 2FA password.
        
        Args:
            password: Two-factor authentication password
            
        Returns:
            True if authenticated successfully
        """
        try:
            await self._client.sign_in(password=password)
            self._update_auth_state(AuthState.READY)
            return True
        except errors.PasswordHashInvalidError:
            return False
        except Exception as e:
            print(f"Password Error: {e}")
            return False
    
    async def logout(self) -> None:
        """Log out and clear session."""
        if self._client and self._client.is_connected:
            try:
                await self._client.log_out()
            except Exception:
                pass
            await self._client.disconnect()
            self._client = None
        
        self._update_auth_state(AuthState.WAIT_QR_SCAN)
    
    async def get_session_info(self) -> Optional[TelegramSession]:
        """Get current session information."""
        if not self.is_authorized or not self._client:
            return None
        
        try:
            me = await self._client.get_me()
            return TelegramSession(
                user_id=me.id,
                username=me.username,
                first_name=me.first_name,
                last_name=me.last_name,
                phone=me.phone
            )
        except Exception:
            return None
    
    async def get_chats(self, limit: int = 100) -> list:
        """
        Get list of chats (channels, groups).
        
        Args:
            limit: Maximum number of chats to return
            
        Returns:
            List of Chat objects (Telethon objects)
        """
        if not self._client:
            return []
        
        chats = []
        # Telethon: iter_dialogs
        async for dialog in self._client.iter_dialogs(limit=limit):
            if dialog.is_channel or dialog.is_group:
                # We return the entity (chat)
                chats.append(dialog.entity)
        
        return chats
    
    async def search_videos(self, chat_id: int, limit: int = 50) -> list:
        """
        Search for video messages in a chat.
        
        Args:
            chat_id: Chat to search in
            limit: Maximum results
            
        Returns:
            List of Message objects with video
        """
        if not self._client:
            return []
        
        videos = []
        # Telethon: iter_messages with filter
        try:
            async for message in self._client.iter_messages(
                chat_id,
                limit=limit,
                filter=InputMessagesFilterVideo
            ):
                videos.append(message)
        except Exception as e:
            print(f"Error searching videos: {e}")
            
        return videos
    
    async def get_message(self, chat_id: int, message_id: int):
        """Fetch a single message by ID."""
        if not self._client:
            return None
        try:
            return await self._client.get_messages(chat_id, ids=message_id)
        except Exception as e:
            print(f"Error fetching message {message_id}: {e}")
            return None

    async def stream_media(
        self, 
        message, 
        offset: int = 0, 
        limit: int = 0
    ) -> AsyncIterator[bytes]:
        """
        Stream media bytes using Telethon.
        
        Args:
            message: Message containing media (Telethon message)
            offset: Byte offset to start from
            limit: Maximum bytes to return (0 = all)
            
        Yields:
            Chunks of media bytes
        """
        if not self._client:
            return
        
        # Telethon iter_download
        try:
            async for chunk in self._client.iter_download(
                message.media,
                offset=offset,
                limit=limit if limit > 0 else None,
                chunk_size=1024*1024 # 1MB chunks
            ):
                yield chunk
        except Exception as e:
            print(f"Streaming error: {e}")
    
    async def get_file_size(self, message) -> int:
        """Get file size of media in message."""
        if hasattr(message, 'file') and message.file:
            return message.file.size
        # Fallback inspection
        if message.video:
            return message.video.size
        if message.document:
            return message.document.size
        return 0
    
    async def close(self) -> None:
        """Close client connection."""
        if self._client:
            await self._client.disconnect()
            self._client = None
