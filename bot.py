import os
import sys
import time
import requests
import telebot
from telebot import types
import yt_dlp

# =========================
# TOKEN CHECK
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("FATAL: BOT_TOKEN is not set")
    sys.exit(1)

print("BOT TOKEN FOUND")

# =========================
# FORCE DELETE WEBHOOK
# =========================
print("DELETING WEBHOOK...")
try:
    r = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
        timeout=10
    )
    print("deleteWebhook response:", r.text)
except Exception as e:
    print("Webhook delete error:", e)

# =========================
# BOT INIT
# =========================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

user_links = {}

print("BOT INITIALIZED")

# =========================
# YT-DLP BASE OPTIONS
# =========================
YDL_BASE = {
    "quiet": True,
    "retries": 10,
    "socket_timeout": 30,
    "nocheckcertificate": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0"
    }
}

# =========================
# HANDLERS
# =========================
@bot.message_handler(commands=["start"])
def start_handler(message):
    print("START COMMAND RECEIVED")
    bot.send_message(
        message.chat.id,
        "Привет!\n\n"
        "Отправь ссылку на YouTube, а я скачаю:\n"
        "🎥 Видео (MP4)\n"
        "🎵 Аудио (MP3)"
    )


@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def link_handler(message):
    print("YOUTUBE LINK RECEIVED:", message.text)
    user_links[message.chat.id] = message.text

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎥 Видео (MP4)", callback_data="video"),
        types.InlineKeyboardButton("🎵 Аудио (MP3)", callback_data="audio")
    )

    bot.send_message(message.chat.id, "Что скачать?", reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data in ("video", "audio"))
def download_handler(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)

    print("DOWNLOAD REQUEST:", call.data, url)

    if not url:
        bot.send_message(chat_id, "❌ Ссылка не найдена. Отправь её заново.")
        return

    bot.send_message(chat_id, "⏳ Скачиваю, подожди...")

    try:
        if call.data == "video":
            opts = {
                **YDL_BASE,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
            }
        else:
            opts = {
                **YDL_BASE,
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if call.data == "audio":
                filename = filename.rsplit(".", 1)[0] + ".mp3"

        print("FILE READY:", filename)

        with open(filename, "rb") as f:
            if call.data == "audio":
                bot.send_audio(chat_id, f)
            else:
                bot.send_video(chat_id, f)

        os.remove(filename)
        print("FILE SENT AND REMOVED")

    except Exception as e:
        print("DOWNLOAD ERROR:", e)
        bot.send_message(chat_id, f"❌ Ошибка: {e}")


# =========================
# START POLLING
# =========================
print("STARTING POLLING...")

while True:
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60
        )
    except Exception as e:
        print("POLLING ERROR:", e)
        time.sleep(5)
