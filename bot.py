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

requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# STORAGE (in-memory)
# =========================
users = {}
favorites = {}
last_links = {}

# =========================
# I18N
# =========================
TEXT = {
    "ru": {
        "hero_title": "🎬 <b>YouTube Downloader</b>",
        "hero_text": (
            "Добро пожаловать!\n\n"
            "Я помогу тебе:\n"
            "• 🎥 скачать видео\n"
            "• 🎵 сохранить аудио\n"
            "• 📊 выбрать качество\n"
            "• 📥 загрузить плейлисты\n\n"
            "Просто начни 👇"
        ),
        "menu": "Выбери действие:",
        "send_link": "🔗 Пришли ссылку на YouTube",
        "choose": "Что скачать?",
        "quality": "📊 Выбери качество:",
        "downloading": "⏳ Скачиваю…",
        "sending": "📤 Отправляю файл…",
        "done": "✅ Готово",
        "no_link": "Сначала пришли ссылку 🙂",
        "fav_added": "⭐ Добавлено в избранное",
        "fav_empty": "Избранного пока нет",
        "back": "🏠 В главное меню",
        "lang_switched": "Язык переключён",
    },
    "en": {
        "hero_title": "🎬 <b>YouTube Downloader</b>",
        "hero_text": (
            "Welcome!\n\n"
            "I can help you:\n"
            "• 🎥 download videos\n"
            "• 🎵 extract audio\n"
            "• 📊 choose quality\n"
            "• 📥 download playlists\n\n"
            "Just start 👇"
        ),
        "menu": "Choose an action:",
        "send_link": "🔗 Send YouTube link",
        "choose": "What to download?",
        "quality": "📊 Choose quality:",
        "downloading": "⏳ Downloading…",
        "sending": "📤 Sending file…",
        "done": "✅ Done",
        "no_link": "Send a link first 🙂",
        "fav_added": "⭐ Added to favorites",
        "fav_empty": "No favorites yet",
        "back": "🏠 Main menu",
        "lang_switched": "Language switched",
    }
}

def t(uid, key):
    return TEXT[users.get(uid, {}).get("lang", "ru")][key]

# =========================
# YT-DLP (no ffmpeg)
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
def hero_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔗 Скачать с YouTube", callback_data="action_download"),
        types.InlineKeyboardButton("⭐ Избранное", callback_data="favorites"),
        types.InlineKeyboardButton("🌍 RU / EN", callback_data="lang"),
    )
    return kb

def back_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏠 В главное меню", callback_data="home"))
    return kb

def format_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🎥 Видео", callback_data="video"),
        types.InlineKeyboardButton("🎵 Аудио", callback_data="audio"),
    )
    return kb

def quality_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("360p", callback_data="q_360"),
        types.InlineKeyboardButton("720p", callback_data="q_720"),
        types.InlineKeyboardButton("1080p", callback_data="q_1080"),
    )
    kb.add(types.InlineKeyboardButton("🏠 В главное меню", callback_data="home"))
    return kb

# =========================
# HERO / START SCREEN
# =========================
def show_hero(chat_id):
    bot.send_message(
        chat_id,
        f"{t(chat_id,'hero_title')}\n\n{t(chat_id,'hero_text')}",
        reply_markup=hero_keyboard()
    )

@bot.message_handler(commands=["start"])
def start(message):
    users.setdefault(message.chat.id, {"lang": "ru"})
    show_hero(message.chat.id)

@bot.message_handler(func=lambda m: m.chat.id not in users)
def first_touch(message):
    users[message.chat.id] = {"lang": "ru"}
    show_hero(message.chat.id)

# =========================
# LINK
# =========================
@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def link(message):
    last_links[message.chat.id] = message.text
    bot.send_message(
        message.chat.id,
        t(message.chat.id, "choose"),
        reply_markup=format_keyboard()
    )

# =========================
# CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.message.chat.id

    if call.data == "home":
        show_hero(uid)

    elif call.data == "lang":
        users[uid]["lang"] = "en" if users[uid]["lang"] == "ru" else "ru"
        bot.answer_callback_query(call.id, t(uid, "lang_switched"))
        show_hero(uid)

    elif call.data == "favorites":
        fav = favorites.get(uid, [])
        if not fav:
            bot.send_message(uid, t(uid, "fav_empty"), reply_markup=back_keyboard())
        else:
            bot.send_message(uid, "\n\n".join(fav), reply_markup=back_keyboard())

    elif call.data == "action_download":
        bot.send_message(uid, t(uid, "send_link"), reply_markup=back_keyboard())

    elif call.data in ("video", "audio"):
        if uid not in last_links:
            bot.answer_callback_query(call.id, t(uid, "no_link"))
            return
        users[uid]["mode"] = call.data
        if call.data == "video":
            bot.send_message(uid, t(uid, "quality"), reply_markup=quality_keyboard())
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
            file = ydl.prepare_filename(info)

        bot.edit_message_text(t(uid, "sending"), uid, status.message_id)

        with open(file, "rb") as f:
            if mode == "audio":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        favorites.setdefault(uid, []).append(url)
        os.remove(file)

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
# POLLING
# =========================
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        time.sleep(5)
