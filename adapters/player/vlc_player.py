import os
import sys
import ctypes
from domain.ports import VideoPlayerPort
from domain.models import PlaybackState, MediaStatus
from typing import List, Any, Optional

class VlcPlayer(VideoPlayerPort):
    def __init__(self, vlc_path: str = "vlc"):
        # Add vlc folder to PATH and Environment so python-vlc finds it
        full_vlc_path = os.path.abspath(vlc_path)
        
        if os.path.exists(full_vlc_path):
             os.environ["PATH"] = full_vlc_path + os.pathsep + os.environ["PATH"]
             # Important for python-vlc to find libvlc.dll
             os.environ["PYTHON_VLC_MODULE_PATH"] = full_vlc_path 
             
             # For Python 3.8+ on Windows, standard PATH is ignored for DLL loading
             if hasattr(os, 'add_dll_directory'):
                 try:
                     os.add_dll_directory(full_vlc_path)
                 except OSError:
                     pass
             
             # Also try to proactively load the DLL to ensure it works
             try:
                 # Load libvlccore first (dependency)
                 core_path = os.path.join(full_vlc_path, "libvlccore.dll")
                 if os.path.exists(core_path):
                     ctypes.CDLL(core_path)
                 
                 # Then libvlc
                 dll_path = os.path.join(full_vlc_path, "libvlc.dll")
                 if os.path.exists(dll_path):
                     ctypes.CDLL(dll_path)
             except OSError:
                 pass
        
        try:
            import vlc
            self.vlc = vlc
        except ImportError:
            raise ImportError("python-vlc is not installed. Please run 'pip install python-vlc'")
        except OSError:
             raise OSError(f"Could not find or load libvlc.dll in {full_vlc_path} or system path.")

        # Initialize VLC Instance with some default options
        # --no-video-title-show: Don't show filename on video start
        # --quiet: Less log clutter
        # --video-on-top: Keep video on top
        # --drawable-hwnd: For Windows native rendering
        # Background color in VLC is set by setting the video's background
        self.instance = self.vlc.Instance(
            "--no-video-title-show", 
            "--quiet",
            "--no-video-deco"
        )
        self.player = self.instance.media_player_new()
        self.event_manager = self.player.event_manager()
        
        # Internal state
        self._current_media = None
        self._last_position = 0
        self._pending_seek = None
        
        # Callbacks
        print(f"DEBUG: VlcPlayer initialized with path: {full_vlc_path}")
        self._bind_events()

    # ...

    def _handle_playing(self, event):
        if self._on_playback_state_changed:
            self._on_playback_state_changed(PlaybackState.PLAYING)
        # Also implies loaded
        if self._on_media_status_changed:
            self._on_media_status_changed(MediaStatus.LOADED)
        
        # Handle pending seek
        if self._pending_seek is not None:
             # Use seek method logic to reuse set_position
             self.seek(self._pending_seek)
             self._pending_seek = None

    # ...

    def load(self, path: str):
        # Create new media
        abs_path = os.path.abspath(path)
        
        if self._current_media:
            self._current_media.release()
            
        self._current_media = self.instance.media_new(abs_path)
        self.player.set_media(self._current_media)
        self._pending_seek = None # Reset pending seek
        self._last_position = 0

    # ...

    def seek(self, position: int):
        # VLC requires playing state for set_time to work reliable
        # If we are not playing, we schedule it
        state = self.player.get_state()
        # State 3 is Playing, 4 is Paused. 
        # But easier to just store it if we just loaded?
        # If the user drags slider while playing, we want immediate seek.
        # If we are in "Opening" or "Stopped", wait.
        
        # We can try setting it. If it works, good.
        # But robust way for initial load:
        if state in (self.vlc.State.Playing, self.vlc.State.Paused):
             self.player.set_time(position)
        else:
             self._pending_seek = position

        


    def _bind_events(self):
        EventType = self.vlc.EventType
        self.event_manager.event_attach(EventType.MediaPlayerTimeChanged, self._handle_time_changed)
        self.event_manager.event_attach(EventType.MediaPlayerLengthChanged, self._handle_length_changed)
        self.event_manager.event_attach(EventType.MediaPlayerPlaying, self._handle_playing)
        self.event_manager.event_attach(EventType.MediaPlayerPaused, self._handle_paused)
        self.event_manager.event_attach(EventType.MediaPlayerStopped, self._handle_stopped)
        self.event_manager.event_attach(EventType.MediaPlayerEndReached, self._handle_end_reached)
        self.event_manager.event_attach(EventType.MediaPlayerEncounteredError, self._handle_error_event)
        self.event_manager.event_attach(EventType.MediaPlayerOpening, self._handle_opening)
        
        # Buffer events are limited in VLC event system, but we can try MediaPlayerBuffering
        self.event_manager.event_attach(EventType.MediaPlayerBuffering, self._handle_buffering)

    # --- Event Handlers ---

    def _handle_time_changed(self, event):
        # Event provides time in MS
        time = event.u.new_time
        self._last_position = time
        if self._on_position_changed:
            self._on_position_changed(time)

    def _handle_length_changed(self, event):
        duration = event.u.new_length
        if self._on_duration_changed:
            self._on_duration_changed(duration)
        
        # If we were waiting for metadata to handle pending seek or load status
        self._check_metadata_ready()

    def _handle_playing(self, event):
        if self._on_playback_state_changed:
            self._on_playback_state_changed(PlaybackState.PLAYING)
        
        self._check_metadata_ready()

    def _check_metadata_ready(self):
        # Allow loading if we are playing or if we have length
        # This fixes "Missing Data" if length is 0 initially.
        length = self.player.get_length()
        
        # Emit Loaded if not done yet. We assume if we are checking this, we are at least Playing or Length changed.
        if self._on_media_status_changed:
             self._on_media_status_changed(MediaStatus.LOADED)
             
        # Handle pending seek
        if self._pending_seek is not None:
             if length > 0:
                 self.seek(self._pending_seek)
                 self._pending_seek = None
             else:
                 # If length is 0 but we are playing, try set_time directly
                 self.player.set_time(self._pending_seek)
                 self._pending_seek = None

    def _handle_paused(self, event):
        if self._on_playback_state_changed:
            self._on_playback_state_changed(PlaybackState.PAUSED)

    def _handle_stopped(self, event):
        if self._on_playback_state_changed:
            self._on_playback_state_changed(PlaybackState.STOPPED)
    
    def _handle_end_reached(self, event):
        if self._on_media_status_changed:
            self._on_media_status_changed(MediaStatus.End)

    def _handle_error_event(self, event):
        if self._on_media_status_changed:
            self._on_media_status_changed(MediaStatus.ERROR)
        if self._on_error:
            self._on_error("VLC encountered an error.")

    def _handle_opening(self, event):
        if self._on_media_status_changed:
            self._on_media_status_changed(MediaStatus.LOADING)

    def _handle_buffering(self, event):
        percent = event.u.new_cache
        if percent < 100:
             if self._on_media_status_changed:
                 self._on_media_status_changed(MediaStatus.BUFFERING)
        else:
             if self._on_media_status_changed:
                 self._on_media_status_changed(MediaStatus.LOADED)

    # --- VideoPlayerPort Implementation ---

    def load(self, path: str):
        # Create new media
        abs_path = os.path.abspath(path)
        
        if self._current_media:
            self._current_media.release()
            
        self._current_media = self.instance.media_new(abs_path)
        self.player.set_media(self._current_media)
        pass

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def seek(self, position: int):
        pos = int(position)
        state = self.player.get_state()
        
        # Robust seeking strategy
        # 1. If we are playing/paused/buffering, we can try to seek.
        # 2. Prefer set_position (percentage) if duration is known.
        # 3. Fallback to set_time if duration is unknown.
        # 4. If not ready, defer (pending_seek).
        
        if state in (self.vlc.State.Playing, self.vlc.State.Paused, self.vlc.State.Buffering):
             length = self.player.get_length()
             if length > 0:
                 ratio = pos / length
                 ratio = max(0.0, min(1.0, ratio))
                 self.player.set_position(ratio)
             else:
                 # Fallback for streams or unknown duration
                 self.player.set_time(pos)
             
             # Speculative update of last position to ensure immediate get_position accuracy
             # This helps persistence if we close immediately after seeking
             self._last_position = pos
        else:
             # Defer until playback starts
             self._pending_seek = pos

    def get_duration(self) -> int:
        return max(0, int(self.player.get_length()))

    def get_position(self) -> int:
        t = self.player.get_time()
        # If t is -1, it means no media or error.
        if t == -1 and self._last_position > 0:
            return int(self._last_position)
        return max(0, int(t))

    def set_subtitle_track(self, index: int):
        spus = self.player.video_get_spu_description() 
        if not spus: return

        if index == 0:
             pass 
        elif index == 1:
             self.player.video_set_spu(-1)
        else:
             target_idx = index - 2
             real_spus = [t for t in spus if t[0] != -1]
             if 0 <= target_idx < len(real_spus):
                 self.player.video_set_spu(real_spus[target_idx][0])

    def set_audio_track(self, index: int):
        tracks = self.player.audio_get_track_description()
        if not tracks: return
            
        if index == 0:
            pass
        else:
             real_tracks = [t for t in tracks if t[0] != -1]
             target_idx = index - 1
             if 0 <= target_idx < len(real_tracks):
                 self.player.audio_set_track(real_tracks[target_idx][0])

    def get_subtitle_tracks(self) -> List[str]:
        res = ["Auto", "Off"]
        spus = self.player.video_get_spu_description()
        if spus:
            for spu_id, spu_name in spus:
                if spu_id != -1:
                    if isinstance(spu_name, bytes):
                        name = spu_name.decode('utf-8', 'ignore')
                    else:
                        name = spu_name
                    res.append(name)
        return res

    def get_audio_tracks(self) -> List[str]:
        res = ["Auto"]
        tracks = self.player.audio_get_track_description()
        if tracks:
            for track_id, track_name in tracks:
                if track_id != -1:
                     if isinstance(track_name, bytes):
                        name = track_name.decode('utf-8', 'ignore')
                     else:
                        name = track_name
                     res.append(name)
        return res

    def set_video_output(self, widget: Any):
        win_id = int(widget.winId())
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(win_id)
        elif sys.platform.startswith('win'):
            self.player.set_hwnd(win_id)
            # Set the window background to black using Win32 API
            try:
                import ctypes
                from ctypes import wintypes
                
                # Get the GDI32 and User32 DLLs
                gdi32 = ctypes.windll.gdi32
                user32 = ctypes.windll.user32
                
                # Create a black brush
                BLACK_BRUSH = 4  # GetStockObject constant for black brush
                black_brush = gdi32.GetStockObject(BLACK_BRUSH)
                
                # Set the window background brush using SetClassLongPtr
                GCL_HBRBACKGROUND = -10
                user32.SetClassLongPtrW(win_id, GCL_HBRBACKGROUND, black_brush)
                
                # Force repaint
                user32.InvalidateRect(win_id, None, True)
            except Exception as e:
                print(f"DEBUG: Failed to set Win32 background: {e}")
        elif sys.platform.startswith('darwin'):
            self.player.set_nsobject(win_id)
            
        # PRO TIP: Disable VLC mouse input handling so that Qt receives the events (clicks, double clicks).
        # This allows the PlayerScreen event filter to capture DoubleClick for fullscreen toggle.
        self.player.video_set_mouse_input(False)

    def create_video_widget(self, parent: Any = None) -> Any:
        from PySide6.QtWidgets import QFrame
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtCore import Qt
        
        frame = QFrame(parent)
        # Disable transparency attributes - critical for VLC with FramelessWindow
        frame.setAttribute(Qt.WA_TranslucentBackground, False)
        frame.setAttribute(Qt.WA_NoSystemBackground, False)
        frame.setAutoFillBackground(True)
        
        # Set black background using palette (more reliable for native rendering)
        palette = frame.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        palette.setColor(QPalette.Base, QColor(0, 0, 0))
        frame.setPalette(palette)
        frame.setStyleSheet("background-color: black; border: none;")
        return frame

    # --- Callbacks Setters ---

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
