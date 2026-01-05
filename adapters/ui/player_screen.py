import ctypes
from domain.models import PlaybackState, MediaStatus, LoopMode
from app.services import VideoService
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QSlider, QLabel, QComboBox, QApplication, QStackedLayout,
                               QListWidget, QListWidgetItem, QFrame, QFileDialog, QSizePolicy,
                               QAbstractItemView)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QSize

# Constants for Win32 API
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
LWA_COLORKEY = 0x1
LWA_ALPHA = 0x2

class ClickableOverlay(QWidget):
    double_clicked = Signal()
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False) 
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)
        
        # Debounce timer for single/double click distinction
        self.click_timer = QTimer(self)
        self.click_timer.setInterval(250) # 250ms wait for double click
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._on_single_click)
        
        # Apply Win32 layered window attributes AFTER widget is realized
        QTimer.singleShot(100, self._apply_win32_transparency)

    def _apply_win32_transparency(self):
        """Make the overlay truly transparent but still receive mouse events on Windows."""
        if not hasattr(ctypes, 'windll'):
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            LWA_ALPHA = 0x2
            
            # Add WS_EX_LAYERED
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
            
            # Set alpha to 1 (almost invisible but still receives input)
            user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
        except Exception as e:
            print(f"DEBUG: Win32 transparency failed: {e}")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_timer.stop() # Cancel single click
            self.double_clicked.emit()
            event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
             # Start timer instead of immediate emit
             self.click_timer.start()
             event.accept()
        else:
             super().mousePressEvent(event)
             
    def _on_single_click(self):
        self.clicked.emit()
        
    def mouseMoveEvent(self, event):
        event.ignore() 
        super().mouseMoveEvent(event)

class PlaylistPanel(QWidget):
    close_clicked = Signal()

    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        self.setup_ui()
        self.setup_connections()
        self.refresh_playlist()

    def setup_ui(self):
        # Playlist Panel Style
        self.setStyleSheet("background-color: #2b2b2b; border-left: 1px solid #444;")
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(10, 10, 10, 10) # Add some padding
        
        # Header
        header_layout = QHBoxLayout()
        header_lbl = QLabel("Playlist")
        header_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        header_layout.addWidget(header_lbl)
        
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        header_layout.addWidget(self.close_btn)
        
        panel_layout.addLayout(header_layout)
        
        # Toolbar (Add, Shuffle, Loop)
        toolbar_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("+ Add")
        self.add_btn.clicked.connect(self.add_files)
        toolbar_layout.addWidget(self.add_btn)
        
        self.shuffle_btn = QPushButton("Shuffle")
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        toolbar_layout.addWidget(self.shuffle_btn)
        
        self.loop_btn = QPushButton("Loop: Off")
        self.loop_btn.clicked.connect(self.cycle_loop_mode)
        toolbar_layout.addWidget(self.loop_btn)
        
        panel_layout.addLayout(toolbar_layout)
        
        # List
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setStyleSheet("background-color: transparent; border: none; color: white;")
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        
        panel_layout.addWidget(self.list_widget)

    def setup_connections(self):
        self.service.playlist_updated.connect(self.refresh_playlist)
        self.service.loop_mode_changed.connect(self.update_loop_ui)
        self.service.shuffle_mode_changed.connect(self.update_shuffle_ui)
        # self.transparent_area.mousePressEvent = self.on_transparent_click # Handled by event filter

    # Removed event filter for transparent click

    def add_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Add to Playlist", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)")
        if file_paths:
            self.service.add_files(file_paths)

    def toggle_shuffle(self):
        self.service.toggle_shuffle()

    def cycle_loop_mode(self):
        current = self.service.loop_mode
        if current == LoopMode.NO_LOOP:
            new_mode = LoopMode.LOOP_ALL
        elif current == LoopMode.LOOP_ALL:
            new_mode = LoopMode.LOOP_ONE
        else:
            new_mode = LoopMode.NO_LOOP
        self.service.set_loop_mode(new_mode)

    def update_loop_ui(self, mode):
        text = "Loop: Off"
        if mode == LoopMode.LOOP_ALL:
            text = "Loop: All"
        elif mode == LoopMode.LOOP_ONE:
            text = "Loop: One"
        self.loop_btn.setText(text)

    def update_shuffle_ui(self, is_shuffled):
        self.shuffle_btn.setChecked(is_shuffled)
        self.shuffle_btn.setText("Shuffle: On" if is_shuffled else "Shuffle")

    def refresh_playlist(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for idx, video in enumerate(self.service.playlist):
            item = QListWidgetItem(f"{idx + 1}. {video.title}")
            item.setData(Qt.UserRole, video)
            if idx == self.service.current_index:
                # Highlight playing
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(Qt.green)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
            
    def on_item_double_clicked(self, item):
        # We find the index based on the row in the list
        idx = self.list_widget.row(item)
        self.service.play_at_index(idx)

    def on_rows_moved(self, parent, start, end, destination, row):
        new_list = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            video = item.data(Qt.UserRole)
            new_list.append(video)
        
        # Block signal to avoid recursion/refresh while we just rebuilt it
        self.service.playlist_updated.disconnect(self.refresh_playlist)
        self.service.update_playlist(new_list)
        self.service.playlist_updated.connect(self.refresh_playlist)
        
        # Manually trigger refresh to update indices in titles
        self.refresh_playlist()

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
        
        # Debounce timer for fallback click handling
        self.click_timer = QTimer(self)
        self.click_timer.setInterval(250)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._on_single_click_fallback)
        
        # Connect Service Signals
        self.service.position_changed.connect(self._on_position_changed)
        self.service.duration_changed.connect(self._on_duration_changed)
        self.service.playback_state_changed.connect(self._on_playback_state_changed)
        self.service.media_status_changed.connect(self._on_media_status_changed)
        self.service.playback_finished.connect(self._on_playback_finished)

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

        # 2. Main Horizontal Area (Video + Playlist)
        self.central_widget = QWidget()
        self.central_layout = QHBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0,0,0,0)
        self.central_layout.setSpacing(0)
        
        # Video Container
        self.video_container = QWidget()
        self.video_stack = QStackedLayout(self.video_container)
        self.video_stack.setStackingMode(QStackedLayout.StackAll)
        
        self.video_widget = self.service.create_video_widget(self.video_container)
        self.service.set_video_output(self.video_widget)
        self.video_widget.installEventFilter(self) # Install filter to catch clicks/double-clicks
        self.video_stack.addWidget(self.video_widget)
        
        # Clickable Overlay (Top Layer) with Win32 transparency
        # Uses layered window with alpha=1 to be invisible but still receive clicks.
        # This is critical for VLC which renders to a native HWND that paints over Qt.
        self.click_overlay = ClickableOverlay()
        self.click_overlay.double_clicked.connect(self.toggle_fullscreen)
        self.click_overlay.clicked.connect(self._on_video_clicked)
        self.video_stack.addWidget(self.click_overlay)
        
        self.central_layout.addWidget(self.video_container, stretch=1) # Video takes all space by default

        # Playlist Panel (Side by Side)
        self.playlist_panel = PlaylistPanel(self.service)
        self.playlist_panel.hide()
        self.playlist_panel.close_clicked.connect(self.toggle_playlist)
        # Fixed width or ratio? User said 30%
        # We can implement 30% ratio by using stretch factors
        
        self.central_layout.addWidget(self.playlist_panel, stretch=0)
        
        layout.addWidget(self.central_widget, stretch=1)
        
        # Clean up old Win32 stuff references if any remain...

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

        controls_layout.addStretch()
        
        self.playlist_btn = QPushButton("Playlist")
        self.playlist_btn.setCheckable(True)
        self.playlist_btn.clicked.connect(self.toggle_playlist)
        controls_layout.addWidget(self.playlist_btn)

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

    def toggle_playlist(self):
        if self.playlist_panel.isVisible():
            self.playlist_panel.hide()
            self.playlist_btn.setChecked(False)
            # Restore video to full width
            self.central_layout.setStretch(0, 1)
            self.central_layout.setStretch(1, 0)
        else:
            self.playlist_panel.show()
            self.playlist_btn.setChecked(True)
            # Set 70/30 split
            self.central_layout.setStretch(0, 7)
            self.central_layout.setStretch(1, 3)

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

    def _apply_win32_colorkey(self, widget, color_ref=0x00FF00FF): # Magenta 0x00RRGGBB format for Win32 (BGR?)
        # COLORREF in win32 is 0x00BBGGRR
        # Magenta (255, 0, 255) -> 0x00FF00FF
        hwnd = int(widget.winId())
        if hasattr(ctypes, 'windll'):
            try:
                user32 = ctypes.windll.user32
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, color_ref, 0, LWA_COLORKEY)
            except Exception as e:
                print(f"DEBUG: Failed to apply colorkey: {e}")

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
            # Keep overlay on top when playback starts
            self.click_overlay.raise_()
        else:
            self.play_button.setText("Play")

    def _on_media_status_changed(self, status: MediaStatus):
        if status == MediaStatus.LOADED:
             # Start trying to populate tracks with retries
             self.track_retries = 0
             self.populate_tracks_with_retry()
        # Removed auto-close on End; handled by Service's playback_finished signal

    def populate_tracks_with_retry(self):
        self.track_retries += 1
        audio = self.service.get_audio_tracks()

        self.populate_tracks()
        
        if len(audio) <= 1 and self.track_retries < 20: # Retry up to 20 times (10 seconds)
             QTimer.singleShot(500, self.populate_tracks_with_retry)

    def _on_playback_finished(self):
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

    def _on_video_clicked(self):
        # Close playlist if open
        if self.playlist_panel.isVisible():
            self.toggle_playlist()
        else:
             self.toggle_play()

    def set_fullscreen_mode(self, enabled: bool):
        self.fullscreen_mode = enabled
        self.setMouseTracking(enabled)
        self.click_overlay.setMouseTracking(enabled) # Track mouse on overlay for controls
        
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
            # Use global override cursor for QtMultimedia compatibility
            QApplication.setOverrideCursor(Qt.BlankCursor)
            self.controls_hidden = True

    def show_controls(self):
        self.top_controls_widget.show()
        self.bottom_controls_widget.show()
        # Restore cursor using global override
        QApplication.restoreOverrideCursor()
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

        # Capture double click on the video widget (fallback if overlay is behind native window)
        if obj == self.video_widget:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.click_timer.stop() # Cancel fallback single click
                self.toggle_fullscreen.emit()
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.click_timer.start()
                # Do NOT return True here effectively
                
        return super().eventFilter(obj, event)

    def _on_single_click_fallback(self):
         self._on_video_clicked()

    def mouseDoubleClickEvent(self, event):
        # Fallback for when the widget itself gets the event
        if event.button() == Qt.LeftButton:
            self.toggle_fullscreen.emit()
            event.accept()
