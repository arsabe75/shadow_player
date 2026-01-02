import json
import os
from domain.ports import PersistencePort
from typing import Any

class JsonPersistenceAdapter(PersistencePort):
    def __init__(self, file_path: str = "user_data.json"):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                json.dump({}, f)

    def _load_data(self) -> dict:
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_data(self, data: dict):
        with open(self.file_path, 'w') as f:
            json.dump(data, f, indent=4)

    def save_progress(self, path: str, position: int):
        data = self._load_data()
        data[path] = position
        self._save_data(data)

    def load_progress(self, path: str) -> int:
        data = self._load_data()
        return data.get(path, 0)

    def save_setting(self, key: str, value: Any):
        data = self._load_data()
        data[key] = value
        self._save_data(data)

    def load_setting(self, key: str, default: Any = None) -> Any:
        data = self._load_data()
        return data.get(key, default)
