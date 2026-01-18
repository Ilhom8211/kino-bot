import asyncio
import json
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

# Admin ID: sizning Telegram ID (raqam)
# MASALAN: 8429326762
ADMIN_ID = 8429326762  # <-- SHU YERNI O'ZINGIZNIKI QILING

DATA_FILE = "movies.json"
CONFIG_FILE = "config.json"  # kanal_chat_id shu yerga yoziladi

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# STORAGE
# =========================
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

MOVIES = load_json(DATA_FILE, {})   # {"1": {"file_id": "...", "caption": "...", "added_at": "..."}}
CONFIG = load_json(CONFIG_FILE, {"channel_chat_id": None})

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =========================
# KEYBOARDS
# =========================
def user_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎬 Kino olish", callback_data="u_get")
    kb.button(text="📃 Kino ro‘yxati", callback_data="u_list")
    kb.button(text="ℹ️ Yordam", callback_data="u_help")
    kb.adjust(2, 1)
    return kb.as_markup()

def admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Kino qo‘shish", callback_data="a_add_help")
    kb.button(text="📊 Statistika", callback_data="a_stats")
    kb.button(text="📢 Kanal CHAT_ID sozlash", callback_data="a_set_chat")
    kb.button(text="📃 Kino ro‘yxati", callback_data="a_list")
    kb.button(text="🗑 Kino o‘chirish", callback_data="a_del_help")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

# =========================
# TEXTS
# =========================
START_TEXT = (
    "Salom! 👋\n\n"
    "🎬 Kino kodi yuboring.\n"
    "Masalan: 1001\n\n"
    "📌 Kino qo‘shish faqat admin uchun.\n"
)

HELP_TEXT = (
    "📌 Qanday ishlaydi?\n\n"
    "1) Kino olish: chatga kino kodini yozing (masalan 1001)\n"
    "2) Kino ro‘yxati: /list\n\n"
    "👮 Admin uchun:\n"
    "✅ Kino qo‘shish: videoga reply qilib /add 1001\n"
    "✅ Kanal CHAT_ID: kanaldagi postni botga forward qiling (bot CHAT_ID ni saqlaydi)\n"
)

# =========================
# COMMANDS
# =========================
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(START_TEXT, reply_markup=user_keyboard())
    if is_admin(message.from_user.id):
        await message.answer("👮 Admin panel:", reply_markup=admin_keyboard())

@dp.message(F.text == "/help")
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)

@dp.message(F.text == "/panel")
async def cmd_panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Siz admin emassiz.")
    await message.answer("👮 Admin panel:", reply_markup=admin_keyboard())

@dp.message(F.text == "/list")
async def cmd_list(message: Message):
    if not MOVIES:
        return await message.answer("Hali kino yo‘q.")
    keys = sorted(MOVIES.keys(), key=lambda x: int(x) if x.isdigit() else x)
    txt = "🎞 Kinolar ro‘yxati:\n" + "\n".join([f"• {k}" for k in keys])
    await message.answer(txt)

@dp.message(F.text == "/stats")
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Statistika faqat admin uchun.")
    await message.answer(make_stats_text())

def make_stats_text() -> str:
    total = len(MOVIES)
    ch = CONFIG.get("channel_chat_id")
    return (
        "📊 Statistika:\n\n"
        f"🎬 Umumiy kinolar: {total}\n"
        f"📢 Kanal CHAT_ID: {ch if ch else 'yo‘q (hali sozlanmagan)'}\n"
        f"🕒 Oxirgi update: {now_str()}\n"
    )

# =========================
# ADMIN: ADD MOVIE
# =========================
@dp.message(F.text.startswith("/add"))
async def add_movie(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Bu buyruq faqat admin uchun.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Format: videoga reply qilib `/add 1001`")

    code = parts[1].strip()

    if not message.reply_to_message:
        return await message.answer("❗ Videoga reply qilib yuboring.\nMasalan: videoga reply → /add 1001")

    m = message.reply_to_message
    file_id = None
    caption = ""

    # video/document bo'lishi mumkin
    if m.video:
        file_id = m.video.file_id
        caption = m.caption or ""
    elif m.document:
        file_id = m.document.file_id
        caption = m.caption or ""
    else:
        return await message.answer("❗ Reply qilgan xabaringiz video/document emas.")

    MOVIES[code] = {"file_id": file_id, "caption": caption, "added_at": now_str()}
    save_json(DATA_FILE, MOVIES)

    await message.answer(f"✅ Qo‘shildi! Kod: {code}")

    # Agar kanal_chat_id bor bo'lsa, kanalga ham post qilib qo'yamiz (ixtiyoriy)
    channel_chat_id = CONFIG.get("channel_chat_id")
    if channel_chat_id:
        try:
            text = f"🎬 Kino kodi: {code}\n\n📩 Botga yozing: {code}"
            # videoni kanalga yuborish
            if m.video:
                await bot.send_video(chat_id=channel_chat_id, video=file_id, caption=text)
            else:
                await bot.send_document(chat_id=channel_chat_id, document=file_id, caption=text)
        except Exception as e:
            await message.answer("⚠️ Kanalga yuborishda xatolik bo‘ldi. (Bot kanalda admin emas yoki CHAT_ID xato)")

# =========================
# ADMIN: DELETE MOVIE
# =========================
@dp.message(F.text.startswith("/del"))
async def del_movie(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Bu buyruq faqat admin uchun.")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("❗ Format: /del 1001")

    code = parts[1].strip()
    if code not in MOVIES:
        return await message.answer("❌ Bunday kod yo‘q.")

    del MOVIES[code]
    save_json(DATA_FILE, MOVIES)
    await message.answer(f"🗑 O‘chirildi: {code}")

# =========================
# GET MOVIE BY CODE (USER)
# =========================
@dp.message(F.text)
async def get_movie(message: Message):
    text = message.text.strip()

    # buyruqlarni bu handlerda ushlamasin
    if text.startswith("/"):
        return

    data = MOVIES.get(text)
    if not data:
        return await message.answer("❌ Bunday kod topilmadi. /list ni ko‘rib oling.")
    file_id = data["file_id"]

    # video/document yuboramiz
    try:
        await bot.send_video(chat_id=message.chat.id, video=file_id)
    except Exception:
        # video bo'lmasa document bo'lishi mumkin
        await bot.send_document(chat_id=message.chat.id, document=file_id)

# =========================
# FORWARD: GET CHANNEL CHAT_ID
# =========================
@dp.message(F.forward_origin)
async def handle_forward_origin(message: Message):
    # faqat admin yuborsa yaxshi (aks holda ham ishlayveradi)
    if not is_admin(message.from_user.id):
        return

    origin = message.forward_origin
    chat = getattr(origin, "chat", None)
    if not chat:
        return await message.answer("❗ Bu kanal postidan forward emas. Kanaldagi postni forward qiling.")

    # chat.id -> kanal chat_id
    CONFIG["channel_chat_id"] = chat.id
    save_json(CONFIG_FILE, CONFIG)

    await message.answer(f"✅ Kanal CHAT_ID saqlandi:\n{chat.id}\n📢 {getattr(chat, 'title', '')}")

# Eski forward usuli uchun ham qo'yamiz
@dp.message(F.forward_from_chat)
async def handle_forward_from_chat(message: Message):
    if not is_admin(message.from_user.id):
        return
    chat = message.forward_from_chat
    if not chat:
        return
    CONFIG["channel_chat_id"] = chat.id
    save_json(CONFIG_FILE, CONFIG)
    await message.answer(f"✅ Kanal CHAT_ID saqlandi:\n{chat.id}\n📢 {chat.title}")

# =========================
# CALLBACKS
# =========================
@dp.callback_query()
async def callbacks(call: CallbackQuery):
    data = call.data

    # USER
    if data == "u_help":
        await call.message.answer(HELP_TEXT)
    elif data == "u_list":
        if not MOVIES:
            await call.message.answer("Hali kino yo‘q.")
        else:
            keys = sorted(MOVIES.keys(), key=lambda x: int(x) if x.isdigit() else x)
            txt = "🎞 Kinolar ro‘yxati:\n" + "\n".join([f"• {k}" for k in keys])
            await call.message.answer(txt)
    elif data == "u_get":
        await call.message.answer("🎬 Kino kodini yozing.\nMasalan: 1001")

    # ADMIN
    elif data == "a_stats":
        if is_admin(call.from_user.id):
            await call.message.answer(make_stats_text())
    elif data == "a_list":
        if is_admin(call.from_user.id):
            if not MOVIES:
                await call.message.answer("Hali kino yo‘q.")
            else:
                keys = sorted(MOVIES.keys(), key=lambda x: int(x) if x.isdigit() else x)
                txt = "🎞 Kinolar ro‘yxati:\n" + "\n".join([f"• {k}" for k in keys])
                await call.message.answer(txt)
    elif data == "a_add_help":
        if is_admin(call.from_user.id):
            await call.message.answer("➕ Kino qo‘shish:\nVideoga reply qilib yozing:\n/add 1001")
    elif data == "a_del_help":
        if is_admin(call.from_user.id):
            await call.message.answer("🗑 Kino o‘chirish:\n/del 1001")
    elif data == "a_set_chat":
        if is_admin(call.from_user.id):
            await call.message.answer(
                "📢 Kanal CHAT_ID sozlash:\n"
                "1) Kanalingizga istalgan post tashlang\n"
                "2) O‘sha postni botga FORWARD qiling\n"
                "3) Bot CHAT_ID ni chiqarib, saqlab oladi ✅"
            )

    await call.answer()

# =========================
# RUN
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
