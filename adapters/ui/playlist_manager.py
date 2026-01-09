from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, 
    QListWidgetItem, QAbstractItemView, QFrame
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    PushButton, PrimaryPushButton, TitleLabel, SubtitleLabel,
    ListWidget, ToolButton, TransparentToolButton, FluentIcon,
    CardWidget, BodyLabel, LineEdit, CheckBox
)
from domain.models import Video

class PlaylistManagerScreen(QWidget):
    back_clicked = Signal()
    playlist_started = Signal(list, bool) # Emits (list of videos, start_from_beginning)

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.current_videos: list[Video] = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        
        self.back_btn = TransparentToolButton(FluentIcon.LEFT_ARROW)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        header_layout.addWidget(self.back_btn)
        
        title = TitleLabel("Playlist Manager")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)

        # Toolbar
        toolbar = CardWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)

        self.load_btn = PushButton(FluentIcon.FOLDER, "Load Playlist")
        self.load_btn.clicked.connect(self.load_playlist)
        toolbar_layout.addWidget(self.load_btn)

        self.save_btn = PushButton(FluentIcon.SAVE, "Save Playlist")
        self.save_btn.clicked.connect(self.save_playlist)
        toolbar_layout.addWidget(self.save_btn)

        toolbar_layout.addSpacing(20)
        
        self.add_btn = PushButton(FluentIcon.ADD, "Add Videos")
        self.add_btn.clicked.connect(self.add_videos)
        toolbar_layout.addWidget(self.add_btn)

        self.clear_btn = PushButton(FluentIcon.DELETE, "Clear")
        self.clear_btn.clicked.connect(self.clear_list)
        toolbar_layout.addWidget(self.clear_btn)

        toolbar_layout.addStretch()
        
        # Start from Beginning checkbox
        self.start_from_beginning_cb = CheckBox("Start from Beginning")
        self.start_from_beginning_cb.setToolTip("When checked, all videos will start from 0:00 ignoring saved progress")
        toolbar_layout.addWidget(self.start_from_beginning_cb)
        
        toolbar_layout.addSpacing(12)
        
        # Play Button
        self.play_btn = PrimaryPushButton(FluentIcon.PLAY, "Play Now")
        self.play_btn.setFixedSize(140, 36)
        self.play_btn.clicked.connect(self.start_playback)
        toolbar_layout.addWidget(self.play_btn)

        layout.addWidget(toolbar)

        # Main List
        self.list_widget = ListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        
        # Context menu for removing items? 
        # For now just use a remove button or delete key could be added later.
        # Let's add a small helper label
        hint_label = BodyLabel("Drag items to reorder. Double click to play from specific video.")
        hint_label.setTextColor(Qt.gray, Qt.gray)
        layout.addWidget(hint_label)

        layout.addWidget(self.list_widget)

    def add_videos(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Videos", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)"
        )
        if file_paths:
            videos = [Video(path) for path in file_paths]
            self.current_videos.extend(videos)
            self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        for idx, video in enumerate(self.current_videos):
            item = QListWidgetItem(f"{idx + 1}. {video.title}")
            item.setData(Qt.UserRole, video)
            self.list_widget.addItem(item)

    def on_rows_moved(self):
        # Update internal list based on new order
        new_list = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            video = item.data(Qt.UserRole)
            new_list.append(video)
        self.current_videos = new_list
        # Refresh to update numbering
        self.refresh_list()

    def clear_list(self):
        self.current_videos.clear()
        self.refresh_list()

    def save_playlist(self):
        if not self.current_videos:
            return
            
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Playlist", "", "M3U Playlist (*.m3u)"
        )
        if path:
            # En Linux, QFileDialog no agrega la extensión automáticamente
            if not path.lower().endswith('.m3u'):
                path += '.m3u'
            # We temporarily set the service's playlist to save it (or expose a static helper, but service is easier)
            # Actually, `save_playlist_to_file` reads `self.playlist`. 
            # Let's make a temporary helper or slightly modify service method? 
            # Or better, just write the logic here since we have the list.
            # BUT the instruction said "Logic... in VideoService". 
            # So I should use the service.
            
            # Use a temporary swap or better, add a `save_list_to_file` in service?
            # Re-reading my plan: "Writes the current `playlist` videos..." 
            # Okay, let's overload or modify `save_playlist_to_file` to accept a list optionally?
            # Or just write it here to be simple, it's just text writing.
            # I'll stick to using the service to keep logic centralized, but I'll need to 
            # make sure I don't disrupt the *playing* playlist if I'm just manager.
            # Actually, the user might want to save *this* list without playing it.
            # So I will add a static/helper method to service or just implement here.
            # Given the constraints, I will implement it here using clean code, duplicating the trivial write logic 
            # is better than coupling the "playing state" with "editing state".
            
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for video in self.current_videos:
                        f.write(f"#EXTINF:-1,{video.title}\n")
                        f.write(f"{video.path}\n")
            except Exception as e:
                print(f"Error saving playlist: {e}")

    def load_playlist(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Playlist", "", "M3U Playlist (*.m3u)"
        )
        if path:
            # Use service to parse
            videos = self.service.load_playlist_from_file(path)
            if videos:
                self.current_videos = videos
                self.refresh_list()

    def start_playback(self):
        if self.current_videos:
            self.playlist_started.emit(self.current_videos, self.start_from_beginning_cb.isChecked())
