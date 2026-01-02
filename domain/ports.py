from abc import ABC, abstractmethod
from typing import List, Any
from domain.models import PlaybackState, MediaStatus

class VideoPlayerPort(ABC):
    @abstractmethod
    def load(self, path: str):
        pass

    @abstractmethod
    def play(self):
        pass

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def seek(self, position: int):
        pass

    @abstractmethod
    def get_duration(self) -> int:
        pass

    @abstractmethod
    def get_position(self) -> int:
        pass

    @abstractmethod
    def set_subtitle_track(self, index: int):
        pass

    @abstractmethod
    def set_audio_track(self, index: int):
        pass
        
    @abstractmethod
    def get_subtitle_tracks(self) -> List[str]:
        pass

    @abstractmethod
    def get_audio_tracks(self) -> List[str]:
        pass
        
    @abstractmethod
    def create_video_widget(self, parent: Any = None) -> Any:
        """Create the appropriate UI widget for this player."""
        pass

    @abstractmethod
    def set_video_output(self, widget: Any):
        pass
        
    # Observability
    @abstractmethod
    def set_on_position_changed(self, callback):
        """Callback(position_ms: int)"""
        pass
        
    @abstractmethod
    def set_on_duration_changed(self, callback):
        """Callback(duration_ms: int)"""
        pass
        
    @abstractmethod
    def set_on_playback_state_changed(self, callback):
        """Callback(state: PlaybackState)"""
        pass
        
    @abstractmethod
    def set_on_media_status_changed(self, callback):
        """Callback(status: MediaStatus)"""
        pass
        
    @abstractmethod
    def set_on_error(self, callback):
        """Callback(error_msg: str)"""
        pass

class PersistencePort(ABC):
    @abstractmethod
    def save_progress(self, path: str, position: int):
        pass

    @abstractmethod
    def load_progress(self, path: str) -> int:
        pass

    @abstractmethod
    def save_setting(self, key: str, value: Any):
        pass

    @abstractmethod
    def load_setting(self, key: str, default: Any = None) -> Any:
        pass
