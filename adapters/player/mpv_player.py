import os
import sys
import ctypes
from domain.ports import VideoPlayerPort
from domain.models import PlaybackState, MediaStatus
from typing import List, Any

class MpvPlayer(VideoPlayerPort):
    def __init__(self, mpv_path: str = "mpv"):
        # Add mpv folder to PATH so ctypes can find the DLL
        if sys.platform == 'win32':
            full_mpv_path = os.path.abspath(mpv_path)
            dll_loaded = False
            
            if os.path.exists(full_mpv_path):
                    os.environ["PATH"] = full_mpv_path + os.pathsep + os.environ["PATH"]
                    
                    # Try to pre-load DLL with various possible names
                    dll_names = ["libmpv-2.dll", "mpv-1.dll", "mpv-2.dll", "libmpv.dll"]
                    for dll_name in dll_names:
                        dll_path = os.path.join(full_mpv_path, dll_name)
                        if os.path.exists(dll_path):
                            try:
                                ctypes.CDLL(dll_path)
                                dll_loaded = True
                                break
                            except OSError:
                                continue
            
            if not dll_loaded:
                raise OSError(f"Could not find or load libmpv DLL in {full_mpv_path}. Expected one of: libmpv-2.dll, mpv-1.dll, mpv-2.dll, libmpv.dll")
        else:
            # On Linux, python-mpv usually finds the system library (libmpv.so) 
            # as long as 'libmpv-dev' or similar is installed.
            pass
        
        import mpv
        
        try:
            # On Linux, configure MPV for X11 embedding
            if sys.platform.startswith('linux'):
                self.mpv = mpv.MPV(
                    vo='x11',           # Force X11 video output (most compatible for embedding)
                    input_default_bindings=False,
                    input_vo_keyboard=False
                )
            else:
                self.mpv = mpv.MPV()
            self.mpv['keep-open'] = 'yes'
        except Exception as e:
            print(f"MPV init error: {type(e).__name__}: {e}")
            raise
        
        # Internal state
        self._pending_seek = None
        
        # Callbacks
        self._on_position_changed = None
        self._on_duration_changed = None
        self._on_playback_state_changed = None
        self._on_media_status_changed = None
        self._on_error = None

        # setup observers
        @self.mpv.property_observer('time-pos')
        def on_time_pos(name, value):
            if self._on_position_changed and value is not None:
                self._on_position_changed(int(value * 1000))

        @self.mpv.property_observer('duration')
        def on_duration(name, value):
            if value is not None and value > 0:
                # Handle pending seek
                if self._pending_seek is not None:
                    try:
                         self.mpv.seek(self._pending_seek / 1000.0, reference="absolute")
                    except:
                        pass
                    self._pending_seek = None
                
                if self._on_media_status_changed:
                    self._on_media_status_changed(MediaStatus.LOADED)
                if self._on_duration_changed:
                    self._on_duration_changed(int(value * 1000))

        @self.mpv.property_observer('pause')
        def on_pause(name, value):
            self._update_playback_state()

        @self.mpv.property_observer('idle-active')
        def on_idle(name, value):
            self._update_playback_state()
            if value and self._on_media_status_changed:
                self._on_media_status_changed(MediaStatus.NO_MEDIA)

        @self.mpv.property_observer('paused-for-cache')
        def on_buffering(name, value):
            if self._on_media_status_changed:
                if value:
                    self._on_media_status_changed(MediaStatus.BUFFERING)
                else:
                    # Assume loaded if not buffering, though strictly might be checking idle
                    if not self.mpv.idle_active:
                         self._on_media_status_changed(MediaStatus.LOADED)

        @self.mpv.property_observer('eof-reached')
        def on_eof(name, value):
            if value and self._on_media_status_changed:
                self._on_media_status_changed(MediaStatus.End)
                
    def _update_playback_state(self):
        if self._on_playback_state_changed:
            if self.mpv.idle_active:
                self._on_playback_state_changed(PlaybackState.STOPPED)
            elif self.mpv.pause:
                self._on_playback_state_changed(PlaybackState.PAUSED)
            else:
                self._on_playback_state_changed(PlaybackState.PLAYING)

    def load(self, path: str):
        # Notify loading
        if self._on_media_status_changed:
            self._on_media_status_changed(MediaStatus.LOADING)
        
        self.mpv.play(path)
        self.mpv.pause = True

    def play(self):
        self.mpv.pause = False

    def pause(self):
        self.mpv.pause = True

    def stop(self):
        try:
            self.mpv.stop()
        except:
            pass

    def seek(self, position: int):
        try:
            self.mpv.seek(position / 1000.0, reference="absolute")
        except Exception:
            self._pending_seek = position

    def get_duration(self) -> int:
        try:
            d = self.mpv.duration
            return int(d * 1000) if d else 0
        except:
            return 0

    def get_position(self) -> int:
        try:
            p = self.mpv.time_pos
            return int(p * 1000) if p else 0
        except:
            return 0

    def set_subtitle_track(self, index: int):
        if index == 0:
            self.mpv.sid = 'auto'
        elif index == 1:
            self.mpv.sid = 'no'
        else:
            try:
                subs = [t for t in self.mpv.track_list if t['type'] == 'sub']
                track_index = index - 2
                if 0 <= track_index < len(subs):
                    self.mpv.sid = subs[track_index]['id']
            except:
                pass

    def set_audio_track(self, index: int):
        if index == 0:
            self.mpv.aid = 'auto'
        else:
            try:
                audios = [t for t in self.mpv.track_list if t['type'] == 'audio']
                track_index = index - 1
                if 0 <= track_index < len(audios):
                    self.mpv.aid = audios[track_index]['id']
            except:
                pass
        
    def get_subtitle_tracks(self) -> List[str]:
        tracks = ["Auto", "Off"]
        try:
            for t in self.mpv.track_list:
                if t['type'] == 'sub':
                    title = t.get('title') or 'Track'
                    lang = t.get('lang') or 'unk'
                    tracks.append(f"{title} ({lang})")
        except:
            pass
        return tracks

    def set_volume(self, volume: int):
        try:
            self.mpv.volume = volume
        except:
            pass

    def set_muted(self, muted: bool):
        try:
            self.mpv.mute = muted
        except:
            pass

    def get_audio_tracks(self) -> List[str]:
        tracks = ["Auto"]
        try:
            for t in self.mpv.track_list:
                if t['type'] == 'audio':
                    title = t.get('title') or 'Track'
                    lang = t.get('lang') or 'unk'
                    tracks.append(f"{title} ({lang})")
        except:
            pass
        return tracks
        
    def create_video_widget(self, parent: Any = None) -> Any:
        from PySide6.QtWidgets import QWidget
        widget = QWidget(parent)
        widget.setStyleSheet("background-color: black;")
        widget.setObjectName("MpvVideoWidget")
        return widget

    def set_video_output(self, widget: Any):
        wid = int(widget.winId())
        print(f"DEBUG MPV: Setting wid to {wid}")
        self.mpv.wid = wid

    # Implement setters
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
