"""
HTTP Streaming Proxy for Telegram videos.
Translates HTTP Range requests to Telegram stream_media() calls.
"""
import asyncio
import struct
from typing import Optional, Callable, AsyncIterator, Any

from aiohttp import web

from adapters.telegram.tdlib_client import TDLibClient


class StreamingProxy:
    """
    HTTP proxy server that serves Telegram media with Range request support.
    
    Features:
    - Range request support for video seeking
    - MOOV atom detection for MP4 files
    - Automatic byte range translation to stream_media()
    """
    
    def __init__(
        self, 
        client: 'TelegramClient',  # Type hint string to avoid import if needed
        host: str = "127.0.0.1",
        port: int = 8765
    ):
        """
        Initialize streaming proxy.
        
        Args:
            client: Telethon client for media access
            host: Host to bind to
            port: Port to listen on
        """
        self.client = client
        self.host = host
        self.port = port
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        
        # Active streams: message_id -> (chat_id, file_size)
        self._streams: dict[str, tuple[int, int, int]] = {}
    
    @property
    def base_url(self) -> str:
        """Get base URL for the proxy."""
        return f"http://{self.host}:{self.port}"
    
    
    def get_stream_url(self, message_id: int, chat_id: int, file_size: int, message_obj: Any = None) -> str:
        """
        Register a stream and get its URL.
        
        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            file_size: Total file size in bytes
            message_obj: Telethon Message object (cached to avoid re-fetching)
            
        Returns:
            URL to stream the video
        """
        stream_id = f"{chat_id}_{message_id}"
        self._streams[stream_id] = (message_id, chat_id, file_size, message_obj)
        return f"{self.base_url}/stream/{stream_id}"
    
    async def start(self) -> None:
        """Start the HTTP server."""
        self._app = web.Application()
        self._app.router.add_get("/stream/{stream_id}", self._handle_stream)
        self._app.router.add_get("/health", self._handle_health)
        
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
    
    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._streams.clear()
    
    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.Response(text="OK")
    
    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Handle stream request with Range support.
        
        Supports:
        - Range: bytes=start-end
        - Range: bytes=start-
        - No Range header (full file)
        """
        stream_id = request.match_info['stream_id']
        
        if stream_id not in self._streams:
            return web.Response(status=404, text="Stream not found")
        
        # Unpack with optional message_obj (might be 3 or 4 items depending on version)
        # But we just updated it to 4.
        data = self._streams[stream_id]
        if len(data) == 4:
            message_id, chat_id, file_size, message = data
        else:
            # Fallback for old/race condition
            message_id, chat_id, file_size = data
            message = None
        
        # Parse Range header
        range_header = request.headers.get('Range', '')
        start = 0
        end = file_size - 1
        
        if range_header.startswith('bytes='):
            range_spec = range_header[6:]
            if '-' in range_spec:
                parts = range_spec.split('-')
                if parts[0]:
                    start = int(parts[0])
                if parts[1]:
                    end = int(parts[1])
        
        # Clamp values
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        content_length = end - start + 1
        
        # Prepare response
        if range_header:
            response = web.StreamResponse(status=206)
            response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        else:
            response = web.StreamResponse(status=200)
        
        # Fetch the actual message object first to get mime_type - DONE via cache
        if not message:
            print(f"[Proxy] Warning: Message not cached for {stream_id}, fetching...")
            try:
                messages = await self.client.get_messages(chat_id, ids=[message_id])
                if messages:
                    message = messages[0]
            except Exception as e:
                print(f"[Proxy] Error fetching message: {e}")

        response.headers['Content-Type'] = 'video/mp4'
        if message and hasattr(message, 'document') and message.document:
             mime = getattr(message.document, 'mime_type', 'video/mp4')
             if mime:
                 response.headers['Content-Type'] = mime
        
        # print(f"[Proxy] Response Headers: Content-Type={response.headers['Content-Type']}, Content-Length={content_length}")
        
        await response.prepare(request)
        
        # print(f"[Proxy] Starting stream for {stream_id} range={start}-{end}")
        
        # Stream data from Telegram
        try:
            if not message:
                 print("[Proxy] Check: No message object to download from!")
                 return response

            bytes_sent = 0
            # Smaller chunk size for better MPV compatibility and seeking
            chunk_size = 64 * 1024  
            
            # print(f"[Proxy] Downloading media from message {message.id}...")
            # Use iter_download
            async for chunk in self.client.iter_download(
                message.media,
                offset=start,
                limit=content_length, # Telethon limit is bytes
                chunk_size=chunk_size,
                request_size=chunk_size
            ):
                 try:
                     if bytes_sent == 0:
                         print(f"[Proxy] FIRST CHUNK RECEIVED: {len(chunk)} bytes")
                     
                     await response.write(chunk)
                     bytes_sent += len(chunk)
                     
                     if bytes_sent % (1024*1024) == 0: # Log every 1MB
                        print(f"[Proxy] Sent {bytes_sent} bytes so far...")
                        
                 except (ConnectionResetError, BrokenPipeError) as e:
                     # This is normal when player stops or seeks
                     print(f"[Proxy] Client disconnected (normal): {e}")
                     break
                 except Exception as e:
                     if "Cannot write to closing transport" in str(e):
                         print(f"[Proxy] Client disconnected (transport closed).")
                         break
                     print(f"[Proxy] Client disconnected during write: {e}")
                     break
            
            print(f"[Proxy] Stream finished. Sent {bytes_sent}/{content_length}")
            
        except asyncio.CancelledError:
            print("[Proxy] Stream cancelled")
            pass
        except Exception as e:
            print(f"[Proxy] Streaming error: {e}")
        
        return response


class MoovAtomHandler:
    """
    Handles MOOV atom positioning for MP4 files.
    
    For videos with MOOV at end, this class can:
    1. Detect MOOV position
    2. Read MOOV atom
    3. Serve MOOV-first virtual file
    """
    
    ATOM_HEADER_SIZE = 8
    
    @staticmethod
    def parse_atom_header(data: bytes) -> tuple[int, str]:
        """
        Parse MP4 atom header.
        
        Args:
            data: 8 bytes of atom header
            
        Returns:
            Tuple of (size, type)
        """
        if len(data) < 8:
            return 0, ""
        
        size = struct.unpack('>I', data[:4])[0]
        atom_type = data[4:8].decode('ascii', errors='ignore')
        
        return size, atom_type
    
    @staticmethod
    async def find_moov_position(
        read_chunk: Callable[[int, int], AsyncIterator[bytes]],
        file_size: int
    ) -> Optional[tuple[int, int]]:
        """
        Find MOOV atom position in file.
        
        Args:
            read_chunk: Async function to read bytes(offset, limit)
            file_size: Total file size
            
        Returns:
            Tuple of (moov_offset, moov_size) or None
        """
        offset = 0
        
        while offset < file_size:
            # Read atom header
            header_data = b""
            async for chunk in read_chunk(offset, MoovAtomHandler.ATOM_HEADER_SIZE):
                header_data += chunk
            
            if len(header_data) < 8:
                break
            
            size, atom_type = MoovAtomHandler.parse_atom_header(header_data)
            
            if size == 0:
                break
            
            if atom_type == 'moov':
                return offset, size
            
            offset += size
        
        return None
    
    @staticmethod
    def is_moov_at_start(moov_position: Optional[tuple[int, int]]) -> bool:
        """Check if MOOV is at start of file (offset < 100KB)."""
        if moov_position is None:
            return True  # Assume OK if we can't find it
        
        moov_offset, _ = moov_position
        return moov_offset < 100 * 1024  # 100KB threshold


class TelegramStreamingProxy(StreamingProxy):
    """
    Extended streaming proxy with Telegram-specific features.
    """
    
    def __init__(self, tdlib_client: TDLibClient, cache_dir=None, **kwargs):
        super().__init__(tdlib_client, **kwargs)
        self.cache_dir = cache_dir
        self.moov_handler = MoovAtomHandler()
    
    async def prepare_stream(
        self, 
        message_id: int, 
        chat_id: int, 
        file_size: int
    ) -> str:
        """
        Prepare a video for streaming.
        
        For MP4 files with MOOV at end, this may need to
        download and cache the MOOV atom first.
        
        Args:
            message_id: Telegram message ID
            chat_id: Telegram chat ID
            file_size: Total file size
            
        Returns:
            Stream URL
        """
        # TODO: Implement MOOV-at-end handling
        # For now, just register the stream
        return self.get_stream_url(message_id, chat_id, file_size)
