from telethon import TelegramClient

# Print all client methods containing 'Topic' or 'Forum'
for attr in dir(TelegramClient):
    if 'forum' in attr.lower() or 'topic' in attr.lower():
        print(f"Client method: {attr}")
