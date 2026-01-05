from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QDialog, 
    QRadioButton, QButtonGroup, QMessageBox, QHBoxLayout, QListWidget, 
    QListWidgetItem, QAbstractItemView, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QAction

class SettingsDialog(QDialog):
    def __init__(self, persistence, on_engine_change=None):
        super().__init__()
        self.persistence = persistence
        self.on_engine_change = on_engine_change
        self.setWindowTitle("Settings")
        self.setFixedSize(300, 200)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Select Video Player Engine:"))
        
        self.group = QButtonGroup(self)
        
        self.radio_qt = QRadioButton("QtMultimedia (Default)")
        self.radio_mpv = QRadioButton("MPV (Advanced)")
        self.radio_vlc = QRadioButton("VLC (Universal)")
        
        self.group.addButton(self.radio_qt)
        self.group.addButton(self.radio_mpv)
        self.group.addButton(self.radio_vlc)
        
        layout.addWidget(self.radio_qt)
        layout.addWidget(self.radio_mpv)
        layout.addWidget(self.radio_vlc)
        
        self.current_engine = self.persistence.load_setting("player_engine", "qt")
        if self.current_engine == "mpv":
            self.radio_mpv.setChecked(True)
        elif self.current_engine == "vlc":
            self.radio_vlc.setChecked(True)
        else:
            self.radio_qt.setChecked(True)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)

    def save_settings(self):
        new_engine = "qt"
        if self.radio_mpv.isChecked():
            new_engine = "mpv"
        elif self.radio_vlc.isChecked():
            new_engine = "vlc"
        
        self.persistence.save_setting("player_engine", new_engine)
        
        if new_engine != self.current_engine and self.on_engine_change:
            self.on_engine_change(new_engine)
            QMessageBox.information(self, "Engine Changed", f"Player engine changed to {new_engine.upper()}.")
        
        self.accept()

class RecentVideoItemWidget(QWidget):
    delete_clicked = Signal()

    def __init__(self, path):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Filename label
        name = path.split("/")[-1].split("\\")[-1]
        self.label = QLabel(name)
        self.label.setToolTip(path)
        layout.addWidget(self.label)
        
        layout.addStretch()
        
        # Delete button
        self.del_btn = QPushButton("X")
        self.del_btn.setFixedSize(20, 20)
        self.del_btn.setStyleSheet("color: red; font-weight: bold;")
        self.del_btn.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.del_btn)

class HomeScreen(QWidget):
    video_selected = Signal(str)
    files_selected = Signal(list)

    def __init__(self, persistence, on_engine_change=None):
        super().__init__()
        self.persistence = persistence
        self.on_engine_change = on_engine_change
        self.setup_ui()
        self.load_recent_videos()

    def setup_ui(self):
        # Main Horizontal Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # LEFT SIDE - Buttons using existing layout style
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setAlignment(Qt.AlignCenter)
        
        self.label = QLabel("Welcome to Shadow Player")
        self.label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        left_layout.addWidget(self.label, alignment=Qt.AlignCenter)

        self.open_button = QPushButton("Open File(s)")
        self.open_button.setFixedSize(200, 50)
        self.open_button.setStyleSheet("font-size: 16px;")
        self.open_button.clicked.connect(self.browse_file)
        left_layout.addWidget(self.open_button, alignment=Qt.AlignCenter)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setFixedSize(200, 50)
        self.settings_button.setStyleSheet("font-size: 16px; margin-top: 10px;")
        self.settings_button.clicked.connect(self.open_settings)
        left_layout.addWidget(self.settings_button, alignment=Qt.AlignCenter)

        # Size Policy for Left Side (Expandable)
        left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(left_container, stretch=7) # 70% width roughly

        # RIGHT SIDE - Recent Videos List
        self.right_container = QWidget()
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title wrapper for right side
        header_layout = QHBoxLayout()
        title_label = QLabel("Recent Videos")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_all_recent)
        header_layout.addWidget(clear_btn)
        
        right_layout.addLayout(header_layout)

        # List Widget
        self.recent_list = QListWidget()
        self.recent_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.recent_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.recent_list.itemClicked.connect(self.on_item_clicked)
        # Handle drop event to save order
        self.recent_list.model().rowsMoved.connect(self.save_recent_order)
        
        right_layout.addWidget(self.recent_list)
        
        # Size Policy for Right Side (Fixed 30% relative to left)
        self.right_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        # Using stretch factor 3 for 30%
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
        # Called when drag-drop finishes
        # Need to wait a tiny bit for model to update or just read items directly
        # QListWidget updates model then emits signal.
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
        # Move to top by re-adding it
        self.add_recent_video(path)
        # Verify file still exists? Optional.
        self.video_selected.emit(path)

    def open_settings(self):
        dialog = SettingsDialog(self.persistence, self.on_engine_change)
        dialog.exec()

    def browse_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Video(s)", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)")
        if file_paths:
            # We treat the first one as "most recent" for the list logic, or add all?
            # Let's add the first one so it appears in recent.
            # Ideally we should start the player with the playlist.
            
            # Add to recent
            for path in reversed(file_paths):
                 self.add_recent_video(path)

            # Signal main window to play these files
            self.files_selected.emit(file_paths)
