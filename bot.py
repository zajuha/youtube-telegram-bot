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

requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=10)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================================================
# CONSTANTS
# ==================================================
MAX_FILE_MB = 49
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================================================
# MEMORY
# ==================================================
users = {}
last_links = {}
favorites = {}

# ==================================================
# TEXT
# ==================================================
TEXT = {
    "hero": (
        "🌿 <b>Добро пожаловать</b>\n\n"
        "Я спокойно помогу скачать видео или аудио с YouTube.\n\n"
        "Нажми кнопку ниже — и просто вставь ссылку 🤍"
    ),
    "ask_link": "🔗 Пожалуйста, вставь ссылку на YouTube",
    "choose_format": "Что ты хочешь скачать?",
    "choose_quality": "Выбери качество:",
    "downloading": "⏳ Я начинаю загрузку…\nПожалуйста, подожди.",
    "sending": "📤 Отправляю файл…",
    "done": "✅ Готово!\n\nЕсли хочешь — пришли следующую ссылку 🙂",
    "too_big": (
        "😔 <b>Файл слишком большой</b>\n\n"
        "Telegram не позволяет ботам отправлять такие объёмы.\n"
        "Попробуй выбрать качество ниже."
    ),
    "no_link": "Сначала пришли ссылку 🙂",
    "unknown": (
        "🤍 Я здесь, чтобы помогать.\n\n"
        "Просто пришли ссылку на YouTube."
    ),
}

# ==================================================
# YT-DLP
# ==================================================
YDL_BASE = {
    "quiet": True,
    "retries": 5,
    "socket_timeout": 30,
    "nocheckcertificate": True,
}

# ==================================================
# KEYBOARDS
# ==================================================
def start_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀 Начать", callback_data="start_bot"))
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
    return kb

# ==================================================
# HELPERS
# ==================================================
def typing(chat_id, sec=1.0):
    bot.send_chat_action(chat_id, "typing")
    time.sleep(sec)

# ==================================================
# START
# ==================================================
@bot.message_handler(commands=["start"])
def start(message):
    users.setdefault(message.chat.id, {})
    typing(message.chat.id)
    bot.send_message(message.chat.id, TEXT["hero"], reply_markup=start_keyboard())

# ==================================================
# START BUTTON
# ==================================================
@bot.callback_query_handler(func=lambda c: c.data == "start_bot")
def start_button(call):
    uid = call.message.chat.id
    typing(uid)
    bot.edit_message_text("✨ Отлично, начинаем!", uid, call.message.message_id)
    typing(uid)
    bot.send_message(uid, TEXT["ask_link"])

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
        reply_markup=format_keyboard()
    )

# ==================================================
# CALLBACKS (FORMAT / QUALITY)
# ==================================================
@bot.callback_query_handler(func=lambda c: c.data in ("video", "audio"))
def format_choice(call):
    uid = call.message.chat.id

    if uid not in last_links:
        bot.answer_callback_query(call.id, TEXT["no_link"])
        return

    users[uid]["mode"] = call.data

    if call.data == "video":
        bot.send_message(uid, TEXT["choose_quality"], reply_markup=quality_keyboard())
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
        typing(uid, 1.2)

        with open(file_path, "rb") as f:
            if mode == "audio":
                bot.send_audio(uid, f)
            else:
                bot.send_video(uid, f)

        favorites.setdefault(uid, []).append(url)
        os.remove(file_path)

        bot.edit_message_text(TEXT["done"], uid, status.message_id)

        # сбрасываем ссылку, чтобы не было повторов
        last_links.pop(uid, None)

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
