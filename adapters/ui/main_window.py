from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget, QMainWindow
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QCloseEvent
from qfluentwidgets import setTheme, Theme
from adapters.ui.home_screen import HomeScreen
from adapters.ui.player_screen import PlayerScreen
from app.services import VideoService

class MainWindow(QMainWindow):
    def __init__(self, service: VideoService):
        super().__init__()
        self.service = service
        self.setWindowTitle("Shadow Player")
        self.setMinimumSize(800, 600)
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

        self.stack.addWidget(self.home_screen)
        self.stack.addWidget(self.player_screen)

        self.setup_connections()

    def setup_connections(self):
        self.home_screen.video_selected.connect(self.on_video_selected)
        self.home_screen.files_selected.connect(self.on_files_selected)

        self.player_screen.back_clicked.connect(self.show_home)
        self.player_screen.toggle_fullscreen.connect(self.toggle_fullscreen_state)

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
        """Handle hot-swapping of player engine."""
        # Create new player adapter
        if new_engine == "mpv":
            from adapters.player.mpv_player import MpvPlayer
            new_player = MpvPlayer()
        elif new_engine == "vlc":
            from adapters.player.vlc_player import VlcPlayer
            new_player = VlcPlayer()
        else:
            from adapters.player.qt_player import QtPlayer
            new_player = QtPlayer()
        
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
            content=f"Player engine changed to {new_engine.upper()}.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3000
        )
