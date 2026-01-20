"""
Test script for Telegram QR Code Login using Telethon.
Run this directly: python scripts/test_qr_auth.py
"""
import asyncio
from pathlib import Path
import sys
import qrcode
from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient, events, errors
from adapters.telegram.config import load_telegram_credentials


async def test_qr_auth():
    """Test Telegram QR authentication directly using Telethon."""
    print("=== Telegram QR Auth Test ===\n")
    
    # Load credentials
    api_id, api_hash = load_telegram_credentials()
    print(f"API ID: {api_id}")
    
    # Setup working directory (separate session for test)
    session_dir = Path.home() / ".shadow_player" / "test_session_qr"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = str(session_dir / "telethon_qr_test")
    
    # Create client
    client = TelegramClient(
        session_file, 
        api_id, 
        api_hash,
        system_version="Windows",
        device_model="Shadow Player QR",
        app_version="1.0.0"
    )
    
    print("\nConnecting to Telegram...")
    await client.connect()
    print("Connected!\n")
    
    if await client.is_user_authorized():
        print("✓ Already authorized!")
        me = await client.get_me()
        print(f"  - User: {me.first_name} (@{me.username})")
        await client.disconnect()
        return

    print("Generating QR Login Code...")
    
    try:
        # Initiate QR login
        qr_login = await client.qr_login()
        
        print("\n" + "="*50)
        print("IMPORTANTE: Se abrirá una imagen con el código QR.")
        print("1. Abre Telegram en tu celular.")
        print("2. Ve a Ajustes > Dispositivos > Vincular un dispositivo.")
        print("3. Escanea el código QR.")
        print("="*50 + "\n")
        
        # Generate QR image
        print(f"QR URL: {qr_login.url[:20]}...")
        img = qrcode.make(qr_login.url)
        img_path = session_dir / "login_qr.png"
        img.save(img_path)
        
        # Open image with default viewer
        import os
        os.startfile(img_path)
        
        print("Waiting for scan...")
        
        
        # Wait for login
        try:
            user = await qr_login.wait(timeout=120)  # 2 minutes timeout
        except errors.SessionPasswordNeededError:
            print("\n" + "="*50)
            print("🔐 SE REQUIERE CONTRASEÑA DE VERIFICACIÓN (2FA)")
            print("="*50 + "\n")
            password = input("Ingresa tu contraseña de Telegram (Cloud Password): ").strip()
            user = await client.sign_in(password=password)
        
        print("\n✓ Successfully logged in via QR!")
        print(f"  - User: {user.first_name} (@{user.username})")
        print(f"  - Phone: {user.phone}")
            
    except asyncio.TimeoutError:
        print("\n✗ Timeout: QR code expired or not scanned.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    finally:
        await client.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(test_qr_auth())
