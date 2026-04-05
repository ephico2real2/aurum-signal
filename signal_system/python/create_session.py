import asyncio, os, sys
sys.path.insert(0, '.')
from pathlib import Path
from telethon import TelegramClient

api_id   = int(os.environ['TELEGRAM_API_ID'])
api_hash = os.environ['TELEGRAM_API_HASH']
phone    = os.environ['TELEGRAM_PHONE']

Path("config").mkdir(exist_ok=True)
client = TelegramClient('config/telegram_session', api_id, api_hash)

async def main():
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"Session created OK — logged in as {me.first_name} (@{me.username})")
    await client.disconnect()

asyncio.run(main())
