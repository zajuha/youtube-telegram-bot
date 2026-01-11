import os
import sys
import time
import requests
import telebot
from telebot import types
import yt_dlp
from datetime import datetime, timedelta

# ==================================================
# ENV
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    sys.exit("BOT_TOKEN is missing")

requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=10)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================================================
# CONSTANTS
# ==================================================
MAX_FILE_MB = 49
DOWNLOAD_DIR = "downloads"
FILE_TTL_MINUTES = 15
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================================================
# MEMORY
# ==================================================
last_links = {}
link_info = {}
download_counter = 0

# ==================================================
# TEXT
# ==================================================
TEXT = {
    "hero": (
        "🌿 <b>Добро пожаловать</b>\n\n"
        "Я помогу скачать видео или музыку с YouTube.\n"
        "Просто вставь ссылку 🤍"
    ),
    "ask_link": "🔗 Вставь ссылку на YouTube",
    "choose_format": "Что будем скачивать?",
    "downloading": "⏳ Загружаю, пожалуйста подожди…",
    "sending": "📤 Отправляю файл…",
    "done": "✅ Готово!\n\nЕсли хочешь — пришли следующую ссылку 🙂",
    "too_big": (
        "😔 <b>Файл слишком большой</b>\n\n"
        "Попробуй выбрать качество ниже."
    ),
    "unknown": "Я жду ссылку на YouTube 🙂",
}

# ==================================================
# YT-DLP BASE
# ==================================================
YDL_BASE = {
    "quiet": True,
    "nocheckcertificate": True,
    "retries": 5,
    "socket_timeout": 30,
}

# ==================================================
# KEYBOARDS
# ==================================================
def format_keyboard(suggest_audio=False):
    kb = types.InlineKeyboardMarkup()
    if suggest_audio:
        kb.add(types.InlineKeyboardButton("🎵 Скачать аудио (рекомендовано)", callback_data="audio"))
        kb.add(types.InlineKeyboardButton("🎥 Скачать видео", callback_data="video"))
    else:
        kb.add(
            types.InlineKeyboardButton("🎥 Скачать видео", callback_data="video"),
            types.InlineKeyboardButton("🎵 Скачать аудио", callback_data="audio"),
        )
    return kb

def quality_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("360p", callback_data="q_360"),
        types.InlineKeyboardButton("720p", callback_data="q_720"),
        types.InlineKeyboardButton("1080p", callback_data="q_1080"),
    )
    return kb

# ==================================================
# HELPERS
# ==================================================
def typing(chat_id, sec=1.0):
    bot.send_chat_action(chat_id, "typing")
    time.sleep(sec)

def cleanup_files():
    now = datetime.now()
    for file in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, file)
        if os.path.isfile(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if now - mtime > timedelta(minutes=FILE_TTL_MINUTES):
                try:
                    os.remove(path)
                except:
                    pass

def smart_detect(info):
    title = info.get("title", "").lower()
    duration = info.get("duration", 0)
    width = info.get("width", 0)
    height = info.get("height", 0)

    if "audio" in title or "official audio" in title:
        return True
    if duration and duration < 180:
        return True
    if height and width and height > width:
        return True

    return False

# ==================================================
# START
# ==================================================
@bot.message_handler(commands=["start"])
def start(message):
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["hero"])
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["ask_link"])

# ==================================================
# LINK HANDLER
# ==================================================
@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def handle_link(message):
    uid = message.chat.id
    last_links[uid] = message.text

    typing(uid)

    with yt_dlp.YoutubeDL({**YDL_BASE, "skip_download": True}) as ydl:
        info = ydl.extract_info(message.text, download=False)
        link_info[uid] = info

    suggest_audio = smart_detect(info)

    bot.send_message(
        uid,
        TEXT["choose_format"],
        reply_markup=format_keyboard(suggest_audio)
    )

# ==================================================
# CALLBACKS
# ==================================================
@bot.callback_query_handler(func=lambda c: c.data in ("video", "audio"))
def format_choice(call):
    uid = call.message.chat.id

    if call.data == "video":
        bot.send_message(uid, "📊 Выбери качество:", reply_markup=quality_keyboard())
    else:
        download(uid, "audio", None)

@bot.callback_query_handler(func=lambda c: c.data.startswith("q_"))
def quality_choice(call):
    uid = call.message.chat.id
    quality = call.data.split("_")[1]
    download(uid, "video", quality)

# ==================================================
# DOWNLOAD
# ==================================================
def download(uid, mode, quality):
    global download_counter
    cleanup_files()

    url = last_links.get(uid)
    if not url:
        bot.send_message(uid, TEXT["unknown"])
        return

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
        typing(uid, 1.2)

        with open(file_path, "rb") as f:
            if mode == "audio":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        download_counter += 1

        os.remove(file_path)
        last_links.pop(uid, None)
        link_info.pop(uid, None)

        bot.edit_message_text(
            TEXT["done"] + f"\n\n📊 Всего скачиваний: <b>{download_counter}</b>",
            uid,
            status.message_id
        )

    except Exception as e:
        bot.edit_message_text(f"❌ {e}", uid, status.message_id)

# ==================================================
# FALLBACK
# ==================================================
@bot.message_handler(func=lambda m: True)
def fallback(message):
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["unknown"])

# ==================================================
# POLLING
# ==================================================
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        time.sleep(5)
