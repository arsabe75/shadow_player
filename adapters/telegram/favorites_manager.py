"""
Favorites manager for Telegram channels and groups.
Handles persistence with encrypted storage.
"""
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

from adapters.security.secure_storage import SecureStorage


@dataclass
class FavoriteChannel:
    """A favorite Telegram channel or group."""
    chat_id: int
    title: str
    username: Optional[str]
    chat_type: str  # 'channel', 'supergroup', 'group'
    video_count: int
    thumbnail_path: Optional[str]
    added_at: float
    last_accessed: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FavoriteChannel':
        """Create from dictionary."""
        return cls(**data)


class FavoritesManager:
    """
    Manages favorite channels and groups.
    Uses encrypted storage for persistence.
    """
    
    STORAGE_KEY = "telegram_favorites"
    
    def __init__(self, secure_storage: SecureStorage):
        """
        Initialize favorites manager.
        
        Args:
            secure_storage: SecureStorage instance
        """
        self.secure_storage = secure_storage
        self._favorites: Optional[List[FavoriteChannel]] = None
    
    def _load(self) -> List[FavoriteChannel]:
        """Load favorites from storage."""
        if self._favorites is not None:
            return self._favorites
        
        data = self.secure_storage.load_encrypted(self.STORAGE_KEY)
        if data is None:
            self._favorites = []
        else:
            self._favorites = [
                FavoriteChannel.from_dict(item) 
                for item in data.get('favorites', [])
            ]
        
        return self._favorites
    
    def _save(self) -> None:
        """Save favorites to storage."""
        if self._favorites is None:
            return
        
        data = {
            'favorites': [f.to_dict() for f in self._favorites]
        }
        self.secure_storage.save_encrypted(self.STORAGE_KEY, data)
    
    def get_favorites(self) -> List[FavoriteChannel]:
        """
        Get all favorites sorted by last access (most recent first).
        
        Returns:
            List of FavoriteChannel objects
        """
        favorites = self._load()
        return sorted(favorites, key=lambda x: x.last_accessed, reverse=True)
    
    def add_favorite(self, channel: FavoriteChannel) -> bool:
        """
        Add a channel to favorites.
        
        Args:
            channel: Channel to add
            
        Returns:
            True if added, False if already exists
        """
        favorites = self._load()
        
        # Check for duplicates
        if any(f.chat_id == channel.chat_id for f in favorites):
            return False
        
        # Set timestamps if not set
        if channel.added_at == 0:
            channel.added_at = time.time()
        if channel.last_accessed == 0:
            channel.last_accessed = time.time()
        
        favorites.append(channel)
        self._save()
        return True
    
    def remove_favorite(self, chat_id: int) -> bool:
        """
        Remove a channel from favorites.
        
        Args:
            chat_id: Chat ID to remove
            
        Returns:
            True if removed, False if not found
        """
        favorites = self._load()
        original_len = len(favorites)
        
        self._favorites = [f for f in favorites if f.chat_id != chat_id]
        
        if len(self._favorites) < original_len:
            self._save()
            return True
        return False
    
    def update_access(self, chat_id: int) -> None:
        """
        Update last access time for a channel.
        
        Args:
            chat_id: Chat ID to update
        """
        favorites = self._load()
        
        for favorite in favorites:
            if favorite.chat_id == chat_id:
                favorite.last_accessed = time.time()
                self._save()
                break
    
    def update_video_count(self, chat_id: int, count: int) -> None:
        """
        Update video count for a channel.
        
        Args:
            chat_id: Chat ID to update
            count: New video count
        """
        favorites = self._load()
        
        for favorite in favorites:
            if favorite.chat_id == chat_id:
                favorite.video_count = count
                self._save()
                break
    
    def is_favorite(self, chat_id: int) -> bool:
        """
        Check if a channel is in favorites.
        
        Args:
            chat_id: Chat ID to check
            
        Returns:
            True if favorite, False otherwise
        """
        favorites = self._load()
        return any(f.chat_id == chat_id for f in favorites)
    
    def get_favorite(self, chat_id: int) -> Optional[FavoriteChannel]:
        """
        Get a specific favorite by chat ID.
        
        Args:
            chat_id: Chat ID to find
            
        Returns:
            FavoriteChannel or None
        """
        favorites = self._load()
        for favorite in favorites:
            if favorite.chat_id == chat_id:
                return favorite
        return None
    
    def clear_all(self) -> None:
        """Clear all favorites."""
        self._favorites = []
        self._save()
