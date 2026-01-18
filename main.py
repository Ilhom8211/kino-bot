import os
import re
import asyncio
from typing import Optional, List

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode

DB_PATH = "db.sqlite3"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # e.g. "8429326762,123456"
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env topilmadi!")

def parse_admin_ids(raw: str) -> List[int]:
    if not raw:
        return []
    out = []
    for p in raw.replace(";", ",").split(","):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out

ADMIN_IDS = set(parse_admin_ids(ADMIN_IDS_RAW))

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ---------- DB ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            first_seen INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS movies(
            code INTEGER PRIMARY KEY,
            file_id TEXT NOT NULL,
            message_id INTEGER,
            added_by INTEGER,
            added_at INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            k TEXT PRIMARY KEY,
            v TEXT
        )
        """)
        await db.commit()

async def set_setting(k: str, v: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
        await db.commit()

async def get_setting(k: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT v FROM settings WHERE k=?", (k,))
        row = await cur.fetchone()
        return row[0] if row else None

async def add_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users(user_id, first_seen) VALUES(?, strftime('%s','now')) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id,)
        )
        await db.commit()

async def stats_counts():
    async with aiosqlite.connect(DB_PATH) as db:
        cur1 = await db.execute("SELECT COUNT(*) FROM users")
        users_count = (await cur1.fetchone())[0]
        cur2 = await db.execute("SELECT COUNT(*) FROM movies")
        movies_count = (await cur2.fetchone())[0]
        return users_count, movies_count

async def get_movie(code: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT code, file_id, message_id FROM movies WHERE code=?",
            (code,)
        )
        return await cur.fetchone()

async def insert_movie(code: int, file_id: str, message_id: Optional[int], added_by: int) -> bool:
    """Return True if inserted, False if code already exists"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO movies(code,file_id,message_id,added_by,added_at) VALUES(?,?,?,?,strftime('%s','now'))",
                (code, file_id, message_id, added_by)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def delete_movie(code: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM movies WHERE code=?", (code,))
        await db.commit()
        return cur.rowcount > 0

# ---------- Admin helper ----------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ---------- UI ----------
def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kino qo‘shish", callback_data="adm_add")],
        [InlineKeyboardButton(text="🗑 Kino o‘chirish", callback_data="adm_del")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📣 Kanalni ulash (forward)", callback_data="adm_setch")],
    ])

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")]
    ])

# ---------- Simple in-memory state (enough for 1-2 admins) ----------
# states: NONE / WAIT_VIDEO / WAIT_CODE / WAIT_DEL_CODE / WAIT_CHANNEL_FORWARD
STATE = {}   # user_id -> str
TEMP = {}    # user_id -> dict

def set_state(uid: int, st: str):
    STATE[uid] = st

def get_state(uid: int) -> str:
    return STATE.get(uid, "NONE")

# ---------- Handlers ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await add_user(message.from_user.id)
    txt = "Salom! Kino kodini yuboring.\nMasalan: <b>1001</b>"
    if is_admin(message.from_user.id):
        txt += "\n\nAdmin: /panel"
    await message.answer(txt)

@dp.message(Command("panel"))
async def cmd_panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Siz admin emassiz.")
    await message.answer("⚙️ Admin panel:", reply_markup=admin_kb())

@dp.callback_query(F.data == "adm_back")
async def cb_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Admin emas.", show_alert=True)
    set_state(call.from_user.id, "NONE")
    TEMP.pop(call.from_user.id, None)
    await call.message.edit_text("⚙️ Admin panel:", reply_markup=admin_kb())
    await call.answer()

@dp.callback_query(F.data == "adm_stats")
async def cb_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Admin emas.", show_alert=True)
    u, m = await stats_counts()
    await call.message.edit_text(
        f"📊 <b>Statistika</b>\n\n👤 Foydalanuvchilar: <b>{u}</b>\n🎬 Kinolar: <b>{m}</b>",
        reply_markup=back_kb()
    )
    await call.answer()

@dp.callback_query(F.data == "adm_setch")
async def cb_set_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Admin emas.", show_alert=True)
    set_state(call.from_user.id, "WAIT_CHANNEL_FORWARD")
    await call.message.edit_text(
        "📣 Kanalni ulash:\n\n"
        "1) Kanalda biror post tashlang\n"
        "2) O‘sha postni <b>kanaldan menga forward qiling</b>\n\n"
        "Shunda men CHAT_ID ni olib saqlayman.",
        reply_markup=back_kb()
    )
    await call.answer()

@dp.callback_query(F.data == "adm_add")
async def cb_add(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Admin emas.", show_alert=True)
    set_state(call.from_user.id, "WAIT_VIDEO")
    TEMP[call.from_user.id] = {}
    await call.message.edit_text(
        "➕ Kino qo‘shish:\n\n"
        "1) Video yuboring (yoki existing videoni forward qiling)\n"
        "2) Keyin men sizdan kod so‘rayman.",
        reply_markup=back_kb()
    )
    await call.answer()

@dp.callback_query(F.data == "adm_del")
async def cb_del(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Admin emas.", show_alert=True)
    set_state(call.from_user.id, "WAIT_DEL_CODE")
    await call.message.edit_text(
        "🗑 Kino o‘chirish:\n\nO‘chirmoqchi bo‘lgan kino kodini yozing. (Masalan: 1001)",
        reply_markup=back_kb()
    )
    await call.answer()

@dp.message(F.video)
async def on_video(message: Message):
    uid = message.from_user.id
    if not is_admin(uid):
        return  # oddiy user video yuborsa e'tibor bermaymiz
    if get_state(uid) != "WAIT_VIDEO":
        return
    # save file_id
    TEMP.setdefault(uid, {})
    TEMP[uid]["file_id"] = message.video.file_id
    set_state(uid, "WAIT_CODE")
    await message.answer("✅ Video qabul qilindi. Endi kino kodini yuboring (faqat raqam).")

@dp.message(F.text)
async def on_text(message: Message):
    uid = message.from_user.id
    text = (message.text or "").strip()

    await add_user(uid)

    # --- Admin states ---
    if is_admin(uid):
        st = get_state(uid)

        # waiting channel forward
        if st == "WAIT_CHANNEL_FORWARD":
            fchat = message.forward_from_chat
            if not fchat:
                return await message.answer("❗ Bu forward emas. Kanal postini <b>forward</b> qilib yuboring.")
            await set_setting("channel_id", str(fchat.id))
            set_state(uid, "NONE")
            await message.answer(f"✅ Kanal CHAT_ID saqlandi: <code>{fchat.id}</code>\n📣 {fchat.title or ''}")

        # waiting code after video
        elif st == "WAIT_CODE":
            if not text.isdigit():
                return await message.answer("❗ Kod faqat raqam bo‘lsin. Masalan: 1001")
            code = int(text)
            file_id = TEMP.get(uid, {}).get("file_id")
            if not file_id:
                set_state(uid, "WAIT_VIDEO")
                return await message.answer("Video topilmadi. Qaytadan video yuboring.")
            channel_id = await get_setting("channel_id")
            msg_id = None

            # If channel is set, also post to channel (optional)
            if channel_id:
                try:
                    sent = await bot.send_video(chat_id=int(channel_id), video=file_id, caption=f"Kino kodi: {code}")
                    msg_id = sent.message_id
                except Exception:
                    # channel posting failed -> continue anyway
                    msg_id = None

            ok = await insert_movie(code=code, file_id=file_id, message_id=msg_id, added_by=uid)
            set_state(uid, "NONE")
            TEMP.pop(uid, None)

            if not ok:
                return await message.answer("⚠️ Bu kod bilan kino allaqachon mavjud.")
            return await message.answer(f"✅ Qo‘shildi! Kod: <b>{code}</b>")

        # waiting delete code
        elif st == "WAIT_DEL_CODE":
            if not text.isdigit():
                return await message.answer("❗ Kod faqat raqam bo‘lsin. Masalan: 1001")
            code = int(text)
            ok = await delete_movie(code)
            set_state(uid, "NONE")
            if ok:
                return await message.answer(f"✅ O‘chirildi: <b>{code}</b>")
            else:
                return await message.answer("⚠️ Bunday kod topilmadi.")

    # --- User movie search ---
    if text.isdigit():
        code = int(text)
        row = await get_movie(code)
        if not row:
            return await message.answer("❌ Bunday kod topilmadi.")
        _, file_id, message_id = row

        channel_id = await get_setting("channel_id")
        # If we have channel & message_id -> copy from channel (nicer)
        if channel_id and message_id:
            try:
                return await bot.copy_message(chat_id=uid, from_chat_id=int(channel_id), message_id=int(message_id))
            except Exception:
                pass
        # fallback: send by file_id
        return await message.answer_video(video=file_id)

    # default text
    await message.answer("Kino kodini yuboring. Masalan: 1001")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
