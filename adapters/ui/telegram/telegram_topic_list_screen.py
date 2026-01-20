"""
Screen for listing topics (threads) in a Telegram Forum.
"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidgetItem,
    QLabel, QFrame
)
from qfluentwidgets import (
    PushButton, SubtitleLabel, BodyLabel, ListWidget,
    IndeterminateProgressRing, InfoBar, InfoBarPosition,
    CardWidget
)

from adapters.telegram.async_worker import get_telegram_worker, TelegramOp

class TelegramTopicListScreen(QWidget):
    """Screen to browse topics in a forum."""
    
    back_requested = Signal()
    topic_selected = Signal(object, object)  # chat_id, thread_id (topic id)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat = None
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
        self.title_label = SubtitleLabel("Topics")
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)
        
        # List
        self.list_widget = ListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)
        
        # Loading
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("background-color: transparent;")
        self.loading_overlay.hide()
        
        l_layout = QVBoxLayout(self.loading_overlay)
        l_layout.setAlignment(Qt.AlignCenter)
        self.spinner = IndeterminateProgressRing()
        l_layout.addWidget(self.spinner)
        l_layout.addWidget(BodyLabel("Cargando topics..."))
        
    def resizeEvent(self, event):
        self.loading_overlay.resize(self.size())
        super().resizeEvent(event)
        
    def load_topics(self, chat):
        """Load topics for a forum chat."""
        self.chat = chat
        self.title_label.setText(getattr(chat, 'title', 'Topics'))
        
        self.loading_overlay.show()
        self.list_widget.clear()
        
        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.GET_FORUM_TOPICS,
            self._on_topics_loaded,
            chat_id=chat.id
        )
        
    def _on_topics_loaded(self, success, result):
        self.loading_overlay.hide()
        if success:
            self.show_topics(result)
        else:
            InfoBar.error(
                title="Error",
                content=f"No se pudieron cargar los topics: {result}",
                parent=self,
                position=InfoBarPosition.TOP
            )
            
    def show_topics(self, topics):
        if not topics:
             InfoBar.info("Vacío", "No hay topics encontrados", parent=self)
             return
             
        for topic in topics:
            item = QListWidgetItem(self.list_widget)
            # Store thread_id (id of the top message of the topic)
            item.setData(Qt.UserRole, topic.id)
            
            # Simple item widget
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(10, 10, 10, 10)
            
            icon = BodyLabel(getattr(topic, 'icon_emoji_id', '') or "💬")
            layout.addWidget(icon)
            
            title = BodyLabel(getattr(topic, 'title', 'Topic sin título'))
            layout.addWidget(title)
            layout.addStretch()
            
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)
            
    def _on_item_clicked(self, item):
        topic_id = item.data(Qt.UserRole)
        # Pass chat_id and topic_id (thread_id)
        if self.chat:
            self.topic_selected.emit(self.chat.id, topic_id)
