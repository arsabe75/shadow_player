import ctypes
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel, QComboBox, QApplication, QStackedLayout
from PySide6.QtCore import Qt, QTimer, Signal, QEvent
from app.services import VideoService
from domain.models import PlaybackState, MediaStatus

# Constants for Win32 API
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
LWA_COLORKEY = 0x1
LWA_ALPHA = 0x2

class PlayerScreen(QWidget):
    # ... (signals)
    back_clicked = Signal()
    toggle_fullscreen = Signal()

    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        self.updating_slider = False
        
        # State tracking
        self.fullscreen_mode = False
        self.controls_hidden = False
        self.current_playback_state = PlaybackState.STOPPED
        self.current_duration = 0
        
        self.setup_ui()
        self.setup_connections()
        
        # Timer for hiding controls (keep this, it's UI behavior not polling)
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000) # 3 seconds
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_controls)
        
        # Connect Service Signals
        self.service.position_changed.connect(self._on_position_changed)
        self.service.duration_changed.connect(self._on_duration_changed)
        self.service.playback_state_changed.connect(self._on_playback_state_changed)
        self.service.media_status_changed.connect(self._on_media_status_changed)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top Controls Container
        self.top_controls_widget = QWidget()
        top_layout = QHBoxLayout(self.top_controls_widget)
        self.back_button = QPushButton("Back")
        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        
        layout.addWidget(self.top_controls_widget)

        # Video Stack Container
        self.video_container = QWidget()
        self.video_stack = QStackedLayout(self.video_container)
        self.video_stack.setStackingMode(QStackedLayout.StackAll)

        # 1. Video Backend Widget (Bottom Layer)
        self.video_widget = self.service.create_video_widget(self.video_container)
        self.service.set_video_output(self.video_widget)
        self.video_stack.addWidget(self.video_widget)

        # 2. Input Overlay (Top Layer)
        self.input_overlay = QWidget()
        
        # Win32 Transparency Trick Part 2: "Alpha 1"
        # We don't set a color key. We just set a background (black) and then make it 99% transparent via Alpha.
        self.input_overlay.setStyleSheet("background-color: black;")
        
        # Force Native Window
        self.input_overlay.setAttribute(Qt.WA_NativeWindow, True) 
        # Important: Do NOT use WA_TranslucentBackground with this trick, it conflicts.
        
        self.input_overlay.installEventFilter(self)
        self.video_stack.addWidget(self.input_overlay)
        self.video_stack.setCurrentWidget(self.input_overlay)
        self.input_overlay.raise_()
        
        layout.addWidget(self.video_container, stretch=1)
        
        # Apply the Win32 attributes immediately after creation (requires HWND)
        self.input_overlay.winId() # Force creation
        self._apply_win32_transparency(self.input_overlay)

        # Bottom Controls Container
        self.bottom_controls_widget = QWidget()
        bottom_layout = QVBoxLayout(self.bottom_controls_widget)
        
        # Slider
        self.slider = QSlider(Qt.Horizontal)
        bottom_layout.addWidget(self.slider)

        # Controls (Play/Stop/Time)
        controls_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setMaximumWidth(80)
        controls_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setMaximumWidth(80)
        controls_layout.addWidget(self.stop_button)
        
        self.time_label = QLabel("00:00 / 00:00")
        controls_layout.addWidget(self.time_label)

        bottom_layout.addLayout(controls_layout)
        
        # Tracks
        tracks_layout = QHBoxLayout()
        tracks_layout.addWidget(QLabel("Audio:"))
        self.audio_combo = QComboBox()
        self.audio_combo.setMinimumWidth(200)
        tracks_layout.addWidget(self.audio_combo)
        
        self.audio_combo.blockSignals(True)
        
        tracks_layout.addWidget(QLabel("Subtitles:"))
        self.subtitle_combo = QComboBox()
        self.subtitle_combo.setMinimumWidth(200)
        tracks_layout.addWidget(self.subtitle_combo)
        tracks_layout.addStretch()
        
        bottom_layout.addLayout(tracks_layout)

        layout.addWidget(self.bottom_controls_widget)

    def _apply_win32_transparency(self, widget):
        hwnd = int(widget.winId())
        if hasattr(ctypes, 'windll'):
            try:
                # Add WS_EX_LAYERED to extended style
                user32 = ctypes.windll.user32
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
                
                # Set Layered Attributes: ALPHA = 1 (Almost transparent but clickable)
                # LWA_ALPHA = 0x2
                # Alpha value: 1 (0 is invisible/hollow, 255 is opaque)
                user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
            except Exception as e:
                print(f"DEBUG: Failed to apply transparency: {e}")

    def setup_connections(self):
        self.back_button.clicked.connect(self._on_back_clicked)
        
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop_video)
        
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.valueChanged.connect(self.on_slider_moved)

        # Connect combo boxes
        self.audio_combo.currentIndexChanged.connect(self.on_audio_track_changed)
        self.subtitle_combo.currentIndexChanged.connect(self.on_subtitle_track_changed)

    def _on_back_clicked(self):
        self.service.close_video()
        self.back_clicked.emit()

    # --- Signal Handlers ---

    def _on_position_changed(self, position):
        if not self.updating_slider:
            self.slider.setValue(position)
            self.update_time_label(position, self.current_duration)

    def _on_duration_changed(self, duration):
        self.current_duration = duration
        if duration > 0:
            self.slider.setMaximum(duration)
        self.update_time_label(self.slider.value(), duration)

    def _on_playback_state_changed(self, state: PlaybackState):
        self.current_playback_state = state
        if state == PlaybackState.PLAYING:
            self.play_button.setText("Pause")
        else:
            self.play_button.setText("Play")

    def _on_media_status_changed(self, status: MediaStatus):
        if status == MediaStatus.LOADED:
             # Populate tracks when loaded
             self.populate_tracks()
        elif status == MediaStatus.End:
             # Maybe reset UI or auto-close?
             # Close the player when video ends and reset progress
             self.service.close_video(reset_progress=True)
             self.back_clicked.emit()

    # --- UI Logic ---

    def update_time_label(self, position, duration):
        def format_time(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000) % 60
            hours = (ms // 3600000)
            if hours > 0:
                return f"{hours:02}:{minutes:02}:{seconds:02}"
            return f"{minutes:02}:{seconds:02}"
            
        self.time_label.setText(f"{format_time(position)} / {format_time(duration)}")

    def toggle_play(self):
        if self.current_playback_state == PlaybackState.PLAYING:
            self.service.pause()
        else:
            self.service.play()

    def stop_video(self):
        self.service.close_video()
        self.back_clicked.emit()

    def on_slider_pressed(self):
        self.updating_slider = True

    def on_slider_released(self):
        self.updating_slider = False
        self.service.seek(self.slider.value())

    def on_slider_moved(self, value):
        if self.updating_slider:
             self.update_time_label(value, self.current_duration)

    def _on_position_changed(self, position):
        if not self.updating_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(False)
            self.update_time_label(position, self.current_duration)

    def on_audio_track_changed(self, index):
        self.service.set_audio_track(index)

    def on_subtitle_track_changed(self, index):
        self.service.set_subtitle_track(index)
        
    def populate_tracks(self):
        self.audio_combo.blockSignals(True)
        self.subtitle_combo.blockSignals(True)
        
        self.audio_combo.clear()
        self.subtitle_combo.clear()
        
        audio_tracks = self.service.get_audio_tracks()
        subtitle_tracks = self.service.get_subtitle_tracks()
        
        self.audio_combo.addItems(audio_tracks)
        self.subtitle_combo.addItems(subtitle_tracks)
        
        self.audio_combo.blockSignals(False)
        self.subtitle_combo.blockSignals(False)

    def set_fullscreen_mode(self, enabled: bool):
        self.fullscreen_mode = enabled
        self.setMouseTracking(enabled)
        # Track mouse on overlay to show/hide controls
        self.input_overlay.setMouseTracking(enabled)
        
        if enabled:
            self.start_hide_timer()
            self.show_controls()
            QApplication.instance().installEventFilter(self)
        else:
            self.hide_timer.stop()
            self.show_controls()
            QApplication.instance().removeEventFilter(self)

    def start_hide_timer(self):
        self.hide_timer.start()

    def hide_controls(self):
        if self.fullscreen_mode:
            self.top_controls_widget.hide()
            self.bottom_controls_widget.hide()
            self.setCursor(Qt.BlankCursor)
            self.controls_hidden = True

    def show_controls(self):
        self.top_controls_widget.show()
        self.bottom_controls_widget.show()
        self.setCursor(Qt.ArrowCursor)
        self.controls_hidden = False
        if self.fullscreen_mode:
            self.start_hide_timer()

    def mouseMoveEvent(self, event):
        if self.fullscreen_mode:
            self.show_controls()
        super().mouseMoveEvent(event)

    def eventFilter(self, obj, event):
        if self.fullscreen_mode and event.type() == QEvent.Type.MouseMove:
            self.show_controls()

        # Capture double click on the OVERLAY, not the video widget
        if obj == self.input_overlay:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.toggle_fullscreen.emit()
                return True
                
        return super().eventFilter(obj, event)
