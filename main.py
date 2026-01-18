import os
import re
import sqlite3
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties


# ========== ENV ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # example: "8429326762,123456"
# CHANNEL_ID ni forward orqali ham saqlaymiz, ENV bo‘lsa default bo‘ladi
CHANNEL_ID_ENV = os.getenv("CHANNEL_ID", "").strip()  # example: "-1001234567890"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Railway/Render variables ga BOT_TOKEN qo‘ying.")


def parse_admin_ids(raw: str) -> set[int]:
    ids = set()
    for part in re.split(r"[,\s]+", raw.strip()) if raw else []:
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS = parse_admin_ids(ADMIN_IDS_RAW)

# ========== BOT ==========
bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

DB_PATH = "kino.db"


# ========== DB ==========
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def db_init():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        code TEXT PRIMARY KEY,
        file_id TEXT NOT NULL,
        file_type TEXT NOT NULL,  -- "video" / "document"
        caption TEXT,
        added_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.commit()
    conn.close()


def cfg_get(key: str) -> str | None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def cfg_set(key: str, value: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO config(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()
    conn.close()


def get_channel_id() -> int | None:
    # Priority: DB -> ENV
    val = cfg_get("CHANNEL_ID")
    if val and re.fullmatch(r"-?\d+", val.strip()):
        return int(val.strip())
    if CHANNEL_ID_ENV and re.fullmatch(r"-?\d+", CHANNEL_ID_ENV.strip()):
        return int(CHANNEL_ID_ENV.strip())
    return None


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def touch_user(user_id: int):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, first_seen) VALUES(?, ?)",
        (user_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def movies_count() -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM movies")
    n = cur.fetchone()[0]
    conn.close()
    return n


def users_count() -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    conn.close()
    return n


def movie_get(code: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT code, file_id, file_type, caption FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    return row  # None or tuple


def movie_add(code: str, file_id: str, file_type: str, caption: str | None):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO movies(code, file_id, file_type, caption, added_at) VALUES(?,?,?,?,?)",
        (code, file_id, file_type, caption, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def movie_delete(code: str) -> bool:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM movies WHERE code=?", (code,))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ========== KEYBOARDS ==========
def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Kino qo‘shish", callback_data="admin:add")],
            [InlineKeyboardButton(text="🗑 Kino o‘chirish", callback_data="admin:del")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stat")],
            [InlineKeyboardButton(text="📣 Kanalni ulash (forward)", callback_data="admin:setch")],
        ]
    )


# admin holat (soddaroq)
ADMIN_STATE: dict[int, str] = {}  # user_id -> "await_del_code" / "await_add_code"


def normalize_code(text: str) -> str:
    return (text or "").strip()


# ========== HANDLERS ==========
@dp.message(Command("start"))
async def cmd_start(message: Message):
    touch_user(message.from_user.id)

    txt = (
        "Salom! Kino kodini yuboring.\n"
        "Masalan: <b>1001</b>\n\n"
    )
    if is_admin(message.from_user.id):
        txt += "Admin: /panel"
    await message.answer(txt)


@dp.message(Command("panel"))
async def cmd_panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Siz admin emassiz.")
    await message.answer("⚙️ <b>Admin panel</b>", reply_markup=admin_panel_kb())


# ==== Kanal chat_id olish (forward) ====
@dp.message(F.forward_from_chat)
async def got_forward(message: Message):
    # Admin forward qilsa kanal ID saqlaymiz
    if not is_admin(message.from_user.id):
        return

    chat = message.forward_from_chat
    # kanal bo‘lsa id -100... bo‘ladi
    cfg_set("CHANNEL_ID", str(chat.id))

    await message.answer(
        f"✅ Kanal CHAT_ID saqlandi:\n<b>{chat.id}</b>\n📣 {chat.title or ''}"
    )


# ==== Admin callbacklar ====
@dp.callback_query(F.data.startswith("admin:"))
async def admin_callbacks(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Admin emassiz.", show_alert=True)
        return

    action = call.data.split(":", 1)[1]

    if action == "stat":
        u = users_count()
        m = movies_count()
        ch = get_channel_id()
        ch_txt = f"<b>{ch}</b>" if ch else "Ulanmagan"
        await call.message.answer(
            f"📊 <b>Statistika</b>\n"
            f"👤 Userlar: <b>{u}</b>\n"
            f"🎬 Kinolar: <b>{m}</b>\n"
            f"📣 Kanal: {ch_txt}"
        )
        await call.answer()
        return

    if action == "add":
        ADMIN_STATE[call.from_user.id] = "await_add_video"
        await call.message.answer(
            "➕ Kino qo‘shish:\n"
            "1) Videoni (yoki faylni) yuboring\n"
            "2) Keyin kodini yuborasiz (masalan: 1001)\n\n"
            "⚠️ Videoni yuborib bo‘lgach, kodni oddiy mesaj qilib yozing."
        )
        await call.answer()
        return

    if action == "del":
        ADMIN_STATE[call.from_user.id] = "await_del_code"
        await call.message.answer("🗑 O‘chirish uchun kod yuboring (masalan: 1001)")
        await call.answer()
        return

    if action == "setch":
        await call.message.answer(
            "📣 Kanalni ulash:\n"
            "1) Kanalga bitta post tashlang\n"
            "2) O‘sha postni BOTga <b>forward</b> qiling\n\n"
            "Bot CHAT_ID ni o‘zi saqlab oladi ✅"
        )
        await call.answer()
        return

    await call.answer("Noma’lum buyruq.", show_alert=True)


# ==== Admin kino qo‘shish 1-qadam: video/doc qabul qilish ====
ADMIN_PENDING_MEDIA: dict[int, dict] = {}  # user_id -> {"file_id":..., "type":..., "caption":...}

@dp.message()
async def all_messages_router(message: Message):
    touch_user(message.from_user.id)

    uid = message.from_user.id
    state = ADMIN_STATE.get(uid)

    # ===== ADMIN FLOW =====
    if is_admin(uid) and state == "await_add_video":
        # video yoki document qabul qilamiz
        if message.video:
            ADMIN_PENDING_MEDIA[uid] = {
                "file_id": message.video.file_id,
                "type": "video",
                "caption": message.caption
            }
            ADMIN_STATE[uid] = "await_add_code"
            return await message.answer("✅ Video olindi. Endi kodini yuboring (masalan: 1001)")

        if message.document:
            ADMIN_PENDING_MEDIA[uid] = {
                "file_id": message.document.file_id,
                "type": "document",
                "caption": message.caption
            }
            ADMIN_STATE[uid] = "await_add_code"
            return await message.answer("✅ Fayl olindi. Endi kodini yuboring (masalan: 1001)")

        return await message.answer("Video yoki fayl yuboring.")

    if is_admin(uid) and state == "await_add_code":
        code = normalize_code(message.text or "")
        if not code or not re.fullmatch(r"\d{1,20}", code):
            return await message.answer("❌ Kod faqat raqam bo‘lsin. Masalan: 1001")

        # duplicate tekshiruv
        if movie_get(code):
            ADMIN_STATE.pop(uid, None)
            ADMIN_PENDING_MEDIA.pop(uid, None)
            return await message.answer("⚠️ Bu kod avvaldan bor. Boshqa kod kiriting yoki o‘chirib qayta qo‘shing.")

        media = ADMIN_PENDING_MEDIA.get(uid)
        if not media:
            ADMIN_STATE.pop(uid, None)
            return await message.answer("❌ Media topilmadi. Admin paneldan qayta boshlang: /panel")

        # DB ga qo‘shamiz
        movie_add(code, media["file_id"], media["type"], media.get("caption"))

        # kanalga ham tashlaymiz (agar ulangan bo‘lsa)
        ch = get_channel_id()
        if ch:
            try:
                cap = f"🎬 Kod: <b>{code}</b>"
                if media.get("caption"):
                    cap += f"\n\n{media['caption']}"
                if media["type"] == "video":
                    await bot.send_video(ch, media["file_id"], caption=cap)
                else:
                    await bot.send_document(ch, media["file_id"], caption=cap)
            except Exception as e:
                # kanalga tashlashda xato bo‘lsa ham kino saqlangan bo‘ladi
                await message.answer(f"✅ Qo‘shildi (DB). Lekin kanalga yuborishda xato: {e}")

        ADMIN_STATE.pop(uid, None)
        ADMIN_PENDING_MEDIA.pop(uid, None)
        return await message.answer(f"✅ Qo‘shildi! Kod: <b>{code}</b>")

    if is_admin(uid) and state == "await_del_code":
        code = normalize_code(message.text or "")
        if not code or not re.fullmatch(r"\d{1,20}", code):
            ADMIN_STATE.pop(uid, None)
            return await message.answer("❌ Noto‘g‘ri kod. Masalan: 1001")

        ok = movie_delete(code)
        ADMIN_STATE.pop(uid, None)
        if ok:
            return await message.answer(f"🗑 O‘chirildi: <b>{code}</b>")
        else:
            return await message.answer("❌ Bunday kod topilmadi.")

    # ===== USER FLOW (kod yuborsa kino qaytaradi) =====
    text = (message.text or "").strip()
    if not text:
        return

    if not re.fullmatch(r"\d{1,20}", text):
        # boshqa gap bo‘lsa indamaymiz (xohlasa /start bilan yo‘riqnoma)
        return

    row = movie_get(text)
    if not row:
        return await message.answer("❌ Bunday kod topilmadi.")

    _, file_id, ftype, caption = row

    try:
        if ftype == "video":
            await message.answer_video(file_id, caption=caption)
        else:
            await message.answer_document(file_id, caption=caption)
    except Exception:
        # ba’zida file_id eskirib qolishi mumkin (kamdan-kam)
        await message.answer("⚠️ Kino yuborishda xatolik. Admin qayta yuklasin.")


async def main():
    db_init()

    # ENV'da CHANNEL_ID bo‘lsa DBga yozib qo‘yamiz (bir marta)
    if CHANNEL_ID_ENV and not cfg_get("CHANNEL_ID"):
        cfg_set("CHANNEL_ID", CHANNEL_ID_ENV)

    print("Bot started...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
