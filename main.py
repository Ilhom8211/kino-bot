import asyncio
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762
DATA_FILE = "movies.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

def load_movies() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_movies(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

MOVIES = load_movies()

@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "Salom! Kino kodini yuboring.\n"
        "Masalan: 1001\n\n"
    )

@dp.message(F.text.startswith("/add"))
async def add_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Siz admin emassiz!")
        return


    code = parts[1].strip()

    if not message.reply_to_message or not message.reply_to_message.video:
        await message.answer("Videoni reply qiling: video yuboring -> reply -> /add 1001")
        return

    file_id = message.reply_to_message.video.file_id
    MOVIES[code] = file_id
    save_movies(MOVIES)

    await message.answer(f"✅ Saqlandi! Kod: {code}\nEndi {code} yozilsa video chiqadi.")

@dp.message(F.text == "/list")
async def list_movies(message: Message):
    if not MOVIES:
        await message.answer("Hali kino yo‘q.")
        return
    text = "🎬 Kinolar:\n" + "\n".join([f"{k}" for k in sorted(MOVIES.keys())])
    await message.answer(text)

@dp.message(F.text)
async def get_movie(message: Message):
    code = message.text.strip()
    file_id = MOVIES.get(code)
    if file_id:
        await bot.send_video(chat_id=message.chat.id, video=file_id)
    else:
        await message.answer("❌ Bunday kod topilmadi.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
