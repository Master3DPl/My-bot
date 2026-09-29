import os
import io
import gc
import json
import random
import threading
from flask import Flask
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeVideoClip
import yt_dlp

# --- НАЛАШТУВАННЯ ТА ІНІЦІАЛІЗАЦІЯ ---
TOKEN = "ТУТ_ВСТАВТЕ_ВАШ_ТОКЕН_БОТА"  # <--- Замініть на токен вашого бота
ADMIN_ID = 123456789                  # <--- Замініть на ваш Telegram ID (суперадмін)

bot = telebot.TeleBot(TOKEN)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Файли для збереження даних
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")

# Стани
user_photos_buffer = {}  # chat_id -> [list of photo bytes]
admin_as_user_mode = set() # адміністратори, які увійшли в режим звичайного юзера
admin_broadcast_mode = set() # адміністратори, які вводять текст для розсилки
admin_chatting_with = {} # admin_id -> target_user_id (режим діалогу з юзером)

# Цитати для відео
QUOTES = {
    "ru": [
        "Время не ждет, оно лишь меняет нас.",
        "Каждый шаг — это новая история.",
        "Иногда молчание говорит громче слов.",
        "Создавай свою реальность каждый день.",
        "Сила внутри, а не снаружи."
    ],
    "uk": [
        "Час не чекає, він лише змінює нас.",
        "Кожен крок — це нова історія.",
        "Іноді мовчання говорить голосніше за слова.",
        "Створюй свою реальність щодня.",
        "Сила всередині, а не ззовні."
    ]
}

# --- РОБОТА З ФАЙЛАМИ ДАНИХ ---
def load_json(file_path, default_val):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return default_val

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving {file_path}: {e}")

allowed_users = load_json(USERS_FILE, []) # Список дозволених користувачів
bot_config = load_json(CONFIG_FILE, {"bot_active": True, "video_enabled": True, "user_languages": {}})

# --- FLASK СЕРВЕР ДЛЯ ХОСТИНГУ (Render тощо) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
def get_user_lang(chat_id):
    str_id = str(chat_id)
    return bot_config["user_languages"].get(str_id, "uk")

def set_user_lang(chat_id, lang):
    str_id = str(chat_id)
    bot_config["user_languages"][str_id] = lang
    save_json(CONFIG_FILE, bot_config)

def get_user_keyboard(lang, user_id=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if user_id and user_id in admin_as_user_mode:
        kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))

    if lang == "ru":
        kb.row(KeyboardButton("🌐 Сменить язык"), KeyboardButton("🎬 Инструкция"))
        kb.row(KeyboardButton("🎵 Украинская музыка"))
    else:
        kb.row(KeyboardButton("🌐 Змінити мову"), KeyboardButton("🎬 Інструкція"))
        kb.row(KeyboardButton("🎵 Українська музика"))
    return kb

def get_admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("👥 Список користувачів"), KeyboardButton("📢 Розсилка"))
    kb.row(KeyboardButton("⚙️ Увімк./Вимк. бота"), KeyboardButton("🎬 Увімк./Вимк. генерацію відео"))
    kb.row(KeyboardButton("👤 Вийти в режим юзера"))
    return kb

# --- ГЕНЕРАЦІЯ ТЕКСТУ ТА ВІДЕО ---
def create_pure_text_image(text, output_path):
    img = Image.new('RGBA', (960, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Вибираємо випадковий шрифт з наявних (font1.ttf, font2.ttf тощо) або стандартний
    available_fonts = [f for f in os.listdir(BASE_DIR) if f.startswith("font") and f.endswith(".ttf")]
    font_path = os.path.join(BASE_DIR, random.choice(available_fonts)) if available_fonts else os.path.join(BASE_DIR, "font.ttf")
    
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/impact.ttf"

    try:
        font = ImageFont.truetype(font_path, 34)
    except:
        font = ImageFont.load_default()

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
                w_test = len(test_line) * 16
                
            if w_test <= 820:
                current_line = test_line
            else:
                all_lines.append(current_line)
                current_line = word
        if current_line:
            all_lines.append(current_line)

    line_height = 42
    total_text_height = len(all_lines) * line_height
    start_y = (720 - total_text_height) / 2

    y = start_y
    for line in all_lines:
        if line == "":
            y += line_height / 2
            continue
        
        try:
            w = font.getlength(line)
        except:
            w = len(line) * 16
            
        x = (960 - w) / 2
        
        shadow_offset = 3
        for dx, dy in [(-shadow_offset, -shadow_offset), (shadow_offset, -shadow_offset), 
                       (-shadow_offset, shadow_offset), (shadow_offset, shadow_offset),
                       (-shadow_offset, 0), (shadow_offset, 0), (0, -shadow_offset), (0, shadow_offset)]:
            draw.text((x + dx, y + dy), line, font=font, fill=shadow_color)
            
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height

    img.save(output_path)

def generate_video_from_photos(chat_id, photo_bytes_list, lang, video_index=1):
    output_path = os.path.join(BASE_DIR, f"output_{chat_id}_{video_index}.mp4")
    text_img_path = os.path.join(BASE_DIR, f"text_{chat_id}_{video_index}.png")
    temp_files = [text_img_path, output_path]

    try:
        chosen_quote = random.choice(QUOTES[lang])
        create_pure_text_image(chosen_quote, text_img_path)

        clips = []
        sequence_indices = []
        for i in range(25): # 25 кадрів по 0.2 сек = рівно 5 секунд відео
            sequence_indices.append(i % len(photo_bytes_list))

        # Випадковий унікальний фільтр для цього відео
        filter_types = ["noir", "contrast", "bright", "matte", "vintage"]
        chosen_filter = random.choice(filter_types)

        for i, photo_idx in enumerate(sequence_indices):
            p_bytes = photo_bytes_list[photo_idx]
            img = Image.open(io.BytesIO(p_bytes)).convert("RGB")
            
            if chosen_filter == "noir":
                img = ImageOps.grayscale(img)
                img = ImageEnhance.Contrast(img).enhance(1.5)
            elif chosen_filter == "matte":
                img = ImageOps.grayscale(img)
                img = ImageEnhance.Brightness(img).enhance(0.85)
                img = ImageEnhance.Contrast(img).enhance(1.1)
            elif chosen_filter == "bright":
                img = ImageEnhance.Brightness(img).enhance(1.25)
            elif chosen_filter == "vintage":
                img = ImageEnhance.Color(img).enhance(0.4)
                img = ImageEnhance.Contrast(img).enhance(1.2)
            else:
                img = ImageEnhance.Color(img).enhance(0.7)

            # Обрізка під формат 4:3
            img_w, img_h = img.size
            target_aspect = 4 / 3  
            current_aspect = img_w / img_h
            if current_aspect > target_aspect:
                new_w = int(img_h * target_aspect)
                offset = (img_w - new_w) // 2
                img = img.crop((offset, 0, offset + new_w, img_h))
            else:
                new_h = int(img_w / target_aspect)
                offset = (img_h - new_h) // 2
                img = img.crop((0, offset, img_w, offset + new_h))

            img = img.resize((960, 720), Image.Resampling.LANCZOS)

            temp_p = os.path.join(BASE_DIR, f"temp_{chat_id}_{video_index}_{i}.jpg")
            img.save(temp_p, "JPEG", quality=95)
            temp_files.append(temp_p)
            
            # Зміна кадру кожні 0.2 секунди
            img_clip = ImageClip(temp_p).with_duration(0.2)
            clips.append(img_clip)

        video = concatenate_videoclips(clips, method="compose")
        txt_clip = ImageClip(text_img_path).with_duration(video.duration)
        final_video = CompositeVideoClip([video, txt_clip])
        
        final_video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264", 
            audio=False, 
            logger=None
        )

        with open(output_path, 'rb') as vid_file:
            bot.send_video(chat_id, vid_file, reply_markup=get_user_keyboard(lang, chat_id))

    except Exception as e:
        print(f"Video generation error: {e}")
        bot.send_message(chat_id, "❌ Помилка при створенні відео.", reply_markup=get_user_keyboard(lang, chat_id))
    
    finally:
        for p in temp_files:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
        gc.collect()

# --- ОБРОБНИКИ ПОВІДОМЛЕНЬ ТА КОМАНД ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    
    # Перевірка чи бот активний для користувачів
    if not bot_config["bot_active"] and chat_id != ADMIN_ID:
        bot.send_message(chat_id, "⚠️ Бот тимчасово на технічному обслуговуванні.")
        return

    # Додаємо до списку користувачів, якщо ще немає
    if chat_id not in allowed_users and chat_id != ADMIN_ID:
        allowed_users.append(chat_id)
        save_json(USERS_FILE, allowed_users)

    lang = get_user_lang(chat_id)
    
    if chat_id == ADMIN_ID and chat_id not in admin_as_user_mode:
        bot.send_message(chat_id, "👑 Вітаю, пане Адмін!", reply_markup=get_admin_keyboard())
    else:
        welcome_text = "Привіт! Надішли мені **3 або більше фотографій**, і я змонтую для тебе круте відео у форматі 4:3!" if lang == "uk" else "Привет! Пришли мне **3 или более фотографии**, и я смонтирую для тебя крутое видео в формате 4:3!"
        bot.send_message(chat_id, welcome_text, reply_markup=get_user_keyboard(lang, chat_id), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["🌐 Змінити мову", "🌐 Сменить язык"])
def change_language_handler(message):
    chat_id = message.chat.id
    current_lang = get_user_lang(chat_id)
    new_lang = "ru" if current_lang == "uk" else "uk"
    set_user_lang(chat_id, new_lang)
    
    text = "Мову змінено на українську 🇺🇦" if new_lang == "uk" else "Язык изменен на русский 🇷🇺"
    bot.send_message(chat_id, text, reply_markup=get_user_keyboard(new_lang, chat_id))

@bot.message_handler(func=lambda msg: msg.text in ["🎬 Інструкція", "🎬 Инструкция"])
def instruction_handler(message):
    chat_id = message.chat.id
    lang = get_user_lang(chat_id)
    text = (
        "📖 **Як користуватися ботом:**\n\n"
        "1. Надішли в чат **від 3 фотографій** підряд.\n"
        "2. Бот автоматично обробить їх, накладе рандомний фільтр та згенерує відео у форматі 4:3 зі зміною кадрів кожні 0.2 сек.\n"
        "3. Також ти можеш завантажити українську музику через відповідне меню!"
        if lang == "uk" else
        "📖 **Как пользоваться ботом:**\n\n"
        "1. Пришли в чат **от 3 фотографий** подряд.\n"
        "2. Бот автоматически обработает их, наложит рандомный фильтр и сгенерирует видео в формате 4:3 со сменой кадров каждые 0.2 сек.\n"
        "3. Также ты можешь скачать украинскую музыку через соответствующее меню!"
    )
    bot.send_message(chat_id, text, reply_markup=get_user_keyboard(lang, chat_id), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["🎵 Українська музика", "🎵 Украинская музыка"])
def ukr_music_handler(message):
    chat_id = message.chat.id
    lang = get_user_lang(chat_id)
    msg = bot.send_message(chat_id, "🎵 Введіть назву треку або виконавця для пошуку:" if lang == "uk" else "🎵 Введите название трека или исполнителя для поиска:")
    bot.register_next_step_handler(msg, process_music_search)

def process_music_search(message):
    chat_id = message.chat.id
    lang = get_user_lang(chat_id)
    query = message.text
    
    bot.send_message(chat_id, "⏳ Шукаю та завантажую музику..." if lang == "uk" else "⏳ Ищу и скачиваю музыку...")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'default_search': 'ytsearch1',
        'noplaylist': True,
        'outtmpl': os.path.join(BASE_DIR, 'music_temp.%(ext)s'),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            audio_path = os.path.splitext(filename)[0] + '.mp3'
            
        with open(audio_path, 'rb') as audio_file:
            bot.send_audio(chat_id, audio_file, reply_markup=get_user_keyboard(lang, chat_id))
            
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception as e:
        print(f"Music search error: {e}")
        bot.send_message(chat_id, "❌ Не вдалося знайти або завантажити трек.", reply_markup=get_user_keyboard(lang, chat_id))

# --- АДМІН-ПАНЕЛЬ ---
@bot.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID)
def admin_panel_dispatcher(message):
    chat_id = message.chat.id
    text = message.text

    if chat_id in admin_as_user_mode:
        if text == "👑 Повернутися в адмін-панель":
            admin_as_user_mode.remove(chat_id)
            bot.send_message(chat_id, "Ви повернулися в адмін-панель.", reply_markup=get_admin_keyboard())
            return
        # Якщо в режимі юзера - передаємо далі на стандартну обробку фото/тексту
        handle_user_messages(message)
        return

    if text == "👥 Список користувачів":
        bot.send_message(chat_id, f"👥 Кількість користувачів: {len(allowed_users)}")
    elif text == "📢 Розсилка":
        admin_broadcast_mode.add(chat_id)
        bot.send_message(chat_id, "✍️ Надішліть текст для розсилки всім користувачам:")
    elif text == "⚙️ Увімк./Вимк. бота":
        bot_config["bot_active"] = not bot_config["bot_active"]
        save_json(CONFIG_FILE, bot_config)
        status = "Увімкнено ✅" if bot_config["bot_active"] else "Вимкнено ❌"
        bot.send_message(chat_id, f"Статус бота: {status}", reply_markup=get_admin_keyboard())
    elif text == "🎬 Увімк./Вимк. генерацію відео":
        bot_config["video_enabled"] = not bot_config["video_enabled"]
        save_json(CONFIG_FILE, bot_config)
        status = "Увімкнено ✅" if bot_config["video_enabled"] else "Вимкнено ❌"
        bot.send_message(chat_id, f"Генерація відео: {status}", reply_markup=get_admin_keyboard())
    elif text == "👤 Вийти в режим юзера":
        admin_as_user_mode.add(chat_id)
        lang = get_user_lang(chat_id)
        bot.send_message(chat_id, "Ви перейшли в режим користувача.", reply_markup=get_user_keyboard(lang, chat_id))
    else:
        if chat_id in admin_broadcast_mode:
            admin_broadcast_mode.remove(chat_id)
            count = 0
            for uid in allowed_users:
                try:
                    bot.send_message(uid, text)
                    count += 1
                except:
                    pass
            bot.send_message(chat_id, f"📢 Розсилку завершено. Успішно надіслано: {count} користувачам.", reply_markup=get_admin_keyboard())
        else:
            bot.send_message(chat_id, "Оберіть дію на клавіатурі:", reply_markup=get_admin_keyboard())

# --- ОТРИМАННЯ ФОТОГРАФІЙ ВІД КОРИСТУВАЧІВ ---
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    chat_id = message.chat.id
    
    if not bot_config["bot_active"] and chat_id != ADMIN_ID:
        return
        
    if not bot_config["video_enabled"] and chat_id != ADMIN_ID:
        lang = get_user_lang(chat_id)
        bot.send_message(chat_id, "⚠️ Генерація відео тимчасово вимкнена адміністратором.", reply_markup=get_user_keyboard(lang, chat_id))
        return

    # Зберігаємо найвищу якість фото
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    if chat_id not in user_photos_buffer:
        user_photos_buffer[chat_id] = []

    user_photos_buffer[chat_id].append(downloaded_file)
    photos_count = len(user_photos_buffer[chat_id])
    lang = get_user_lang(chat_id)

    if photos_count < 3:
        msg = f"📸 Отримано фото {photos_count}/3. Надішліть ще." if lang == "uk" else f"📸 Получено фото {photos_count}/3. Пришлите еще."
        bot.send_message(chat_id, msg)
    else:
        bot.send_message(chat_id, "🎬 Починаю генерацію відео (зміна кадрів кожні 0.2с)..." if lang == "uk" else "🎬 Начинаю генерацию видео (смена кадров каждые 0.2с)...")
        photos_to_process = user_photos_buffer[chat_id].copy()
        user_photos_buffer[chat_id] = []  # Очищуємо буфер
        
        # Запускаємо рендеринг у фоновому потоці, щоб не блокувати бота
        threading.Thread(target=generate_video_from_photos, args=(chat_id, photos_to_process, lang)).start()

@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    chat_id = message.chat.id
    lang = get_user_lang(chat_id)
    bot.send_message(chat_id, "Будь ласка, надішліть фотографії для створення відео 📸" if lang == "uk" else "Пожалуйста, пришлите фотографии для создания видео 📸", reply_markup=get_user_keyboard(lang, chat_id))

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    keep_alive() # Запускаємо Flask на фоновому потоці для хостингу
    print("Бот успішно запущено!")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
