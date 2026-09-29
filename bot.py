import os
import random
import io
import gc
import json
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFont
from moviepy import ImageClip, concatenate_videoclips, CompositeVideoClip
import yt_dlp

TOKEN = "8658313360:AAGe5E7-ogE6nMqN8I3OlKuAZBqrthhckHg"
bot = telebot.TeleBot(TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

SUPER_ADMIN = "drborys".lower()
SUPER_ADMIN_ID = 000000000  # Зміни на свій реальний Telegram ID, якщо потрібно

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

QUOTES = {
    "ru": [
        "ты годами собираешь чужие инструкции и\nсохраняешь полезные гайды, но так и не\nделаешь первый шаг..\n\nначнешь применять знания на практике или\nснова пролистаешь..",
        "ты выбираешь сидеть в тепле и комфорте,\nподсознательно хороня любые свои амбиции и цели..\n\nвыйдешь из зоны комфорта или снова пролистаешь..",
        "время идет, а ты продолжаешь ждать идеального момента..\n\nа он никогда не наступит, пока ты не начнешь.",
        "дорога не прощает ошибок, она учит\nдержать удар и идти до конца..\n\nтвоя цель стоит того, чтобы рискнуть?"
    ],
    "ua": [
        "ти роками збираєш чужі інструкції та\nзберігаєш корисні гайди, але так і не\nробиш перший крок..\n\nпочнешь застосовувати знання на практиці чи\nзнову прогорнеш..",
        "ти обираєш сидіти в теплі і комфорті,\nпідсвідомо ховаючи будь-які свої амбіції та цілі..\n\nвийдеш із зони комфорту чи знову прогорнеш..",
        "час іде, а ты продовжуєш чекати на ідеальний момент..\n\nа він ніколи не настане, поки ты не почнеш.",
        "дорога не прощає помилок, вона вчить\nтримати удар і йти до кінця..\n\nтвоя мета варта того, щоб ризикнути?"
    ]
}

TEXTS = {
    "ru": {
        "access_denied": "⛔ У вас нет доступа к этому боту.",
        "bot_globally_disabled": "🛠 Бот временно отключен администратором и находится на техническом обслуживании.",
        "video_disabled_for_users": "⛔ Создание видео временно отключено администратором.",
        "active": "🎬 Бот активен! Отправьте **3 или более фото** (любые, поочередно), а затем нажмите кнопку «Готово».",
        "lang_select": "🌐 Выберите язык / Оберіть мову:",
        "lang_changed": "✅ Язык успешно изменен на русский!",
        "photo_wait": "📥 Получено фото №{count}! Можете отправить еще или нажать «Готово» 👇",
        "rendering": "⚡ Быстрый рендер видео...",
        "done": "✅ Готово!",
        "music_downloading": "🔍 Ищу и скачиваю трек для вас...",
        "music_error": "❌ Не удалось скачать трек, попробуйте еще раз."
    },
    "ua": {
        "access_denied": "⛔ У вас немає доступу до цього бота.",
        "bot_globally_disabled": "🛠 Бот тимчасово вимкнений адміністратором на технічне обслуговування.",
        "video_disabled_for_users": "⛔ Створення відео тимчасово вимкнено адміністратором.",
        "active": "🎬 Бот активний! Надішліть **3 або більше фото** (будь-які, по черзі), а потім натисніть кнопку «Готово».",
        "lang_select": "🌐 Оберіть мову / Выберите язык:",
        "lang_changed": "✅ Мову успішно змінено на українську!",
        "photo_wait": "📥 Отримано фото №{count}! Можете надіслати ще або натиснути «Готово» 👇",
        "rendering": "⚡ Швидкий рендер відео...",
        "done": "✅ Готово!",
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
    video_on = config.get("video_creation_enabled", True)
    
    status_btn_text = "🟢 Бот ВКЛЮЧЕН (Нажмите для откл)" if is_on else "🔴 Бот ВЫКЛЮЧЕН (Нажмите для вкл)"
    video_btn_text = "🟢 Генерація відео ВКЛ" if video_on else "🔴 Генерація відео ВИКЛ"
    
    kb.row(KeyboardButton(status_btn_text))
    kb.row(KeyboardButton(video_btn_text))
    kb.row(KeyboardButton("💬 Написать пользователю"), KeyboardButton("📋 Список пользователей"))
    kb.row(KeyboardButton("👤 Вийти в режим юзера (Тест)"))
    kb.row(KeyboardButton("❌ Выйти из режима ответа"))
    return kb

def get_user_keyboard(lang, user_id=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    # Кнопка швидкого повернення в адмін-панель для головного адміна
    if user_id and (user_id == SUPER_ADMIN_ID or (user_id in admin_as_user_mode or is_super_admin(type('obj', (object,), {'from_user': type('obj', (object,), {'id': user_id, 'username': SUPER_ADMIN})})() )):
        kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))

    if lang == "ru":
        kb.row(KeyboardButton("🌐 Сменить язык"), KeyboardButton("🎬 Инструкция"))
        kb.row(KeyboardButton("🎵 Украинская музыка"))
    else:
        kb.row(KeyboardButton("🌐 Змінити мову"), KeyboardButton("🎬 Інструкція"))
        kb.row(KeyboardButton("🎵 Українська музика"))
    return kb

def get_done_keyboard(lang):
    markup = InlineKeyboardMarkup()
    text = "Готово (почати генерацію) ✅" if lang == "ua" else "Готово (начать генерацию) ✅"
    markup.add(InlineKeyboardButton(text, callback_data="done_generation"))
    return markup

def create_pure_text_image(text, output_path):
    img = Image.new('RGBA', (660, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_path = os.path.join(BASE_DIR, "font.ttf")
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/impact.ttf"

    try:
        font = ImageFont.truetype(font_path, 25)
    except:
        font = ImageFont.load_default()

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
                w_test = len(test_line) * 12
                
            if w_test <= 620:
                current_line = test_line
            else:
                all_lines.append(current_line)
                current_line = word
        if current_line:
            all_lines.append(current_line)

    line_height = 32
    total_text_height = len(all_lines) * line_height
    start_y = (300 - total_text_height) / 2

    y = start_y
    for line in all_lines:
        if line == "":
            y += line_height / 2
            continue
        
        try:
            w = font.getlength(line)
        except:
            w = len(line) * 12
            
        x = (660 - w) / 2
        
        shadow_offset = 2
        for dx, dy in [(-shadow_offset, -shadow_offset), (shadow_offset, -shadow_offset), 
                       (-shadow_offset, shadow_offset), (shadow_offset, shadow_offset),
                       (-shadow_offset, 0), (shadow_offset, 0), (0, -shadow_offset), (0, shadow_offset)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
            
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

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
        
        admin_panel_text = "👑 **Панель администратора:**\n\nИспользуйте кнопки меню внизу для управления."
        bot.send_message(message.chat.id, admin_panel_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
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

    user_photos_buffer[user_id] = []
    bot.send_message(user_id, TEXTS[lang]["active"], reply_markup=get_user_keyboard(lang, user_id))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    lang = get_user_lang(user_id)
    is_admin = is_super_admin(call) and user_id not in admin_as_user_mode

    if call.data == "done_generation":
        chat_id = call.message.chat.id
        if not config.get("video_creation_enabled", True) and not is_admin:
            bot.answer_callback_query(call.id, TEXTS[lang]["video_disabled_for_users"], show_alert=True)
            return

        photos = user_photos_buffer.get(chat_id, [])

        if len(photos) < 3:
            alert_text = f"⚠️ Ви надіслали лише {len(photos)} фото. Потрібно мінімум 3!" if lang == "ua" else f"⚠️️ Вы отправили только {len(photos)} фото. Нужно минимум 3!"
            bot.answer_callback_query(call.id, alert_text, show_alert=True)
            return

        bot.answer_callback_query(call.id, "OK")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=TEXTS[lang]["rendering"]
        )
        
        generate_video_from_photos(chat_id, photos, lang)
        user_photos_buffer[chat_id] = []
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
        bot.answer_callback_query(call.id, "⚠️️ У этого пользователя еще нет ID. Попросите его нажать /start в боте!", show_alert=True)
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
            markup.row(
                InlineKeyboardButton("✅ Разрешить", callback_data=f"allow_{target_user_id}_{username or 'noupname'}")
            )
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

    if text and ("Бот ВКЛЮЧЕН" in text or "Бот ВЫКЛЮЧЕН" in text):
        current_status = config.get("bot_enabled", True)
        config["bot_enabled"] = not current_status
        save_config(config)
        
        status_msg = "🟢 **Бот успешно ВКЛЮЧЕН!**" if config["bot_enabled"] else "🔴 **Бот ВЫКЛЮЧЕН!**"
        bot.send_message(message.chat.id, status_msg, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        return

    if text and ("Генерація відео ВКЛ" in text or "Генерація відео ВИКЛ" in text):
        current_video_status = config.get("video_creation_enabled", True)
        config["video_creation_enabled"] = not current_video_status
        save_config(config)
        
        v_status_msg = "🟢 **Створення відео для користувачів УВІМКНЕНО!**" if config["video_creation_enabled"] else "🔴 **Створення відео для користувачів ВИМКНЕНО!**"
        bot.send_message(message.chat.id, v_status_msg, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        return

    elif text == "👤 Вийти в режим юзера (Тест)":
        admin_as_user_mode.add(user_id)
        lang = get_user_lang(user_id)
        bot.send_message(
            message.chat.id, 
            "👤 Ви вийшли з адмін-панелі та перейшли в режим звичайного користувача.\n\nЩоб повернутися назад, натисніть кнопку нижче.", 
            reply_markup=get_user_keyboard(lang, user_id)
        )
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
            bot.send_message(message.chat.id, "ℹ️ Список разрешенных пользователей пока пуст (кроме вас).", reply_markup=get_admin_keyboard())
        else:
            bot.send_message(message.chat.id, "👥 **Выберите пользователя:**", parse_mode="Markdown", reply_markup=markup)
        return

    elif text == "📋 Список пользователей":
        users_list = "\n".join([f"• @{u} (ID: {uid if uid != 0 else 'не получен'})" for u, uid in allowed_users.items()])
        bot.send_message(message.chat.id, f"📋 **Список пользователей с доступом:**\n\n{users_list}", parse_mode="Markdown", reply_markup=get_admin_keyboard())
        return

    elif text == "❌ Выйти из режима ответа":
        if user_id in admin_chat_states:
            del admin_chat_states[user_id]
        bot.send_message(message.chat.id, "❌ Режим непрерывного диалога завершен.", reply_markup=get_admin_keyboard())
        return

    if user_id in admin_chat_states:
        target_chat_id = admin_chat_states[user_id]
        try:
            bot.copy_message(chat_id=target_chat_id, from_chat_id=message.chat.id, message_id=message.message_id)
            bot.send_message(message.chat.id, "✅ Отправлено пользователю", reply_markup=get_admin_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка отправки: {e}", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "ℹ️ Вы не выбрали пользователя для диалога. Нажмите **💬 Написать пользователю**.", parse_mode="Markdown", reply_markup=get_admin_keyboard())

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
        bot.send_message(
            message.chat.id, 
            "👑 Ви знову в адмін-панелі!", 
            reply_markup=get_admin_keyboard()
        )
        return

    if not config.get("bot_enabled", True) and not is_admin:
        bot.send_message(message.chat.id, TEXTS[lang]["bot_globally_disabled"])
        return

    if not is_allowed(message):
        bot.send_message(message.chat.id, TEXTS[lang]["access_denied"])
        return

    admin_chat = config.get("admin_chat_id")
    if admin_chat and not is_super_admin(message) and text not in ["🎵 Украинская музыка", "🎵 Українська музика", "🌐 Сменить язык", "🌐 Змінити мову", "🎬 Инструкция", "🎬 Інструкція"]:
        try:
            username_str = f"@{user.username}" if user.username else f"ID {user_id}"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("💬 Ответить (продолжить діалог)", callback_data=f"chat_with_{user_id}"))
            
            bot.send_message(admin_chat, f"📩 **Сообщение от {username_str}:**", parse_mode="Markdown")
            bot.copy_message(chat_id=admin_chat, from_chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
        except Exception as e:
            print(f"Error forwarding to admin: {e}")

    if text in ["🌐 Сменить язык", "🌐 Змінити мову"]:
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🇺🇦 Українська", callback_data="setlang_ua"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru")
        )
        bot.send_message(message.chat.id, TEXTS[lang]["lang_select"], reply_markup=markup)
        return
    elif text in ["🎬 Инструкция", "🎬 Інструкція"]:
        instr = "Отправьте 3 или более фото (любые), а затем нажмите кнопку «Готово», и бот автоматически соберет их в крутое видео!" if lang == "ru" else "Надішліть 3 або більше фото (будь-які), а потім натисніть кнопку «Готово», і бот автоматично збере їх у круте відео!"
        bot.send_message(message.chat.id, instr, reply_markup=get_user_keyboard(lang, user_id))
        return
    elif text in ["🎵 Украинская музыка", "🎵 Українська музика"]:
        send_random_ukr_music(message.chat.id, lang, user_id)
        return

    if message.content_type == 'photo':
        chat_id = message.chat.id
        
        if not config.get("video_creation_enabled", True) and not is_admin:
            bot.reply_to(message, TEXTS[lang]["video_disabled_for_users"], reply_markup=get_user_keyboard(lang, user_id))
            if chat_id in user_photos_buffer:
                user_photos_buffer[chat_id] = []
            return

        if chat_id not in user_photos_buffer:
            user_photos_buffer[chat_id] = []

        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            img = Image.open(io.BytesIO(downloaded_file))
            img = img.convert("RGB")
            
            img = ImageOps.grayscale(img)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.4)
            img = img.convert("RGB")

            target_w, target_h = 720, 960
            img_w, img_h = img.size
            scale = max(target_w / img_w, target_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            img = img.crop((left, top, left + target_w, top + target_h))

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=95)
            img_byte_arr.seek(0)
            
            user_photos_buffer[chat_id].append(img_byte_arr.read())
            count = len(user_photos_buffer[chat_id])

            bot.reply_to(
                message,
                TEXTS[lang]["photo_wait"].format(count=count),
                reply_markup=get_done_keyboard(lang)
            )

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {e}", reply_markup=get_user_keyboard(lang, user_id))

def send_random_ukr_music(chat_id, lang, user_id):
    track_query = random.choice(UKR_TRACKS)
    msg = bot.send_message(chat_id, TEXTS[lang]["music_downloading"])
    
    audio_path = os.path.join(BASE_DIR, f"track_{chat_id}.mp3")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(BASE_DIR, f"track_{chat_id}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'default_search': 'ytsearch1',
        'quiet': True
    }
    
    try:
        real_title = track_query
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_query, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            real_title = info.get('title', track_query)
            
        actual_file = None
        for f in os.listdir(BASE_DIR):
            if f.startswith(f"track_{chat_id}") and f.endswith(".mp3"):
                actual_file = os.path.join(BASE_DIR, f)
                break
                
        if actual_file and os.path.exists(actual_file):
            with open(actual_file, 'rb') as audio:
                bot.send_audio(
                    chat_id, 
                    audio, 
                    caption=f"🎵 {real_title}", 
                    title=real_title, 
                    reply_markup=get_user_keyboard(lang, user_id)
                )
            bot.delete_message(chat_id, msg.message_id)
            os.remove(actual_file)
        else:
            bot.edit_message_text(TEXTS[lang]["music_error"], chat_id, msg.message_id)
            
    except Exception as e:
        print(f"Music download error: {e}")
        try:
            bot.edit_message_text(TEXTS[lang]["music_error"], chat_id, msg.message_id)
        except:
            pass
        
    if os.path.exists(audio_path):
        try: os.remove(audio_path)
        except: pass
    gc.collect()

def generate_video_from_photos(chat_id, photo_bytes_list, lang):
    output_path = os.path.join(BASE_DIR, f"output_{chat_id}.mp4")
    text_img_path = os.path.join(BASE_DIR, f"text_{chat_id}.png")
    temp_files = [text_img_path]

    try:
        chosen_quote = random.choice(QUOTES[lang])
        create_pure_text_image(chosen_quote, text_img_path)

        total_photos = len(photo_bytes_list)
        sequence_bytes = []
        for i in range(25):
            sequence_bytes.append(photo_bytes_list[i % total_photos])

        clips = []
        for i, p_bytes in enumerate(sequence_bytes):
            temp_p = os.path.join(BASE_DIR, f"temp_{chat_id}_{i}.jpg")
            with open(temp_p, "wb") as f:
                f.write(p_bytes)
            temp_files.append(temp_p)
            
            img_clip = ImageClip(temp_p, duration=0.2)
            clips.append(img_clip)

        video = concatenate_videoclips(clips, method="compose")
        txt_clip = ImageClip(text_img_path, transparent=True, duration=5.0)

        final_video = CompositeVideoClip([
            video,
            txt_clip.with_position(('center', 'center'))
        ])

        final_video.write_videofile(
            output_path, 
            fps=15, 
            codec='libx264', 
            preset='ultrafast', 
            audio=False,
            logger=None
        )

        with open(output_path, 'rb') as vid:
            bot.send_video(chat_id, vid, caption=TEXTS[lang]["done"], reply_markup=get_user_keyboard(lang, chat_id))

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

print("Бот запущен!")
bot.polling(none_stop=True)
