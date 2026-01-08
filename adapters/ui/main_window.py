from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget, QMainWindow
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QKeyEvent, QCloseEvent
from qfluentwidgets import setTheme, Theme, StateToolTip
from adapters.ui.home_screen import HomeScreen
from adapters.ui.player_screen import PlayerScreen
from adapters.ui.playlist_manager import PlaylistManagerScreen
from app.services import VideoService


class PlayerInitWorker(QObject):
    """Worker to initialize player adapters in a background thread.
    
    NOTE: Only VLC and MPV should be initialized in background.
    QtPlayer must be created in the main thread since it's a QObject.
    """
    finished = Signal(object)  # Emits the initialized player
    error = Signal(str)

    def __init__(self, engine: str):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            if self.engine == "mpv":
                from adapters.player.mpv_player import MpvPlayer
                player = MpvPlayer()
            elif self.engine == "vlc":
                from adapters.player.vlc_player import VlcPlayer
                player = VlcPlayer()
            else:
                # Should not reach here - Qt is handled synchronously
                raise ValueError("QtPlayer should not be initialized in background thread")
            self.finished.emit(player)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        self.setWindowTitle("Shadow Player")
        self.setMinimumSize(1024, 768)
        self.resize(1024, 768)
        self.was_maximized_before_fullscreen = False

        # Set dark theme by default for a media player
        setTheme(Theme.DARK)
        
        # Apply dark theme to window
        self.setStyleSheet("""
            QMainWindow {
                background-color: #202020;
            }
        """)

        # Central widget and layout
        self.central_widget = QWidget()
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)
        
        # Use stacked widget for screens
        self.stack = QStackedWidget()
        self.central_layout.addWidget(self.stack)
        
        # Set central widget using QMainWindow's method
        self.setCentralWidget(self.central_widget)

        self.home_screen = HomeScreen(self.service.persistence, self.handle_engine_change)
        self.player_screen = PlayerScreen(service)
        self.playlist_manager = PlaylistManagerScreen(service)

        self.stack.addWidget(self.home_screen)
        self.stack.addWidget(self.player_screen)
        self.stack.addWidget(self.playlist_manager)

        self.setup_connections()

    def setup_connections(self):
        self.home_screen.video_selected.connect(self.on_video_selected)
        self.home_screen.files_selected.connect(self.on_files_selected)
        self.home_screen.lists_clicked.connect(self.show_playlist_manager)

        self.player_screen.back_clicked.connect(self.show_home)
        self.player_screen.toggle_fullscreen.connect(self.toggle_fullscreen_state)
        
        self.playlist_manager.back_clicked.connect(self.show_home)
        self.playlist_manager.playlist_started.connect(self.on_playlist_started)
        
        # Add videos to recent list as they start playing
        self.service.video_started.connect(self.home_screen.add_recent_video)

    def show_playlist_manager(self):
        self.stack.setCurrentWidget(self.playlist_manager)

    def on_playlist_started(self, videos: list, start_from_beginning: bool = False):
        if not videos: return
        paths = [v.path for v in videos]
        self.service.play_files(paths, start_from_beginning=start_from_beginning)
        self.stack.setCurrentWidget(self.player_screen)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F:
            self.toggle_fullscreen_state()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent):
        self.service.close_video()
        super().closeEvent(event)

    def toggle_fullscreen_state(self):
        if self.isFullScreen():
            # Restore previous window state
            if self.was_maximized_before_fullscreen:
                self.showMaximized()
            else:
                self.showNormal()
            self.player_screen.set_fullscreen_mode(False)
        else:
            # Save current state before going fullscreen
            self.was_maximized_before_fullscreen = self.isMaximized()
            self.showFullScreen()
            self.player_screen.set_fullscreen_mode(True)

    def on_video_selected(self, path: str):
        self.service.open_video(path)
        self.stack.setCurrentWidget(self.player_screen)
        
    def on_files_selected(self, paths: list[str]):
        if not paths: return
        self.service.play_files(paths)
        self.stack.setCurrentWidget(self.player_screen)


    def show_home(self):
        # Exit fullscreen mode if active before returning to home
        if self.isFullScreen():
            self.toggle_fullscreen_state()
        
        self.stack.setCurrentWidget(self.home_screen)

    def handle_engine_change(self, new_engine: str):
        """Handle hot-swapping of player engine.
        
        QtPlayer is initialized synchronously (required for QObject thread affinity).
        VLC and MPV are initialized in a background thread to avoid UI freezes.
        """
        self._pending_engine = new_engine
        
        # QtPlayer must be created in the main thread (it's a QObject)
        if new_engine == "qt":
            from adapters.player.qt_player import QtPlayer
            new_player = QtPlayer()
            self._finalize_engine_swap(new_player)
            return
        
        # For VLC/MPV, use background thread to avoid UI freeze
        # Show loading indicator
        self._engine_change_tooltip = StateToolTip(
            "Initializing Player",
            f"Loading {new_engine.upper()} engine...",
            self
        )
        self._engine_change_tooltip.move(
            self.width() // 2 - self._engine_change_tooltip.width() // 2,
            20
        )
        self._engine_change_tooltip.show()
        
        # Disable engine selector during initialization
        self.home_screen.setEnabled(False)
        
        # Create worker and thread
        self._init_thread = QThread()
        self._init_worker = PlayerInitWorker(new_engine)
        self._init_worker.moveToThread(self._init_thread)
        
        # Connect signals
        self._init_thread.started.connect(self._init_worker.run)
        self._init_worker.finished.connect(self._on_player_initialized)
        self._init_worker.error.connect(self._on_player_init_error)
        self._init_worker.finished.connect(self._init_thread.quit)
        self._init_worker.error.connect(self._init_thread.quit)
        self._init_thread.finished.connect(self._cleanup_init_thread)
        
        # Start initialization in background
        self._init_thread.start()

    def _on_player_initialized(self, new_player):
        """Called when player initialization completes successfully."""
        # Hide loading indicator
        if hasattr(self, '_engine_change_tooltip') and self._engine_change_tooltip:
            self._engine_change_tooltip.setContent("Done!")
            self._engine_change_tooltip.setState(True)
            self._engine_change_tooltip.close()
        
        # Re-enable UI
        self.home_screen.setEnabled(True)
        
        # Finalize the swap
        self._finalize_engine_swap(new_player)

    def _finalize_engine_swap(self, new_player):
        """Finalize the engine swap - shared by sync (Qt) and async (VLC/MPV) paths."""
        # Swap player in service
        self.service.swap_player(new_player)
        
        # Recreate player screen with new player
        old_player_screen = self.player_screen
        self.stack.removeWidget(old_player_screen)
        old_player_screen.deleteLater()
        
        self.player_screen = PlayerScreen(self.service)
        self.stack.addWidget(self.player_screen)
        
        # Reconnect signals
        self.player_screen.back_clicked.connect(self.show_home)
        self.player_screen.toggle_fullscreen.connect(self.toggle_fullscreen_state)
        
        # Show success message
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.success(
            title="Engine Changed",
            content=f"Player engine changed to {self._pending_engine.upper()}.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3000
        )

    def _on_player_init_error(self, error_msg: str):
        """Called when player initialization fails."""
        # Hide loading indicator
        if hasattr(self, '_engine_change_tooltip'):
            self._engine_change_tooltip.close()
        
        # Re-enable UI
        self.home_screen.setEnabled(True)
        
        # Show error message
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.error(
            title="Initialization Failed",
            content=f"Failed to initialize {self._pending_engine.upper()}: {error_msg}",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000
        )

    def _cleanup_init_thread(self):
        """Clean up thread resources after initialization."""
        if hasattr(self, '_init_thread'):
            self._init_thread.deleteLater()
            self._init_thread = None
        if hasattr(self, '_init_worker'):
            self._init_worker = None
