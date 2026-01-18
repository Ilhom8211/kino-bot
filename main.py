import asyncio
import json
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

# ====== CONFIG ======
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762  # <-- shu yerga o'zingizni Telegram ID raqam qilib yozing
DATA_FILE = "movies.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====== STORAGE ======
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

# ====== HELPERS ======
def is_admin(message: Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID

# ====== BOT HANDLERS ======
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "Salom! Kino kodini yuboring.\n"
        "Masalan: 1001\n\n"
        "Admin uchun: videoga reply qilib /add 1001"
    )

@dp.message(F.text.startswith("/add"))
async def add_movie(message: Message):
    # faqat admin qo'sha olsin
    if not is_admin(message):
        await message.answer("❌ Siz admin emassiz.")
        return

    # /add 1001 -> kodni ajratib olish
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗ To‘g‘ri yozing: videoga reply qilib `/add 1001`")
        return
    code = parts[1].strip()

    # reply bo'lishi shart
    if not message.reply_to_message:
        await message.answer("❗ Videoga reply qiling, keyin `/add 1001` yozing.")
        return

    # reply qilingan xabarda video borligini tekshiramiz
    video = message.reply_to_message.video
    if not video:
        await message.answer("❗ Siz videoga reply qilishingiz kerak.")
        return

    MOVIES[code] = video.file_id
    save_movies(MOVIES)
    await message.answer(f"✅ Qo‘shildi! Kod: {code}")

@dp.message(F.text == "/list")
async def list_movies(message: Message):
    if not MOVIES:
        await message.answer("Hali kino yo‘q.")
        return
    text = "🎬 Kinolar:\n" + "\n".join(sorted(MOVIES.keys()))
    await message.answer(text)

@dp.message(F.text)
async def get_movie(message: Message):
    code = message.text.strip()
    file_id = MOVIES.get(code)
    if file_id:
        await bot.send_video(chat_id=message.chat.id, video=file_id)
    else:
        await message.answer("❌ Bunday kod topilmadi.")

# ====== RENDER PORT (WEB SERVICE uchun) ======
async def handle_root(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ====== MAIN ======
async def main():
    await start_web_server()   # Render port ko'rsin
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
