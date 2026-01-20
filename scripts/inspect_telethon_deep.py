from telethon import TelegramClient, version
from telethon.tl import functions
import importlib

print(f"Telethon Version: {version.__version__}")

found = False

# Iterate over all submodules in functions
import pkgutil
package = functions
for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
    try:
        module = importlib.import_module(f"telethon.tl.functions.{modname}")
        for attr in dir(module):
            if 'Forum' in attr or 'Topic' in attr:
                print(f"Found {attr} in telethon.tl.functions.{modname}")
                if 'GetForumTopics' in attr:
                    found = True
    except Exception as e:
        pass

if not found:
    print("GetForumTopicsRequest technically not found via scan.")
