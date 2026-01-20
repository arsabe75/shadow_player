import sys
import os
import ctypes

# Add project root to sys.path to ensure absolute imports work correctly
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Pre-load MPV DLL before any Qt imports to avoid conflicts
# Check settings first using a minimal JSON read
def _preload_mpv_if_needed():
    import json
    try:
        if sys.platform == 'win32':
            with open("user_data.json", "r") as f:
                data = json.load(f)
                if data.get("player_engine") == "mpv":
                    mpv_path = os.path.abspath("mpv")
                    if os.path.exists(mpv_path):
                        os.environ["PATH"] = mpv_path + os.pathsep + os.environ["PATH"]
                        for dll_name in ["libmpv-2.dll", "mpv-1.dll", "mpv-2.dll"]:
                            dll_path = os.path.join(mpv_path, dll_name)
                            if os.path.exists(dll_path):
                                ctypes.CDLL(dll_path)
                                break
    except (FileNotFoundError, json.JSONDecodeError):
        pass

_preload_mpv_if_needed()

from PySide6.QtWidgets import QApplication
from adapters.player.qt_player import QtPlayer
from adapters.persistence.json_adapter import JsonPersistenceAdapter
from app.services import VideoService
from adapters.ui.main_window import MainWindow

def main():
    if sys.platform == 'linux':
        # Force XCB backend for reliable window embedding (VLC/MPV) on Linux 
        # (especially needed on Wayland systems)
        if "QT_QPA_PLATFORM" not in os.environ:
             os.environ["QT_QPA_PLATFORM"] = "xcb"

    app = QApplication(sys.argv)

    # Composition Root
    persistence_adapter = JsonPersistenceAdapter()
    
    player_engine = "mpv" # FORCED DEBUG
    print(f"DEBUG: Active Player Engine: {player_engine}")
    
    if player_engine == "mpv":
        from adapters.player.mpv_player import MpvPlayer
        player_adapter = MpvPlayer()
    elif player_engine == "vlc":
        from adapters.player.vlc_player import VlcPlayer
        player_adapter = VlcPlayer()
    else:
        player_adapter = QtPlayer()

    video_service = VideoService(player_adapter, persistence_adapter)
    main_window = MainWindow(video_service)

    main_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
