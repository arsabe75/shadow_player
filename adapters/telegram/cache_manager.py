"""
Telegram video cache manager with LRU eviction strategy.
Implements NVR-style storage management with configurable limits.
"""
import shutil
import sqlite3
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import List, Optional


class CacheSizeLimit(IntEnum):
    """Cache size limits in bytes."""
    GB_2 = 2 * 1024 * 1024 * 1024
    GB_4 = 4 * 1024 * 1024 * 1024
    GB_6 = 6 * 1024 * 1024 * 1024
    GB_8 = 8 * 1024 * 1024 * 1024
    GB_10 = 10 * 1024 * 1024 * 1024
    GB_30 = 30 * 1024 * 1024 * 1024
    GB_50 = 50 * 1024 * 1024 * 1024


class CacheRetention(IntEnum):
    """Retention periods in seconds."""
    DAYS_3 = 3 * 24 * 60 * 60
    WEEK_1 = 7 * 24 * 60 * 60
    MONTH_1 = 30 * 24 * 60 * 60
    UNLIMITED = -1


@dataclass
class DiskInfo:
    """Information about disk where cache is stored."""
    total: int          # Total space in bytes
    used: int           # Used space in bytes
    free: int           # Free space in bytes
    cache_used: int     # Space used by app cache
    
    @property
    def free_percent(self) -> float:
        """Percentage of free disk space."""
        return (self.free / self.total) * 100 if self.total > 0 else 0
    
    @property
    def available_for_cache(self) -> int:
        """Available space for cache (leaving 5GB reserve)."""
        RESERVE = 5 * 1024 * 1024 * 1024  # 5GB minimum reserve
        return max(0, self.free - RESERVE)


@dataclass
class CacheSettings:
    """User cache configuration."""
    size_limit: int = CacheSizeLimit.GB_10
    retention_period: int = CacheRetention.WEEK_1
    auto_cleanup_enabled: bool = True


@dataclass
class CacheEntry:
    """Entry in the cache index."""
    file_id: str
    message_id: int
    chat_id: int
    file_path: str
    file_size: int
    last_access: float
    download_time: float


class TelegramCacheManager:
    """
    Cache manager for Telegram videos with NVR-style LRU eviction.
    
    Features:
    - SQLite index for fast lookups
    - LRU (Least Recently Used) eviction strategy
    - Configurable size and time limits
    - Disk space detection
    """
    
    def __init__(self, cache_dir: Path, settings: Optional[CacheSettings] = None):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory for cached video files
            settings: Cache configuration (defaults to 10GB, 1 week)
        """
        self.cache_dir = cache_dir
        self.settings = settings or CacheSettings()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize SQLite database for cache index."""
        db_path = self.cache_dir / "cache_index.db"
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                file_id TEXT PRIMARY KEY,
                message_id INTEGER,
                chat_id INTEGER,
                file_path TEXT,
                file_size INTEGER,
                last_access REAL,
                download_time REAL
            )
        """)
        
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_access 
            ON cache_entries(last_access)
        """)
        
        self._conn.commit()
    
    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._init_database()
        return self._conn
    
    def get_disk_info(self) -> DiskInfo:
        """Get information about disk where cache is stored."""
        usage = shutil.disk_usage(self.cache_dir)
        cache_size = self.get_current_size()
        
        return DiskInfo(
            total=usage.total,
            used=usage.used,
            free=usage.free,
            cache_used=cache_size
        )
    
    def get_available_size_limits(self) -> List[tuple]:
        """
        Get size limits that fit in available disk space.
        
        Returns:
            List of (label, value, enabled) tuples
        """
        disk_info = self.get_disk_info()
        available = disk_info.available_for_cache
        
        ALL_LIMITS = [
            ("2 GB", CacheSizeLimit.GB_2),
            ("4 GB", CacheSizeLimit.GB_4),
            ("6 GB", CacheSizeLimit.GB_6),
            ("8 GB", CacheSizeLimit.GB_8),
            ("10 GB", CacheSizeLimit.GB_10),
            ("30 GB", CacheSizeLimit.GB_30),
            ("50 GB", CacheSizeLimit.GB_50),
        ]
        
        result = []
        for label, value in ALL_LIMITS:
            enabled = value <= available
            result.append((label, value, enabled))
        
        return result
    
    def get_current_size(self) -> int:
        """Get current cache size in bytes."""
        cursor = self.conn.execute("SELECT SUM(file_size) FROM cache_entries")
        result = cursor.fetchone()[0]
        return result or 0
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics for UI display.
        
        Returns:
            Dictionary with file_count, total_size, size_limit, usage_percent
        """
        cursor = self.conn.execute("""
            SELECT COUNT(*), SUM(file_size) FROM cache_entries
        """)
        count, total_size = cursor.fetchone()
        total_size = total_size or 0
        
        return {
            'file_count': count or 0,
            'total_size': total_size,
            'size_limit': self.settings.size_limit,
            'usage_percent': (total_size / self.settings.size_limit * 100)
                if self.settings.size_limit > 0 else 0
        }
    
    def get_cached_path(self, file_id: str) -> Optional[str]:
        """
        Get path of cached file if it exists.
        
        Args:
            file_id: Telegram file ID
            
        Returns:
            File path or None if not cached
        """
        cursor = self.conn.execute(
            "SELECT file_path FROM cache_entries WHERE file_id = ?",
            (file_id,)
        )
        row = cursor.fetchone()
        
        if row:
            path = Path(row[0])
            if path.exists():
                self.update_access_time(file_id)
                return row[0]
            else:
                # File was deleted externally, remove from index
                self._remove_entry(file_id)
        
        return None
    
    def add_entry(self, entry: CacheEntry) -> None:
        """
        Add or update entry in cache index.
        
        Args:
            entry: Cache entry to add
        """
        self.conn.execute("""
            INSERT OR REPLACE INTO cache_entries 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.file_id,
            entry.message_id,
            entry.chat_id,
            entry.file_path,
            entry.file_size,
            entry.last_access,
            entry.download_time
        ))
        self.conn.commit()
        
        # Trigger cleanup if needed
        if self.settings.auto_cleanup_enabled:
            self.cleanup()
    
    def update_access_time(self, file_id: str) -> None:
        """Update last access time for LRU tracking."""
        self.conn.execute(
            "UPDATE cache_entries SET last_access = ? WHERE file_id = ?",
            (time.time(), file_id)
        )
        self.conn.commit()
    
    def cleanup(self) -> int:
        """
        Run LRU cleanup. Removes old files until within limits.
        
        Returns:
            Bytes freed
        """
        freed_bytes = 0
        current_time = time.time()
        
        # 1. Remove by age if retention limit is set
        if self.settings.retention_period > 0:
            cutoff = current_time - self.settings.retention_period
            cursor = self.conn.execute("""
                SELECT file_id, file_path, file_size 
                FROM cache_entries WHERE last_access < ?
            """, (cutoff,))
            
            for file_id, file_path, file_size in cursor.fetchall():
                freed_bytes += self._delete_cached_file(file_id, file_path, file_size)
        
        # 2. Remove by size if exceeds limit
        while self.get_current_size() > self.settings.size_limit:
            # Get oldest file (LRU)
            cursor = self.conn.execute("""
                SELECT file_id, file_path, file_size 
                FROM cache_entries ORDER BY last_access ASC LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                freed_bytes += self._delete_cached_file(*row)
            else:
                break
        
        return freed_bytes
    
    def _delete_cached_file(self, file_id: str, file_path: str, file_size: int) -> int:
        """Delete cached file and its index entry."""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
            self._remove_entry(file_id)
            return file_size
        except Exception:
            return 0
    
    def _remove_entry(self, file_id: str) -> None:
        """Remove entry from index."""
        self.conn.execute("DELETE FROM cache_entries WHERE file_id = ?", (file_id,))
        self.conn.commit()
    
    def clear_all(self) -> int:
        """
        Clear entire cache.
        
        Returns:
            Bytes freed
        """
        freed = 0
        cursor = self.conn.execute(
            "SELECT file_id, file_path, file_size FROM cache_entries"
        )
        
        for file_id, file_path, file_size in cursor.fetchall():
            freed += self._delete_cached_file(file_id, file_path, file_size)
        
        return freed
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes < 0:
        return "Unlimited"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    
    return f"{size_bytes:.1f} PB"
