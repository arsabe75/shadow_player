from telethon import TelegramClient, version
from telethon.tl.functions import channels

print(f"Telethon Version: {version.__version__}")

if hasattr(channels, 'GetForumTopicsRequest'):
    print("GetForumTopicsRequest FOUND")
else:
    print("GetForumTopicsRequest NOT FOUND")
    print("Available attributes in telethon.tl.functions.channels:")
    # Print only those containing 'Forum' or 'Topic' to avoid spam
    for attr in dir(channels):
        if 'Forum' in attr or 'Topic' in attr:
            print(f" - {attr}")
