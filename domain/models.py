from dataclasses import dataclass
import os
from enum import Enum, auto

class PlaybackState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()

class MediaStatus(Enum):
    NO_MEDIA = auto()
    LOADING = auto()
    LOADED = auto()
    BUFFERING = auto()
    End = auto() # End of media
    ERROR = auto()

@dataclass
class Video:
    path: str
    title: str = ""

    def __post_init__(self):
        if not self.title:
            self.title = os.path.basename(self.path)
