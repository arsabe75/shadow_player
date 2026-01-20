"""
Screen for browsing all Telegram chats and channels.
"""
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidgetItem,
    QLabel, QFrame
)
from qfluentwidgets import (
    PushButton, SubtitleLabel, BodyLabel, CaptionLabel,
    ListWidget, SearchLineEdit, ProgressRing, CardWidget,
    InfoBar, InfoBarPosition
)

from adapters.telegram.tdlib_client import TDLibClient

class TelegramBrowseScreen(QWidget):
    """Screen to browse and search Telegram chats."""
    
    back_requested = Signal()
    chat_selected = Signal(object)  # chat_id (object to handle 64-bit int)
    
    def __init__(self, tdlib_client: TDLibClient, parent=None):
        super().__init__(parent)
        self.tdlib_client = tdlib_client
        self.chats = []
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        
        back_btn = PushButton("← Atrás")
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        
        header.addStretch()
        title = SubtitleLabel("Explorar Chats")
        header.addWidget(title)
        header.addStretch()
        
        layout.addLayout(header)
        
        # Search bar
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("Buscar chats...")
        self.search_bar.textChanged.connect(self._filter_chats)
        layout.addWidget(self.search_bar)
        
        # List
        self.list_widget = ListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)
        
        # Loading indicator
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("background-color: transparent;")
        self.loading_overlay.hide()
        
        loading_layout = QVBoxLayout(self.loading_overlay)
        loading_layout.setAlignment(Qt.AlignCenter)
        
        # Use IndeterminateProgressRing for loading spinner
        from qfluentwidgets import IndeterminateProgressRing
        self.spinner = IndeterminateProgressRing()
        loading_layout.addWidget(self.spinner)
        loading_layout.addWidget(BodyLabel("Cargando chats..."))
        
    def resizeEvent(self, event):
        self.loading_overlay.resize(self.size())
        super().resizeEvent(event)
        
    def load_chats(self):
        """Load chats from Telegram."""
        self.loading_overlay.show()
        # self.spinner.start() # Not needed for IndeterminateProgressRing, handled by visibility or automatic
        self.list_widget.clear()
        
        from adapters.telegram.async_worker import get_telegram_worker, TelegramOp
        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.GET_CHATS,
            self._on_chats_loaded,
            limit=100
        )
        
    def _on_chats_loaded(self, success, result):
        if success:
            self.show_chats(result)
        else:
            self.loading_overlay.hide()
            # self.spinner.stop()
            InfoBar.error(
                title="Error",
                content=f"No se pudieron cargar los chats: {result}",
                parent=self,
                position=InfoBarPosition.TOP
            )

    def show_chats(self, chats):
        """Display loaded chats."""
        self.chats = chats
        self._filter_chats("")
        self.loading_overlay.hide()
        # self.spinner.stop()
        
    def _filter_chats(self, text):
        """Filter displayed chats."""
        if not self.chats:
            return
            
        self.list_widget.clear()
        search_text = text.lower().strip()
        
        for chat in self.chats:
            title = getattr(chat, 'title', 'Unknown')
            if search_text and search_text not in title.lower():
                continue
                
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.UserRole, chat.id)
            
            # Custom widget for item
            widget = QWidget()
            h_layout = QHBoxLayout(widget)
            h_layout.setContentsMargins(10, 5, 10, 5)
            
            # Icon placeholder
            icon = BodyLabel("📢" if getattr(chat, 'broadcast', False) else "👥")
            h_layout.addWidget(icon)
            
            # Title
            name = BodyLabel(title)
            h_layout.addWidget(name)
            h_layout.addStretch()
            
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)

    def _on_item_clicked(self, item):
        chat_id = item.data(Qt.UserRole)
        # Find the chat object
        chat = next((c for c in self.chats if c.id == chat_id), None)
        if chat:
            self.chat_selected.emit(chat)
