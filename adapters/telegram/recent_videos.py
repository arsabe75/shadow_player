"""
Recent videos manager for Telegram.
Maintains separate lists for local and Telegram videos.
"""
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

from adapters.security.secure_storage import SecureStorage


@dataclass
class TelegramVideo:
    """Video from Telegram with playback progress."""
    message_id: int
    chat_id: int
    chat_title: str
    file_id: str
    title: str
    duration: int  # seconds
    file_size: int  # bytes
    thumbnail_path: Optional[str]
    progress_percent: float  # 0-100
    progress_position: int  # milliseconds
    last_played: float  # timestamp
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TelegramVideo':
        """Create from dictionary."""
        return cls(**data)


class RecentVideosManager:
    """
    Manages recent Telegram videos.
    Uses encrypted storage for persistence.
    Separate from local video history.
    """
    
    STORAGE_KEY = "recent_telegram_videos"
    MAX_ENTRIES = 50
    
    def __init__(self, secure_storage: SecureStorage):
        """
        Initialize recent videos manager.
        
        Args:
            secure_storage: SecureStorage instance
        """
        self.secure_storage = secure_storage
        self._videos: Optional[List[TelegramVideo]] = None
    
    def _load(self) -> List[TelegramVideo]:
        """Load videos from storage."""
        if self._videos is not None:
            return self._videos
        
        data = self.secure_storage.load_encrypted(self.STORAGE_KEY)
        if data is None:
            self._videos = []
        else:
            self._videos = [
                TelegramVideo.from_dict(item)
                for item in data.get('videos', [])
            ]
        
        return self._videos
    
    def _save(self) -> None:
        """Save videos to storage."""
        if self._videos is None:
            return
        
        data = {
            'videos': [v.to_dict() for v in self._videos]
        }
        self.secure_storage.save_encrypted(self.STORAGE_KEY, data)
    
    def get_recent(self, limit: int = 10) -> List[TelegramVideo]:
        """
        Get recent videos sorted by last played.
        
        Args:
            limit: Maximum videos to return
            
        Returns:
            List of TelegramVideo objects
        """
        videos = self._load()
        sorted_videos = sorted(videos, key=lambda x: x.last_played, reverse=True)
        return sorted_videos[:limit]
    
    def add_or_update(self, video: TelegramVideo) -> None:
        """
        Add video to recent list or update if exists.
        
        Args:
            video: Video to add/update
        """
        videos = self._load()
        
        # Find existing entry
        existing_idx = None
        for i, v in enumerate(videos):
            if v.message_id == video.message_id and v.chat_id == video.chat_id:
                existing_idx = i
                break
        
        # Update last played
        video.last_played = time.time()
        
        if existing_idx is not None:
            # Update existing
            videos[existing_idx] = video
        else:
            # Add new
            videos.insert(0, video)
            
            # Trim to max entries
            if len(videos) > self.MAX_ENTRIES:
                videos = videos[:self.MAX_ENTRIES]
        
        self._videos = videos
        self._save()
    
    def update_progress(
        self, 
        message_id: int, 
        chat_id: int, 
        progress_percent: float,
        progress_position: int
    ) -> None:
        """
        Update playback progress for a video.
        
        Args:
            message_id: Message ID of the video
            chat_id: Chat ID
            progress_percent: Progress 0-100
            progress_position: Position in milliseconds
        """
        videos = self._load()
        
        for video in videos:
            if video.message_id == message_id and video.chat_id == chat_id:
                video.progress_percent = progress_percent
                video.progress_position = progress_position
                video.last_played = time.time()
                self._save()
                break
    
    def get_progress(self, message_id: int, chat_id: int) -> Optional[int]:
        """
        Get saved progress position for a video.
        
        Args:
            message_id: Message ID
            chat_id: Chat ID
            
        Returns:
            Progress position in milliseconds or None
        """
        videos = self._load()
        
        for video in videos:
            if video.message_id == message_id and video.chat_id == chat_id:
                return video.progress_position
        
        return None
    
    def remove(self, message_id: int, chat_id: int) -> bool:
        """
        Remove a video from recent list.
        
        Args:
            message_id: Message ID
            chat_id: Chat ID
            
        Returns:
            True if removed, False if not found
        """
        videos = self._load()
        original_len = len(videos)
        
        self._videos = [
            v for v in videos 
            if not (v.message_id == message_id and v.chat_id == chat_id)
        ]
        
        if len(self._videos) < original_len:
            self._save()
            return True
        return False
    
    def clear_all(self) -> None:
        """Clear all recent videos."""
        self._videos = []
        self._save()
