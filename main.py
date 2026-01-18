import os
import re
import asyncio
import sqlite3
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


# ===================== CONFIG =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # masalan: 8429326762,123456789
CHANNEL_CHAT_ID_RAW = os.getenv("CHANNEL_CHAT_ID", "").strip()  # ixtiyoriy: -1003632115541

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env yo'q!")

def parse_admins(raw: str) -> set[int]:
    if not raw:
        return set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out = set()
    for p in parts:
        if p.lstrip("-").isdigit():
            out.add(int(p))
    return out

ADMIN_IDS = parse_admins(ADMIN_IDS_RAW)

CHANNEL_CHAT_ID = None
if CHANNEL_CHAT_ID_RAW and CHANNEL_CHAT_ID_RAW.lstrip("-").isdigit():
    CHANNEL_CHAT_ID = int(CHANNEL_CHAT_ID_RAW)

DB_PATH = "kino.db"

# ===================== DB =====================
def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies(
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            caption TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            first_seen_ts INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()

def db_add_user(user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, first_seen_ts) VALUES(?, strftime('%s','now'))", (user_id,))
    con.commit()
    con.close()

def db_get_stats():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM movies")
    movies_count = cur.fetchone()[0]
    con.close()
    return users_count, movies_count

def db_get_movie(code: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT file_id, caption FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    con.close()
    return row  # (file_id, caption) or None

def db_add_movie(code: str, file_id: str, caption: str | None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Duplicate bo'lsa error chiqaramiz
    cur.execute("SELECT 1 FROM movies WHERE code=?", (code,))
    exists = cur.fetchone() is not None
    if exists:
        con.close()
        return False
    cur.execute("INSERT INTO movies(code, file_id, caption) VALUES(?,?,?)", (code, file_id, caption))
    con.commit()
    con.close()
    return True

def db_delete_movie(code: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM movies WHERE code=?", (code,))
    deleted = cur.rowcount
    con.commit()
    con.close()
    return deleted > 0


# ===================== UI =====================
BTN_ADMIN_PANEL = "⚙️ Admin panel"
BTN_ADD = "➕ Kino qo‘shish"
BTN_DEL = "🗑️ Kino o‘chirish"
BTN_STATS = "📊 Statistika"
BTN_BACK = "⬅️ Orqaga"

def kb_main(is_admin: bool):
    if is_admin:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=BTN_ADMIN_PANEL)],
                [KeyboardButton(text=BTN_STATS)],
            ],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATS)],
        ],
        resize_keyboard=True
    )

def kb_admin():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_DEL)],
            [KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True
    )


# ===================== FSM (oddiy) =====================
@dataclass
class PendingAction:
    mode: str  # "add" | "del" | ""

PENDING: dict[int, PendingAction] = {}  # user_id -> PendingAction


# ===================== BOT =====================
router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

CODE_RE = re.compile(r"^\d{1,10}$")  # 1..10 raqam

@router.message(CommandStart())
async def start(m: Message):
    db_add_user(m.from_user.id)
    text = (
        "Salom! Kino kodini yuboring.\n"
        "Masalan: 1001\n\n"
    )
    if is_admin(m.from_user.id):
        text += "Admin: /panel yoki tugmalar orqali."
    await m.answer(text, reply_markup=kb_main(is_admin(m.from_user.id)))

@router.message(Command("panel"))
async def panel_cmd(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")
    await m.answer("⚙️ Admin panel:", reply_markup=kb_admin())

@router.message(F.text == BTN_ADMIN_PANEL)
async def panel_btn(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")
    await m.answer("⚙️ Admin panel:", reply_markup=kb_admin())

@router.message(F.text == BTN_BACK)
async def back_btn(m: Message):
    db_add_user(m.from_user.id)
    PENDING.pop(m.from_user.id, None)
    await m.answer("Bosh menyu:", reply_markup=kb_main(is_admin(m.from_user.id)))

@router.message(Command("stat"))
@router.message(F.text == BTN_STATS)
async def stats(m: Message):
    db_add_user(m.from_user.id)
    users_count, movies_count = db_get_stats()
    await m.answer(
        f"📊 Statistika\n\n"
        f"👥 Botni ishlatganlar: <b>{users_count}</b>\n"
        f"🎬 Kinolar soni: <b>{movies_count}</b>",
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == BTN_ADD)
async def ask_add(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")
    PENDING[m.from_user.id] = PendingAction(mode="add")
    await m.answer(
        "➕ Kino qo‘shish:\n"
        "1) Videoni yuboring (yoki kanal postini forward qiling)\n"
        "2) Video ustiga reply qilib: <b>/add 123</b>\n\n"
        "Yoki videoni yuborgandan keyin shunchaki kodni yozing: <b>123</b>",
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == BTN_DEL)
async def ask_del(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")
    PENDING[m.from_user.id] = PendingAction(mode="del")
    await m.answer("🗑️ O‘chirish uchun kodni yuboring. Masalan: 123")

@router.message(Command("add"))
async def add_cmd(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")

    # /add 123
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2 or not CODE_RE.match(parts[1].strip()):
        return await m.answer("❗ To‘g‘ri format: /add 123")

    code = parts[1].strip()

    # video reply bo‘lishi kerak
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.answer("❗ Videoga reply qilib yuboring: videoga reply → /add 123")

    file_id = m.reply_to_message.video.file_id
    caption = m.reply_to_message.caption

    ok = db_add_movie(code, file_id, caption)
    if not ok:
        return await m.answer("⚠️ Bu kod bilan kino allaqachon mavjud!")

    await m.answer(f"✅ Qo‘shildi! Kod: <b>{code}</b>", parse_mode=ParseMode.HTML)

@router.message(Command("del"))
async def del_cmd(m: Message):
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return await m.answer("❌ Siz admin emassiz.")
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2 or not CODE_RE.match(parts[1].strip()):
        return await m.answer("❗ To‘g‘ri format: /del 123")
    code = parts[1].strip()
    ok = db_delete_movie(code)
    if ok:
        await m.answer(f"🗑️ O‘chirildi: <b>{code}</b>", parse_mode=ParseMode.HTML)
    else:
        await m.answer("❌ Bunday kod topilmadi.")

@router.message(F.video)
async def video_received(m: Message):
    """
    Admin 'Kino qo‘shish' bosib video yuborsa — keyin kod so‘raymiz.
    """
    db_add_user(m.from_user.id)
    if not is_admin(m.from_user.id):
        return  # oddiy user video yuborsa e'tibor bermaymiz

    act = PENDING.get(m.from_user.id)
    if act and act.mode == "add":
        await m.answer("✅ Video keldi. Endi kod yuboring (masalan 123).")
        # videoni vaqtincha saqlab turamiz (reply ishlatmasdan ham qo‘shish uchun)
        # message_id orqali keyin reply qildirish qiyin, shuning uchun oddiy yo‘l:
        # admin /add bilan reply qilsin — eng ishonchli.
        # Shuning uchun bu yerda faqat yo'l ko'rsatamiz.

@router.message(F.text)
async def text_router(m: Message):
    db_add_user(m.from_user.id)
    txt = (m.text or "").strip()

    # Admin “delete mode”da bo‘lsa, yuborgan raqamini o‘chirish deb olamiz
    act = PENDING.get(m.from_user.id)
    if act and act.mode == "del" and CODE_RE.match(txt):
        if not is_admin(m.from_user.id):
            return await m.answer("❌ Siz admin emassiz.")
        ok = db_delete_movie(txt)
        PENDING.pop(m.from_user.id, None)
        if ok:
            return await m.answer(f"🗑️ O‘chirildi: <b>{txt}</b>", parse_mode=ParseMode.HTML)
        return await m.answer("❌ Bunday kod topilmadi.")

    # Oddiy kino kodi
    if CODE_RE.match(txt):
        row = db_get_movie(txt)
        if not row:
            return await m.answer("❌ Bunday kod topilmadi.")
        file_id, caption = row
        return await m.answer_video(video=file_id, caption=caption)

    # Boshqa textlar
    if is_admin(m.from_user.id):
        return await m.answer(
            "Kino kodi yuboring (masalan 1001) yoki /panel.",
            reply_markup=kb_main(True)
        )
    return await m.answer("Kino kodi yuboring (masalan 1001).")


async def main():
    db_init()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)  # ✅ aiogram 3.7+ to‘g‘ri
    )
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
