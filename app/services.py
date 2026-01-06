from PySide6.QtCore import QObject, Signal
from domain.ports import VideoPlayerPort, PersistencePort
from domain.models import Video, PlaybackState, MediaStatus
from typing import Any
import random
from domain.models import Video, PlaybackState, MediaStatus, LoopMode

class VideoService(QObject):
    # Signals
    playback_state_changed = Signal(object) # PlaybackState
    media_status_changed = Signal(object) # MediaStatus
    position_changed = Signal(int)
    duration_changed = Signal(int)
    error_occurred = Signal(str)
    playlist_updated = Signal() # Emitted when playlist content or order changes
    loop_mode_changed = Signal(object) # LoopMode
    shuffle_mode_changed = Signal(bool)
    playback_finished = Signal() # Emitted when the entire playlist/session ends
    
    # Audio Signals
    volume_changed = Signal(int)
    muted_changed = Signal(bool)

    # Internal signal to bridge non-Qt threads (VLC) to Main Thread

    # Internal signal to bridge non-Qt threads (VLC) to Main Thread
    _internal_status_signal = Signal(object)

    def __init__(self, player: VideoPlayerPort, persistence: PersistencePort):
        super().__init__()
        self.player = player
        self.persistence = persistence
        self.current_video = None
        
        # Playlist State
        self.playlist: list[Video] = []
        self.original_playlist: list[Video] = [] # For shuffle
        self.current_index = -1
        self.loop_mode = LoopMode.NO_LOOP
        # Playlist State
        self.playlist: list[Video] = []
        self.original_playlist: list[Video] = [] # For shuffle
        self.current_index = -1
        self.loop_mode = LoopMode.NO_LOOP
        self.is_shuffled = False
        
        # Audio State
        self.volume = 100
        self.is_muted = False
        
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
        
        if status == MediaStatus.End:
             self._on_video_ended()
        elif status == MediaStatus.LOADED:
            if hasattr(self, '_pending_initial_seek') and self._pending_initial_seek > 0:
                 from PySide6.QtCore import QTimer
                 QTimer.singleShot(250, self._execute_initial_seek)

    def _execute_initial_seek(self):
        if hasattr(self, '_pending_initial_seek') and self._pending_initial_seek > 0:
             self.player.seek(self._pending_initial_seek)
             self._pending_initial_seek = 0

    def open_video(self, path: str):
        # Legacy support or single file open
        self.play_files([path])

    def play_files(self, paths: list[str], start_from_beginning: bool = False):
        """Replaces current playlist with new files and plays the first one."""
        self.start_from_beginning = start_from_beginning
        self.cleanup_playlist()
        self.add_files(paths)
        if self.playlist:
            self.play_at_index(0)

    def add_files(self, paths: list[str]):
        """Appends files to the playlist."""
        new_videos = [Video(path) for path in paths]
        self.playlist.extend(new_videos)
        
        if self.is_shuffled:
            # If shuffled, also add to original in correct place? 
            # Or just append to original and shuffle newly added? Only full reshuffle for now.
            self.original_playlist.extend(new_videos)
            # We don't auto-reshuffle here to avoid disturbing current order too much, 
            # just append to end of current shuffle view.
        else:
            self.original_playlist.extend(new_videos)
            
        self.playlist_updated.emit()

    def play_at_index(self, index: int):
        if 0 <= index < len(self.playlist):
            # Save progress of current video before switching to new one
            if self.current_video:
                self._save_current_progress()
            
            self.current_index = index
            video = self.playlist[index]
            self._load_and_play(video)
            self.playlist_updated.emit() # update UI for active item

    def _load_and_play(self, video: Video):
        self.current_video = video
        self.player.load(video.path)
        
        # If "Start from Beginning" is checked, start from 0
        if getattr(self, 'start_from_beginning', False):
            self._pending_initial_seek = 0
        else:
            # Normal behavior: resume from saved progress if any
            saved_position = self.persistence.load_progress(video.path)
            if saved_position > 0:
                self._pending_initial_seek = saved_position
            else:
                self._pending_initial_seek = 0
            
        self.player.play()

    def _on_video_ended(self):
        # Handle Loop One
        if self.loop_mode == LoopMode.LOOP_ONE:
            self.player.seek(0)
            self.player.play()
            return

        # Auto-advance
        if self.cur_has_next():
            self.play_next()
        elif self.loop_mode == LoopMode.LOOP_ALL:
            self.play_at_index(0)
        else:
            # Playlist finished
            self.close_video(reset_progress=True)
            self.playback_finished.emit()

    def cur_has_next(self):
        return self.current_index + 1 < len(self.playlist)

    def play_next(self):
        if self.cur_has_next():
            self.play_at_index(self.current_index + 1)
        elif self.loop_mode == LoopMode.LOOP_ALL and self.playlist:
            self.play_at_index(0)

    def play_previous(self):
        if self.current_index > 0:
            self.play_at_index(self.current_index - 1)
        elif self.loop_mode == LoopMode.LOOP_ALL and self.playlist:
             self.play_at_index(len(self.playlist) - 1)

    def cleanup_playlist(self):
        self.playlist.clear()
        self.original_playlist.clear()
        self.current_index = -1
        self.playlist_updated.emit()

    def set_loop_mode(self, mode: LoopMode):
        self.loop_mode = mode
        self.loop_mode_changed.emit(mode)

    def toggle_shuffle(self):
        self.is_shuffled = not self.is_shuffled
        
        if self.is_shuffled:
            # Save current playing video to keep it playing
            current_video = self.playlist[self.current_index] if 0 <= self.current_index < len(self.playlist) else None
            
            # Shuffle
            # self.original_playlist is already up to date if we maintained it
            # But wait, self.playlist is currently authoritative. 
            # Ensure original is synced if we modified playlist (reorder)
            if not self.original_playlist:
                 self.original_playlist = list(self.playlist)

            random.shuffle(self.playlist)
            
            # If playing, move current video to top or find its new index
            if current_video:
                new_index = self.playlist.index(current_video)
                self.current_index = new_index
        else:
            # Restore order
            # We need to find where the current video is in the original list
            current_video = self.playlist[self.current_index] if 0 <= self.current_index < len(self.playlist) else None
            
            if self.original_playlist:
                self.playlist = list(self.original_playlist)
            
            if current_video and current_video in self.playlist:
                self.current_index = self.playlist.index(current_video)
            else:
                self.current_index = 0 # Fallback
                
        self.shuffle_mode_changed.emit(self.is_shuffled)
        self.playlist_updated.emit()

    def update_playlist(self, new_playlist: list[Video]):
        self.playlist = new_playlist
        if not self.is_shuffled:
            self.original_playlist = list(self.playlist)
        
        if self.current_video and self.current_video in self.playlist:
             self.current_index = self.playlist.index(self.current_video)
        else:
             self.current_index = -1
             
        self.playlist_updated.emit()

    def reorder_playlist(self, from_index: int, to_index: int):
        if 0 <= from_index < len(self.playlist) and 0 <= to_index < len(self.playlist):
            item = self.playlist.pop(from_index)
            self.playlist.insert(to_index, item)
            
            # If we moved the playing video, update current_index
            if self.current_index == from_index:
                self.current_index = to_index
            elif from_index < self.current_index <= to_index:
                self.current_index -= 1
            elif to_index <= self.current_index < from_index:
                self.current_index += 1
            
            # If not shuffled, update original too
            if not self.is_shuffled:
                 item_orig = self.original_playlist.pop(from_index)
                 self.original_playlist.insert(to_index, item_orig)

            self.playlist_updated.emit()

    def remove_from_playlist(self, index: int):
         if 0 <= index < len(self.playlist):
             # removing currently playing?
             was_playing = (index == self.current_index)
             
             removed = self.playlist.pop(index)
             if not self.is_shuffled:
                 self.original_playlist.remove(removed)
                 
             if index < self.current_index:
                 self.current_index -= 1
             elif index == self.current_index:
                 # If we removed the playing one, play next?
                 if self.cur_has_next():
                     self.play_at_index(self.current_index) # Index is now next item
                 elif self.playlist:
                      self.play_at_index(len(self.playlist)-1)
                 else:
                      self.stop()
             
             self.playlist_updated.emit()

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
        
        # Apply current state
        self.player.set_volume(self.volume)
        self.player.set_muted(self.is_muted)

    def seek(self, position: int):
        self.player.seek(position)
        
    def seek_relative(self, offset_ms: int):
        current = self.get_position()
        duration = self.get_duration()
        if duration == 0: return
        new_pos = max(0, min(duration, current + offset_ms))
        self.seek(new_pos)

    def seek_to_percentage(self, percent: int):
        duration = self.get_duration()
        if duration == 0: return
        # Clamp percent 0-100
        safe_percent = max(0, min(100, percent))
        target_pos = int((safe_percent / 100.0) * duration)
        self.seek(target_pos)

    def set_volume(self, volume: int):
        self.volume = max(0, min(100, volume))
        self.player.set_volume(self.volume)
        self.volume_changed.emit(self.volume)
        
        # If we change volume, we probably want to unmute if muted (optional, but common UX)
        if self.is_muted and self.volume > 0:
             self.is_muted = False
             self.player.set_muted(False)
             self.muted_changed.emit(False)

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.player.set_muted(self.is_muted)
        self.muted_changed.emit(self.is_muted)
        
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

    def save_playlist_to_file(self, path: str):
        """Saves the current playlist to an M3U file."""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for video in self.playlist:
                    # Write metadata if available (duration not strictly tracked in model yet, but title is)
                    f.write(f"#EXTINF:-1,{video.title}\n")
                    f.write(f"{video.path}\n")
        except Exception as e:
            self.error_occurred.emit(f"Failed to save playlist: {e}")

    def load_playlist_from_file(self, path: str) -> list[Video]:
        """Parses an M3U file and returns a list of Video objects."""
        new_videos = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            current_title = ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("#EXTINF:"):
                    # #EXTINF:duration,title
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        current_title = parts[1]
                elif line.startswith("#"):
                    continue
                else:
                    # Is a file path
                    video = Video(line, title=current_title if current_title else "")
                    new_videos.append(video)
                    current_title = "" # Reset for next entry
            
            return new_videos

        except Exception as e:
            self.error_occurred.emit(f"Failed to load playlist: {e}")
            return []
