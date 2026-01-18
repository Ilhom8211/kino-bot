import os
import json
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762  # <-- shu yerga admin ID (raqam!)
DATA_FILE = "movies.json"
STATE_FILE = "state.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------- Storage ----------
def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

MOVIES = load_json(DATA_FILE, {})          # { "1001": {"file_id": "...", "title": "..."} }
STATE = load_json(STATE_FILE, {"waiting": {}})  # {"waiting": {"8429...": "add" / "del"}}

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Admin panel")],
            [KeyboardButton(text="➕ Kino qo‘shish"), KeyboardButton(text="🗑 Kino o‘chirish")],
            [KeyboardButton(text="📊 Statistika")],
        ],
        resize_keyboard=True
    )

def user_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Kino qidirish")],
        ],
        resize_keyboard=True
    )

# ---------- Simple HTTP server (Render port) ----------
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
    print(f"HTTP server started on port {port}")

# ---------- Bot Handlers ----------
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    text = "Salom! Kino kodini yuboring.\nMasalan: 1001"
    if is_admin(message.from_user.id):
        text += "\n\nAdmin: /panel"
        await message.answer(text, reply_markup=admin_kb())
    else:
        await message.answer(text, reply_markup=user_kb())

@dp.message(F.text == "/panel")
async def panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")
    await message.answer("⚙️ Admin panel:", reply_markup=admin_kb())

@dp.message(F.text == "⚙️ Admin panel")
async def panel_btn(message: Message):
    await panel(message)

@dp.message(F.text == "➕ Kino qo‘shish")
async def add_btn(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")
    STATE["waiting"][str(message.from_user.id)] = "add"
    save_json(STATE_FILE, STATE)
    await message.answer("🎬 Video yuboring (video'ga reply qilib /add KOD ham bo‘ladi).")

@dp.message(F.text == "🗑 Kino o‘chirish")
async def del_btn(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")
    STATE["waiting"][str(message.from_user.id)] = "del"
    save_json(STATE_FILE, STATE)
    await message.answer("🗑 O‘chirish uchun kod yuboring. Masalan: 1001")

@dp.message(F.text == "📊 Statistika")
async def stats_btn(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")
    count = len(MOVIES)
    await message.answer(f"📊 Statistika:\n🎞 Bazada kinolar: {count} ta")

@dp.message(F.text.startswith("/add"))
async def add_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")

    if not message.reply_to_message or not message.reply_to_message.video:
        return await message.answer("❗ /add ishlashi uchun videoga reply qiling.\nMasalan: video'ga reply qilib /add 1001")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Kod yozing. Masalan: /add 1001")

    code = parts[1].strip()
    file_id = message.reply_to_message.video.file_id

    MOVIES[code] = {"file_id": file_id}
    save_json(DATA_FILE, MOVIES)
    await message.answer(f"✅ Qo‘shildi! Kod: {code}")

@dp.message(F.text.startswith("/del"))
async def del_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Kod yozing. Masalan: /del 1001")

    code = parts[1].strip()
    if code in MOVIES:
        MOVIES.pop(code)
        save_json(DATA_FILE, MOVIES)
        return await message.answer(f"🗑 O‘chirildi: {code}")

    await message.answer("❌ Bunday kod topilmadi.")

@dp.message(F.video)
async def video_came(message: Message):
    # Agar admin "Kino qo‘shish" bosgan bo‘lsa, keyin kod so‘raymiz
    if not is_admin(message.from_user.id):
        return

    if STATE["waiting"].get(str(message.from_user.id)) == "add":
        STATE["waiting"][str(message.from_user.id)] = "add_wait_code"
        save_json(STATE_FILE, STATE)
        # vaqtинча video file_id ни state га сақлаб қўямиз
        STATE["last_video_file_id"] = message.video.file_id
        save_json(STATE_FILE, STATE)
        await message.answer("✅ Video olindi. Endi kod yuboring (masalan: 1001).")

@dp.message(F.text)
async def any_text(message: Message):
    text = message.text.strip()

    # Admin flow: video keldi, endi kod kutilyapti
    if is_admin(message.from_user.id) and STATE["waiting"].get(str(message.from_user.id)) == "add_wait_code":
        code = text
        file_id = STATE.get("last_video_file_id")
        if not file_id:
            STATE["waiting"].pop(str(message.from_user.id), None)
            save_json(STATE_FILE, STATE)
            return await message.answer("❌ Video topilmadi. Qaytadan 'Kino qo‘shish' bosing.")
        MOVIES[code] = {"file_id": file_id}
        save_json(DATA_FILE, MOVIES)
        STATE["waiting"].pop(str(message.from_user.id), None)
        STATE.pop("last_video_file_id", None)
        save_json(STATE_FILE, STATE)
        return await message.answer(f"✅ Qo‘shildi! Kod: {code}")

    # Admin flow: delete waiting
    if is_admin(message.from_user.id) and STATE["waiting"].get(str(message.from_user.id)) == "del":
        code = text
        if code in MOVIES:
            MOVIES.pop(code)
            save_json(DATA_FILE, MOVIES)
            STATE["waiting"].pop(str(message.from_user.id), None)
            save_json(STATE_FILE, STATE)
            return await message.answer(f"🗑 O‘chirildi: {code}")
        else:
            return await message.answer("❌ Bunday kod topilmadi.")

    # User search: if number -> send video
    if text.isdigit():
        code = text
        movie = MOVIES.get(code)
        if not movie:
            return await message.answer("❌ Bunday kod topilmadi.")
        return await message.answer_video(movie["file_id"], caption=f"🎬 Kod: {code}")

    # fallback
    if is_admin(message.from_user.id):
        await message.answer("Kod yuboring (masalan: 1001) yoki /panel.")
    else:
        await message.answer("Kino kodini yuboring (masalan: 1001).")

# ---------- Main ----------
async def main():
    # Render Web Service uchun port server
    await start_web_server()

    # Bot polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
