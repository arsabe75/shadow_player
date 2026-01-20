"""
Main Telegram screen with favorites, recent videos, and navigation.
Side-by-side layout matching home screen proportions.
"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QSizePolicy, QListWidgetItem, QAbstractItemView
)
from qfluentwidgets import (
    PushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    CardWidget, FluentIcon, InfoBar, InfoBarPosition,
    ScrollArea, ListWidget, TransparentToolButton
)

from adapters.telegram.favorites_manager import FavoritesManager, FavoriteChannel
from adapters.telegram.recent_videos import RecentVideosManager, TelegramVideo
from adapters.telegram.cache_manager import format_size


class FavoriteChannelCard(CardWidget):
    """Card widget for a favorite channel."""
    
    clicked = Signal(int)  # chat_id
    remove_clicked = Signal(int)  # chat_id
    
    def __init__(self, channel: FavoriteChannel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        
        # Icon
        icon_label = BodyLabel("📢" if self.channel.chat_type == 'channel' else "👥")
        icon_label.setFixedWidth(30)
        layout.addWidget(icon_label)
        
        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        title = BodyLabel(self.channel.title)
        title.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(title)
        
        subtitle = CaptionLabel(f"{self.channel.video_count} videos")
        info_layout.addWidget(subtitle)
        
        layout.addLayout(info_layout, stretch=1)
        
        # Play button
        play_btn = PushButton("▶️")
        play_btn.setFixedWidth(50)
        play_btn.clicked.connect(lambda: self.clicked.emit(self.channel.chat_id))
        layout.addWidget(play_btn)
        
        # Remove button
        remove_btn = PushButton("✕")
        remove_btn.setFixedWidth(40)
        remove_btn.setStyleSheet("color: #ff6b6b;")
        remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.channel.chat_id))
        layout.addWidget(remove_btn)
        
        self.setCursor(Qt.PointingHandCursor)
    
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(self.channel.chat_id)


class RecentVideoItemWidget(QWidget):
    """Widget for a recent video item in the list."""
    
    clicked = Signal(int, int)  # message_id, chat_id
    delete_clicked = Signal(int, int)  # message_id, chat_id
    
    def __init__(self, video: TelegramVideo, parent=None):
        super().__init__(parent)
        self.video = video
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        # Video icon
        icon_label = BodyLabel("🎬")
        icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)
        
        # Video info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)
        
        # Title (truncated)
        title = self.video.title if len(self.video.title) <= 35 else self.video.title[:32] + "..."
        title_label = BodyLabel(title)
        title_label.setToolTip(self.video.title)
        info_layout.addWidget(title_label)
        
        # Duration and chat
        duration_min = self.video.duration // 60
        duration_sec = self.video.duration % 60
        meta_text = f"{duration_min}:{duration_sec:02d} • {self.video.chat_title}"
        meta_label = CaptionLabel(meta_text)
        meta_label.setStyleSheet("color: #888;")
        info_layout.addWidget(meta_label)
        
        layout.addLayout(info_layout, stretch=1)
        
        # Progress indicator
        if self.video.progress_percent > 0:
            progress_label = CaptionLabel(f"{int(self.video.progress_percent)}%")
            progress_label.setStyleSheet("color: #4CAF50;")
            layout.addWidget(progress_label)
        
        # Delete button
        del_btn = TransparentToolButton(FluentIcon.DELETE)
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(
            self.video.message_id, self.video.chat_id
        ))
        layout.addWidget(del_btn)


class TelegramMainScreen(QWidget):
    """Main Telegram screen with side-by-side layout."""
    
    # Navigation signals
    back_requested = Signal()
    storage_requested = Signal()
    logout_requested = Signal()
    channel_selected = Signal(int)  # chat_id
    video_selected = Signal(int, int)  # message_id, chat_id
    browse_requested = Signal()
    add_favorite_requested = Signal()
    
    def __init__(
        self, 
        favorites_manager: FavoritesManager,
        recent_videos_manager: RecentVideosManager,
        parent=None
    ):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.recent_videos_manager = recent_videos_manager
        self._setup_ui()
    
    def _setup_ui(self):
        # Main horizontal layout (matching home screen)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)
        
        # ========== LEFT SIDE - Favorites ==========
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(16)
        
        # Header
        header = QHBoxLayout()
        
        back_btn = PushButton("← Inicio")
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        
        header.addStretch()
        
        title = SubtitleLabel("✈️ Telegram")
        header.addWidget(title)
        
        header.addStretch()
        
        storage_btn = PushButton("⚙️")
        storage_btn.setToolTip("Almacenamiento")
        storage_btn.clicked.connect(self.storage_requested.emit)
        header.addWidget(storage_btn)
        
        logout_btn = PushButton("🚪")
        logout_btn.setToolTip("Cerrar sesión")
        logout_btn.clicked.connect(self._on_logout_clicked)
        header.addWidget(logout_btn)
        
        left_layout.addLayout(header)
        
        # Favorites section header
        favorites_header = QHBoxLayout()
        favorites_header.addWidget(SubtitleLabel("⭐ Canales y Grupos Favoritos"))
        favorites_header.addStretch()
        
        add_btn = PushButton("+ Agregar")
        add_btn.clicked.connect(self.add_favorite_requested.emit)
        favorites_header.addWidget(add_btn)
        
        left_layout.addLayout(favorites_header)
        
        # Favorites list (scrollable)
        favorites_scroll = ScrollArea()
        favorites_scroll.setWidgetResizable(True)
        favorites_scroll.setFrameShape(QFrame.NoFrame)
        
        favorites_content = QWidget()
        self.favorites_container = QVBoxLayout(favorites_content)
        self.favorites_container.setSpacing(8)
        self.favorites_container.setContentsMargins(0, 0, 0, 0)
        self.favorites_container.addStretch()
        
        favorites_scroll.setWidget(favorites_content)
        left_layout.addWidget(favorites_scroll)
        
        # Browse all button
        browse_btn = PushButton("📂 Explorar todos los chats")
        browse_btn.clicked.connect(self.browse_requested.emit)
        left_layout.addWidget(browse_btn)
        
        # Size policy for left side (expandable like home screen)
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(left_container, stretch=7)
        
        # ========== RIGHT SIDE - Recent Videos (Card like home screen) ==========
        self.right_container = CardWidget()
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        
        # Right header
        right_header = QHBoxLayout()
        right_header.addWidget(SubtitleLabel("📹 Videos Recientes"))
        right_header.addStretch()
        
        clear_btn = TransparentToolButton(FluentIcon.DELETE)
        clear_btn.setToolTip("Limpiar historial")
        clear_btn.clicked.connect(self._on_clear_recent)
        right_header.addWidget(clear_btn)
        
        right_layout.addLayout(right_header)
        
        # Recent videos list
        self.recent_list = ListWidget()
        self.recent_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.recent_list.itemClicked.connect(self._on_recent_item_clicked)
        right_layout.addWidget(self.recent_list)
        
        # Size policy for right side (matching home screen proportions)
        self.right_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        main_layout.addWidget(self.right_container, stretch=3)
    
    def refresh(self):
        """Refresh favorites and recent videos."""
        self._refresh_favorites()
        self._refresh_recent_videos()
    
    def _refresh_favorites(self):
        """Refresh favorites list."""
        # Clear existing (keep the stretch at the end)
        while self.favorites_container.count() > 1:
            item = self.favorites_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add favorites
        favorites = self.favorites_manager.get_favorites()
        
        if not favorites:
            empty_label = CaptionLabel("No hay favoritos. Agrega canales o grupos.")
            self.favorites_container.insertWidget(0, empty_label)
        else:
            for i, favorite in enumerate(favorites):
                card = FavoriteChannelCard(favorite)
                card.clicked.connect(self._on_channel_clicked)
                card.remove_clicked.connect(self._on_remove_favorite)
                self.favorites_container.insertWidget(i, card)
    
    def _refresh_recent_videos(self):
        """Refresh recent videos list."""
        self.recent_list.clear()
        
        videos = self.recent_videos_manager.get_recent(20)
        
        if not videos:
            # Show empty message
            item = QListWidgetItem(self.recent_list)
            item.setText("No hay videos recientes")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        else:
            for video in videos:
                item = QListWidgetItem(self.recent_list)
                item.setData(Qt.UserRole, (video.message_id, video.chat_id))
                
                widget = RecentVideoItemWidget(video)
                widget.clicked.connect(self._on_video_clicked)
                widget.delete_clicked.connect(self._on_remove_recent)
                
                item.setSizeHint(widget.sizeHint())
                self.recent_list.setItemWidget(item, widget)
        
        # Update visibility
        self.right_container.setVisible(len(videos) > 0 or True)  # Always show for now
    
    def _on_channel_clicked(self, chat_id: int):
        """Handle channel click."""
        self.favorites_manager.update_access(chat_id)
        self.channel_selected.emit(chat_id)
    
    def _on_video_clicked(self, message_id: int, chat_id: int):
        """Handle video click."""
        self.video_selected.emit(message_id, chat_id)
    
    def _on_recent_item_clicked(self, item: QListWidgetItem):
        """Handle recent list item click."""
        data = item.data(Qt.UserRole)
        if data:
            message_id, chat_id = data
            self.video_selected.emit(message_id, chat_id)
    
    def _on_remove_favorite(self, chat_id: int):
        """Handle remove favorite click."""
        self.favorites_manager.remove_favorite(chat_id)
        self._refresh_favorites()
        
        InfoBar.success(
            title="Eliminado",
            content="Canal eliminado de favoritos",
            position=InfoBarPosition.TOP,
            parent=self.window()
        )
    
    def _on_remove_recent(self, message_id: int, chat_id: int):
        """Handle remove recent video."""
        self.recent_videos_manager.remove(message_id, chat_id)
        self._refresh_recent_videos()
    
    def _on_clear_recent(self):
        """Clear all recent videos."""
        self.recent_videos_manager.clear_all()
        self._refresh_recent_videos()
        
        InfoBar.info(
            title="Historial limpiado",
            content="Videos recientes eliminados",
            position=InfoBarPosition.TOP,
            parent=self.window()
        )
    
    def _on_logout_clicked(self):
        """Handle logout click with confirmation."""
        # TODO: Add confirmation dialog
        self.logout_requested.emit()
