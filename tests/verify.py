import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer
from domain.ports import PersistencePort
from domain.models import PlaybackState, MediaStatus
from adapters.player.vlc_player import VlcPlayer
from app.services import VideoService

# Mock Persistence
class MockPersistence(PersistencePort):
    def save_progress(self, path, position):
        print(f"MockPersistence: Saving {path} at {position}")
    def load_progress(self, path):
        return 0
    def save_setting(self, key, value):
        pass
    def load_setting(self, key, default=None):
        return default

def verify():
    app = QCoreApplication(sys.argv)
    
    print("Initializing components...")
    try:
        player = VlcPlayer()
        print("VLC Player initialized successfully.")
    except Exception as e:
        print(f"ERROR initializing VLC: {e}")
        return

    service = VideoService(player, MockPersistence())
    
    # Verify signals
    def on_playback_state(state):
        print(f"SIGNAL: PlaybackState -> {state}")
        
    def on_media_status(status):
        print(f"SIGNAL: MediaStatus -> {status}")
        
    def on_error(msg):
        print(f"SIGNAL: Error -> {msg}")
        QTimer.singleShot(100, app.quit) # Exit on error
        
    service.playback_state_changed.connect(on_playback_state)
    service.media_status_changed.connect(on_media_status)
    service.error_occurred.connect(on_error)
    
    print("Starting test...")
    # Try to load a missing file to trigger error
    service.open_video("missing_file.mp4")
    
    # Set a timeout to quit if no signal
    QTimer.singleShot(3000, lambda: (print("Timeout!"), app.quit()))
    
    sys.exit(app.exec())

if __name__ == "__main__":
    verify()
