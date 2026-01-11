import os
import sys
import time
import requests
import telebot
from telebot import types
import yt_dlp

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    sys.exit("BOT_TOKEN missing")

# =========================
# WEBHOOK OFF
# =========================
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# STORAGE (IN-MEMORY)
# =========================
users = {}
favorites = {}
last_links = {}

# =========================
# I18N
# =========================
TEXT = {
    "ru": {
        "welcome": "👋 <b>Привет!</b>\n\nПришли ссылку на YouTube.\nЯ скачаю видео или аудио.",
        "choose": "🔽 Что скачать?",
        "quality": "📊 Выбери качество:",
        "downloading": "⏳ Скачиваю…",
        "sending": "📤 Отправляю файл…",
        "done": "✅ Готово",
        "no_link": "Сначала пришли ссылку 🙂",
        "fav_added": "⭐ Добавлено в избранное",
        "fav_empty": "Избранного пока нет",
    },
    "en": {
        "welcome": "👋 <b>Hello!</b>\n\nSend a YouTube link.\nI’ll download video or audio.",
        "choose": "🔽 What to download?",
        "quality": "📊 Choose quality:",
        "downloading": "⏳ Downloading…",
        "sending": "📤 Sending file…",
        "done": "✅ Done",
        "no_link": "Send a link first 🙂",
        "fav_added": "⭐ Added to favorites",
        "fav_empty": "No favorites yet",
    }
}

def t(uid, key):
    lang = users.get(uid, {}).get("lang", "ru")
    return TEXT[lang][key]

# =========================
# YT-DLP
# =========================
YDL_BASE = {
    "quiet": True,
    "retries": 5,
    "socket_timeout": 30,
    "nocheckcertificate": True,
}

# =========================
# KEYBOARDS
# =========================
def main_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎥 Video", callback_data="video"),
        types.InlineKeyboardButton("🎵 Audio", callback_data="audio"),
    )
    kb.add(
        types.InlineKeyboardButton("⭐ Favorites", callback_data="favorites"),
        types.InlineKeyboardButton("🌍 RU/EN", callback_data="lang"),
    )
    return kb

def quality_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("360p", callback_data="q_360"),
        types.InlineKeyboardButton("720p", callback_data="q_720"),
        types.InlineKeyboardButton("1080p", callback_data="q_1080"),
    )
    return kb

# =========================
# START / FIRST TOUCH
# =========================
@bot.message_handler(commands=["start"])
@bot.message_handler(func=lambda m: m.chat.id not in users)
def welcome(message):
    users.setdefault(message.chat.id, {"lang": "ru"})
    bot.send_message(message.chat.id, t(message.chat.id, "welcome"), reply_markup=main_kb(message.chat.id))

# =========================
# LINK HANDLER
# =========================
@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def link(message):
    last_links[message.chat.id] = message.text
    bot.send_message(message.chat.id, t(message.chat.id, "choose"), reply_markup=main_kb(message.chat.id))

# =========================
# CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.message.chat.id

    if call.data == "lang":
        users[uid]["lang"] = "en" if users[uid]["lang"] == "ru" else "ru"
        bot.answer_callback_query(call.id, "OK")
        bot.send_message(uid, t(uid, "welcome"), reply_markup=main_kb(uid))

    elif call.data == "favorites":
        fav = favorites.get(uid, [])
        if not fav:
            bot.send_message(uid, t(uid, "fav_empty"))
        else:
            bot.send_message(uid, "\n".join(fav))

    elif call.data in ("video", "audio"):
        if uid not in last_links:
            bot.answer_callback_query(call.id, t(uid, "no_link"))
            return
        users[uid]["mode"] = call.data
        if call.data == "video":
            bot.send_message(uid, t(uid, "quality"), reply_markup=quality_kb())
        else:
            download(uid, "audio", None)

    elif call.data.startswith("q_"):
        q = call.data.split("_")[1]
        download(uid, "video", q)

# =========================
# DOWNLOAD
# =========================
def download(uid, mode, quality):
    url = last_links[uid]
    status = bot.send_message(uid, t(uid, "downloading"))

    try:
        if mode == "video":
            fmt = f"best[ext=mp4][height<={quality}]/best[ext=mp4]"
        else:
            fmt = "bestaudio[ext=m4a]/bestaudio"

        opts = {
            **YDL_BASE,
            "format": fmt,
            "outtmpl": "downloads/%(title)s.%(ext)s",
            "noplaylist": False,
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            files = ydl.prepare_filename(info)

        bot.edit_message_text(t(uid, "sending"), uid, status.message_id)

        with open(files, "rb") as f:
            if mode == "audio":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        favorites.setdefault(uid, []).append(url)
        os.remove(files)
        bot.edit_message_text(t(uid, "done"), uid, status.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ {e}", uid, status.message_id)

# =========================
# ADMIN
# =========================
@bot.message_handler(commands=["admin"])
def admin(message):
    if message.chat.id != ADMIN_ID:
        return
    bot.send_message(
        message.chat.id,
        f"👑 Admin\n\nUsers: {len(users)}\nFavorites: {sum(len(v) for v in favorites.values())}"
    )

# =========================
# FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(message.chat.id, t(message.chat.id, "welcome"), reply_markup=main_kb(message.chat.id))

# =========================
# POLLING
# =========================
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        time.sleep(5)
