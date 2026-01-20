from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFileDialog, QHBoxLayout, 
    QListWidgetItem, QAbstractItemView, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QAction
from qfluentwidgets import (
    PushButton, PrimaryPushButton, TitleLabel, BodyLabel, SubtitleLabel,
    ListWidget, RadioButton, MessageBox, InfoBar, InfoBarPosition,
    CardWidget, FluentIcon, TransparentToolButton
)

class SettingsDialog(MessageBox):
    def __init__(self, persistence, on_engine_change=None, parent=None):
        super().__init__(
            title="Settings",
            content="Select Video Player Engine:",
            parent=parent
        )
        self.persistence = persistence
        self.on_engine_change = on_engine_change
        self.setup_ui()

    def setup_ui(self):
        # Rename default buttons to Save and Cancel
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")
        
        # Radio buttons for engine selection
        self.radio_qt = RadioButton("QtMultimedia (Default)")
        self.radio_mpv = RadioButton("MPV (Advanced)")
        self.radio_vlc = RadioButton("VLC (Universal)")
        
        # Add to the text layout
        self.textLayout.addWidget(self.radio_qt)
        self.textLayout.addWidget(self.radio_mpv)
        self.textLayout.addWidget(self.radio_vlc)
        
        # Load current setting
        self.current_engine = self.persistence.load_setting("player_engine", "qt")
        if self.current_engine == "mpv":
            self.radio_mpv.setChecked(True)
        elif self.current_engine == "vlc":
            self.radio_vlc.setChecked(True)
        else:
            self.radio_qt.setChecked(True)
        
        # Connect save button
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self.save_settings)

    def save_settings(self):
        # Prevent double execution
        if hasattr(self, '_saving') and self._saving:
            return
        self._saving = True
        
        new_engine = "qt"
        if self.radio_mpv.isChecked():
            new_engine = "mpv"
        elif self.radio_vlc.isChecked():
            new_engine = "vlc"
        
        self.persistence.save_setting("player_engine", new_engine)
        
        if new_engine != self.current_engine and self.on_engine_change:
            self.on_engine_change(new_engine)
        
        self.accept()

class RecentVideoItemWidget(QWidget):
    delete_clicked = Signal()

    def __init__(self, path):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        # Filename label
        name = path.split("/")[-1].split("\\")[-1]
        self.label = BodyLabel(name)
        self.label.setToolTip(path)
        layout.addWidget(self.label)
        
        layout.addStretch()
        
        # Delete button with Fluent icon
        self.del_btn = TransparentToolButton(FluentIcon.DELETE)
        self.del_btn.setFixedSize(24, 24)
        self.del_btn.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.del_btn)

class HomeScreen(QWidget):
    video_selected = Signal(str)
    files_selected = Signal(list)
    lists_clicked = Signal()
    telegram_clicked = Signal()  # Navigate to Telegram screen

    def __init__(self, persistence, on_engine_change=None):
        super().__init__()
        self.persistence = persistence
        self.on_engine_change = on_engine_change
        self.setup_ui()
        self.load_recent_videos()

    def setup_ui(self):
        # Main Horizontal Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        # LEFT SIDE - Buttons
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setAlignment(Qt.AlignCenter)
        left_layout.setSpacing(16)
        
        self.label = TitleLabel("Welcome to Shadow Player")
        self.label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.label)
        
        left_layout.addSpacing(20)

        left_layout.addSpacing(20)

        # File Operations Container
        files_layout = QHBoxLayout()
        files_layout.setSpacing(4)

        self.open_button = PrimaryPushButton(FluentIcon.FOLDER, "Local Files")
        self.open_button.setFixedSize(160, 50)
        self.open_button.clicked.connect(self.browse_file)
        files_layout.addWidget(self.open_button)

        self.lists_button = PushButton(FluentIcon.LIBRARY, "Lists")
        self.lists_button.setFixedSize(80, 50)
        self.lists_button.clicked.connect(self.lists_clicked.emit)
        files_layout.addWidget(self.lists_button)

        # Center the button group
        button_container = QWidget()
        button_container.setLayout(files_layout)
        button_container.setFixedWidth(250)
        
        left_layout.addWidget(button_container, alignment=Qt.AlignCenter)

        # Telegram button
        self.telegram_button = PushButton("✈️ Telegram")
        self.telegram_button.setFixedSize(250, 50)
        self.telegram_button.clicked.connect(self.telegram_clicked.emit)
        left_layout.addWidget(self.telegram_button, alignment=Qt.AlignCenter)

        self.settings_button = PushButton(FluentIcon.SETTING, "Settings")
        self.settings_button.setFixedSize(250, 50)
        self.settings_button.clicked.connect(self.open_settings)
        left_layout.addWidget(self.settings_button, alignment=Qt.AlignCenter)

        # Size Policy for Left Side (Expandable)
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(left_container, stretch=7)

        # RIGHT SIDE - Recent Videos List in a Card
        self.right_container = CardWidget()
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        
        # Title wrapper for right side
        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("Recent Videos")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        clear_btn = TransparentToolButton(FluentIcon.DELETE)
        clear_btn.setToolTip("Clear All")
        clear_btn.clicked.connect(self.clear_all_recent)
        header_layout.addWidget(clear_btn)
        
        right_layout.addLayout(header_layout)

        # Fluent List Widget
        self.recent_list = ListWidget()
        self.recent_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.recent_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.recent_list.itemClicked.connect(self.on_item_clicked)
        self.recent_list.model().rowsMoved.connect(self.save_recent_order)
        
        right_layout.addWidget(self.recent_list)
        
        # Size Policy for Right Side
        self.right_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        main_layout.addWidget(self.right_container, stretch=3)

    def load_recent_videos(self):
        self.recent_list.clear()
        paths = self.persistence.get_recent_videos()
        for path in paths:
            self.add_item_to_list(path)
        self.update_list_visibility()

    def update_list_visibility(self):
        has_items = self.recent_list.count() > 0
        self.right_container.setVisible(has_items)

    def add_item_to_list(self, path):
        item = QListWidgetItem(self.recent_list)
        item.setData(Qt.UserRole, path)
        
        # Custom widget for item
        widget = RecentVideoItemWidget(path)
        widget.delete_clicked.connect(lambda: self.remove_recent_video(item))
        
        item.setSizeHint(widget.sizeHint())
        self.recent_list.setItemWidget(item, widget)

    def add_recent_video(self, path):
        # Check if already exists, move to top if so
        videos = self.get_current_list_paths()
        if path in videos:
            videos.remove(path)
        videos.insert(0, path)
        
        # Limit size
        if len(videos) > 50:
            videos = videos[:50]
            
        self.persistence.save_recent_videos(videos)
        self.load_recent_videos()

    def get_current_list_paths(self):
        paths = []
        for i in range(self.recent_list.count()):
            item = self.recent_list.item(i)
            paths.append(item.data(Qt.UserRole))
        return paths

    def save_recent_order(self):
        paths = self.get_current_list_paths()
        self.persistence.save_recent_videos(paths)

    def remove_recent_video(self, item):
        row = self.recent_list.row(item)
        self.recent_list.takeItem(row)
        self.save_recent_order()
        self.update_list_visibility()

    def clear_all_recent(self):
        self.recent_list.clear()
        self.persistence.save_recent_videos([])
        self.update_list_visibility()

    def on_item_clicked(self, item):
        path = item.data(Qt.UserRole)
        self.add_recent_video(path)
        self.video_selected.emit(path)

    def open_settings(self):
        dialog = SettingsDialog(self.persistence, self.on_engine_change, self)
        dialog.exec()

    def browse_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Video(s)", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)")
        if file_paths:
            for path in reversed(file_paths):
                 self.add_recent_video(path)
            self.files_selected.emit(file_paths)
