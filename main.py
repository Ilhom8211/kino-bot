import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

# ====== SOZLAMALAR ======
TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable topilmadi!")

ADMIN_ID = 8429326762          # <-- sizning ID (rasmda ko'rinyapti)
CHANNEL_ID = 0                 # <-- keyin bu yerga -100.... ni qo'yamiz

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ====== KANAL ID NI OLISH UCHUN (ADMIN FORWARD QILSA) ======
@dp.message(F.forward_from_chat)
async def show_chat_id(message: Message):
    if message.from_user is None:
        return
    if message.from_user.id != ADMIN_ID:
        return
    chat = message.forward_from_chat
    await message.answer(f"✅ CHAT_ID: {chat.id}\nEndi CHANNEL_ID joyiga shuni qo'ying.")


# ====== START ======
@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    await message.answer(
        "Salom! Kino kodini yuboring.\n"
        "Admin: videoga reply qilib /add yozing.\n\n"
        "Kanal ID olish: kanaldagi postni menga forward qiling."
    )


# ====== ADD (ADMIN) ======
@dp.message(F.text.startswith("/add"))
async def add_movie(message: Message):
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Siz admin emassiz.")
        return

    if CHANNEL_ID == 0:
        await message.answer("❗ Avval kanal postini menga forward qiling (CHAT_ID chiqadi).")
        return

    if not message.reply_to_message:
        await message.answer("❗ Videoga reply qilib yozing: /add 1001")
        return

    parts = message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❗ To'g'ri yozing: /add 1001")
        return

    code = parts[1]

    # Reply qilingan xabarni kanalga copy qilamiz
    sent = await bot.copy_message(
        chat_id=CHANNEL_ID,
        from_chat_id=message.chat.id,
        message_id=message.reply_to_message.message_id
    )

    # Kod sifatida "siz yozgan code" ishlaydi, lekin saqlash yo'q
    # Shuning uchun kanal post_id ni ham berib qo'yamiz:
    await message.answer(
        f"✅ Kino kanalga saqlandi!\n"
        f"🔢 Siz bergan kod: {code}\n"
        f"🆔 Kanal post ID: {sent.message_id}\n\n"
        f"Eng oson usul: kod sifatida kanal post ID ishlating: {sent.message_id}"
    )


# ====== KINO OLISH (USER KOD YUBORSA) ======
@dp.message(F.text)
async def get_movie(message: Message):
    text = message.text.strip()

    if text.startswith("/"):
        return

    if CHANNEL_ID == 0:
        await message.answer("⚠️ Kanal hali ulanmagan. Admin kanal ID ni o'rnatishi kerak.")
        return

    if not text.isdigit():
        await message.answer("❗ Faqat raqam (kino kodi) yuboring.")
        return

    movie_id = int(text)

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=movie_id
        )
    except Exception:
        await message.answer("❌ Bunday kod topilmadi.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
