from PySide6.QtCore import QObject, Signal
from domain.ports import VideoPlayerPort, PersistencePort
from domain.models import Video, PlaybackState, MediaStatus
from typing import Any

class VideoService(QObject):
    # Signals
    playback_state_changed = Signal(object) # PlaybackState
    media_status_changed = Signal(object) # MediaStatus
    position_changed = Signal(int)
    duration_changed = Signal(int)
    error_occurred = Signal(str)

    # Internal signal to bridge non-Qt threads (VLC) to Main Thread
    _internal_status_signal = Signal(object)

    def __init__(self, player: VideoPlayerPort, persistence: PersistencePort):
        super().__init__()
        self.player = player
        self.persistence = persistence
        self.current_video = None
        
        # Connect internal signal to handler on Main Thread
        self._internal_status_signal.connect(self._on_media_status_changed)
        
        self._bind_player_callbacks()

    def _bind_player_callbacks(self):
        self.player.set_on_position_changed(self.position_changed.emit)
        self.player.set_on_duration_changed(self.duration_changed.emit)
        self.player.set_on_playback_state_changed(self.playback_state_changed.emit)
        
        # Pass the SIGNAL EMITTER as the callback. 
        # Signal.emit is thread-safe and queues the slot execution to the QObject's thread (Main).
        self.player.set_on_media_status_changed(self._internal_status_signal.emit)
        
        self.player.set_on_error(self.error_occurred.emit)

    def _on_media_status_changed(self, status):
        # Forward the signal first
        self.media_status_changed.emit(status)
        
        if status == MediaStatus.LOADED:
            if hasattr(self, '_pending_initial_seek') and self._pending_initial_seek > 0:
                 from PySide6.QtCore import QTimer
                 QTimer.singleShot(250, self._execute_initial_seek)

    def _execute_initial_seek(self):
        if hasattr(self, '_pending_initial_seek') and self._pending_initial_seek > 0:
             self.player.seek(self._pending_initial_seek)
             self._pending_initial_seek = 0

    def open_video(self, path: str):
        self.current_video = Video(path)
        self.player.load(path)
        
        saved_position = self.persistence.load_progress(path)
        if saved_position > 0:
            self._pending_initial_seek = saved_position
        else:
            self._pending_initial_seek = 0
            
        self.player.play()

    def _save_current_progress(self):
        # We can use the last known position from player
        if self.current_video:
            pos = self.player.get_position()
            self.persistence.save_progress(self.current_video.path, pos)

    def play(self):
        self.player.play()

    def pause(self):
        self._save_current_progress()
        self.player.pause()

    def stop(self):
        self._save_current_progress()
        self.player.stop()

    def close_video(self, reset_progress: bool = False):
        """Stops the video, saves progress, and releases the current video context."""
        if self.current_video:
            if reset_progress:
                self.persistence.save_progress(self.current_video.path, 0)
            else:
                self._save_current_progress()
            self.player.stop()
            self.current_video = None

    def swap_player(self, new_player: VideoPlayerPort):
        """Swap the player adapter at runtime."""
        # Stop current playback if any
        if self.current_video:
            self._save_current_progress()
            self.player.stop()
            self.current_video = None
            
        # Replace player
        self.player = new_player
        
        # Re-bind callbacks
        self._bind_player_callbacks()

    def seek(self, position: int):
        self.player.seek(position)
        
    def create_video_widget(self, parent: Any = None) -> Any:
        return self.player.create_video_widget(parent)

    def set_video_output(self, widget: Any):
        self.player.set_video_output(widget)

    def get_duration(self) -> int:
        return self.player.get_duration()
        
    def get_position(self) -> int:
        return self.player.get_position()

    def get_audio_tracks(self):
        return self.player.get_audio_tracks()

    def get_subtitle_tracks(self):
        return self.player.get_subtitle_tracks()
    
    def set_audio_track(self, index: int):
        self.player.set_audio_track(index)
        
    def set_subtitle_track(self, index: int):
        self.player.set_subtitle_track(index)
