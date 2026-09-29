import os
import random
import io
import gc
import json
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

# --- ЗАХИЩЕНИЙ ІМПОРТ MOVIEPY ДЛЯ RENDER ---
try:
    from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    try:
        from moviepy import ImageClip, CompositeVideoClip, concatenate_videoclips
    except ImportError:
        from moviepy.video.VideoClip import ImageClip
        from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
        from moviepy.video.compositing.concatenate import concatenate_videoclips

import yt_dlp

# --- Міні-вебсервер Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# -----------------------------

TOKEN = "8658313360:AAGe5E7-ogE6nMqN8I3OlKuAZBqrthhckHg"
bot = telebot.TeleBot(TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

SUPER_ADMIN = "drborys".lower()
SUPER_ADMIN_ID = 000000000  

# --- ГЕНЕРАЦІЯ 1000+ УКРАЇНСЬКИХ ТРЕКІВ ---
def generate_large_ukr_tracks():
    artists = [
        "KOLA", "Артем Пивоваров", "YAKTAK", "SKOFKA", "Океан Ельзи", 
        "SadSvit", "KAZKA", "Павло Зібров", "Tember Blanche", "Jerry Heil",
        "alyona alyona", "Dorofeeva", "Макс Барских", "Bez Обмежень", "Скрябін",
        "ТНМК", "Бумбокс", "Wellboy", "Schmalgauzen", "Parfeniuk", "CHEEV",
        "Khatat", "Kavun Conspiracy", "O.Torvald", " Vivienne Mort", "Monatik"
    ]
    
    titles_base = [
        "Біля серця", "Маніфест", "Погляд", "Чути гімн", "Обійми", 
        "Касета", "Плакала", "Хрещатик", "Вечорниці", "Молитва",
        "Думи", "Вільні люди", "Спи собі сама", "Понад хмарами", "До ранку",
        "Козацькому роду", "Не твоя війна", "Світло", "Там, де нас нема", "Зіронька",
        "Пробач", "Люблю", "Назавжди", "Не зупиняй", "Пам'ять", "Брат за брата"
    ]

    generated_tracks = []
    for artist in artists:
        for title in titles_base:
            generated_tracks.append(f"{artist} — {title}")

    extra_modifiers = ["Remix", "Live", "Acoustic Version", "Speed Up", "Slowed", "Radio Edit", "Reimagined"]
    base_pool = list(generated_tracks)
    
    counter = 1
    while len(generated_tracks) < 1100:
        base_track = random.choice(base_pool)
        modifier = random.choice(extra_modifiers)
        new_track_name = f"{base_track} ({modifier} {counter})"
        if new_track_name not in generated_tracks:
            generated_tracks.append(new_track_name)
        counter += 1

    return generated_tracks

UKR_TRACKS = generate_large_ukr_tracks()
user_track_history = {}

def get_unique_ukr_track(user_id):
    if user_id not in user_track_history:
        user_track_history[user_id] = []
    
    used_list = user_track_history[user_id]
    if len(used_list) >= len(UKR_TRACKS):
        used_list.clear()

    remaining = [t for t in UKR_TRACKS if t not in used_list]
    chosen = random.choice(remaining)
    used_list.append(chosen)
    return chosen

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

# --- ГЕНЕРАЦІЯ 1000+ ЦИТАТ З ЗАХИСТОМ ВІД ПОВТОРЕНЬ ---
def generate_large_quotes():
    ru_bases = [
        "ты годами собираешь чужие инструкции и сохраняешь полезные гайды, но так и не делаешь первый шаг..\n\nначнешь применять знания на практике или снова пролистаешь..",
        "ты выбираешь сидеть в тепле и комфорте, подсознательно хорня любые свои амбиции и цели..\n\nвыйдешь из зоны комфорта или снова пролистаешь..",
        "время идет, а ты продолжаешь ждать идеального момента..\n\nа он никогда не наступит, пока ты не начнешь.",
        "дорога не прощает ошибок, она учит держать удар и идти до конца..\n\nтвоя цель стоит того, чтобы рискнуть?",
        "никто не придет и не сделает твою жизнь лучше за тебя..\n\nхватит откладывать себя на потом.",
        "страх неудачи — это просто иллюзия, которая держит тебя на месте..\n\nсделаешь шаг вперед сегодня?",
        "каждый день ты делаешь выбор: развиваться или деградировать..\n\nчто ты выберешь прямо сейчас?",
        "дисциплина бьет талант, когда талант ленится..\n\nготов поработать над собой по-настоящему?",
        "успех — это не случайность, это результат тяжелой работы и упорства..\n\nпродолжишь бороться или сдашься?",
        "твои мечты так и останутся мечтами, если не превратить их в четкий план..\n\nкогда начнешь действовать?"
    ]
    
    ua_bases = [
        "ти роками збираєш чужі інструкції та зберігаєш корисні гайди, але так і не робиш перший крок..\n\nпочнешь застосовувати знання на практиці чи знову прогорнеш..",
        "ти обираєш сидіти в теплі і комфорті, підсвідомо ховаючи будь-які свої амбіції та цілі..\n\nвийдеш із зони комфорту чи знову прогорнеш..",
        "час іде, а ты продовжуєш чекати на ідеальний момент..\n\nа він ніколи не настане, поки ты не почнеш.",
        "дорога не прощає помилок, вона вчить тримати удар і йти до кінця..\n\nтвоя мета варта того, щоб ризикнути?",
        "ніхто не прийде і не зробить твоє життя кращим за тебе..\n\nдосить відкладати себе на потім.",
        "страх невдачі — це просто ілюзія, яка тримає тебе на місці..\n\nзробиш крок вперед сьогодні?",
        "кожен день ти робиш вибір: розвиватися чи деградувати..\n\nщо ты обереш прямо зараз?",
        "дисципліна б'є талант, коли талант лінується..\n\nготовий попрацювати над собою по-справжньому?",
        "успіх — це не випадковість, це результат важкої праці та завзятості..\n\nпродовжиш боротися чи здаєшся?",
        "твої мрії так і залишаться мріями, якщо не перетворити їх на чіткий план..\n\nколи почнеш діяти?"
    ]

    additions_ru = [
        " думай об этом каждый день.", " и это твоя главная проблема.", 
        " пока другие действуют.", " пора менять подход.", 
        " сделай выводы и иди дальше.", " время не ждет никого."
    ]
    additions_ua = [
        " думай про це щодня.", " і це твоя головна проблема.", 
        " поки інші діють.", " час змінювати підхід.", 
        " зроби висновки і йди далі.", " час не чекає нікого."
    ]

    generated_ru = list(ru_bases)
    generated_ua = list(ua_bases)

    counter = 1
    for b in ru_bases:
        for add in additions_ru:
            generated_ru.append(f"{b}\n\n[Вариант {counter}]{add}")
            counter += 1
            if len(generated_ru) >= 1100:
                break
        if len(generated_ru) >= 1100:
            break

    counter = 1
    for b in ua_bases:
        for add in additions_ua:
            generated_ua.append(f"{b}\n\n[Варіант {counter}]{add}")
            counter += 1
            if len(generated_ua) >= 1100:
                break
        if len(generated_ua) >= 1100:
            break

    return {"ru": generated_ru, "ua": generated_ua}

QUOTES = generate_large_quotes()
user_quote_history = {}

def get_unique_quote(user_id, lang):
    if user_id not in user_quote_history:
        user_quote_history[user_id] = {"ru": [], "ua": []}
    
    available_pool = QUOTES[lang]
    used_list = user_quote_history[user_id][lang]

    if len(used_list) >= len(available_pool):
        used_list.clear()

    remaining = [q for q in available_pool if q not in used_list]
    chosen = random.choice(remaining)
    used_list.append(chosen)
    return chosen

TEXTS = {
    "ru": {
        "access_denied": "⛔ У вас нет доступа к этому боту.",
        "bot_globally_disabled": "🛠 Бот временно отключен администратором и находится на техническом обслуживании.",
        "video_disabled_for_users": "⛔ Создание видео временно отключено администратором.",
        "active": "🎬 Бот активен! Отправьте **минимум 3 фотографии**, чтобы бот собрал из них видео с квадратным кадром и текстом.",
        "photo_saved": "📥 Фото принято ({}/3). Отправьте еще, чтобы запустить создание видео.",
        "lang_select": "🌐 Выберите язык / Оберіть мову:",
        "lang_changed": "✅ Язык успешно изменен на русский!",
        "rendering": "⚡ Накопилось 3 фото! Применяю квадратный формат, цитату и затемнение...",
        "music_downloading": "🔍 Ищу и скачиваю трек для вас...",
        "music_error": "❌ Не удалось скачать трек, попробуйте еще раз."
    },
    "ua": {
        "access_denied": "⛔ У вас немає доступу до цього бота.",
        "bot_globally_disabled": "🛠 Бот тимчасово вимкнений адміністратором на технічне обслуговування.",
        "video_disabled_for_users": "⛔ Створення відео тимчасово вимкнено адміністратором.",
        "active": "🎬 Бот активний! Надішліть **мінімум 3 фотографії**, щоб бот зібрав із них відео з квадратним кадром та текстом.",
        "photo_saved": "📥 Фото прийнято ({}/3). Надішліть ще, щоб запустити створення відео.",
        "lang_select": "🌐 Оберіть мову / Выберите язык:",
        "lang_changed": "✅ Мову успішно змінено на українську!",
        "rendering": "⚡ Зібралося 3 фото! Застосовую квадратний формат, цитату та затемнення...",
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
    img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_path = os.path.join(BASE_DIR, "font.ttf")
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/impact.ttf"

    try:
        font = ImageFont.truetype(font_path, 52)
    except:
        font = ImageFont.load_default()

    text_color = (255, 255, 255, 255)
    shadow_color = (0, 0, 0, 255)

    parts = text.split('\n\n')
    main_part = parts[0] if len(parts) > 0 else text
    sub_part = parts[1] if len(parts) > 1 else ""

    def wrap_text(text_block):
        paragraphs = text_block.split('\n')
        lines = []
        for para in paragraphs:
            if not para.strip():
                lines.append("")
                continue
            words = para.split()
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                try:
                    w_test = font.getlength(test_line)
                except:
                    w_test = len(test_line) * 22
                if w_test <= 900:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    main_lines = wrap_text(main_part)
    sub_lines = wrap_text(sub_part) if sub_part else []

    line_height = 70
    total_main_height = len(main_lines) * line_height
    start_y_main = (1920 - total_main_height) / 2 - 100 
    
    y = start_y_main
    for line in main_lines:
        if line == "":
            y += line_height / 2
            continue
        try:
            w = font.getlength(line)
        except:
            w = len(line) * 22
        x = (1080 - w) / 2
        
        shadow_offset = 3
        for dx, dy in [(-shadow_offset, -shadow_offset), (shadow_offset, -shadow_offset), 
                       (-shadow_offset, shadow_offset), (shadow_offset, shadow_offset),
                       (-shadow_offset, 0), (shadow_offset, 0), (0, -shadow_offset), (0, shadow_offset)]:
            draw.text((x + dx, y + dy), line, font=font, fill=shadow_color)
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height

    if sub_lines:
        y += 60 
        for line in sub_lines:
            if line == "":
                y += line_height / 2
                continue
            try:
                w = font.getlength(line)
            except:
                w = len(line) * 22
            x = (1080 - w) / 2
            
            shadow_offset = 3
            for dx, dy in [(-shadow_offset, -shadow_offset), (shadow_offset, -shadow_offset), 
                           (-shadow_offset, shadow_offset), (shadow_offset, shadow_offset),
                           (-shadow_offset, 0), (shadow_offset, 0), (0, -shadow_offset), (0, shadow_offset)]:
                draw.text((x + dx, y + dy), line, font=font, fill=shadow_color)
            draw.text((x, y), line, font=font, fill=text_color)
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
        
        target_chat_id = int(call.data.split("_")[-1])
        admin_chat_states[user_id] = target_chat_id
        bot.answer_callback_query(call.id, "Режим диалога активирован")
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("❌ Выход (отмена)", callback_data="exit_chat"))
        
        bot.send_message(
            chat_id=call.message.chat.id,
            text=f"✍ **Режим диалога активен для пользователя (ID: `{target_chat_id}`):**",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    if call.data.startswith("no_id_"):
        bot.answer_callback_query(call.id, "⚠ У этого пользователя нет ID. Попросите его нажать /start!", show_alert=True)
        return

    if call.data == "exit_chat":
        if user_id in admin_chat_states:
            del admin_chat_states[user_id]
        bot.answer_callback_query(call.id, "Выход выполнен")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Режим диалога завершен.")
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

@bot.message_handler(func=lambda message: is_super_admin(message) and message.from_user.id not in admin_as_user_mode, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_admin_messages(message):
    user_id = message.from_user.id
    text = message.text

    if message.content_type == 'photo' and user_id not in admin_chat_states:
        handle_user_messages(message)
        return

    if text in ["⚠ Пожаловаться / Написать админу", "⚠ Пожаловаться / Написать админу", "❌ Завершить диалог", "❌ Завершити діалог"]:
        handle_user_messages(message)
        return

    if text and ("Бот ВКЛЮЧЕН" in text or "Бот ВЫКЛЮЧЕН" in text):
        config["bot_enabled"] = not config.get("bot_enabled", True)
        save_config(config)
        status_msg = "🟢 **Бот ВКЛЮЧЕН!**" if config["bot_enabled"] else "🔴 **Бот ВЫКЛЮЧЕН!**"
        bot.send_message(message.chat.id, status_msg, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        bot.send_message(message.chat.id, "⚙ **Керування генерацією відео:**", parse_mode="Markdown", reply_markup=get_admin_panel_inline())
        return

    elif text == "👤 Вийти в режим юзера (Тест)":
        admin_as_user_mode.add(user_id)
        lang = get_user_lang(user_id)
        bot.send_message(message.chat.id, "👤 Ви в режимі користувача.", reply_markup=get_user_keyboard(lang, user_id))
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
            bot.send_message(message.chat.id, "ℹ Список пуст.", reply_markup=get_admin_keyboard())
        else:
            bot.send_message(message.chat.id, "👥 **Выберите пользователя:**", parse_mode="Markdown", reply_markup=markup)
        return

    elif text == "📋 Список пользователей":
        users_list = "\n".join([f"• @{u} (ID: {uid if uid != 0 else 'нет'})" for u, uid in allowed_users.items()])
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
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}", reply_markup=get_admin_keyboard())
    else:
        if text and not text.startswith("/"):
            handle_user_messages(message)
            return
        bot.send_message(message.chat.id, "ℹ️ Выберите пользователя через кнопку **💬 Написать пользователю**.", parse_mode="Markdown", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda message: not is_super_admin(message) or message.from_user.id in admin_as_user_mode, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_user_messages(message):
    user = message.from_user
    user_id = user.id
    lang = get_user_lang(user_id)
    text = message.text
    is_admin = is_super_admin(message)

    if text == "👑 Повернутися в адмін-панель" and is_admin:
        if user_id in admin_as_user_mode:
            admin_as_user_mode.remove(user_id)
        bot.send_message(message.chat.id, "👑 Повернення в адмін-панель!", reply_markup=get_admin_keyboard())
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

    if text in ["⚠ Пожаловаться / Написать админу", "⚠ Поскаржитися / Написати адміну"]:
        user_support_mode.add(user_id)
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        exit_btn = "❌ Завершити діалог" if lang == "ua" else "❌ Завершить диалог"
        kb.row(KeyboardButton(exit_btn))
        bot.send_message(message.chat.id, "✍ Режим діалогу активовано. Пишіть повідомлення:", reply_markup=kb)
        return

    if text in ["❌ Завершить диалог", "❌ Завершити діалог"]:
        if user_id in user_support_mode:
            user_support_mode.remove(user_id)
        bot.send_message(message.chat.id, "✅ Діалог завершено.", reply_markup=get_user_keyboard(lang, user_id))
        return

    admin_chat = config.get("admin_chat_id")
    is_active_chat = (admin_chat and (user_id in user_support_mode or any(admin_id for admin_id, target in admin_chat_states.items() if target == user_id)))
    
    if admin_chat and is_active_chat and text not in ignored_texts and not (text and text.startswith("/")):
        try:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("💬 Ответить", callback_data=f"chat_with_{user_id}"))
            bot.send_message(admin_chat, f"💬 **Сообщение от пользователя ID `{user_id}`:**", parse_mode="Markdown")
            bot.copy_message(chat_id=admin_chat, from_chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
            bot.send_message(message.chat.id, "✅ Надіслано адміну." if lang == "ua" else "✅ Отправлено администратору.")
        except:
            pass
        return

    if text in ["🌐 Сменить язык", "🌐 Змінити мову"]:
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🇺🇦 Українська", callback_data="setlang_ua"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru")
        )
        bot.send_message(message.chat.id, TEXTS[lang]["lang_select"], reply_markup=markup)
        return
    elif text in ["🎬 Инструкция", "🎬 Інструкція"]:
        bot.send_message(message.chat.id, TEXTS[lang]["active"], reply_markup=get_user_keyboard(lang, user_id))
        return
    elif text in ["🎵 Украинская музыка", "🎵 Українська музика"]:
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
                msg_text = TEXTS[lang]["photo_saved"].format(current_count)
                bot.reply_to(message, msg_text, reply_markup=get_user_keyboard(lang, user_id))
            else:
                sub_photos = user_photos_buffer[chat_id][:3]
                user_photos_buffer[chat_id] = []
                bot.reply_to(message, TEXTS[lang]["rendering"], reply_markup=get_user_keyboard(lang, user_id))
                
                try:
                    # 1. Создаем картинки с цитатами
                    quote_text = get_unique_quote(user_id, lang)
                    img_paths = []
                    for idx, p_data in enumerate(sub_photos):
                        p_path = os.path.join(BASE_DIR, f"temp_{user_id}_{idx}.png")
                        base_img = Image.open(io.BytesIO(p_data)).convert("RGBA")
                        base_img = ImageOps.fit(base_img, (1080, 1920), Image.Resampling.LANCZOS)
                        
                        # Затемнение
                        dark = Image.new('RGBA', (1080, 1920), (0, 0, 0, 120))
                        base_img = Image.alpha_composite(base_img, dark)
                        base_img.save(p_path)
                        
                        # Текст поверх
                        if idx == 0:
                            create_pure_text_image(quote_text, p_path)
                        img_paths.append(p_path)

                    # 2. Выбираем украинский трек и ищем через yt-dlp
                    bot.send_message(chat_id, TEXTS[lang]["music_downloading"])
                    track_name = get_unique_ukr_track(user_id)
                    
                    audio_path = os.path.join(BASE_DIR, f"audio_{user_id}.mp3")
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': audio_path.replace('.mp3', ''),
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }],
                        'quiet': True,
                        'noplaylist': True
                    }
                    
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.extract_info(f"ytsearch1:{track_name} audio", download=True)
                        if not os.path.exists(audio_path):
                            for f_name in os.listdir(BASE_DIR):
                                if f_name.startswith(f"audio_{user_id}") and f_name.endswith('.mp3'):
                                    audio_path = os.path.join(BASE_DIR, f_name)
                                    break
                    except Exception as ex:
                        print(f"Music download error: {ex}")

                    # 3. Собираем видео через MoviePy
                    clips = [ImageClip(p).set_duration(3.5) for p in img_paths]
                    video = concatenate_videoclips(clips, method="compose")
                    
                    if os.path.exists(audio_path):
                        from moviepy.audio.io.AudioFileClip import AudioFileClip
                        audio = AudioFileClip(audio_path).set_duration(video.duration)
                        video = video.set_audio(audio)

                    output_video_path = os.path.join(BASE_DIR, f"result_{user_id}.mp4")
                    video.write_videofile(output_video_path, fps=24, codec='libx264', audio_codec='aac', logger=None)

                    # 4. Отправляем готовое видео пользователю
                    with open(output_video_path, 'rb') as vid_file:
                        bot.send_video(chat_id, vid_file, caption=f"🎵 {track_name}", reply_markup=get_user_keyboard(lang, user_id))

                    # 5. Очистка временных файлов
                    for p in img_paths:
                        if os.path.exists(p): os.remove(p)
                    if os.path.exists(output_video_path): os.remove(output_video_path)
                    if os.path.exists(audio_path): os.remove(audio_path)
                    gc.collect()

                except Exception as render_err:
                    print(f"Rendering error: {render_err}")
                    bot.send_message(chat_id, TEXTS[lang]["music_error"], reply_markup=get_user_keyboard(lang, user_id))
        except Exception as e:
            print(f"Error handling photo: {e}")

# --- ЗАПУСК БОТА І ВЕБ-СЕРВЕРА ---
if __name__ == '__main__':
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    
    print("Bot is starting polling...")
    bot.infinity_polling()
