"""
Telegram API credentials configuration.
Loads credentials from environment variables or obfuscated file.
"""
import os
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv


def load_telegram_credentials() -> Tuple[int, str]:
    """
    Load Telegram API credentials.
    
    Priority:
    1. Environment variables (TELEGRAM_API_ID, TELEGRAM_API_HASH)
    2. .env file in project root
    3. Obfuscated credentials file (for distribution)
    
    Returns:
        Tuple of (api_id, api_hash)
        
    Raises:
        ValueError: If credentials not found
    """
    # Try loading from .env file
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
    
    # Check environment variables
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    
    if api_id and api_hash:
        return int(api_id), api_hash
    
    # Fallback to obfuscated credentials (for distribution)
    try:
        from adapters.telegram._credentials import get_credentials
        return get_credentials()
    except ImportError:
        pass
    
    raise ValueError(
        "Telegram credentials not found. "
        "Set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables "
        "or create a .env file. See .env.example for template."
    )


def validate_credentials(api_id: int, api_hash: str) -> bool:
    """
    Basic validation of credential format.
    
    Args:
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        
    Returns:
        True if format appears valid
    """
    # API ID should be a positive integer
    if api_id <= 0:
        return False
    
    # API Hash should be 32 hex characters
    if len(api_hash) != 32:
        return False
    
    try:
        int(api_hash, 16)
    except ValueError:
        return False
    
    return True
