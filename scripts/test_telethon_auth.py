"""
Simple test script to verify Telegram authentication using TELETHON.
Run this directly: python scripts/test_telethon_auth.py
"""
import asyncio
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient, events, errors
from adapters.telegram.config import load_telegram_credentials


async def test_auth():
    """Test Telegram authentication directly using Telethon."""
    print("=== Telegram Auth Test (TELETHON) ===\n")
    
    # Load credentials
    api_id, api_hash = load_telegram_credentials()
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:8]}...")
    
    # Setup working directory
    session_dir = Path.home() / ".shadow_player" / "test_session_telethon"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = str(session_dir / "telethon_test")
    
    print(f"\nSession file: {session_file}")
    
    # Create client
    client = TelegramClient(
        session_file, 
        api_id, 
        api_hash,
        system_version="Windows",
        device_model="Test Script (Telethon)",
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

    # Get phone number from user
    phone = input("Enter your phone number with country code (e.g., +521234567890): ").strip()
    print(f"\nSending code to {phone}...")
    
    try:
        # Send code
        send_code_result = await client.send_code_request(phone)
        
        print("\nrequest sent!")
        print(f"Phone code hash: {send_code_result.phone_code_hash}")
        
        # Check next code type (simplistic check)
        # Telethon doesn't expose 'next_type' as plainly in the return object sometimes
        # but usually sends logic internally.
        
        print("\n" + "="*50)
        print("IMPORTANTE: Revisa tu App de Telegram, SMS o notificaciones.")
        print("="*50 + "\n")

        # Ask for code
        code = input("Enter the code you received: ").strip()
        
        try:
            await client.sign_in(phone, code, phone_code_hash=send_code_result.phone_code_hash)
            print("\n✓ Successfully logged in!")
            
            me = await client.get_me()
            print(f"  - User: {me.first_name} (@{me.username})")
            print(f"  - Phone: {me.phone}")
            
        except errors.SessionPasswordNeededError:
            password = input("\n2FA Password required. Enter password: ").strip()
            await client.sign_in(password=password)
            print("\n✓ Successfully logged in with 2FA!")
            
        except Exception as e:
            print(f"\n✗ Sign in error: {e}")
            
    except Exception as e:
        print(f"\n✗ Error calling send_code_request: {e}")
    
    finally:
        await client.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(test_auth())
