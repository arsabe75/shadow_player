"""
Simple test script to verify Telegram authentication.
Run this directly: python scripts/test_telegram_auth.py
"""
import asyncio
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyrogram import Client
from adapters.telegram.config import load_telegram_credentials


async def test_auth():
    """Test Telegram authentication directly."""
    print("=== Telegram Auth Test ===\n")
    
    # Load credentials
    api_id, api_hash = load_telegram_credentials()
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:8]}...")
    
    # Setup working directory
    workdir = Path.home() / ".shadow_player" / "test_session"
    workdir.mkdir(parents=True, exist_ok=True)
    
    # Create client
    client = Client(
        name="telegram_test",
        api_id=api_id,
        api_hash=api_hash,
        workdir=str(workdir),
        app_version="1.0.0",
        device_model="Test Script",
        system_version="Windows"
    )
    
    print("\nConnecting to Telegram...")
    await client.connect()
    print("Connected!\n")
    
    # Get phone number from user
    phone = input("Enter your phone number with country code (e.g., +521234567890): ").strip()
    print(f"\nSending code to {phone}...")
    print("(Trying with force_sms=True to send via SMS)")
    
    try:
        # First try normally
        sent_code = await client.send_code(phone)
        
        # If type is APP, try to resend via SMS
        # If type is APP, warn the user and attempt resend after delay
        if "APP" in str(sent_code.type):
            print("\n" + "="*50)
            print("IMPORTANTE: El código fue enviado a tu APLICACIÓN de Telegram.")
            print("Por favor revisa tus chats en el celular o PC (chat 'Telegram' o 'Service Notifications').")
            print("="*50 + "\n")
            
            print("Intentaremos reenviar por SMS en 60 segundos si no lo encuentras...")
            try:
                # Wait loop
                for i in range(60, 0, -1):
                    print(f"Esperando {i}s para solicitar SMS...  ", end="\r")
                    await asyncio.sleep(1)
                print("\nSolicitando envío por SMS...")
                
                sent_code = await client.resend_code(phone, sent_code.phone_code_hash)
                print(f"\n✓ SMS Solicitado. Nuevo tipo: {sent_code.type}")
            except Exception as e:
                print(f"\nNo se pudo enviar SMS (Telegram dice: {e})")
                print("Intenta usar el código enviado a la APP.")
        
        print(f"\n✓ Estado del código:")
        print(f"  - Hash: {sent_code.phone_code_hash}")
        print(f"  - Tipo: {sent_code.type}")
        print(f"  - Timeout: {getattr(sent_code, 'timeout', 'N/A')}")
        
        # Ask for code
        code = input("\nEnter the code you received: ").strip()
        
        try:
            await client.sign_in(phone, sent_code.phone_code_hash, code)
            print("\n✓ Successfully logged in!")
            
            me = await client.get_me()
            print(f"  - User: {me.first_name} (@{me.username})")
            print(f"  - Phone: {me.phone_number}")
            
        except Exception as e:
            if "SESSION_PASSWORD_NEEDED" in str(e):
                password = input("\n2FA Password required. Enter password: ").strip()
                await client.check_password(password)
                print("\n✓ Successfully logged in with 2FA!")
            else:
                print(f"\n✗ Sign in error: {e}")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    finally:
        await client.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(test_auth())
