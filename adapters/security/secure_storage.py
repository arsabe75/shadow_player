"""
Secure storage for Shadow Player using OS keyring and Fernet encryption.
Cross-platform: Windows (DPAPI), Linux (Secret Service), macOS (Keychain).
"""
import json
import base64
import secrets
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
import keyring
from keyring.errors import PasswordDeleteError


class SecureStorage:
    """Cross-platform secure storage using OS keyring + Fernet encryption."""
    
    SERVICE_NAME = "ShadowPlayer"
    
    def __init__(self, data_dir: Path):
        """
        Initialize secure storage.
        
        Args:
            data_dir: Directory for encrypted data files
        """
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._fernet: Fernet | None = None
    
    @property
    def fernet(self) -> Fernet:
        """Get or create Fernet instance with key from OS keyring."""
        if self._fernet is None:
            key = self._get_or_create_master_key()
            self._fernet = Fernet(key)
        return self._fernet
    
    def _get_or_create_master_key(self) -> bytes:
        """Get master key from OS keyring or create new one."""
        key = keyring.get_password(self.SERVICE_NAME, "master_key")
        
        if key is None:
            # First run: generate new key
            key = Fernet.generate_key().decode()
            keyring.set_password(self.SERVICE_NAME, "master_key", key)
        
        return key.encode()
    
    def get_or_create_encryption_key(self, purpose: str) -> bytes:
        """
        Generate or retrieve a purpose-specific encryption key.
        
        Args:
            purpose: Key identifier (e.g., 'tdlib_db', 'user_config')
            
        Returns:
            Base64-encoded 32-byte key
        """
        key_name = f"key_{purpose}"
        stored = keyring.get_password(self.SERVICE_NAME, key_name)
        
        if stored is None:
            # Generate 32-byte key encoded as base64
            raw_key = secrets.token_bytes(32)
            stored = base64.b64encode(raw_key).decode()
            keyring.set_password(self.SERVICE_NAME, key_name, stored)
        
        return stored.encode()
    
    def save_encrypted(self, filename: str, data: dict[str, Any]) -> None:
        """
        Save data encrypted to file.
        
        Args:
            filename: Name without extension (e.g., 'user_config')
            data: Dictionary to encrypt and save
        """
        json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        encrypted = self.fernet.encrypt(json_data)
        
        filepath = self.data_dir / f"{filename}.enc"
        filepath.write_bytes(encrypted)
    
    def load_encrypted(self, filename: str) -> dict[str, Any] | None:
        """
        Load and decrypt data from file.
        
        Args:
            filename: Name without extension
            
        Returns:
            Decrypted dictionary or None if file doesn't exist
        """
        filepath = self.data_dir / f"{filename}.enc"
        
        if not filepath.exists():
            return None
        
        try:
            encrypted = filepath.read_bytes()
            decrypted = self.fernet.decrypt(encrypted)
            return json.loads(decrypted.decode('utf-8'))
        except Exception:
            # Corrupted or invalid file
            return None
    
    def delete_encrypted(self, filename: str) -> bool:
        """
        Delete an encrypted file.
        
        Args:
            filename: Name without extension
            
        Returns:
            True if deleted, False if didn't exist
        """
        filepath = self.data_dir / f"{filename}.enc"
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    
    def delete_all(self) -> None:
        """Delete all encrypted data and keys (for logout/reset)."""
        # Delete all encrypted files
        for enc_file in self.data_dir.glob("*.enc"):
            try:
                enc_file.unlink()
            except Exception:
                pass
        
        # Delete keys from keyring
        keys_to_delete = [
            "master_key",
            "key_tdlib_db",
            "key_user_config",
            "key_favorites",
            "key_recent_videos"
        ]
        
        for key_name in keys_to_delete:
            try:
                keyring.delete_password(self.SERVICE_NAME, key_name)
            except PasswordDeleteError:
                pass  # Key doesn't exist
    
    def has_stored_data(self) -> bool:
        """Check if any encrypted data exists."""
        return any(self.data_dir.glob("*.enc"))
