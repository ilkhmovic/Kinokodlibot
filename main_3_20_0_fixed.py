import os
import json
import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

# Logging sozlash
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = "7674234953:AAElS6zcapmZ0Js_ZRubLFsvMXXPquezvJI"
CHANNEL_ID = -1002654125887  # Kinolar saqlanadigan kanal ID si
ADMIN_PASSWORD = "admin123"  # Admin paroli

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# JSON fayllar mavjudligini tekshiradi, yo'q bo'lsa yaratadi
def ensure_file(filename, default_data):
    try:
        if not os.path.exists(filename):
            with open(filename, "w", encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
        logger.info(f"{filename} fayli tayyor")
    except Exception as e:
        logger.error(f"{filename} faylini yaratishda xatolik: {e}")

ensure_file("data.json", {})
ensure_file("admins.json", [])
ensure_file("channels.json", [])
ensure_file("statistics.json", {})
ensure_file("movie_info.json", {})

# JSON yuklash va saqlash
def load_json(filename):
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"{filename} faylini yuklashda xatolik: {e}")
        return {} if filename == "data.json" else []

def save_json(filename, data):
    try:
        with open(filename, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"{filename} fayli saqlandi")
    except Exception as e:
        logger.error(f"{filename} faylini saqlashda xatolik: {e}")

film_data = load_json("data.json")
admins = load_json("admins.json")
channels = load_json("channels.json")
statistics = load_json("statistics.json")
movie_info = load_json("movie_info.json")

# Global o'zgaruvchilar
waiting_for_password = set()
waiting_for_channel = set()
waiting_for_code_data = {}
waiting_for_movie_info = {}
users_count = set()  # Foydalanuvchilar soni uchun

# Admin klaviaturasi
def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo'shish"), KeyboardButton(text="📝 Video tasnifi")],
            [KeyboardButton(text="📢 Kanal qo'shish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🗑 Kanal o'chirish"), KeyboardButton(text="🗑 Video o'chirish")],
            [KeyboardButton(text="🗑 Ma'lumot o'chirish"), KeyboardButton(text="❌ Tugmalarni yopish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# URL dan kanal ID va message ID ni ajratib olish
def parse_telegram_url(url):
    try:
        if '/c/' in url:
            match = re.search(r'/c/(\d+)/(\d+)', url)
            if match:
                channel_id = f"-100{match.group(1)}"
                message_id = int(match.group(2))
                return channel_id, message_id
        else:
            match = re.search(r't\.me/([^/]+)/(\d+)', url)
            if match:
                username = f"@{match.group(1)}"
                message_id = int(match.group(2))
                return username, message_id
        return None, None
    except Exception as e:
        logger.error(f"URL parse qilishda xatolik: {e}")
        return None, None

# Admin ro'yxatdan o'tish
@dp.message(Command("add_admin"))
async def register_admin(message: types.Message):
    try:
        user_id = message.from_user.id
        waiting_for_password.add(user_id)
        await message.reply("Iltimos, admin parolini kiriting:")
        logger.info(f"User {user_id} admin parolini so'rayapti")
    except Exception as e:
        logger.error(f"register_admin xatolik: {e}")
        await message.reply("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

# Start komandasi
@dp.message(Command("start"))
async def start_command(message: types.Message):
    try:
        user_id = message.from_user.id

        # Foydalanuvchi sonini hisoblash
        users_count.add(user_id)

        # Agar admin bo'lsa, admin tugmalarini ko'rsatish
        if user_id in admins:
            await message.reply(
                "👨‍💼 Admin paneliga xush kelibsiz!\n"
                "Quyidagi tugmalardan foydalaning:",
                reply_markup=get_admin_keyboard()
            )
            return

        # Obuna tekshirish va tugmalar tayyorlash
        if channels:
            # Telegram kanallari va boshqa ijtimoiy tarmoqlarni ajratish
            telegram_channels = [ch for ch in channels if str(ch).startswith('@') or str(ch).startswith('-') or str(ch).isdigit()]
            other_links = [ch for ch in channels if not (str(ch).startswith('@') or str(ch).startswith('-') or str(ch).isdigit())]

            # Telegram kanallari uchun obuna tekshirish
            all_ok = True
            for ch_id in telegram_channels:
                try:
                    member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                    if member.status in ["left", "kicked"]:
                        all_ok = False
                        break
                except Exception as e:
                    logger.error(f"Obuna tekshirishda xatolik {ch_id}: {e}")
                    if "chat not found" in str(e).lower():
                        if ch_id in channels:
                            channels.remove(ch_id)
                            save_json("channels.json", channels)
                    all_ok = False
                    break

            # Agar Telegram kanallariga obuna bo‘lmasa yoki boshqa ijtimoiy tarmoqlar bo‘lsa
            if not all_ok or other_links:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[])

                # Telegram kanallari uchun tugmalar
                for ch_id in telegram_channels:
                    try:
                        chat_info = await bot.get_chat(ch_id)
                        channel_name = chat_info.title if chat_info.title else "Kanal"
                        if str(ch_id).startswith('-100'):
                            channel_id = str(ch_id)[4:]
                            invite_link = f"https://t.me/c/{channel_id}/1"
                        elif str(ch_id).startswith('@'):
                            invite_link = f"https://t.me/{str(ch_id)[1:]}"
                        else:
                            invite_link = f"https://t.me/{ch_id}"
                        keyboard.inline_keyboard.append([
                            InlineKeyboardButton(text=f"📢 {channel_name}", url=invite_link)
                        ])
                    except Exception as e:
                        logger.error(f"Kanal ma'lumotlarini olishda xatolik {ch_id}: {e}")
                        if str(ch_id).startswith('-100'):
                            channel_id = str(ch_id)[4:]
                            backup_link = f"https://t.me/c/{channel_id}/1"
                        else:
                            backup_link = f"https://t.me/{ch_id}"
                        keyboard.inline_keyboard.append([
                            InlineKeyboardButton(text="📢 Telegram", url=backup_link)
                        ])

                # Boshqa ijtimoiy tarmoqlar uchun tugmalar
                for ch_id in other_links:
                    if 'instagram.com/' in str(ch_id).lower():
                        button_text = "📷 Instagram"
                    elif 'facebook.com/' in str(ch_id).lower() or 'fb.com/' in str(ch_id).lower():
                        button_text = "📘 Facebook"
                    elif 'twitter.com/' in str(ch_id).lower() or 'x.com/' in str(ch_id).lower():
                        button_text = "🐦 Twitter"
                    elif 'youtube.com/' in str(ch_id).lower() or 'youtu.be/' in str(ch_id).lower():
                        button_text = "📺 YouTube"
                    elif 'tiktok.com/' in str(ch_id).lower():
                        button_text = "🎵 TikTok"
                    else:
                        button_text = "🔗 Follow"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=button_text, url=str(ch_id))
                    ])

                # Obuna tekshirish tugmasi (faqat Telegram kanallari uchun)
                if telegram_channels:
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text="✅ Obuna tekshirish", callback_data="check_subscription")
                    ])

                # Xabar matni
                msg = "👋 Salom! Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling:\n\n"
                if telegram_channels:
                    msg += "📺 Telegram kanallariga obuna bo‘lgandan keyin ✅ Obuna tekshirish tugmasini bosing\n"
                if other_links:
                    msg += "🌐 Boshqa ijtimoiy tarmoqlarga obuna bo‘ling\n"
                msg += "🎬 Keyin kino kodini yuboring"

                await message.reply(msg, reply_markup=keyboard)
                return

        # Agar obuna talab qilinmasa yoki barcha Telegram kanallariga obuna bo‘lingan bo‘lsa
        await message.reply("👋 Salom! Kino kodini yuboring.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"Start komandasi: {user_id}")
    except Exception as e:
        logger.error(f"start_command xatolik: {e}")
        await message.reply("❌ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")

# Admin tugmalarini boshqarish
@dp.message(lambda message: message.text in ["🎬 Kino qo'shish", "📝 Video tasnifi", "📢 Kanal qo'shish", "📊 Statistika", "🗑 Kanal o'chirish", "🗑 Video o'chirish", "🗑 Ma'lumot o'chirish", "❌ Tugmalarni yopish"])
async def handle_admin_buttons(message: types.Message):
    try:
        user_id = message.from_user.id

        if user_id not in admins:
            await message.reply("❌ Sizda admin huquqlari yo'q.")
            return

        text = message.text

        if text == "🎬 Kino qo'shish":
            await message.reply(
                "Kino qo'shish uchun kod va video ma'lumotlarini yuboring:\n\n"
                "Format: kod message_id\n"
                "yoki\n"
                "Format: kod https://t.me/kanal/123\n\n"
                "Misol: 123 456\n"
                "yoki: 123 https://t.me/kinolar/456"
            )
            waiting_for_code_data[user_id] = True

        elif text == "📝 Video tasnifi":
            await message.reply(
                "Video tasnifi qo'shish uchun ma'lumotlarni yuboring:\n\n"
                "Format: kod Nomi|Janri|Tili|Davomiyligi\n\n"
                "Misol: 123 Spiderman|Fantastika|Ingliz tili|2 soat 30 daqiqa"
            )
            waiting_for_movie_info[user_id] = True

        elif text == "📢 Kanal qo'shish":
            await message.reply(
                "Kanal ID yoki linkini yuboring:\n\n"
                "📺 Telegram kanali: -1001234567890 yoki @kanalname\n"
                "📷 Instagram: https://instagram.com/username\n"
                "📘 Facebook: https://facebook.com/username\n"
                "🐦 Twitter: https://twitter.com/username\n"
                "📺 YouTube: https://youtube.com/@username"
            )
            waiting_for_channel.add(user_id)

        elif text == "📊 Statistika":
            total_movies = len(film_data)
            total_downloads = sum(stats.get("downloads", 0) for stats in statistics.values())
            total_channels = len(channels)
            total_users = len(users_count)

            stats_text = (
                f"📊 **Bot Statistikasi**\n\n"
                f"👥 Jami foydalanuvchilar: {total_users}\n"
                f"🎬 Jami kinolar: {total_movies}\n"
                f"⬇️ Jami yuklab olishlar: {total_downloads}\n"
                f"📢 Kanallar soni: {total_channels}\n"
                f"👨‍💼 Adminlar soni: {len(admins)}"
            )

            if statistics:
                stats_text += "\n\n📈 **Eng ommabop kinolar:**\n"
                sorted_movies = sorted(statistics.items(), key=lambda x: x[1].get("downloads", 0), reverse=True)[:5]
                for i, (code, stats) in enumerate(sorted_movies, 1):
                    movie_name = movie_info.get(code, {}).get("name", f"Kod: {code}")
                    downloads = stats.get("downloads", 0)
                    stats_text += f"{i}. {movie_name} - {downloads} marta\n"

            await message.reply(stats_text)

        elif text == "🗑 Kanal o'chirish":
            if not channels:
                await message.reply("❌ Hech qanday kanal mavjud emas.")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for ch_id in channels:
                try:
                    if str(ch_id).startswith('@') or str(ch_id).startswith('-') or str(ch_id).isdigit():
                        try:
                            chat_info = await bot.get_chat(ch_id)
                            channel_name = f"📺 {chat_info.title}" if chat_info.title else f"📺 {str(ch_id)}"
                        except:
                            channel_name = f"📺 {str(ch_id)}"
                    else:
                        if 'instagram.com/' in str(ch_id).lower():
                            channel_name = f"📷 Instagram: {str(ch_id).split('/')[-1]}"
                        elif 'facebook.com/' in str(ch_id).lower() or 'fb.com/' in str(ch_id).lower():
                            channel_name = f"📘 Facebook: {str(ch_id).split('/')[-1]}"
                        elif 'twitter.com/' in str(ch_id).lower() or 'x.com/' in str(ch_id).lower():
                            channel_name = f"🐦 Twitter: {str(ch_id).split('/')[-1]}"
                        elif 'youtube.com/' in str(ch_id).lower() or 'youtu.be/' in str(ch_id).lower():
                            channel_name = f"📺 YouTube: {str(ch_id).split('/')[-1]}"
                        elif 'tiktok.com/' in str(ch_id).lower():
                            channel_name = f"🎵 TikTok: {str(ch_id).split('/')[-1]}"
                        else:
                            channel_name = f"🔗 {str(ch_id)}"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=f"🗑 {channel_name}", callback_data=f"delete_channel_{ch_id}")
                    ])
                except Exception as e:
                    logger.error(f"Kanal nomini olishda xatolik {ch_id}: {e}")
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=f"🗑 {str(ch_id)}", callback_data=f"delete_channel_{ch_id}")
                    ])

            await message.reply("O'chirish uchun kanalni tanlang:", reply_markup=keyboard)

        elif text == "🗑 Video o'chirish":
            if not film_data:
                await message.reply("❌ Hech qanday video mavjud emas.")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for code, video_data in film_data.items():
                movie_name = movie_info.get(code, {}).get("name", f"Kod: {code}")
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=f"🗑 {movie_name}", callback_data=f"delete_video_{code}")
                ])

            await message.reply("O'chirish uchun videoni tanlang:", reply_markup=keyboard)

        elif text == "🗑 Ma'lumot o'chirish":
            if not movie_info:
                await message.reply("❌ Hech qanday ma'lumot mavjud emas.")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for code, info in movie_info.items():
                movie_name = info.get("name", f"Kod: {code}")
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text=f"🗑 {movie_name}", callback_data=f"delete_info_{code}")
                ])

            await message.reply("O'chirish uchun ma'lumotni tanlang:", reply_markup=keyboard)

        elif text == "❌ Tugmalarni yopish":
            await message.reply("Admin tugmalari yopildi.", reply_markup=ReplyKeyboardRemove())

    except Exception as e:
        logger.error(f"handle_admin_buttons xatolik: {e}")
        await message.reply("❌ Xatolik yuz berdi.")

# Barcha matnli xabarlarni qayta ishlash
@dp.message()
async def handle_text(message: types.Message):
    try:
        user_id = message.from_user.id
        text = message.text.strip()

        # Foydalanuvchi sonini yangilash
        users_count.add(user_id)

        # Admin parol kutilayotgan bo'lsa
        if user_id in waiting_for_password:
            if text == ADMIN_PASSWORD:
                if user_id not in admins:
                    admins.append(user_id)
                    save_json("admins.json", admins)
                    await message.reply("✅ Siz admin bo'ldingiz!", reply_markup=get_admin_keyboard())
                    logger.info(f"Yangi admin: {user_id}")
                else:
                    await message.reply("Siz allaqachon adminsiz.", reply_markup=get_admin_keyboard())
            else:
                await message.reply("❌ Parol noto'g'ri.")
            waiting_for_password.remove(user_id)
            return

        # Kanal qo'shish kutilayotgan bo'lsa
        if user_id in waiting_for_channel:
            if user_id not in admins:
                await message.reply("❌ Sizda admin huquqlari yo'q.")
                waiting_for_channel.remove(user_id)
                return

            is_valid = False
            if text.startswith('@') or (text.startswith('-') and text[1:].isdigit()) or text.isdigit():
                is_valid = True
            elif 'instagram.com/' in text.lower():
                is_valid = True
            elif 'facebook.com/' in text.lower() or 'fb.com/' in text.lower():
                is_valid = True
            elif 'twitter.com/' in text.lower() or 'x.com/' in text.lower():
                is_valid = True
            elif 'youtube.com/' in text.lower() or 'youtu.be/' in text.lower():
                is_valid = True
            elif 'tiktok.com/' in text.lower():
                is_valid = True

            if is_valid:
                if text not in channels:
                    channels.append(text)
                    save_json("channels.json", channels)

                    if text.startswith('@') or text.startswith('-') or text.isdigit():
                        link_type = "📺 Telegram kanali"
                    elif 'instagram.com/' in text.lower():
                        link_type = "📷 Instagram sahifasi"
                    elif 'facebook.com/' in text.lower() or 'fb.com/' in text.lower():
                        link_type = "📘 Facebook sahifasi"
                    elif 'twitter.com/' in text.lower() or 'x.com/' in text.lower():
                        link_type = "🐦 Twitter sahifasi"
                    elif 'youtube.com/' in text.lower() or 'youtu.be/' in text.lower():
                        link_type = "📺 YouTube kanali"
                    elif 'tiktok.com/' in text.lower():
                        link_type = "🎵 TikTok sahifasi"
                    else:
                        link_type = "🔗 Link"

                    await message.reply(f"✅ {link_type} qo'shildi: {text}")
                    logger.info(f"Kanal qo'shildi: {text}")
                else:
                    await message.reply("❗ Bu link allaqachon mavjud.")
            else:
                await message.reply(
                    "❌ Noto'g'ri format!\n\n"
                    "Quyidagi formatlardan foydalaning:\n"
                    "📺 Telegram: -1001234567890 yoki @kanalname\n"
                    "📷 Instagram: https://instagram.com/username\n"
                    "📘 Facebook: https://facebook.com/username\n"
                    "🐦 Twitter: https://twitter.com/username\n"
                    "📺 YouTube: https://youtube.com/@username"
                )
            waiting_for_channel.remove(user_id)
            return

        # Kino qo'shish kutilayotgan bo'lsa
        if user_id in waiting_for_code_data:
            if user_id not in admins:
                await message.reply("❌ Sizda admin huquqlari yo'q.")
                del waiting_for_code_data[user_id]
                return

            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await message.reply("❌ Format noto'g'ri. Misol: 123 456 yoki 123 https://t.me/kanal/456")
                return

            code = parts[0]
            value = parts[1]

            if value.startswith('https://t.me/'):
                film_data[code] = value
                save_json("data.json", film_data)
                if code not in statistics:
                    statistics[code] = {"downloads": 0}
                    save_json("statistics.json", statistics)
                await message.reply(f"✅ Kino kodi '{code}' URL bilan saqlandi.")
                logger.info(f"Kino URL qo'shildi: {code} -> {value}")
            else:
                try:
                    msg_id = int(value)
                    film_data[code] = msg_id
                    save_json("data.json", film_data)
                    if code not in statistics:
                        statistics[code] = {"downloads": 0}
                    save_json("statistics.json", statistics)
                    await message.reply(f"✅ Kino kodi '{code}' message ID bilan saqlandi.")
                    logger.info(f"Kino qo'shildi: {code} -> {msg_id}")
                except ValueError:
                    await message.reply("❌ Message ID raqam bo'lishi kerak yoki to'g'ri URL kiriting.")
            del waiting_for_code_data[user_id]
            return

        # Video tasnifi kutilayotgan bo'lsa
        if user_id in waiting_for_movie_info:
            if user_id not in admins:
                await message.reply("❌ Sizda admin huquqlari yo'q.")
                del waiting_for_movie_info[user_id]
                return

            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await message.reply("❌ Format noto'g'ri. Misol: 123 Spiderman|Fantastika|Ingliz tili|2 soat")
                return

            code = parts[0]
            info_text = parts[1]

            if code not in film_data:
                await message.reply("❌ Bu kod mavjud emas. Avval kino qo'shing.")
                return

            try:
                info_parts = info_text.split('|')
                if len(info_parts) != 4:
                    await message.reply("❌ Ma'lumotlar to'liq emas. Format: Nomi|Janri|Tili|Davomiyligi")
                    return

                movie_info[code] = {
                    "name": info_parts[0].strip(),
                    "genre": info_parts[1].strip(),
                    "language": info_parts[2].strip(),
                    "duration": info_parts[3].strip()
                }
                save_json("movie_info.json", movie_info)

                await message.reply(f"✅ Kino ma'lumotlari saqlandi:\n\n"
                                  f"🎬 **{movie_info[code]['name']}**\n"
                                  f"🎭 Janri: {movie_info[code]['genre']}\n"
                                  f"🌐 Tili: {movie_info[code]['language']}\n"
                                  f"⏱ Davomiyligi: {movie_info[code]['duration']}")
                logger.info(f"Kino ma'lumotlari qo'shildi: {code}")
            except Exception as e:
                logger.error(f"Ma'lumot qo'shishda xatolik: {e}")
                await message.reply("❌ Ma'lumot qo'shishda xatolik.")
            del waiting_for_movie_info[user_id]
            return

        # Agar bu raqam (kod) bo'lsa
        if text.isdigit():
            # Har safar avval obuna tekshirish
            if channels:
                telegram_channels = [ch for ch in channels if str(ch).startswith('@') or str(ch).startswith('-') or str(ch).isdigit()]
                all_ok = True
                for ch_id in telegram_channels:
                    try:
                        member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                        if member.status in ["left", "kicked"]:
                            all_ok = False
                            break
                    except Exception as e:
                        logger.error(f"Obuna tekshirishda xatolik {ch_id}: {e}")
                        if "chat not found" in str(e).lower():
                            if ch_id in channels:
                                channels.remove(ch_id)
                                save_json("channels.json", channels)
                        all_ok = False
                        break

                if not all_ok:
                    await handle_code(message, text)
                    return

            await send_video_with_info(message, text)
        else:
            await message.reply("❓ Noma'lum buyruq. Kino kodini yuboring yoki /start bosing.")
    except Exception as e:
        logger.error(f"handle_text xatolik: {e}")
        try:
            await message.reply("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
        except:
            pass

async def handle_code(message: types.Message, code: str):
    try:
        user_id = message.from_user.id

        if code not in film_data:
            await message.reply("❌ Bu kod bo'yicha kino topilmadi.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for ch_id in channels:
            try:
                if str(ch_id).startswith('@') or str(ch_id).startswith('-') or str(ch_id).isdigit():
                    chat_info = await bot.get_chat(ch_id)
                    channel_name = chat_info.title if chat_info.title else "Kanal"
                    if str(ch_id).startswith('-100'):
                        channel_id = str(ch_id)[4:]
                        invite_link = f"https://t.me/c/{channel_id}/1"
                    elif str(ch_id).startswith('@'):
                        invite_link = f"https://t.me/{str(ch_id)[1:]}"
                    else:
                        invite_link = f"https://t.me/{ch_id}"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=f"📢 {channel_name}", url=invite_link)
                    ])
                else:
                    if 'instagram.com/' in str(ch_id).lower():
                        button_text = "📷 Instagram"
                    elif 'facebook.com/' in str(ch_id).lower() or 'fb.com/' in str(ch_id).lower():
                        button_text = "📘 Facebook"
                    elif 'twitter.com/' in str(ch_id).lower() or 'x.com/' in str(ch_id).lower():
                        button_text = "🐦 Twitter"
                    elif 'youtube.com/' in str(ch_id).lower() or 'youtu.be/' in str(ch_id).lower():
                        button_text = "📺 YouTube"
                    elif 'tiktok.com/' in str(ch_id).lower():
                        button_text = "🎵 TikTok"
                    else:
                        button_text = "🔗 Follow"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=button_text, url=str(ch_id))
                    ])
            except Exception as e:
                logger.error(f"Kanal ma'lumotlarini olishda xatolik {ch_id}: {e}")
                if str(ch_id).startswith('-100'):
                    channel_id = str(ch_id)[4:]
                    backup_link = f"https://t.me/c/{channel_id}/1"
                else:
                    backup_link = f"https://t.me/{ch_id}"
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="📢 Kanalga obuna", url=backup_link)
                ])

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"check_{code}")
        ])

        await message.reply("📺 Kino olish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"handle_code xatolik: {e}")
        await message.reply("❌ Xatolik yuz berdi.")

async def send_video_with_info(message: types.Message, code: str):
    try:
        user_id = message.from_user.id

        if code not in film_data:
            await message.reply("❌ Bu kod bo'yicha kino topilmadi.")
            return

        video_data = film_data[code]

        if code not in statistics:
            statistics[code] = {"downloads": 0}
        statistics[code]["downloads"] += 1
        save_json("statistics.json", statistics)

        caption = ""
        if code in movie_info:
            info = movie_info[code]
            downloads = statistics[code]["downloads"]
            caption = (
                f"🎬 **{info['name']}**\n\n"
                f"🎭 Janri: {info['genre']}\n"
                f"🌐 Tili: {info['language']}\n"
                f"⏱ Davomiyligi: {info['duration']}\n"
                f"📊 Yuklab olishlar: {downloads}"
            )

        try:
            if isinstance(video_data, str) and video_data.startswith('https://t.me/'):
                channel_id, message_id = parse_telegram_url(video_data)
                if channel_id and message_id:
                    try:
                        await bot.copy_message(
                            chat_id=user_id,
                            from_chat_id=channel_id,
                            message_id=message_id,
                            caption=caption,
                            parse_mode="Markdown"
                        )
                        logger.info(f"Video copy qilindi: {code} -> {user_id}")
                    except Exception as e:
                        logger.error(f"Copy qilishda xatolik: {e}")
                        if caption:
                            await message.reply(f"{caption}\n\n🎬 Videoni ko'rish uchun: {video_data}", parse_mode="Markdown")
                        else:
                            await message.reply(f"🎬 Videoni ko'rish uchun: {video_data}")
                else:
                    if caption:
                        await message.reply(f"{caption}\n\n🎬 Videoni ko'rish uchun: {video_data}", parse_mode="Markdown")
                    else:
                        await message.reply(f"🎬 Videoni ko'rish uchun: {video_data}")
            else:
                try:
                    await bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=CHANNEL_ID,
                        message_id=video_data,
                        caption=caption,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Video copy qilindi: {code} -> {user_id}")
                except Exception as e:
                    logger.error(f"Copy qilishda xatolik: {e}")
                    await bot.forward_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=video_data)
                    if caption:
                        await bot.send_message(chat_id=user_id, text=caption, parse_mode="Markdown")

            logger.info(f"Kino yuborildi: {code} -> {user_id}")
        except Exception as e:
            logger.error(f"Kino yuborishda xatolik: {e}")
            await message.reply("❌ Kino yuborishda xatolik yuz berdi.")
    except Exception as e:
        logger.error(f"send_video_with_info xatolik: {e}")
        await message.reply("❌ Xatolik yuz berdi.")

# Start dan obuna tekshirish
@dp.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription_from_start(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id

        all_ok = True
        not_subscribed_channels = []

        telegram_channels = [ch for ch in channels if str(ch).startswith('@') or str(ch).startswith('-') or str(ch).isdigit()]

        for ch_id in telegram_channels:
            try:
                member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                if member.status in ["left", "kicked"]:
                    all_ok = False
                    not_subscribed_channels.append(ch_id)
            except Exception as e:
                logger.error(f"Obuna tekshirishda xatolik {ch_id}: {e}")
                if "chat not found" in str(e).lower():
                    logger.warning(f"Kanal {ch_id} topilmadi, ro'yxatdan o'chirilmoqda")
                    if ch_id in channels:
                        channels.remove(ch_id)
                        save_json("channels.json", channels)
                else:
                    all_ok = False
                    not_subscribed_channels.append(ch_id)

        if all_ok:
            await callback_query.message.edit_text(
                "✅ Telegram kanallariga obuna tasdiqlandi!\n\n"
                "🎬 Endi kino kodini yuboring va kino oling!"
            )
            logger.info(f"Start obuna tasdiqlandi: {user_id}")
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for ch_id in not_subscribed_channels:
                try:
                    chat_info = await bot.get_chat(ch_id)
                    channel_name = chat_info.title if chat_info.title else "Kanal"
                    if str(ch_id).startswith('-100'):
                        channel_id = str(ch_id)[4:]
                        invite_link = f"https://t.me/c/{channel_id}/1"
                    elif str(ch_id).startswith('@'):
                        invite_link = f"https://t.me/{str(ch_id)[1:]}"
                    else:
                        invite_link = f"https://t.me/{ch_id}"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=f"📢 {channel_name}", url=invite_link)
                    ])
                except:
                    invite_link = f"https://t.me/{str(ch_id)[1:]}" if str(ch_id).startswith('@') else f"https://t.me/c/{str(ch_id)[4:]}/1"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text="📢 Kanal", url=invite_link)
                    ])
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Qayta tekshirish", callback_data="check_subscription")
            ])
            await callback_query.message.edit_text(
                "❌ Quyidagi Telegram kanallariga hali obuna bo‘lmagansiz:",
                reply_markup=keyboard
            )
            await callback_query.answer("Iltimos, barcha Telegram kanallariga obuna bo‘ling!", show_alert=True)
    except Exception as e:
        logger.error(f"check_subscription_from_start xatolik: {e}")
        await callback_query.answer("❌ Xatolik yuz berdi.", show_alert=True)

# Obuna tekshirish (kino uchun)
@dp.callback_query(lambda c: c.data.startswith("check_"))
async def process_check(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        code = callback_query.data.split("_")[1]

        if code not in film_data:
            await callback_query.answer("❌ Kod topilmadi.", show_alert=True)
            return

        all_ok = True
        not_subscribed_channels = []

        telegram_channels = [ch for ch in channels if str(ch).startswith('@') or str(ch).startswith('-') or str(ch).isdigit()]

        for ch_id in telegram_channels:
            try:
                member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                if member.status in ["left", "kicked"]:
                    all_ok = False
                    not_subscribed_channels.append(ch_id)
            except Exception as e:
                logger.error(f"Obuna tekshirishda xatolik {ch_id}: {e}")
                if "chat not found" in str(e).lower():
                    logger.warning(f"Kanal {ch_id} topilmadi, ro'yxatdan o'chirilmoqda")
                    if ch_id in channels:
                        channels.remove(ch_id)
                        save_json("channels.json", channels)
                else:
                    all_ok = False
                    not_subscribed_channels.append(ch_id)

        if all_ok:
            await callback_query.message.edit_text("✅ Obuna tasdiqlandi!")

            video_data = film_data[code]

            if code not in statistics:
                statistics[code] = {"downloads": 0}
            statistics[code]["downloads"] += 1
            save_json("statistics.json", statistics)

            caption = ""
            if code in movie_info:
                info = movie_info[code]
                downloads = statistics[code]["downloads"]
                caption = (f"🎬 **{info['name']}**\n\n"
                          f"🎭 Janri: {info['genre']}\n"
                          f"🌐 Tili: {info['language']}\n"
                          f"⏱ Davomiyligi: {info['duration']}\n"
                          f"📊 Yuklab olishlar: {downloads}")

            try:
                if isinstance(video_data, str) and video_data.startswith('https://t.me/'):
                    channel_id, message_id = parse_telegram_url(video_data)
                    if channel_id and message_id:
                        try:
                            await bot.copy_message(
                                chat_id=user_id,
                                from_chat_id=channel_id,
                                message_id=message_id,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.error(f"Copy qilishda xatolik: {e}")
                            if caption:
                                await bot.send_message(chat_id=user_id, text=f"{caption}\n\n🎬 Videoni ko'rish uchun: {video_data}", parse_mode="Markdown")
                            else:
                                await bot.send_message(chat_id=user_id, text=f"🎬 Videoni ko'rish uchun: {video_data}")
                    else:
                        if caption:
                            await bot.send_message(chat_id=user_id, text=f"{caption}\n\n🎬 Videoni ko'rish uchun: {video_data}", parse_mode="Markdown")
                        else:
                            await bot.send_message(chat_id=user_id, text=f"🎬 Videoni ko'rish uchun: {video_data}")
                else:
                    try:
                        await bot.copy_message(
                            chat_id=user_id,
                            from_chat_id=CHANNEL_ID,
                            message_id=video_data,
                            caption=caption,
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.error(f"Copy qilishda xatolik: {e}")
                        await bot.forward_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=video_data)
                        if caption:
                            await bot.send_message(chat_id=user_id, text=caption, parse_mode="Markdown")

                logger.info(f"Obuna tasdiqlandi: {code} -> {user_id}")
            except Exception as e:
                logger.error(f"Kino yuborishda xatolik: {e}")
                await callback_query.answer("❌ Kino yuborishda xatolik yuz berdi.", show_alert=True)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for ch_id in not_subscribed_channels:
                try:
                    chat_info = await bot.get_chat(ch_id)
                    channel_name = chat_info.title if chat_info.title else "Kanal"
                    if str(ch_id).startswith('-100'):
                        channel_id = str(ch_id)[4:]
                        invite_link = f"https://t.me/c/{channel_id}/1"
                    elif str(ch_id).startswith('@'):
                        invite_link = f"https://t.me/{str(ch_id)[1:]}"
                    else:
                        invite_link = f"https://t.me/{ch_id}"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text=f"📢 {channel_name}", url=invite_link)
                    ])
                except:
                    invite_link = f"https://t.me/{str(ch_id)[1:]}" if str(ch_id).startswith('@') else f"https://t.me/c/{str(ch_id)[4:]}/1"
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(text="📢 Kanal", url=invite_link)
                    ])
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Qayta tekshirish", callback_data=f"check_{code}")
            ])
            await callback_query.message.edit_text(
                "❌ Quyidagi Telegram kanallariga hali obuna bo‘lmagansiz:",
                reply_markup=keyboard
            )
            await callback_query.answer("Iltimos, barcha Telegram kanallariga obuna bo‘ling!", show_alert=True)
    except Exception as e:
        logger.error(f"process_check xatolik: {e}")
        await callback_query.answer("❌ Xatolik yuz berdi.", show_alert=True)

# O'chirish callback query larini boshqarish
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def handle_delete_callbacks(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id

        if user_id not in admins:
            await callback_query.answer("❌ Sizda admin huquqlari yo'q!", show_alert=True)
            return

        data_parts = callback_query.data.split("_", 2)
        action = data_parts[1]
        item_id = data_parts[2]

        if action == "channel":
            if item_id in channels:
                try:
                    if str(item_id).startswith('@') or str(item_id).startswith('-') or str(item_id).isdigit():
                        try:
                            chat_info = await bot.get_chat(item_id)
                            channel_name = f"📺 {chat_info.title}" if chat_info.title else f"📺 {str(item_id)}"
                        except:
                            channel_name = f"📺 {str(item_id)}"
                    else:
                        if 'instagram.com/' in str(item_id).lower():
                            channel_name = f"📷 Instagram: {str(item_id).split('/')[-1]}"
                        elif 'facebook.com/' in str(item_id).lower() or 'fb.com/' in str(item_id).lower():
                            channel_name = f"📘 Facebook: {str(item_id).split('/')[-1]}"
                        elif 'twitter.com/' in str(item_id).lower() or 'x.com/' in str(item_id).lower():
                            channel_name = f"🐦 Twitter: {str(item_id).split('/')[-1]}"
                        elif 'youtube.com/' in str(item_id).lower() or 'youtu.be/' in str(item_id).lower():
                            channel_name = f"📺 YouTube: {str(item_id).split('/')[-1]}"
                        elif 'tiktok.com/' in str(item_id).lower():
                            channel_name = f"🎵 TikTok: {str(item_id).split('/')[-1]}"
                        else:
                            channel_name = f"🔗 {str(item_id)}"
                except Exception as e:
                    logger.error(f"Kanal nomini olishda xatolik {item_id}: {e}")
                    channel_name = str(item_id)

                channels.remove(item_id)
                save_json("channels.json", channels)
                await callback_query.message.edit_text(f"✅ Kanal '{channel_name}' o'chirildi.")
                logger.info(f"Kanal o'chirildi: {item_id}")
            else:
                await callback_query.answer("❌ Kanal topilmadi!", show_alert=True)

        elif action == "video":
            if item_id in film_data:
                movie_name = movie_info.get(item_id, {}).get("name", f"Kod: {item_id}")
                del film_data[item_id]
                save_json("data.json", film_data)
                if item_id in statistics:
                    del statistics[item_id]
                    save_json("statistics.json", statistics)
                await callback_query.message.edit_text(f"✅ Video '{movie_name}' o'chirildi.")
                logger.info(f"Video o'chirildi: {item_id}")
            else:
                await callback_query.answer("❌ Video topilmadi!", show_alert=True)

        elif action == "info":
            if item_id in movie_info:
                movie_name = movie_info[item_id].get("name", f"Kod: {item_id}")
                del movie_info[item_id]
                save_json("movie_info.json", movie_info)
                await callback_query.message.edit_text(f"✅ Ma'lumot '{movie_name}' o'chirildi.")
                logger.info(f"Ma'lumot o'chirildi: {item_id}")
            else:
                await callback_query.answer("❌ Ma'lumot topilmadi!", show_alert=True)

    except Exception as e:
        logger.error(f"handle_delete_callbacks xatolik: {e}")
        await callback_query.answer("❌ Xatolik yuz berdi.", show_alert=True)

# Bot ishga tushadi
async def main():
    logger.info("🚀 Bot ishga tushmoqda...")

    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot to'xtatildi (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Botda xatolik: {e}")
        await asyncio.sleep(5)
        logger.info("🔄 Bot qaytadan ishga tushirilmoqda...")

if __name__ == "__main__":
    asyncio.run(main())