import asyncio
import json
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# ====== SETTINGS ======
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762  # <-- O'ZINGIZNING ADMIN ID
DATA_FILE = "movies.json"
CHANNEL_FILE = "channel.json"
# ======================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------- Storage helpers ----------
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


MOVIES = load_json(DATA_FILE, {})
CHANNEL = load_json(CHANNEL_FILE, {"chat_id": None, "title": None})

# ---------- Keyboards ----------
def user_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino olish")],
            [KeyboardButton(text="ℹ️ Yordam")]
        ],
        resize_keyboard=True
    )

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kino qo‘shish"), KeyboardButton(text="🗑 Kino o‘chirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⚙️ Admin panel")]
        ],
        resize_keyboard=True
    )

def is_admin(message: Message) -> bool:
    return message.from_user and message.from_user.id == ADMIN_ID


# ---------- Commands ----------
@dp.message(F.text == "/start")
async def start(message: Message):
    text = (
        "Salom! Kino kodini yuboring.\n"
        "Masalan: 1001\n\n"
        "Admin uchun:\n"
        "1) Kanal postini menga FORWARD qiling (CHAT_ID chiqadi)\n"
        "2) Videoga reply qilib: /add 1001\n"
    )
    if is_admin(message):
        await message.answer(text, reply_markup=admin_kb())
    else:
        await message.answer(text, reply_markup=user_kb())


@dp.message(F.text == "/panel")
async def panel_cmd(message: Message):
    if not is_admin(message):
        return
    await message.answer("⚙️ Admin panel", reply_markup=admin_kb())


# ---------- Admin buttons ----------
@dp.message(F.text == "⚙️ Admin panel")
async def panel_btn(message: Message):
    if not is_admin(message):
        return
    await message.answer("⚙️ Admin panel (buyruqlar):\n"
                         "➕ Kino qo‘shish (videoga reply qilib /add 1001)\n"
                         "🗑 Kino o‘chirish (/del 1001)\n"
                         "📊 Statistika (/stats)\n"
                         "Kanal chat_id olish: kanal postini menga forward qiling")


@dp.message(F.text == "📊 Statistika")
async def stats_btn(message: Message):
    if not is_admin(message):
        return
    await send_stats(message)


@dp.message(F.text == "➕ Kino qo‘shish")
async def add_btn(message: Message):
    if not is_admin(message):
        return
    await message.answer("➕ Kino qo‘shish:\n"
                         "1) Kanal postini forward qiling (CHAT_ID chiqadi)\n"
                         "2) Kanalga video tashlang\n"
                         "3) Video postga reply qilib yuboring: /add 1001")


@dp.message(F.text == "🗑 Kino o‘chirish")
async def del_btn(message: Message):
    if not is_admin(message):
        return
    await message.answer("🗑 Kino o‘chirish:\nMasalan: /del 1001")


# ---------- User buttons ----------
@dp.message(F.text == "🎬 Kino olish")
async def get_btn(message: Message):
    await message.answer("Kino kodini yuboring.\nMasalan: 1001")


@dp.message(F.text == "ℹ️ Yordam")
async def help_btn(message: Message):
    await message.answer("ℹ️ Yordam:\n"
                         "1) Kino olish: kod yuborasiz (1001)\n"
                         "2) Admin bo‘lsangiz: /panel\n")


# ---------- Forward from channel: save CHAT_ID ----------
@dp.message(F.forward_from_chat)
async def forward_handler(message: Message):
    """
    Kanal postini botga forward qilinsa:
    CHANNEL chat_id saqlaydi va admin'ga ko'rsatadi
    """
    if not is_admin(message):
        return

    chat = message.forward_from_chat
    # channel / supergroup bo'lishi mumkin, lekin bizga chat.id kerak
    CHANNEL["chat_id"] = chat.id
    CHANNEL["title"] = getattr(chat, "title", None)
    CHANNEL["saved_at"] = datetime.now().isoformat(timespec="seconds")
    save_json(CHANNEL_FILE, CHANNEL)

    await message.answer(f"✅ Kanal CHAT_ID saqlandi:\n{CHANNEL['chat_id']}\n📣 {CHANNEL.get('title')}")


# ---------- Admin: Add movie ----------
@dp.message(F.text.startswith("/add"))
async def add_movie(message: Message):
    if not is_admin(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗️To‘g‘ri yozing: /add 1001 (videoga reply qilib)")
        return

    code = parts[1].strip()

    if not message.reply_to_message or not message.reply_to_message.video:
        await message.answer("❗️Videoga reply qiling va /add 1001 yozing.")
        return

    # Agar kanal chat_id hali saqlanmagan bo'lsa ogohlantiramiz
    if not CHANNEL.get("chat_id"):
        await message.answer("❗️ Avval kanal postini menga forward qiling (CHAT_ID chiqadi).")
        return

    file_id = message.reply_to_message.video.file_id
    MOVIES[code] = file_id
    save_json(DATA_FILE, MOVIES)

    await message.answer(f"✅ Qo‘shildi! Kod: {code}")


# ---------- Admin: Delete movie ----------
@dp.message(F.text.startswith("/del"))
async def del_movie(message: Message):
    if not is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗️To‘g‘ri yozing: /del 1001")
        return

    code = parts[1].strip()
    if code in MOVIES:
        MOVIES.pop(code, None)
        save_json(DATA_FILE, MOVIES)
        await message.answer(f"🗑 O‘chirildi: {code}")
    else:
        await message.answer("❌ Bunday kod topilmadi.")


# ---------- Admin: Stats ----------
@dp.message(F.text == "/stats")
async def stats_cmd(message: Message):
    if not is_admin(message):
        return
    await send_stats(message)


async def send_stats(message: Message):
    total = len(MOVIES)
    ch = CHANNEL.get("chat_id")
    title = CHANNEL.get("title")
    await message.answer(
        "📊 Statistika:\n"
        f"🎞 Kinolar soni: {total}\n"
        f"📣 Kanal: {title if title else '-'}\n"
        f"🆔 CHAT_ID: {ch if ch else 'saqlanmagan'}"
    )


# ---------- Get movie by code (IMPORTANT: ignore buttons!) ----------
@dp.message(F.text)
async def get_movie(message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    # ✅ tugmalar matnlari kino kodi bo'lib ketmasin
    ignore = {
        "🎬 Kino olish", "ℹ️ Yordam",
        "➕ Kino qo‘shish", "🗑 Kino o‘chirish",
        "📊 Statistika", "⚙️ Admin panel",
        "Admin panel", "Kino qo‘shish", "Kino o‘chirish", "Statistika"
    }
    if text in ignore:
        return

    # /... komandalar boshqa handlerlarda
    if text.startswith("/"):
        return

    code = text
    file_id = MOVIES.get(code)
    if file_id:
        await bot.send_video(chat_id=message.chat.id, video=file_id)
    else:
        await message.answer("❌ Bunday kod topilmadi.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
