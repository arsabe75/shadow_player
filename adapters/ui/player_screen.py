import ctypes
from domain.models import PlaybackState, MediaStatus, LoopMode
from app.services import VideoService
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,  
                               QApplication, QStackedLayout,
                               QListWidgetItem, QFrame, QFileDialog, QSizePolicy,
                               QAbstractItemView, QSlider, QStyleOptionSlider, QStyle)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QSize
from PySide6.QtGui import QMouseEvent
from qfluentwidgets import (
    PushButton, ToolButton, TransparentToolButton, BodyLabel,
    SubtitleLabel, ListWidget, ComboBox, CardWidget, FluentIcon, ToggleButton
)


class VideoSlider(QSlider):
    """
    Custom slider for video progress that supports:
    - Click to seek (not just drag)
    - Proper visual synchronization
    - Styled to match the dark theme
    """
    # Signal emitted when user interacts (click or drag release)
    userSeeked = Signal(int)  # Emits the new value
    
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self._is_dragging = False  # True while user is dragging
        self.setRange(0, 10000)
        self._apply_style()
    
    def _apply_style(self):
        """Apply dark theme styling to the slider."""
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #3d3d3d;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: #3d3d3d;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: none;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #e0e0e0;
            }
            QSlider::handle:horizontal:pressed {
                background: #c0c0c0;
            }
        """)
    
    def _calculateValueFromPosition(self, pos_x, pos_y):
        """Calculate slider value from mouse position."""
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove_rect = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
        )
        handle_rect = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
        )
        
        if self.orientation() == Qt.Horizontal:
            slider_length = groove_rect.width() - handle_rect.width()
            slider_min = groove_rect.x() + handle_rect.width() // 2
            pos = pos_x
        else:
            slider_length = groove_rect.height() - handle_rect.height()
            slider_min = groove_rect.y() + handle_rect.height() // 2
            pos = pos_y
        
        if slider_length > 0:
            new_val = self.minimum() + (self.maximum() - self.minimum()) * (pos - slider_min) / slider_length
            return max(self.minimum(), min(self.maximum(), int(new_val)))
        return self.value()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse click to seek directly to that position."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            new_val = self._calculateValueFromPosition(event.position().x(), event.position().y())
            self.setValue(new_val)
            # Emit seek immediately on click
            self.userSeeked.emit(new_val)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle drag."""
        if self._is_dragging and (event.buttons() & Qt.LeftButton):
            new_val = self._calculateValueFromPosition(event.position().x(), event.position().y())
            self.setValue(new_val)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release - emit seek signal and end drag."""
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.userSeeked.emit(self.value())
        super().mouseReleaseEvent(event)
    
    def isUserInteraction(self) -> bool:
        """Returns True if user is currently dragging the slider."""
        return self._is_dragging

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

class PlaylistPanel(CardWidget):
    close_clicked = Signal()

    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        self.setup_ui()
        self.setup_connections()
        self.refresh_playlist()

    def setup_ui(self):
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        header_lbl = SubtitleLabel("Playlist")
        header_layout.addWidget(header_lbl)
        
        header_layout.addStretch()
        
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE)
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        header_layout.addWidget(self.close_btn)
        
        panel_layout.addLayout(header_layout)
        
        # Toolbar (Add, Shuffle, Loop)
        toolbar_layout = QHBoxLayout()
        
        self.add_btn = ToolButton(FluentIcon.ADD)
        self.add_btn.setToolTip("Add Files")
        self.add_btn.clicked.connect(self.add_files)
        toolbar_layout.addWidget(self.add_btn)

        self.save_btn = ToolButton(FluentIcon.SAVE)
        self.save_btn.setToolTip("Save Playlist")
        self.save_btn.clicked.connect(self.save_playlist)
        toolbar_layout.addWidget(self.save_btn)
        
        self.shuffle_btn = ToggleButton("Shuffle")
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        toolbar_layout.addWidget(self.shuffle_btn)
        
        self.loop_btn = PushButton("Loop: Off")
        self.loop_btn.clicked.connect(self.cycle_loop_mode)
        toolbar_layout.addWidget(self.loop_btn)
        
        toolbar_layout.addStretch()
        
        panel_layout.addLayout(toolbar_layout)
        
        # List
        self.list_widget = ListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        
        panel_layout.addWidget(self.list_widget)

    def setup_connections(self):
        self.service.playlist_updated.connect(self.refresh_playlist)
        self.service.loop_mode_changed.connect(self.update_loop_ui)
        self.service.shuffle_mode_changed.connect(self.update_shuffle_ui)

    def add_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Add to Playlist", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)")
        if file_paths:
            self.service.add_files(file_paths)

    def save_playlist(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "M3U Playlist (*.m3u)")
        if path:
            self.service.save_playlist_to_file(path)

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
        idx = self.list_widget.row(item)
        self.service.play_at_index(idx)

    def on_rows_moved(self, parent, start, end, destination, row):
        new_list = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            video = item.data(Qt.UserRole)
            new_list.append(video)
        
        self.service.playlist_updated.disconnect(self.refresh_playlist)
        self.service.update_playlist(new_list)
        self.service.playlist_updated.connect(self.refresh_playlist)
        
        self.refresh_playlist()

class PlayerScreen(QWidget):
    back_clicked = Signal()
    toggle_fullscreen = Signal()

    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        
        # State tracking
        self.fullscreen_mode = False
        self.controls_hidden = False
        self.current_playback_state = PlaybackState.STOPPED
        self.current_duration = 0
        
        self.setup_ui()
        self.setup_connections()
        
        # Timer for hiding controls
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000)
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
        self.top_controls_widget.setStyleSheet("background-color: rgba(32, 32, 32, 180);")
        top_layout = QHBoxLayout(self.top_controls_widget)
        top_layout.setContentsMargins(8, 4, 8, 4)
        
        self.back_button = ToolButton(FluentIcon.LEFT_ARROW)
        self.back_button.setToolTip("Back")
        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        
        layout.addWidget(self.top_controls_widget)

        # Main Horizontal Area (Video + Playlist)
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("background-color: black;")
        self.central_layout = QHBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0,0,0,0)
        self.central_layout.setSpacing(0)
        
        # Video Container - set black background for letterboxing
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background-color: black;")
        self.video_stack = QStackedLayout(self.video_container)
        self.video_stack.setStackingMode(QStackedLayout.StackAll)
        
        self.video_widget = self.service.create_video_widget(self.video_container)
        self.video_widget.setStyleSheet("background-color: black;")
        self.service.set_video_output(self.video_widget)
        self.video_widget.installEventFilter(self)
        self.video_stack.addWidget(self.video_widget)
        
        # Clickable Overlay
        self.click_overlay = ClickableOverlay()
        self.click_overlay.double_clicked.connect(self.toggle_fullscreen)
        self.click_overlay.clicked.connect(self._on_video_clicked)
        self.video_stack.addWidget(self.click_overlay)
        
        self.central_layout.addWidget(self.video_container, stretch=1)

        # Playlist Panel
        self.playlist_panel = PlaylistPanel(self.service)
        self.playlist_panel.hide()
        self.playlist_panel.close_clicked.connect(self.toggle_playlist)
        
        self.central_layout.addWidget(self.playlist_panel, stretch=0)
        
        layout.addWidget(self.central_widget, stretch=1)

        # Bottom Controls Container
        self.bottom_controls_widget = QWidget()
        self.bottom_controls_widget.setStyleSheet("background-color: rgba(32, 32, 32, 200);")
        bottom_layout = QVBoxLayout(self.bottom_controls_widget)
        bottom_layout.setContentsMargins(12, 8, 12, 8)
        bottom_layout.setSpacing(6)
        
        # Custom Video Slider with click-to-seek support
        self.slider = VideoSlider(Qt.Horizontal)
        bottom_layout.addWidget(self.slider)

        # Controls (Play/Stop/Time)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        
        self.prev_button = ToolButton(FluentIcon.LEFT_ARROW)
        self.prev_button.setToolTip("Previous")
        controls_layout.addWidget(self.prev_button)

        self.play_button = ToolButton(FluentIcon.PLAY)
        self.play_button.setToolTip("Play")
        controls_layout.addWidget(self.play_button)

        self.next_button = ToolButton(FluentIcon.RIGHT_ARROW)
        self.next_button.setToolTip("Next")
        controls_layout.addWidget(self.next_button)

        self.stop_button = ToolButton(FluentIcon.POWER_BUTTON)
        self.stop_button.setToolTip("Stop")
        controls_layout.addWidget(self.stop_button)
        
        self.time_label = BodyLabel("00:00 / 00:00")
        controls_layout.addWidget(self.time_label)

        controls_layout.addStretch()
        
        self.playlist_btn = ToggleButton("Playlist")
        self.playlist_btn.setIcon(FluentIcon.MENU)
        self.playlist_btn.clicked.connect(self.toggle_playlist)
        controls_layout.addWidget(self.playlist_btn)

        bottom_layout.addLayout(controls_layout)
        
        # Tracks
        tracks_layout = QHBoxLayout()
        tracks_layout.setSpacing(8)
        
        tracks_layout.addWidget(BodyLabel("Audio:"))
        self.audio_combo = ComboBox()
        self.audio_combo.setMinimumWidth(200)
        tracks_layout.addWidget(self.audio_combo)
        
        self.audio_combo.blockSignals(True)
        
        tracks_layout.addWidget(BodyLabel("Subtitles:"))
        self.subtitle_combo = ComboBox()
        self.subtitle_combo.setMinimumWidth(200)
        tracks_layout.addWidget(self.subtitle_combo)
        tracks_layout.addStretch()
        
        bottom_layout.addLayout(tracks_layout)

        layout.addWidget(self.bottom_controls_widget)

    def toggle_playlist(self):
        if self.playlist_panel.isVisible():
            self.playlist_panel.hide()
            self.playlist_btn.setChecked(False)
            self.central_layout.setStretch(0, 1)
            self.central_layout.setStretch(1, 0)
        else:
            self.playlist_panel.show()
            self.playlist_btn.setChecked(True)
            self.central_layout.setStretch(0, 7)
            self.central_layout.setStretch(1, 3)

    def _apply_win32_transparency(self, widget):
        hwnd = int(widget.winId())
        if hasattr(ctypes, 'windll'):
            try:
                user32 = ctypes.windll.user32
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)
            except Exception as e:
                print(f"DEBUG: Failed to apply transparency: {e}")

    def _apply_win32_colorkey(self, widget, color_ref=0x00FF00FF):
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
        
        # Connect VideoSlider's userSeeked signal - fires on both click and drag release
        self.slider.userSeeked.connect(self.on_slider_seek)

        self.audio_combo.currentIndexChanged.connect(self.on_audio_track_changed)
        self.subtitle_combo.currentIndexChanged.connect(self.on_subtitle_track_changed)

        self.prev_button.clicked.connect(self.service.play_previous)
        self.next_button.clicked.connect(self.service.play_next)
        
        self.service.playlist_updated.connect(self.update_navigation_controls)
        
        # Initial state
        self.update_navigation_controls()

    def _on_back_clicked(self):
        self.service.close_video()
        self.back_clicked.emit()

    def _position_to_slider(self, position: int) -> int:
        """Convert position in ms to slider value (0-10000)."""
        if self.current_duration <= 0:
            return 0
        return int((position / self.current_duration) * 10000)
    
    def _slider_to_position(self, slider_value: int) -> int:
        """Convert slider value (0-10000) to position in ms."""
        if self.current_duration <= 0:
            return 0
        return int((slider_value / 10000) * self.current_duration)

    def _on_position_changed(self, position):
        # Only update slider if user is not interacting with it
        if not self.slider.isUserInteraction() and self.current_duration > 0:
            # Convert position to normalized slider value
            slider_value = self._position_to_slider(position)
            self.slider.blockSignals(True)
            self.slider.setValue(slider_value)
            self.slider.blockSignals(False)
            self.update_time_label(position, self.current_duration)
        elif not self.slider.isUserInteraction():
            # Just update time label even without valid duration
            self.update_time_label(position, self.current_duration)

    def _on_duration_changed(self, duration):
        if duration > 0:
            self.current_duration = duration
        self.update_time_label(self._slider_to_position(self.slider.value()), self.current_duration)

    def _on_playback_state_changed(self, state: PlaybackState):
        self.current_playback_state = state
        if state == PlaybackState.PLAYING:
            self.play_button.setIcon(FluentIcon.PAUSE)
            self.play_button.setToolTip("Pause")
            self.click_overlay.raise_()
        else:
            self.play_button.setIcon(FluentIcon.PLAY)
            self.play_button.setToolTip("Play")

    def _on_media_status_changed(self, status: MediaStatus):
        if status == MediaStatus.LOADED:
             self.track_retries = 0
             self.populate_tracks_with_retry()

    def populate_tracks_with_retry(self):
        self.track_retries += 1
        audio = self.service.get_audio_tracks()

        self.populate_tracks()
        
        if len(audio) <= 1 and self.track_retries < 20:
             QTimer.singleShot(500, self.populate_tracks_with_retry)

    def _on_playback_finished(self):
         self.back_clicked.emit()

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

    def on_slider_seek(self, slider_value):
        """Called when user seeks via click or drag on the slider."""
        position_ms = self._slider_to_position(slider_value)
        self.service.seek(position_ms)
        self.update_time_label(position_ms, self.current_duration)

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

    def update_navigation_controls(self):
        has_playlist = len(self.service.playlist) > 1
        self.prev_button.setVisible(has_playlist)
        self.next_button.setVisible(has_playlist)

    def _on_video_clicked(self):
        if self.playlist_panel.isVisible():
            self.toggle_playlist()
        else:
             self.toggle_play()

    def set_fullscreen_mode(self, enabled: bool):
        self.fullscreen_mode = enabled
        self.setMouseTracking(enabled)
        self.click_overlay.setMouseTracking(enabled)
        
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
            QApplication.setOverrideCursor(Qt.BlankCursor)
            self.controls_hidden = True

    def show_controls(self):
        self.top_controls_widget.show()
        self.bottom_controls_widget.show()
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

        if obj == self.video_widget:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.click_timer.stop()
                self.toggle_fullscreen.emit()
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.click_timer.start()
                
        return super().eventFilter(obj, event)

    def _on_single_click_fallback(self):
         self._on_video_clicked()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_fullscreen.emit()
            event.accept()
