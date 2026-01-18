import asyncio
import json
import os
from typing import Dict, Any

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762  # <-- SHUNI O'Z ID'ingizga qo'ying (son bo'lsin!)
DATA_FILE = "movies.json"

# --- BOT ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- STORAGE ---
def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {
            "movies": {},         # code -> file_id
            "users": {},          # user_id -> count
            "requests": {},       # code -> count
            "channel_id": None,   # -100...
            "channel_title": None
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "movies": {},
            "users": {},
            "requests": {},
            "channel_id": None,
            "channel_title": None
        }

def save_data(data: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

DB = load_data()

def is_admin(message: Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID

def inc_user(user_id: int):
    DB["users"][str(user_id)] = DB["users"].get(str(user_id), 0) + 1
    save_data(DB)

def inc_code(code: str):
    DB["requests"][code] = DB["requests"].get(code, 0) + 1
    save_data(DB)

# --- KEYBOARDS ---
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Kino olish"), KeyboardButton(text="ℹ️ Yordam")],
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Kino qo‘shish"), KeyboardButton(text="🗑 Kino o‘chirish")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⚙️ Admin panel")],
    ],
    resize_keyboard=True
)

# --- RENDER WEB SERVICE FIX (simple http server to open a port) ---
# Render Web Service port scan talab qiladi. Shu server portni ochib turadi.
async def health_server():
    import asyncio
    from aiohttp import web

    async def handle(_request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    while True:
        await asyncio.sleep(3600)

# --- HANDLERS ---
@dp.message(Command("start"))
async def start_cmd(message: Message):
    text = (
        "Salom! Kino kodini yuboring.\n"
        "Masalan: 1001\n\n"
        "Admin: /panel"
    )
    kb = admin_kb if is_admin(message) else user_kb
    await message.answer(text, reply_markup=kb)

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📌 Qanday ishlaydi:\n"
        "1) Siz kino kodini yuborasiz (masalan 1001)\n"
        "2) Bot agar topilsa videoni yuboradi.\n\n"
        "Admin buyruqlar:\n"
        "/panel  - admin tugmalar\n"
        "/add 777 - (reply qilib) kino qo‘shish\n"
        "/del 777 - kino o‘chirish\n"
        "/stats - statistika\n"
    )

@dp.message(Command("panel"))
async def panel_cmd(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")
    ch = DB.get("channel_id")
    ch_title = DB.get("channel_title")
    await message.answer(
        "⚙️ Admin panel\n\n"
        f"📌 Kanal: {ch_title if ch_title else 'yo‘q'}\n"
        f"📌 CHAT_ID: {ch if ch else 'yo‘q'}\n\n"
        "✅ Kanal chat_id olish uchun:\n"
        "1) Kanalga post tashlang\n"
        "2) O‘sha postni botga FORWARD qiling\n"
        "3) Bot CHAT_ID ni saqlab beradi",
        reply_markup=admin_kb
    )

@dp.message(F.text == "ℹ️ Yordam")
async def help_btn(message: Message):
    await help_cmd(message)

@dp.message(F.text == "🎬 Kino olish")
async def kino_btn(message: Message):
    await message.answer("Kino kodini yuboring. Masalan: 1001")

@dp.message(F.text == "⚙️ Admin panel")
async def admin_panel_btn(message: Message):
    await panel_cmd(message)

@dp.message(F.text == "📊 Statistika")
async def stats_btn(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")
    await stats_cmd(message)

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")
    movies_count = len(DB.get("movies", {}))
    users_count = len(DB.get("users", {}))
    total_requests = sum(DB.get("users", {}).values()) if DB.get("users") else 0
    ch = DB.get("channel_id")
    ch_title = DB.get("channel_title")
    await message.answer(
        "📊 Statistika\n\n"
        f"🎞 Kinolar: {movies_count}\n"
        f"👤 Userlar: {users_count}\n"
        f"📨 So‘rovlar: {total_requests}\n\n"
        f"📌 Kanal: {ch_title if ch_title else 'yo‘q'}\n"
        f"📌 CHAT_ID: {ch if ch else 'yo‘q'}"
    )

@dp.message(F.text == "➕ Kino qo‘shish")
async def add_help_btn(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")
    await message.answer(
        "➕ Kino qo‘shish:\n\n"
        "✅ 1-usul (oddiy):\n"
        "Videoni botga yuboring va videoga REPLY qilib yozing:\n"
        "/add 777\n\n"
        "✅ 2-usul (kanal orqali):\n"
        "Kanalga video tashlang -> kanal postini botga FORWARD qiling.\n"
        "Keyin /add 777 yozing (reply shart emas, oxirgi forward ishlaydi)."
    )

@dp.message(F.text == "🗑 Kino o‘chirish")
async def del_help_btn(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")
    await message.answer("🗑 O‘chirish: /del 777")

# Kanal forward qilinganda CHAT_ID ni saqlash + oxirgi forward video file_id ni yodda saqlash
@dp.message(F.forward_from_chat)
async def handle_forward(message: Message):
    if not is_admin(message):
        return  # oddiy user forward qilsa indamaymiz

    chat = message.forward_from_chat
    # kanal bo'lsa chat.id odatda -100... bo'ladi
    DB["channel_id"] = chat.id
    DB["channel_title"] = chat.title

    # Agar forward qilingan postda video bo'lsa, file_id ni vaqtincha eslab qolamiz
    if message.video:
        DB["last_forward_video_file_id"] = message.video.file_id
    else:
        # kanal posti video bo'lmasa ham CHAT_ID saqlanadi
        DB["last_forward_video_file_id"] = None

    save_data(DB)

    await message.answer(
        f"✅ Kanal CHAT_ID saqlandi:\n{chat.id}\n"
        f"📢 {chat.title if chat.title else ''}"
    )

@dp.message(Command("add"))
async def add_movie(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗️To‘g‘ri yozing: /add 777")

    code = parts[1].strip()

    file_id = None

    # 1) Agar admin videoga reply qilgan bo'lsa
    if message.reply_to_message and message.reply_to_message.video:
        file_id = message.reply_to_message.video.file_id

    # 2) Aks holda, oxirgi forward qilingan kanal videosini ishlatamiz
    if not file_id:
        file_id = DB.get("last_forward_video_file_id")

    if not file_id:
        return await message.answer("❗️Avval video yuboring yoki kanal postini botga forward qiling (video bo‘lsin).")

    DB["movies"][code] = file_id
    save_data(DB)
    await message.answer(f"✅ Qo‘shildi! Kod: {code}")

@dp.message(Command("del"))
async def del_movie(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗️To‘g‘ri yozing: /del 777")

    code = parts[1].strip()
    if code in DB.get("movies", {}):
        del DB["movies"][code]
        save_data(DB)
        await message.answer(f"🗑 O‘chirildi: {code}")
    else:
        await message.answer("❌ Bunday kod yo‘q.")

@dp.message(Command("list"))
async def list_movies(message: Message):
    if not is_admin(message):
        return await message.answer("🚫 Siz admin emassiz.")

    if not DB.get("movies"):
        return await message.answer("Hali kino yo‘q.")

    keys = sorted(DB["movies"].keys(), key=lambda x: (len(x), x))
    text = "🎬 Kinolar:\n" + "\n".join(keys)
    await message.answer(text)

@dp.message(F.text)
async def get_movie(message: Message):
    # user kino so'rasa
    text = (message.text or "").strip()

    if not text:
        return

    # oddiy komanda bo'lsa o'tkazamiz
    if text.startswith("/"):
        return

    inc_user(message.from_user.id)

    file_id = DB.get("movies", {}).get(text)
    if file_id:
        inc_code(text)
        await bot.send_video(chat_id=message.chat.id, video=file_id)
    else:
        await message.answer("❌ Bunday kod topilmadi.")

# --- MAIN ---
async def main():
    # health server (Render Web Service port uchun)
    asyncio.create_task(health_server())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
