"""
Screen for listing videos from a specific Telegram chat.
"""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidgetItem,
    QLabel, QFrame
)
from qfluentwidgets import (
    PushButton, SubtitleLabel, BodyLabel, ListWidget,
    IndeterminateProgressRing, InfoBar, InfoBarPosition,
    CaptionLabel
)

# We can reuse the item widget from MainScreen for now, or redefine a simple one.
# To avoid circular imports if MainScreen is complex, let's define a simple one here 
# or import it if safe. MainScreen imports are usually heavy.
# Let's verify if we can import RecentVideoItemWidget from adapters.ui.telegram.telegram_main_screen
# It might cause circular import if main_screen imports something that eventually imports this.
# MainWindow imports both.
# Let's assume we can try importing, if not we define a local simple one.

try:
    from adapters.ui.telegram.telegram_main_screen import RecentVideoItemWidget
except ImportError:
    # Fallback definition if import fails (UI logic)
    class RecentVideoItemWidget(QWidget):
        clicked = Signal(object, object)
        delete_clicked = Signal(object, object) # Not used here but expected by interface
        def __init__(self, video, parent=None):
            super().__init__(parent)
            l = QHBoxLayout(self)
            l.addWidget(BodyLabel(getattr(video, 'message', 'Video')))
            # Simple fallback

from adapters.telegram.async_worker import get_telegram_worker, TelegramOp

class TelegramVideoListScreen(QWidget):
    """Screen to show videos from a chat."""
    
    back_requested = Signal()
    video_selected = Signal(object, object) # message_id, chat_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_id = None
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        
        self.back_btn = PushButton("← Atrás")
        self.back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_btn)
        
        header.addStretch()
        self.title_label = SubtitleLabel("Videos")
        header.addWidget(self.title_label)
        header.addStretch()
        
        layout.addLayout(header)
        
        # List
        self.list_widget = ListWidget()
        # Item clicked handling is usually done via the widget inside the item for buttons,
        # or itemClicked signal.
        # RecentVideoItemWidget has its own signals.
        layout.addWidget(self.list_widget)
        
        # Loading indicator
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("background-color: transparent;")
        self.loading_overlay.hide()
        
        loading_layout = QVBoxLayout(self.loading_overlay)
        loading_layout.setAlignment(Qt.AlignCenter)
        
        self.spinner = IndeterminateProgressRing()
        loading_layout.addWidget(self.spinner)
        loading_layout.addWidget(BodyLabel("Cargando videos..."))
        
    def resizeEvent(self, event):
        self.loading_overlay.resize(self.size())
        super().resizeEvent(event)
        
    def load_videos(self, chat_id, title="Videos", thread_id=None):
        """Load videos for a chat."""
        self.chat_id = chat_id
        self.title_label.setText(title)
        
        self.loading_overlay.show()
        self.list_widget.clear()
        
        worker = get_telegram_worker()
        worker.execute(
            TelegramOp.GET_CHAT_HISTORY,
            self._on_videos_loaded,
            chat_id=chat_id,
            limit=50,
            thread_id=thread_id
        )
        
    def _on_videos_loaded(self, success, result):
        self.loading_overlay.hide()
        if success:
            self.show_videos(result)
        else:
            InfoBar.error(
                title="Error",
                content=f"No se pudieron cargar los videos: {result}",
                parent=self,
                position=InfoBarPosition.TOP
            )
            
    def show_videos(self, videos):
        if not videos:
            InfoBar.info(
                title="Vacío",
                content="No se encontraron videos en este chat.",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
            
        # We need a wrapper for the raw Telethon message to match what RecentVideoItemWidget expects
        # TelegramMainScreen uses TelegramVideo dataclass usually.
        # Let's look at what RecentVideoItemWidget expects: .video object with title, duration etc.
        # It's better to duplicate a simple VideoItemWidget here tailored for Telethon messages
        # OR adapt the messages. 
        # For speed/robustness, I'll define a simple local widget that handles Telethon messages directly.
        
        self.list_widget.clear()
        for msg in videos:
            item = QListWidgetItem(self.list_widget)
            
            # Create widget
            widget = VideoItemWidget(msg)
            widget.clicked.connect(self._on_video_clicked)
            
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)
            
    def _on_video_clicked(self, message_id, chat_id):
        self.video_selected.emit(message_id, chat_id)


class VideoItemWidget(QWidget):
    """Simple widget for video item."""
    clicked = Signal(object, object) # message_id, chat_id
    
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.message = message
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Icon
        layout.addWidget(BodyLabel("🎬"))
        
        # Info
        info_layout = QVBoxLayout()
        
        # Try to get text/caption or file name
        text = self.message.message or "Video sin título"
        if not text and hasattr(self.message, 'file'):
             text = getattr(self.message.file, 'name', 'Video')
             
        title_label = BodyLabel(text[:50] + "..." if len(text) > 50 else text)
        info_layout.addWidget(title_label)
        
        # Duration/Size if available
        meta = []
        duration = None
        
        # Try to find duration in document attributes
        if hasattr(self.message, 'document') and self.message.document:
            for attr in getattr(self.message.document, 'attributes', []):
                if hasattr(attr, 'duration'):
                    duration = int(attr.duration)
                    break
        
        if duration is not None:
             meta.append(f"{duration // 60}:{duration % 60:02d}")
        
        date_str = self.message.date.strftime("%d/%m/%Y %H:%M")
        meta.append(date_str)
        
        info_layout.addWidget(CaptionLabel(" • ".join(meta)))
        
        layout.addLayout(info_layout, stretch=1)
        
        # Play btn
        play_btn = PushButton("▶️ Reproducir")
        play_btn.clicked.connect(lambda: self.clicked.emit(self.message, self.message.chat_id))
        layout.addWidget(play_btn)
