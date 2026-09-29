import os
import random
import io
import gc
import json
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFont
from moviepy import ImageClip, concatenate_videoclips, CompositeVideoClip, vfx
import yt_dlp

# --- Міні-вебсервер Flask для обходу обмежень безкоштовного Web Service на Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# -----------------------------------------------------------------------------------

TOKEN = "8658313360:AAGe5E7-ogE6nMqN8I3OlKuAZBqrthhckHg"
bot = telebot.TeleBot(TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

SUPER_ADMIN = "drborys".lower()
SUPER_ADMIN_ID = 000000000  # Зміни на свій реальний Telegram ID, якщо потрібно

TRAFFIC_WATERMARK = "@t.me/your_channel"

UKR_TRACKS = [
    "KOLA — Біля серця",
    "Артем Пивоваров — Маніфест",
    "YAKTAK — Погляд",
    "SKOFKA — Чути гімн",
    "Океан Ельзи — Обійми",
    "SadSvit — Касета",
    "KAZKA — Плакала",
    "Павло Зібров — Хрещатик"
]

def load_allowed_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {u.lower(): 0 for u in data}
                elif isinstance(data, dict):
                    return {str(k).lower(): v for k, v in data.items()}
        except:
            pass
    return {SUPER_ADMIN: 0}

def save_allowed_users(users_dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_dict, f, ensure_ascii=False, indent=4)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"bot_enabled": True, "video_creation_enabled": True}

def save_config(config_dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, ensure_ascii=False, indent=4)

allowed_users = load_allowed_users()
config = load_config()

if "bot_enabled" not in config:
    config["bot_enabled"] = True
if "video_creation_enabled" not in config:
    config["video_creation_enabled"] = True
save_config(config)

admin_chat_states = {}
admin_as_user_mode = set()
user_photos_buffer = {}
user_support_mode = set()

QUOTES = {
    "ru": [
        "ты годами собираешь чужие инструкции и\nсохраняешь полезные гайды, но так и не\nделаешь первый шаг..\n\nначнешь применять знания на практике или\nснова пролистаешь..",
        "ты выбираешь сидеть в тепле и комфорте,\nподсознательно хороня любые свои амбиции и цели..\n\nвыйдешь из зоны комфорта или снова пролистаешь..",
        "время идет, а ты продолжаешь ждать идеального момента..\n\nа он никогда не наступит, пока ты не начнешь.",
        "дорога не прощает ошибок, она учит\nдержать удар и идти до конца..\n\nтвоя цель стоит того, чтобы рискнуть?"
    ],
    "ua": [
        "ти роками збираєш чужі інструкції та\nзберігаєш корисні гайди, але так і не\nробиш перший крок..\n\nпочнешь застосовувати знання на практиці чи\nзнову прогорнеш..",
        "ти обираєш сидіти в теплі і комфорті,\nпідсвідомо ховаючи будь-які свої амбиції та цілі..\n\nвийдеш із зони комфорту чи знову прогорнеш..",
        "час іде, а ты продовжуєш чекати на ідеальний момент..\n\nа він ніколи не настане, поки ты не почнеш.",
        "дорога не прощає помилок, вона вчить\nтримати удар і йти до кінця..\n\nтвоя мета варта того, щоб ризикнути?"
    ]
}

TEXTS = {
    "ru": {
        "access_denied": "⛔ У вас нет доступа к этому боту.",
        "bot_globally_disabled": "🛠 Бот временно отключен администратором и находится на техническом обслуживании.",
        "video_disabled_for_users": "⛔ Создание видео временно отключено администратором.",
        "active": "🎬 Бот активен! Отправьте **минимум 3 фотографии**, чтобы бот собрал из них видео для трафика.",
        "photo_saved": "📥 Фото принято ({}/3). Отправьте еще, чтобы запустить создание видео.",
        "lang_select": "🌐 Выберите язык / Оберіть мову:",
        "lang_changed": "✅ Язык успешно изменен на русский!",
        "rendering": "⚡ Генерация видео (формат 3:4) запущенна...",
        "music_downloading": "🔍 Ищу и скачиваю трек для вас...",
        "music_error": "❌ Не удалось скачать трек, попробуйте еще раз."
    },
    "ua": {
        "access_denied": "⛔ У вас немає доступу до цього бота.",
        "bot_globally_disabled": "🛠 Бот тимчасово вимкнений адміністратором на технічне обслуговування.",
        "video_disabled_for_users": "⛔ Створення відео тимчасово вимкнено адміністратором.",
        "active": "🎬 Бот активний! Надішліть **мінімум 3 фотографії**, щоб бот зібрав із них відео для трафіку.",
        "photo_saved": "📥 Фото прийнято ({}/3). Надішліть ще, щоб запустити створення відео.",
        "lang_select": "🌐 Оберіть мову / Выберите язык:",
        "lang_changed": "✅ Мову успішно змінено на українську!",
        "rendering": "⚡ Генерацію відео (формат 3:4) запущено...",
        "music_downloading": "🔍 Шукаю та завантажую трек для вас...",
        "music_error": "❌ Не вдалося завантажити трек, спробуйте ще раз."
    }
}

def get_user_lang(user_id):
    users_lang = config.get("users_lang", {})
    return users_lang.get(str(user_id), "ru")

def set_user_lang(user_id, lang):
    if "users_lang" not in config:
        config["users_lang"] = {}
    config["users_lang"][str(user_id)] = lang
    save_config(config)

def is_super_admin(message_or_callback):
    user_id = message_or_callback.from_user.id
    username = message_or_callback.from_user.username
    return user_id == SUPER_ADMIN_ID or (username and username.lower() == SUPER_ADMIN)

def is_allowed(message):
    if is_super_admin(message):
        return True
    username = message.from_user.username
    if not username:
        return str(message.from_user.id) in allowed_users.values()
    return username.lower() in allowed_users

def get_admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    is_on = config.get("bot_enabled", True)
    status_btn_text = "🟢 Бот ВКЛЮЧЕН (Нажмите для откл)" if is_on else "🔴 Бот ВЫКЛЮЧЕН (Нажмите для вкл)"
    kb.row(KeyboardButton(status_btn_text))
    kb.row(KeyboardButton("💬 Написать пользователю"), KeyboardButton("📋 Список пользователей"))
    kb.row(KeyboardButton("👤 Вийти в режим юзера (Тест)"))
    kb.row(KeyboardButton("❌ Выйти из режима ответа"))
    return kb

def get_admin_panel_inline():
    kb = InlineKeyboardMarkup(row_width=1)
    is_video_on = config.get("video_creation_enabled", True)
    status_text = "🟢 Генерація відео: УВІМКНЕНА" if is_video_on else "🔴 Генерація відео: ВИМКНЕНА"
    kb.add(InlineKeyboardButton(status_text, callback_data="toggle_video_generation"))
    return kb

def get_user_keyboard(lang, user_id=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if user_id and user_id in admin_as_user_mode:
        kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))

    if lang == "ru":
        kb.row(KeyboardButton("🌐 Сменить язык"), KeyboardButton("🎬 Инструкция"))
        kb.row(KeyboardButton("🎵 Украинская музыка"))
        kb.row(KeyboardButton("⚠ Пожаловаться / Написать админу"))
    else:
        kb.row(KeyboardButton("🌐 Змінити мову"), KeyboardButton("🎬 Інструкція"))
        kb.row(KeyboardButton("🎵 Українська музика"))
        kb.row(KeyboardButton("⚠️ Поскаржитися / Написати адміну"))
    return kb

def create_pure_text_image(text, output_path):
    img = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_path = os.path.join(BASE_DIR, "font.ttf")
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/impact.ttf"

    try:
        font = ImageFont.truetype(font_path, 48)
        watermark_font = ImageFont.truetype(font_path, 28)
    except:
        font = ImageFont.load_default()
        watermark_font = ImageFont.load_default()

    text_color = (255, 255, 255, 255)
    shadow_color = (0, 0, 0, 255)

    paragraphs = text.split('\n')
    all_lines = []
    for para in paragraphs:
        if not para.strip():
            all_lines.append("")
            continue
        words = para.split()
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            try:
                w_test = font.getlength(test_line)
            except:
                w_test = len(test_line) * 20
                
            if w_test <= 600:
                current_line = test_line
            else:
                all_lines.append(current_line)
                current_line = word
        if current_line:
            all_lines.append(current_line)

    line_height = 64
    total_text_height = len(all_lines) * line_height
    start_y = (1280 - total_text_height) / 2

    y = start_y
    for line in all_lines:
        if line == "":
            y += line_height / 2
            continue
        
        try:
            w = font.getlength(line)
        except:
            w = len(line) * 20
            
        x = (720 - w) / 2
        
        shadow_offset = 3
        for dx, dy in [(-shadow_offset, -shadow_offset), (shadow_offset, -shadow_offset), 
                       (-shadow_offset, shadow_offset), (shadow_offset, shadow_offset),
                       (-shadow_offset, 0), (shadow_offset, 0), (0, -shadow_offset), (0, shadow_offset)]:
            draw.text((x + dx, y + dy), line, font=font, fill=shadow_color)
            
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height

    wm_text = TRAFFIC_WATERMARK
    try:
        wm_w = watermark_font.getlength(wm_text)
    except:
        wm_w = len(wm_text) * 14
    wm_x = (720 - wm_w) / 2
    wm_y = 1180  

    for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (-2, 0), (2, 0), (0, -2), (0, 2)]:
        draw.text((wm_x + dx, wm_y + dy), wm_text, font=watermark_font, fill=(0, 0, 0, 220))
    draw.text((wm_x, wm_y), wm_text, font=watermark_font, fill=(255, 255, 255, 240))

    img.save(output_path)

@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    user_id = user.id
    lang = get_user_lang(user_id)

    if user.username:
        uname = user.username.lower()
        if uname in allowed_users:
            allowed_users[uname] = user_id
            save_allowed_users(allowed_users)

    if is_super_admin(message) and user_id not in admin_as_user_mode:
        config["admin_chat_id"] = message.chat.id
        save_config(config)
        
        admin_panel_text = "👑 **Панель администратора:**\n\nИспользуйте кнопки меню внизу и настройки ниже:"
        bot.send_message(message.chat.id, admin_panel_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        bot.send_message(message.chat.id, "⚙ **Керування генерацією відео:**", parse_mode="Markdown", reply_markup=get_admin_panel_inline())
        return

    if not config.get("bot_enabled", True) and not is_super_admin(message):
        bot.send_message(message.chat.id, TEXTS[lang]["bot_globally_disabled"])
        return

    if not is_allowed(message):
        username_str = f"@{user.username}" if user.username else f"ID {user.id}"
        bot.send_message(message.chat.id, TEXTS[lang]["access_denied"])
        
        admin_chat = config.get("admin_chat_id")
        if admin_chat:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("💬 Написать", callback_data=f"chat_with_{user.id}"),
                InlineKeyboardButton("❌ Запретить", callback_data=f"deny_{user.id}_{user.username or 'noupname'}")
            )
            try:
                bot.send_message(admin_chat, f"🔔 Запрос доступа от {username_str}\nID: `{user.id}`", parse_mode="Markdown", reply_markup=markup)
            except:
                pass
        return

    if user_id in user_support_mode:
        user_support_mode.remove(user_id)
        
    bot.send_message(user_id, TEXTS[lang]["active"], reply_markup=get_user_keyboard(lang, user_id))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    lang = get_user_lang(user_id)
    is_admin = is_super_admin(call) and user_id not in admin_as_user_mode

    if call.data == "toggle_video_generation":
        if not is_super_admin(call):
            bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
            return
        
        current_status = config.get("video_creation_enabled", True)
        config["video_creation_enabled"] = not current_status
        save_config(config)
        
        new_status_text = "🟢 Генерація відео: УВІМКНЕНА" if config["video_creation_enabled"] else "🔴 Генерація відео: ВИМКНЕНА"
        alert_text = "✅ Генерація відео ввімкнена!" if config["video_creation_enabled"] else "❌ Генерація відео вимкнена!"
        
        try:
            bot.answer_callback_query(call.id, alert_text)
            updated_kb = InlineKeyboardMarkup(row_width=1)
            updated_kb.add(InlineKeyboardButton(new_status_text, callback_data="toggle_video_generation"))
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=updated_kb
            )
        except:
            pass
        return

    if call.data.startswith("setlang_"):
        new_lang = call.data.split("_")[1]
        set_user_lang(user_id, new_lang)
        bot.answer_callback_query(call.id, "OK")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=TEXTS[new_lang]["lang_changed"]
        )
        bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=get_admin_keyboard() if (is_super_admin(call) and user_id not in admin_as_user_mode) else get_user_keyboard(new_lang, user_id))
        return

    if call.data.startswith("select_user_id_") or call.data.startswith("chat_with_"):
        if not is_super_admin(call):
            bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
            return
        
        parts = call.data.split("_")
        target_chat_id = int(parts[-1])
        admin_chat_states[user_id] = target_chat_id
        
        bot.answer_callback_query(call.id, "Режим диалога активирован")
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("❌ Выход (отмена)", callback_data="exit_chat"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=f"✍ **Режим отправки сообщений активен для пользователя (ID: `{target_chat_id}`):**\n\nВсе ваши сообщения будут уходить ему.",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    if call.data.startswith("no_id_"):
        bot.answer_callback_query(call.id, "⚠ У этого пользователя еще нет ID. Попросите его нажать /start!", show_alert=True)
        return

    if call.data == "exit_chat":
        if user_id in admin_chat_states:
            del admin_chat_states[user_id]
        bot.answer_callback_query(call.id, "Выход выполнен")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Режим диалога завершен."
        )
        return

    if call.data.startswith('allow_') or call.data.startswith('deny_'):
        if not is_super_admin(call):
            bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
            return

        data_parts = call.data.split('_')
        action = data_parts[0]
        target_user_id = int(data_parts[1])
        username = data_parts[2] if len(data_parts) > 2 else ""
        if username == 'noupname':
            username = ""
        else:
            username = username.lower()

        target_lang = get_user_lang(target_user_id)
        markup = InlineKeyboardMarkup()

        if action == 'allow':
            if username:
                allowed_users[username] = target_user_id
            else:
                allowed_users[str(target_user_id)] = target_user_id
            save_allowed_users(allowed_users)
            
            bot.answer_callback_query(call.id, "✅ Доступ разрешен!")
            markup.row(
                InlineKeyboardButton("💬 Написать", callback_data=f"chat_with_{target_user_id}"),
                InlineKeyboardButton("❌ Запретить", callback_data=f"deny_{target_user_id}_{username or 'noupname'}")
            )
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Запрос от @{username if username else target_user_id} **ОДОБРЕН**.",
                parse_mode="Markdown",
                reply_markup=markup
            )
            try:
                msg = "🎉 Администратор одобрил ваш доступ! Нажмите /start." if target_lang == "ru" else "🎉 Адміністратор схвалив ваш доступ! Натисніть /start."
                bot.send_message(target_user_id, msg)
            except:
                pass

        elif action == 'deny':
            if username and username in allowed_users:
                del allowed_users[username]
            elif str(target_user_id) in allowed_users:
                del allowed_users[str(target_user_id)]
            save_allowed_users(allowed_users)

            bot.answer_callback_query(call.id, "❌ Доступ отклонен.")
            markup.row(InlineKeyboardButton("✅ Разрешить", callback_data=f"allow_{target_user_id}_{username or 'noupname'}"))
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Запрос от @{username if username else target_user_id} **ОТКЛОНЕН**.",
                parse_mode="Markdown",
                reply_markup=markup
            )
            try:
                msg = "⛔ В доступе отказано." if target_lang == "ru" else "⛔ У доступі відмовлено."
                bot.send_message(target_user_id, msg)
            except:
                pass

@bot.message_handler(func=lambda message: is_super_admin(message) and message.from_user.id not in admin_as_user_mode, content_types=['text', 'photo'])
def handle_admin_messages(message):
    user_id = message.from_user.id
    text = message.text

    if text in ["⚠️ Пожаловаться / Написать админу", "⚠ Пожаловаться / Написать админу", "❌ Завершить диалог", "❌ Завершити діалог"]:
        handle_user_messages(message)
        return

    if text and ("Бот ВКЛЮЧЕН" in text or "Бот ВЫКЛЮЧЕН" in text):
        current_status = config.get("bot_enabled", True)
        config["bot_enabled"] = not current_status
        save_config(config)
        
        status_msg = "🟢 **Бот успешно ВКЛЮЧЕН!**" if config["bot_enabled"] else "🔴 **Бот ВЫКЛЮЧЕН!**"
        bot.send_message(message.chat.id, status_msg, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        bot.send_message(message.chat.id, "⚙ **Керування генерацією відео:**", parse_mode="Markdown", reply_markup=get_admin_panel_inline())
        return

    elif text == "👤 Вийти в режим юзера (Тест)":
        admin_as_user_mode.add(user_id)
        lang = get_user_lang(user_id)
        bot.send_message(message.chat.id, "👤 Ви вийшли з адмін-панелі та перейшли в режим звичайного користувача.", reply_markup=get_user_keyboard(lang, user_id))
        return

    elif text == "💬 Написать пользователю":
        markup = InlineKeyboardMarkup()
        for u, uid in allowed_users.items():
            if u.lower() == SUPER_ADMIN:
                continue
            if uid and uid != 0:
                markup.row(InlineKeyboardButton(f"@{u} (ID: {uid})", callback_data=f"select_user_id_{uid}"))
            else:
                markup.row(InlineKeyboardButton(f"@{u} (Нет ID)", callback_data=f"no_id_{u}"))
        
        if len(markup.keyboard) == 0:
            bot.send_message(message.chat.id, "ℹ Список пользователей пуст.", reply_markup=get_admin_keyboard())
        else:
            bot.send_message(message.chat.id, "👥 **Выберите пользователя:**", parse_mode="Markdown", reply_markup=markup)
        return

    elif text == "📋 Список пользователей":
        users_list = "\n".join([f"• @{u} (ID: {uid if uid != 0 else 'не получен'})" for u, uid in allowed_users.items()])
        bot.send_message(message.chat.id, f"📋 **Список пользователей:**\n\n{users_list}", parse_mode="Markdown", reply_markup=get_admin_keyboard())
        return

    elif text == "❌ Выйти из режима ответа":
        if user_id in admin_chat_states:
            del admin_chat_states[user_id]
        bot.send_message(message.chat.id, "❌ Режим диалога завершен.", reply_markup=get_admin_keyboard())
        return

    if user_id in admin_chat_states:
        target_chat_id = admin_chat_states[user_id]
        try:
            bot.copy_message(chat_id=target_chat_id, from_chat_id=message.chat.id, message_id=message.message_id)
            bot.send_message(message.chat.id, "✅ Отправлено пользователю", reply_markup=get_admin_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка отправки: {e}", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "ℹ️ Выберите пользователя через кнопку **💬 Написать пользователю**.", parse_mode="Markdown", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: not is_super_admin(message) or message.from_user.id in admin_as_user_mode, content_types=['text', 'photo'])
def handle_user_messages(message):
    user = message.from_user
    user_id = user.id
    lang = get_user_lang(user_id)
    text = message.text
    is_admin = is_super_admin(message)

    if text == "👑 Повернутися в адмін-панель" and is_admin:
        if user_id in admin_as_user_mode:
            admin_as_user_mode.remove(user_id)
        bot.send_message(message.chat.id, "👑 Ви знову в адмін-панелі!", reply_markup=get_admin_keyboard())
        bot.send_message(message.chat.id, "⚙ **Керування генерацією відео:**", parse_mode="Markdown", reply_markup=get_admin_panel_inline())
        return

    if not config.get("bot_enabled", True) and not is_admin:
        bot.send_message(message.chat.id, TEXTS[lang]["bot_globally_disabled"])
        return

    if not is_allowed(message):
        bot.send_message(message.chat.id, TEXTS[lang]["access_denied"])
        return

    ignored_texts = [
        "🎵 Украинская музыка", "🎵 Українська музика",
        "🌐 Сменить язык", "🌐 Змінити мову",
        "🎬 Инструкция", "🎬 Інструкція",
        "⚠ Пожаловаться / Написать админу", "⚠️ Поскаржитися / Написати адміну",
        "❌ Завершить диалог", "❌ Завершити діалог"
    ]

    if text in ["⚠️ Пожаловаться / Написать админу", "⚠ Пожаловаться / Написать админу"]:
        user_support_mode.add(user_id)
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        exit_btn = "❌ Завершити діалог" if lang == "ua" else "❌ Завершить диалог"
        kb.row(KeyboardButton(exit_btn))
        bot.send_message(message.chat.id, "✍ Режим діалогу з адміністратором активовано:" if lang == "ua" else "✍ Режим диалога с администратором активирован:", reply_markup=kb)
        return

    if text in ["❌ Завершить диалог", "❌ Завершити діалог"]:
        if user_id in user_support_mode:
            user_support_mode.remove(user_id)
        bot.send_message(message.chat.id, "✅ Діалог завершено:", reply_markup=get_user_keyboard(lang, user_id))
        return

    admin_chat = config.get("admin_chat_id")
    if admin_chat and user_id in user_support_mode and text and text not in ignored_texts and not text.startswith("/"):
        try:
            username_str = f"@{user.username}" if user.username else f"ID {user_id}"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("💬 Ответить", callback_data=f"chat_with_{user_id}"))
            bot.send_message(admin_chat, f"📩 **Повідомлення від {username_str}**:\n\n{text}", parse_mode="Markdown", reply_markup=markup)
            bot.send_message(message.chat.id, "✅ Надіслано адміну.")
        except:
            pass
        return

    if text in ["🌐 Сменить язык", "🌐 Змінити мову"]:
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🇺🇦 Українська", callback_data="setlang_ua"), InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"))
        bot.send_message(message.chat.id, TEXTS[lang]["lang_select"], reply_markup=markup)
        return
    elif text in ["🎬 Инструкция", "🎬 Інструкція"]:
        instr = "Отправьте фотографии, и бот соберет из них видео!" if lang == "ru" else "Надішліть фотографії, і бот збере з них відео!"
        bot.send_message(message.chat.id, instr, reply_markup=get_user_keyboard(lang, user_id))
        return
    elif text in ["🎵 Украинская музыка", "🎵 Українська музика"]:
        send_random_ukr_music(message.chat.id, lang, user_id)
        return

    if message.content_type == 'photo':
        chat_id = message.chat.id
        if not config.get("video_creation_enabled", True) and not is_admin:
            bot.reply_to(message, TEXTS[lang]["video_disabled_for_users"], reply_markup=get_user_keyboard(lang, user_id))
            return

        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            if chat_id not in user_photos_buffer:
                user_photos_buffer[chat_id] = []
            user_photos_buffer[chat_id].append(downloaded_file)

            current_count = len(user_photos_buffer[chat_id])
            if current_count < 3:
                bot.reply_to(message, TEXTS[lang]["photo_saved"].format(current_count), reply_markup=get_user_keyboard(lang, user_id))
            else:
                sub_photos = user_photos_buffer[chat_id][:3]
                user_photos_buffer[chat_id] = []
                bot.send_message(chat_id, TEXTS[lang]["rendering"], reply_markup=get_user_keyboard(lang, user_id))
                generate_video_from_photos(chat_id, sub_photos, lang, video_index=random.randint(100, 999))
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}", reply_markup=get_user_keyboard(lang, user_id))

def send_random_ukr_music(chat_id, lang, user_id):
    track_query = random.choice(UKR_TRACKS)
    msg = bot.send_message(chat_id, TEXTS[lang]["music_downloading"])
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(BASE_DIR, f"track_{chat_id}.%(ext)s"),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
        'default_search': 'ytsearch1',
        'quiet': True
    }
    try:
        real_title = track_query
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_query, download=True)
            if 'entries' in info: info = info['entries'][0]
            real_title = info.get('title', track_query)
            
        actual_file = None
        for f in os.listdir(BASE_DIR):
            if f.startswith(f"track_{chat_id}") and f.endswith(".mp3"):
                actual_file = os.path.join(BASE_DIR, f)
                break
                
        if actual_file and os.path.exists(actual_file):
            with open(actual_file, 'rb') as audio:
                bot.send_audio(chat_id, audio, caption=f"🎵 {real_title}", title=real_title, reply_markup=get_user_keyboard(lang, user_id))
            bot.delete_message(chat_id, msg.message_id)
            os.remove(actual_file)
        else:
            bot.edit_message_text(TEXTS[lang]["music_error"], chat_id, msg.message_id)
    except:
        try: bot.edit_message_text(TEXTS[lang]["music_error"], chat_id, msg.message_id)
        except: pass
    gc.collect()

def generate_video_from_photos(chat_id, photo_bytes_list, lang, video_index=1):
    output_path = os.path.join(BASE_DIR, f"output_{chat_id}_{video_index}.mp4")
    text_img_path = os.path.join(BASE_DIR, f"text_{chat_id}_{video_index}.png")
    temp_files = [text_img_path]

    try:
        chosen_quote = random.choice(QUOTES[lang])
        create_pure_text_image(chosen_quote, text_img_path)

        clips = []
        sequence_indices = [i % len(photo_bytes_list) for i in range(12)]

        for i, photo_idx in enumerate(sequence_indices):
            p_bytes = photo_bytes_list[photo_idx]
            img = Image.open(io.BytesIO(p_bytes)).convert("RGB")
            img = ImageOps.grayscale(img)
            img = ImageEnhance.Contrast(img).enhance(1.5)

            # Повернено обрізку під формат 3:4 (на основі старого коду)
            img_w, img_h = img.size
            target_aspect = 3 / 4  
            current_aspect = img_w / img_h
            if current_aspect > target_aspect:
                new_w = int(img_h * target_aspect)
                offset = (img_w - new_w) // 2
                img = img.crop((offset, 0, offset + new_w, img_h))
            else:
                new_h = int(img_w / target_aspect)
                offset = (img_h - new_h) // 2
                img = img.crop((0, offset, img_w, offset + new_h))

            img = img.resize((720, 960), Image.Resampling.BILINEAR)

            temp_p = os.path.join(BASE_DIR, f"temp_{chat_id}_{video_index}_{i}.jpg")
            img.save(temp_p, "JPEG", quality=85)
            temp_files.append(temp_p)
            
            img_clip = ImageClip(temp_p, duration=0.4).with_effects([vfx.MultiplyColor(0.55)])
            clips.append(img_clip)

        video = concatenate_videoclips(clips, method="compose")
        txt_clip = ImageClip(text_img_path, duration=4.8)

        final_video = CompositeVideoClip([
            video,
            txt_clip.with_position(('center', 'center'))
        ])

        final_video.write_videofile(
            output_path, 
            fps=12, 
            codec='libx264', 
            preset='ultrafast', 
            audio=False,
            logger=None
        )

        with open(output_path, 'rb') as vid:
            bot.send_video(chat_id, vid, caption=f"✅ Готово (формат 3:4)!", reply_markup=get_user_keyboard(lang, chat_id))

    except Exception as e:
        bot.send_message(chat_id, f"❌ Render error: {e}", reply_markup=get_user_keyboard(lang, chat_id))

    for tf in temp_files:
        if os.path.exists(tf):
            try: os.remove(tf)
            except: pass

    if os.path.exists(output_path):
        try: os.remove(output_path)
        except: pass

    gc.collect()

if __name__ == '__main__':
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

    print("Бот та вебсервер запущені!")
    bot.polling(none_stop=True)
