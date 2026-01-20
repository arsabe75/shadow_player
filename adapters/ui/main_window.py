from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget, QMainWindow
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QKeyEvent, QCloseEvent
from qfluentwidgets import setTheme, Theme, StateToolTip, InfoBar, InfoBarPosition
from adapters.ui.home_screen import HomeScreen
from adapters.ui.player_screen import PlayerScreen
from adapters.ui.playlist_manager import PlaylistManagerScreen
from app.services import VideoService
from pathlib import Path


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
        
        # Telegram screens (lazy initialization)
        self._telegram_login_screen = None
        self._telegram_main_screen = None
        self._telegram_storage_screen = None
        self._telegram_initialized = False

        self.setup_connections()

    def setup_connections(self):
        self.home_screen.video_selected.connect(self.on_video_selected)
        self.home_screen.files_selected.connect(self.on_files_selected)
        self.home_screen.lists_clicked.connect(self.show_playlist_manager)
        self.home_screen.telegram_clicked.connect(self.show_telegram)

        self.player_screen.back_clicked.connect(self.show_previous_screen)
        self.player_screen.toggle_fullscreen.connect(self.toggle_fullscreen_state)
        
        self.playlist_manager.back_clicked.connect(self.show_home)
        self.playlist_manager.playlist_started.connect(self.on_playlist_started)
        
        # Add videos to recent list as they start playing
        self.service.video_started.connect(self.home_screen.add_recent_video)
    
    def show_telegram(self):
        """Navigate to Telegram screen (login if not authenticated)."""
        # Show loading indicator immediately
        if hasattr(self, '_telegram_loading_tip') and self._telegram_loading_tip:
            return  # Already loading
        
        from PySide6.QtWidgets import QApplication
        
        self._telegram_loading_tip = StateToolTip(
            "Telegram",
            "Inicializando...",
            self
        )
        self._telegram_loading_tip.move(
            self.width() // 2 - self._telegram_loading_tip.width() // 2,
            20
        )
        self._telegram_loading_tip.show()
        
        # Force UI update to show the tooltip
        QApplication.processEvents()
        
        # Initialize screens if needed (this may take a moment)
        if not self._telegram_initialized:
            self._init_telegram_screens()
        
        # Hide loading
        if hasattr(self, '_telegram_loading_tip') and self._telegram_loading_tip:
            self._telegram_loading_tip.setContent("Listo")
            self._telegram_loading_tip.setState(True)
            self._telegram_loading_tip.close()
            self._telegram_loading_tip = None
        
        if not self._telegram_initialized:
            return
        
        # Check authentication status via worker
        # We start with the login screen (which will show loading)
        # It will either auto-login (if authorized) or show QR
        self.stack.setCurrentWidget(self._telegram_login_screen)
        
        # Trigger auth check
        if self._telegram_login_screen:
            self._telegram_login_screen.check_auth()
    
    def _on_telegram_login_success(self):
        """Called when Telegram login is successful."""
        InfoBar.success(
            title="Telegram",
            content="¡Sesión iniciada correctamente!",
            parent=self,
            position=InfoBarPosition.TOP
        )
        self._show_telegram_main()
    
    def _init_telegram_screens(self):
        """Initialize Telegram screens lazily."""
        try:
            from adapters.security.secure_storage import SecureStorage
            from adapters.telegram.favorites_manager import FavoritesManager
            from adapters.telegram.recent_videos import RecentVideosManager
            from adapters.ui.telegram.telegram_main_screen import TelegramMainScreen
            from adapters.ui.telegram.telegram_login_screen import TelegramLoginScreen
            from adapters.ui.telegram.storage_settings_screen import StorageSettingsScreen
            from adapters.telegram.cache_manager import TelegramCacheManager, CacheSettings
            from adapters.telegram.tdlib_client import TDLibClient
            
            # Setup data directories
            data_dir = Path.home() / ".shadow_player"
            cache_dir = data_dir / "telegram_cache"
            tdlib_dir = data_dir / "tdlib"
            
            # Initialize managers
            self._secure_storage = SecureStorage(data_dir)
            self._tdlib_client = TDLibClient(tdlib_dir, self._secure_storage)
            favorites_manager = FavoritesManager(self._secure_storage)
            recent_videos_manager = RecentVideosManager(self._secure_storage)
            cache_manager = TelegramCacheManager(cache_dir, CacheSettings())
            
            # Create login screen
            self._telegram_login_screen = TelegramLoginScreen(self._tdlib_client)
            self._telegram_login_screen.back_requested.connect(self.show_home)
            self._telegram_login_screen.login_successful.connect(self._on_telegram_login_success)
            self.stack.addWidget(self._telegram_login_screen)
            
            # Create main screen
            self._telegram_main_screen = TelegramMainScreen(
                favorites_manager,
                recent_videos_manager
            )
            self._telegram_main_screen.back_requested.connect(self.show_home)
            self._telegram_main_screen.storage_requested.connect(self._show_telegram_storage)
            self._telegram_main_screen.logout_requested.connect(self._on_telegram_logout)
            self.stack.addWidget(self._telegram_main_screen)
            
            # Create storage screen
            self._telegram_storage_screen = StorageSettingsScreen(cache_manager)
            self._telegram_storage_screen.back_requested.connect(self._show_telegram_main)
            self.stack.addWidget(self._telegram_storage_screen)
            
            # Create browse screen
            from adapters.ui.telegram.telegram_browse_screen import TelegramBrowseScreen
            self._telegram_browse_screen = TelegramBrowseScreen(self._tdlib_client)
            self._telegram_browse_screen.back_requested.connect(self._show_telegram_main)
            self._telegram_browse_screen.chat_selected.connect(self._show_telegram_chat_videos)
            self.stack.addWidget(self._telegram_browse_screen)

            # Create video list screen
            from adapters.ui.telegram.telegram_video_list_screen import TelegramVideoListScreen
            self._telegram_video_list_screen = TelegramVideoListScreen()
            self._telegram_video_list_screen.back_requested.connect(self._handle_telegram_video_back)
            self._telegram_video_list_screen.video_selected.connect(self._play_telegram_video)
            self.stack.addWidget(self._telegram_video_list_screen)
            
            # Create topic list screen
            from adapters.ui.telegram.telegram_topic_list_screen import TelegramTopicListScreen
            self._telegram_topic_list_screen = TelegramTopicListScreen()
            self._telegram_topic_list_screen.back_requested.connect(self._show_telegram_browse)
            self._telegram_topic_list_screen.topic_selected.connect(self._show_telegram_topic_videos)
            self.stack.addWidget(self._telegram_topic_list_screen)
            
            # Connect main screen signals
            self._telegram_main_screen.browse_requested.connect(self._show_telegram_browse)
            
            self._telegram_initialized = True
            
        except ImportError as e:
            InfoBar.error(
                title="Missing Dependencies",
                content=f"Install required packages: pip install -r requirements.txt ({e})",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000
            )
        except Exception as e:
            InfoBar.error(
                title="Telegram Error",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP
            )
    
    def _show_telegram_storage(self):
        """Show Telegram storage settings screen."""
        if self._telegram_storage_screen:
            self._telegram_storage_screen.refresh()
            self.stack.setCurrentWidget(self._telegram_storage_screen)
    
    def _show_telegram_main(self):
        """Navigate back to Telegram main screen."""
        if self._telegram_main_screen:
            self._telegram_main_screen.refresh()
            self.stack.setCurrentWidget(self._telegram_main_screen)

    def _show_telegram_browse(self):
        """Show Telegram chat browser."""
        if hasattr(self, '_telegram_browse_screen'):
            self.stack.setCurrentWidget(self._telegram_browse_screen)
            self._telegram_browse_screen.load_chats()

    def _handle_telegram_video_back(self):
        """Handle back button from video list."""
        # If we have an active thread, go back to topic list
        if hasattr(self, '_active_thread') and self._active_thread:
            if hasattr(self, '_active_chat') and self._active_chat:
                self._show_telegram_chat_videos(self._active_chat)
                return

        # Default: Go back to browse
        self._show_telegram_browse()

    def _show_telegram_chat_videos(self, chat):
        """Show videos for selected chat (or topics if forum)."""
        # Store context
        self._active_chat = chat
        self._active_thread = None
        
        # Check if chat is a forum
        is_forum = getattr(chat, 'forum', False)
        print(f"[MainWindow] Opening chat: {getattr(chat, 'id', 'Unknown')} - Is Forum: {is_forum}")
        
        if is_forum:
             if hasattr(self, '_telegram_topic_list_screen'):
                 self.stack.setCurrentWidget(self._telegram_topic_list_screen)
                 self._telegram_topic_list_screen.load_topics(chat)
        else:
            if hasattr(self, '_telegram_video_list_screen'):
                self.stack.setCurrentWidget(self._telegram_video_list_screen)
                title = getattr(chat, 'title', 'Videos')
                self._telegram_video_list_screen.load_videos(chat.id, title=title)
                
    def _show_telegram_topic_videos(self, chat_id, thread_id):
        """Show videos for a specific topic."""
        # Store context (assuming _active_chat is already set from previous step)
        self._active_thread = thread_id
        
        if hasattr(self, '_telegram_video_list_screen'):
            self.stack.setCurrentWidget(self._telegram_video_list_screen)
            self._telegram_video_list_screen.load_videos(chat_id, thread_id=thread_id)

    def _play_telegram_video(self, message, chat_id):
        """Play a video from Telegram."""
        print(f"[MainWindow] Requesting playback for message {message.id} in chat {chat_id}")
        
        from adapters.telegram.async_worker import get_telegram_worker, TelegramOp
        
        def on_url_ready(success, result):
            if success and result:
                url = result
                print(f"[MainWindow] Playback URL: {url}")
                # Play using service
                # We need to create a Video object or just pass path
                # service.play_files expects paths.
                
                # Remember current screen before switching
                self._previous_screen = self.stack.currentWidget()
                
                self.service.play_files([url])
                self.stack.setCurrentWidget(self.player_screen)
            else:
                 InfoBar.error(
                    title="Error",
                    content="No se pudo obtener el enlace de streaming.",
                    parent=self,
                    position=InfoBarPosition.TOP
                )

        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.GET_STREAM_URL,
            on_url_ready,
            message_id=message.id,
            chat_id=chat_id
        )

    def show_previous_screen(self):
        """Navigate back to the previous screen (used by player)."""
        if hasattr(self, '_previous_screen') and self._previous_screen:
            self.stack.setCurrentWidget(self._previous_screen)
            self._previous_screen = None # Reset
        else:
            self.show_home()
            
    def _on_telegram_logout(self):
        """Handle Telegram logout."""
        from adapters.telegram.async_worker import get_telegram_worker, TelegramOp
        
        # Show loading or status
        InfoBar.info(
            title="Cerrando sesión...",
            content="Por favor espera",
            parent=self,
            position=InfoBarPosition.TOP
        )
        
        def on_logout_finished(success, result):
            # Reset UI
            if self._telegram_login_screen:
                self._telegram_login_screen.reset()
            
            # Navigate to Home
            self.show_home()
            
            InfoBar.success(
                title="Telegram",
                content="Sesión cerrada correctamente",
                parent=self,
                position=InfoBarPosition.TOP
            )
            
        worker = get_telegram_worker()
        worker.execute(TelegramOp.LOGOUT, on_logout_finished)

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
