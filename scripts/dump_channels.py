from telethon.tl.functions import channels
with open('channels_dir.txt', 'w') as f:
    for attr in dir(channels):
        f.write(f"{attr}\n")
