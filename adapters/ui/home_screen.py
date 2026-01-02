from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QDialog, QRadioButton, QButtonGroup, QMessageBox
from PySide6.QtCore import Qt, Signal
from domain.ports import PersistencePort

class SettingsDialog(QDialog):
    def __init__(self, persistence: PersistencePort, on_engine_change=None):
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

class HomeScreen(QWidget):
    video_selected = Signal(str)

    def __init__(self, persistence: PersistencePort, on_engine_change=None):
        super().__init__()
        self.persistence = persistence
        self.on_engine_change = on_engine_change
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel("Welcome to Shadow Player")
        self.label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(self.label, alignment=Qt.AlignCenter)

        self.open_button = QPushButton("Open File")
        self.open_button.setFixedSize(200, 50)
        self.open_button.setStyleSheet("font-size: 16px;")
        self.open_button.clicked.connect(self.browse_file)
        layout.addWidget(self.open_button, alignment=Qt.AlignCenter)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setFixedSize(200, 50)
        self.settings_button.setStyleSheet("font-size: 16px; margin-top: 10px;")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button, alignment=Qt.AlignCenter)

    def open_settings(self):
        dialog = SettingsDialog(self.persistence, self.on_engine_change)
        dialog.exec()

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv)")
        if file_path:
            self.video_selected.emit(file_path)
