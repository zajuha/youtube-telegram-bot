import os
import sys
import time
import requests
import telebot
from telebot import types
import yt_dlp

# ==================================================
# ENV
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    sys.exit("BOT_TOKEN is missing")

# выключаем webhook на всякий случай
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=10)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================================================
# CONSTANTS
# ==================================================
MAX_FILE_MB = 49
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================================================
# MEMORY (Railway free friendly)
# ==================================================
users = {}
last_links = {}
favorites = {}

# ==================================================
# TEXT STYLE (character & tone)
# ==================================================
TEXT = {
    "welcome": (
        "🌿 <b>Добро пожаловать</b>\n\n"
        "Я спокойный и вежливый бот 🤍\n"
        "Помогаю скачивать видео и аудио с YouTube.\n\n"
        "Просто пришли ссылку — я всё сделаю аккуратно и без спешки."
    ),
    "menu": "Выбери, пожалуйста, что ты хочешь сделать 👇",
    "ask_link": "🔗 Пришли ссылку на видео или плейлист YouTube",
    "choose_format": "Что именно нужно скачать?",
    "choose_quality": "Выбери подходящее качество:",
    "downloading": "⏳ Я начинаю загрузку…\nПожалуйста, подожди немного.",
    "sending": "📤 Почти готово… Отправляю файл.",
    "done": "✅ Готово! Если нужно ещё что-нибудь — я рядом 🙂",
    "too_big": (
        "😔 <b>Файл получился слишком большим</b>\n\n"
        "Telegram не позволяет ботам отправлять такие объёмы.\n"
        "Попробуй выбрать качество пониже — так всё получится."
    ),
    "no_link": "Я пока не вижу ссылку. Просто пришли её сообщением 🙂",
    "unknown": (
        "🤍 Я тебя понял.\n\n"
        "Пока я умею работать с YouTube-ссылками.\n"
        "Если что — просто пришли ссылку, и я помогу."
    ),
}

# ==================================================
# YT-DLP (без ffmpeg, стабильно)
# ==================================================
YDL_BASE = {
    "quiet": True,
    "retries": 5,
    "socket_timeout": 30,
    "nocheckcertificate": True,
}

# ==================================================
# UI KEYBOARDS
# ==================================================
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎥 Видео", callback_data="video"),
        types.InlineKeyboardButton("🎵 Аудио", callback_data="audio"),
    )
    kb.add(
        types.InlineKeyboardButton("⭐ Избранное", callback_data="favorites"),
    )
    return kb


def quality_menu():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("360p", callback_data="q_360"),
        types.InlineKeyboardButton("720p", callback_data="q_720"),
        types.InlineKeyboardButton("1080p", callback_data="q_1080"),
    )
    return kb


# ==================================================
# HELPERS
# ==================================================
def typing(chat_id, sec=1.2):
    bot.send_chat_action(chat_id, "typing")
    time.sleep(sec)


# ==================================================
# START / FIRST CONTACT
# ==================================================
@bot.message_handler(commands=["start"])
def start(message):
    users.setdefault(message.chat.id, {})
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["welcome"])
    typing(message.chat.id, 0.8)
    bot.send_message(message.chat.id, TEXT["menu"], reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.chat.id not in users)
def first_touch(message):
    users[message.chat.id] = {}
    start(message)


# ==================================================
# LINK HANDLER
# ==================================================
@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def handle_link(message):
    last_links[message.chat.id] = message.text
    typing(message.chat.id)
    bot.send_message(
        message.chat.id,
        TEXT["choose_format"],
        reply_markup=main_menu()
    )


# ==================================================
# CALLBACKS
# ==================================================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.message.chat.id

    if call.data == "favorites":
        fav = favorites.get(uid, [])
        if not fav:
            bot.send_message(uid, "⭐ Избранного пока нет.")
        else:
            bot.send_message(uid, "⭐ <b>Избранное:</b>\n\n" + "\n\n".join(fav))
        return

    if call.data in ("video", "audio"):
        if uid not in last_links:
            bot.answer_callback_query(call.id, TEXT["no_link"])
            return
        users[uid]["mode"] = call.data
        if call.data == "video":
            bot.send_message(uid, TEXT["choose_quality"], reply_markup=quality_menu())
        else:
            download(uid, "audio", None)

    elif call.data.startswith("q_"):
        quality = call.data.split("_")[1]
        download(uid, "video", quality)


# ==================================================
# DOWNLOAD CORE
# ==================================================
def download(uid, mode, quality):
    url = last_links[uid]
    typing(uid)
    status = bot.send_message(uid, TEXT["downloading"])

    try:
        if mode == "video":
            fmt = f"best[ext=mp4][height<={quality}]/best[ext=mp4]"
        else:
            fmt = "bestaudio[ext=m4a]/bestaudio"

        opts = {
            **YDL_BASE,
            "format": fmt,
            "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        size_mb = os.path.getsize(file_path) / (1024 * 1024)

        if size_mb > MAX_FILE_MB:
            os.remove(file_path)
            bot.edit_message_text(TEXT["too_big"], uid, status.message_id)
            return

        bot.edit_message_text(TEXT["sending"], uid, status.message_id)
        typing(uid, 1.5)

        with open(file_path, "rb") as f:
            if mode == "audio":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        favorites.setdefault(uid, []).append(url)
        os.remove(file_path)

        bot.edit_message_text(TEXT["done"], uid, status.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ {e}", uid, status.message_id)


# ==================================================
# FALLBACK (polite personality)
# ==================================================
@bot.message_handler(func=lambda m: True)
def fallback(message):
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["unknown"])


# ==================================================
# POLLING (SAFE LOOP)
# ==================================================
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        time.sleep(5)
