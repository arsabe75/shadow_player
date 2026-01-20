from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl, QObject, Slot
from domain.ports import VideoPlayerPort
from domain.models import PlaybackState, MediaStatus
from typing import List, Any

class QtPlayerMeta(type(QObject), type(VideoPlayerPort)):
    pass

class QtPlayer(QObject, VideoPlayerPort, metaclass=QtPlayerMeta):
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        
        # Internal state
        self.pending_position = None
        
        # Callbacks
        self._on_position_changed = None
        self._on_duration_changed = None
        self._on_playback_state_changed = None
        self._on_media_status_changed = None
        self._on_error = None
        
        # Connect Signals
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.playbackStateChanged.connect(self._handle_playback_state_changed)
        self.player.positionChanged.connect(self._handle_position_changed)
        self.player.durationChanged.connect(self._handle_duration_changed)
        self.player.errorOccurred.connect(self._handle_error)

    def _handle_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        # Handle pending seek logic
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if self.pending_position is not None:
                self.player.setPosition(self.pending_position)
                self.pending_position = None
        
        # Emit callback
        if self._on_media_status_changed:
            domain_status = self._map_media_status(status)
            self._on_media_status_changed(domain_status)

    def _handle_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        if self._on_playback_state_changed:
            domain_state = self._map_playback_state(state)
            self._on_playback_state_changed(domain_state)

    def _handle_position_changed(self, position: int):
        if self._on_position_changed:
            self._on_position_changed(position)

    def _handle_duration_changed(self, duration: int):
        if self._on_duration_changed:
            self._on_duration_changed(duration)

    def _handle_error(self):
        if self._on_error:
            self._on_error(self.player.errorString())

    def _map_media_status(self, status: QMediaPlayer.MediaStatus) -> MediaStatus:
        if status == QMediaPlayer.MediaStatus.NoMedia:
            return MediaStatus.NO_MEDIA
        elif status == QMediaPlayer.MediaStatus.LoadingMedia:
            return MediaStatus.LOADING
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            return MediaStatus.LOADED
        elif status in (QMediaPlayer.MediaStatus.StalledMedia, QMediaPlayer.MediaStatus.BufferingMedia):
            return MediaStatus.BUFFERING
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            return MediaStatus.End
        return MediaStatus.ERROR

    def _map_playback_state(self, state: QMediaPlayer.PlaybackState) -> PlaybackState:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            return PlaybackState.PLAYING
        elif state == QMediaPlayer.PlaybackState.PausedState:
            return PlaybackState.PAUSED
        return PlaybackState.STOPPED

    # Implementation of VideoPlayerPort
    
    def set_on_position_changed(self, callback):
        self._on_position_changed = callback
        
    def set_on_duration_changed(self, callback):
        self._on_duration_changed = callback
        
    def set_on_playback_state_changed(self, callback):
        self._on_playback_state_changed = callback
        
    def set_on_media_status_changed(self, callback):
        self._on_media_status_changed = callback
        
    def set_on_error(self, callback):
        self._on_error = callback

    def load(self, path: str):
        self.pending_position = None # Clear previous pending
        # Support HTTP URLs for streaming (Telegram) and local files
        if path.startswith('http://') or path.startswith('https://'):
            self.player.setSource(QUrl(path))
        else:
            self.player.setSource(QUrl.fromLocalFile(path))

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def seek(self, position: int):
        if self.player.mediaStatus() in (QMediaPlayer.MediaStatus.NoMedia, QMediaPlayer.MediaStatus.LoadingMedia):
             self.pending_position = position
        else:
             self.player.setPosition(position)

    def get_duration(self) -> int:
        return self.player.duration()

    def get_position(self) -> int:
        return self.player.position()

    def set_subtitle_track(self, index: int):
        # Index 0 = Off, Index 1+ = actual tracks
        if index == 0:
            self.player.setActiveSubtitleTrack(-1)  # -1 disables subtitles
        else:
            self.player.setActiveSubtitleTrack(index - 1)

    def set_audio_track(self, index: int):
        # Index 0 = Auto/default, Index 1+ = actual tracks  
        if index > 0:
            self.player.setActiveAudioTrack(index - 1)
        
    def get_subtitle_tracks(self) -> List[str]:
        tracks = ["Off"]
        for i, track in enumerate(self.player.subtitleTracks()):
            lang = track.value(track.Key.Language)
            title = track.value(track.Key.Title)
            label = title if title else f"Track {i+1}"
            if lang:
                label = f"{label} ({lang})"
            tracks.append(label)
        return tracks

    def set_volume(self, volume: int):
        # QAudioOutput volume is 0.0 to 1.0
        self.audio.setVolume(volume / 100.0)

    def set_muted(self, muted: bool):
        self.audio.setMuted(muted)

    def get_audio_tracks(self) -> List[str]:
        tracks = ["Auto"]
        for i, track in enumerate(self.player.audioTracks()):
            lang = track.value(track.Key.Language)
            title = track.value(track.Key.Title)
            label = title if title else f"Track {i+1}"
            if lang:
                label = f"{label} ({lang})"
            tracks.append(label)
        return tracks
        
    def create_video_widget(self, parent: Any = None) -> Any:
        from PySide6.QtMultimediaWidgets import QVideoWidget
        return QVideoWidget(parent)

    def set_video_output(self, widget: Any):
        self.player.setVideoOutput(widget)
