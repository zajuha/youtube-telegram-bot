import os
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = os.getenv("8439478360:AAGXuImS02c9iTvA6jhxwKhfWzoragcLyBw")

bot = telebot.TeleBot(BOT_TOKEN)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

user_links = {}

YDL_BASE = {
    "quiet": True,
    "retries": 10,
    "socket_timeout": 30,
    "nocheckcertificate": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0"
    }
}

@bot.message_handler(commands=["start"])
def start(m):
    bot.send_message(
        m.chat.id,
        "Привет!\n\n"
        "Отправь ссылку на YouTube:\n"
        "🎥 Видео (MP4)\n"
        "🎵 Аудио (MP3)"
    )

@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def link(m):
    user_links[m.chat.id] = m.text
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎥 Видео", callback_data="v"),
        types.InlineKeyboardButton("🎵 MP3", callback_data="a")
    )
    bot.send_message(m.chat.id, "Что скачать?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["v", "a"])
def load(c):
    url = user_links.get(c.message.chat.id)
    bot.send_message(c.message.chat.id, "⏳ Скачиваю...")

    try:
        if c.data == "v":
            opts = {
                **YDL_BASE,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s"
            }
        else:
            opts = {
                **YDL_BASE,
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }]
            }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            if c.data == "a":
                path = path.rsplit(".", 1)[0] + ".mp3"

        with open(path, "rb") as f:
            if c.data == "a":
                bot.send_audio(c.message.chat.id, f)
            else:
                bot.send_video(c.message.chat.id, f)

        os.remove(path)

    except Exception as e:
        bot.send_message(c.message.chat.id, f"❌ Ошибка: {e}")

bot.infinity_polling()
