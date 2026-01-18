import os
import re
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


DB_PATH = os.getenv("DB_PATH", "data.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # "123,456"
ADMIN_IDS = set()

if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_seen TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL, -- 'video' or 'document'
            caption TEXT,
            added_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


def upsert_user(user: Message):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users(user_id, first_seen) VALUES(?, ?)",
        (user.from_user.id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM movies")
    movies_count = cur.fetchone()[0]
    conn.close()
    return users_count, movies_count


def movie_exists(code: str) -> bool:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM movies WHERE code = ?", (code,))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def add_movie(code: str, file_id: str, file_type: str, caption: str | None):
    conn = db()
    conn.execute(
        "INSERT INTO movies(code, file_id, file_type, caption, added_at) VALUES(?,?,?,?,?)",
        (code, file_id, file_type, caption, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_movie(code: str) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM movies WHERE code = ?", (code,))
    conn.commit()
    cnt = cur.rowcount
    conn.close()
    return cnt


def get_movie(code: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT file_id, file_type, caption FROM movies WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return row  # (file_id, file_type, caption) or None


def set_setting(key: str, value: str):
    conn = db()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_setting(key: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


class AdminFlow(StatesGroup):
    waiting_add_media = State()
    waiting_add_code = State()
    waiting_del_code = State()


def admin_panel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Kino qo‘shish", callback_data="adm:add")
    kb.button(text="🗑 Kino o‘chirish", callback_data="adm:del")
    kb.button(text="📊 Statistika", callback_data="adm:stats")
    kb.button(text="⚙️ Kanal CHAT_ID", callback_data="adm:chatid")
    kb.adjust(2, 2)
    return kb.as_markup()


def cancel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Bekor qilish", callback_data="adm:cancel")
    return kb.as_markup()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env o‘rnatilmagan!")

    init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        upsert_user(m)
        text = "Salom! Kino kodini yuboring.\nMasalan: 1001"
        if is_admin(m.from_user.id):
            text += "\n\nAdmin: /panel"
        await m.answer(text)

    @dp.message(Command("panel"))
    async def panel(m: Message):
        upsert_user(m)
        if not is_admin(m.from_user.id):
            return
        await m.answer("⚙️ Admin panel:", reply_markup=admin_panel_kb())

    @dp.callback_query(F.data == "adm:cancel")
    async def adm_cancel(c: CallbackQuery, state: FSMContext):
        await state.clear()
        await c.message.edit_text("Bekor qilindi.", reply_markup=admin_panel_kb())
        await c.answer()

    @dp.callback_query(F.data == "adm:add")
    async def adm_add(c: CallbackQuery, state: FSMContext):
        if not is_admin(c.from_user.id):
            return await c.answer()
        await state.set_state(AdminFlow.waiting_add_media)
        await c.message.edit_text(
            "➕ Kino qo‘shish:\n"
            "1) Videoni shu yerga yuboring YOKI kanaldan forward qiling.\n"
            "2) Keyin kod so‘rayman.\n\n"
            "❗ Eslatma: dubl kod qo‘shilmaydi.",
            reply_markup=cancel_kb(),
        )
        await c.answer()

    @dp.callback_query(F.data == "adm:del")
    async def adm_del(c: CallbackQuery, state: FSMContext):
        if not is_admin(c.from_user.id):
            return await c.answer()
        await state.set_state(AdminFlow.waiting_del_code)
        await c.message.edit_text("🗑 O‘chirish uchun kodni yuboring (faqat raqam).", reply_markup=cancel_kb())
        await c.answer()

    @dp.callback_query(F.data == "adm:stats")
    async def adm_stats(c: CallbackQuery):
        if not is_admin(c.from_user.id):
            return await c.answer()
        users_count, movies_count = get_stats()
        await c.message.edit_text(
            f"📊 Statistika:\n"
            f"👤 Bot ishlatgan userlar: {users_count}\n"
            f"🎬 Kinolar soni: {movies_count}",
            reply_markup=admin_panel_kb(),
        )
        await c.answer()

    @dp.callback_query(F.data == "adm:chatid")
    async def adm_chatid(c: CallbackQuery):
        if not is_admin(c.from_user.id):
            return await c.answer()
        saved = get_setting("CHANNEL_CHAT_ID")
        msg = "⚙️ Kanal CHAT_ID:\n"
        msg += f"✅ Saqlangan: `{saved}`\n\n" if saved else "❗ Hali saqlanmagan.\n\n"
        msg += "Kanal postini menga forward qiling — men CHAT_ID ni chiqarib saqlab qo‘yaman."
        await c.message.edit_text(msg, reply_markup=admin_panel_kb(), parse_mode="Markdown")
        await c.answer()

    # Admin: kanal postini forward qilsa, CHAT_ID saqlaymiz
    @dp.message(F.forward_from_chat)
    async def forwarded(m: Message, state: FSMContext):
        upsert_user(m)
        if not is_admin(m.from_user.id):
            return

        chat = m.forward_from_chat
        # Kanal bo‘lsa saqlaymiz (lekin majbur emas)
        if chat and str(chat.id).startswith("-100"):
            set_setting("CHANNEL_CHAT_ID", str(chat.id))
            await m.answer(f"✅ Kanal CHAT_ID saqlandi:\n{chat.id}\n📣 {chat.title or ''}")
        # Agar admin kino qo‘shish flow’da bo‘lsa — media sifatida ham ishlatamiz
        st = await state.get_state()
        if st == AdminFlow.waiting_add_media.state:
            file_id = None
            file_type = None
            caption = m.caption

            if m.video:
                file_id = m.video.file_id
                file_type = "video"
            elif m.document:
                file_id = m.document.file_id
                file_type = "document"

            if file_id:
                await state.update_data(file_id=file_id, file_type=file_type, caption=caption)
                await state.set_state(AdminFlow.waiting_add_code)
                await m.answer("Endi kino kodini yuboring (faqat raqam).", reply_markup=cancel_kb())

    # Admin add flow: media qabul qilish
    @dp.message(AdminFlow.waiting_add_media, F.content_type.in_({ContentType.VIDEO, ContentType.DOCUMENT}))
    async def add_media(m: Message, state: FSMContext):
        upsert_user(m)
        if not is_admin(m.from_user.id):
            return

        file_id = None
        file_type = None
        caption = m.caption

        if m.video:
            file_id = m.video.file_id
            file_type = "video"
        elif m.document:
            file_id = m.document.file_id
            file_type = "document"

        if not file_id:
            return await m.answer("Media topilmadi. Video yuboring.", reply_markup=cancel_kb())

        await state.update_data(file_id=file_id, file_type=file_type, caption=caption)
        await state.set_state(AdminFlow.waiting_add_code)
        await m.answer("✅ Media olindi. Endi kodni yuboring (faqat raqam).", reply_markup=cancel_kb())

    # Admin add flow: kod qabul qilish
    @dp.message(AdminFlow.waiting_add_code)
    async def add_code(m: Message, state: FSMContext):
        upsert_user(m)
        if not is_admin(m.from_user.id):
            return

        code = (m.text or "").strip()
        if not re.fullmatch(r"\d{1,10}", code):
            return await m.answer("❗ Kod faqat raqam bo‘lsin. Masalan: 1001", reply_markup=cancel_kb())

        if movie_exists(code):
            await state.clear()
            return await m.answer("⚠️ Bu kod allaqachon mavjud. Boshqa kod bering.", reply_markup=admin_panel_kb())

        data = await state.get_data()
        file_id = data.get("file_id")
        file_type = data.get("file_type")
        caption = data.get("caption")

        if not file_id or not file_type:
            await state.clear()
            return await m.answer("❌ Xatolik: media yo‘q. Qaytadan urinib ko‘ring.", reply_markup=admin_panel_kb())

        add_movie(code, file_id, file_type, caption)
        await state.clear()
        await m.answer(f"✅ Qo‘shildi! Kod: {code}", reply_markup=admin_panel_kb())

    # Admin delete flow
    @dp.message(AdminFlow.waiting_del_code)
    async def del_code(m: Message, state: FSMContext):
        upsert_user(m)
        if not is_admin(m.from_user.id):
            return
        code = (m.text or "").strip()
        if not re.fullmatch(r"\d{1,10}", code):
            return await m.answer("❗ Kod faqat raqam bo‘lsin. Masalan: 1001", reply_markup=cancel_kb())

        cnt = delete_movie(code)
        await state.clear()
        if cnt:
            await m.answer(f"🗑 O‘chirildi: {code}", reply_markup=admin_panel_kb())
        else:
            await m.answer("⚠️ Bunday kod yo‘q.", reply_markup=admin_panel_kb())

    # USER: faqat raqam yuborsa, kino qidiramiz (tugmalar texti bilan aralashmasin)
    @dp.message(F.text.regexp(r"^\d{1,10}$"))
    async def user_code(m: Message):
        upsert_user(m)
        code = m.text.strip()
        row = get_movie(code)
        if not row:
            return await m.answer("❌ Bunday kod topilmadi.")

        file_id, file_type, caption = row
        if file_type == "video":
            await m.answer_video(file_id, caption=caption)
        else:
            await m.answer_document(file_id, caption=caption)

    # USER: boshqa textlar
    @dp.message(F.text)
    async def other_text(m: Message):
        upsert_user(m)
        # admin bo‘lsa, panel eslatamiz
        if is_admin(m.from_user.id) and (m.text or "").strip().lower() in {"panel", "/panel"}:
            return
        await m.answer("Kino kodi yuboring. Masalan: 1001")

    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
