import concurrent.futures
import gc
import io
import json
import logging
import os
import random
import threading
from datetime import datetime
from flask import Flask
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from rapidfuzz import process
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
import yt_dlp
import psutil

# --- АВТОМАТИЧЕСКОЕ ЗАКРЫТИЕ СТАРЫХ КОПИЙ ---
current_pid = os.getpid()
current_script = os.path.basename(__file__)

for proc in psutil.process_iter(["pid", "name", "cmdline"]):
  try:
    if proc.info["pid"] != current_pid:
      cmdline = proc.info["cmdline"]
      if cmdline and any(current_script in arg for arg in cmdline):
        print(f'Закрываю старый экземпляр бота (PID: {proc.info["pid"]})')
        proc.kill()
  except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
    pass
# ---------------------------------------------

# --- ЗАХИЩЕНИЙ ІМПОРТ MOVIEPY ДЛЯ RENDER ---
try:
  from moviepy.editor import (
      CompositeVideoClip,
      ImageClip,
      concatenate_videoclips,
  )
except ImportError:
  try:
    from moviepy import (
        CompositeVideoClip,
        ImageClip,
        concatenate_videoclips,
    )
  except ImportError:
    from moviepy.video.VideoClip import ImageClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is alive and running!"


def run_web():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


TOKEN = "8658313360:AAGe5E7-ogE6nMqN8I3OlKuAZBqrthhckHg"
bot = telebot.TeleBot(TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOGS_LIST_FILE = os.path.join(BASE_DIR, "bot_logs_list.json")
USER_HISTORY_FILE = os.path.join(BASE_DIR, "user_history.json")

SUPER_ADMIN = "drborys".lower()
SUPER_ADMIN_ID = 1049082814

user_music_states = set()

# Хранилище ID сообщений с логами для каждого админа, чтобы авто-удалять их при клике на другие кнопки
admin_last_logs_msg = {}

# Состояния ожидания ввода для админов
admin_input_waiting = set()
admin_history_waiting = set()


def write_log(action_type, user_info, text):
  current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  log_entry = {
      "time": current_time,
      "user": str(user_info),
      "action": str(action_type),
      "details": str(text),
  }
  try:
    logs = []
    if os.path.exists(LOGS_LIST_FILE):
      with open(LOGS_LIST_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)
    logs.append(log_entry)
    if len(logs) > 100:
      logs = logs[-100:]
    with open(LOGS_LIST_FILE, "w", encoding="utf-8") as f:
      json.dump(logs, f, ensure_ascii=False, indent=4)
  except Exception as e:
    print(f"Log write error: {e}")


def track_user_changes(user):
  """Отслеживает изменения никнейма или имени пользователя и записывает в историю"""
  user_id_str = str(user.id)
  current_username = user.username.lower() if user.username else ""
  current_name = user.first_name if user.first_name else ""
  current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  history = {}
  if os.path.exists(USER_HISTORY_FILE):
    try:
      with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    except:
      pass

  if user_id_str not in history:
    history[user_id_str] = {
        "user_id": user.id,
        "records": [{
            "time": current_time,
            "username": current_username,
            "first_name": current_name,
        }],
    }
  else:
    user_records = history[user_id_str]["records"]
    last_record = user_records[-1] if user_records else {}
    if (
        last_record.get("username", "") != current_username
        or last_record.get("first_name", "") != current_name
    ):
      user_records.append({
          "time": current_time,
          "username": current_username,
          "first_name": current_name,
      })

  try:
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
      json.dump(history, f, ensure_ascii=False, indent=4)
  except Exception as e:
    print(f"History write error: {e}")


def clear_previous_logs_message(chat_id, user_id):
  """Удаляет предыдущее сообщение с логами, если оно было отправлено"""
  if user_id in admin_last_logs_msg:
    msg_ids = admin_last_logs_msg[user_id]
    if isinstance(msg_ids, list):
      for m_id in msg_ids:
        try:
          bot.delete_message(chat_id, m_id)
        except:
          pass
    else:
      try:
        bot.delete_message(chat_id, msg_ids)
      except:
        pass
    admin_last_logs_msg.pop(user_id, None)


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
  return {SUPER_ADMIN: SUPER_ADMIN_ID}


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
  return {
      "bot_enabled": True,
      "video_creation_enabled": True,
      "user_approval_required": True,
      "btn_music_enabled": True,
      "btn_lang_enabled": True,
      "btn_instruction_enabled": True,
      "btn_support_enabled": True,
      "admin_chat_ids": [SUPER_ADMIN_ID],
      "extra_admins": [],
  }


def save_config(config_dict):
  with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(config_dict, f, ensure_ascii=False, indent=4)


allowed_users = load_allowed_users()
config = load_config()

if "bot_enabled" not in config:
  config["bot_enabled"] = True
if "video_creation_enabled" not in config:
  config["video_creation_enabled"] = True
if "user_approval_required" not in config:
  config["user_approval_required"] = True
if "btn_music_enabled" not in config:
  config["btn_music_enabled"] = True
if "btn_lang_enabled" not in config:
  config["btn_lang_enabled"] = True
if "btn_instruction_enabled" not in config:
  config["btn_instruction_enabled"] = True
if "btn_support_enabled" not in config:
  config["btn_support_enabled"] = True
if "admin_chat_ids" not in config:
  config["admin_chat_ids"] = [SUPER_ADMIN_ID]
if "extra_admins" not in config:
  config["extra_admins"] = []
save_config(config)

admin_chat_states = {}
admin_as_user_mode = set()
user_photos_buffer = {}
user_support_mode = set()


def generate_large_quotes():
  ru_bases = [
      (
          "ты годами собираешь чужие инструкции и сохраняешь полезные гайды,"
          " но так и не делаешь первый шаг..\n\nначнешь применять знания на"
          " практике или снова пролистаешь.."
      ),
      (
          "ты выбираешь сидеть в тепле и комфорте, подсознательно пряча любые"
          " свои амбиции и цели..\n\nвыйдешь из зоны комфорта или снова"
          " пролистаешь.."
      ),
      (
          "время идет, а ты продолжаешь ждать идеального момента..\n\nа он"
          " никогда не наступит, пока ты не начнешь."
      ),
      (
          "дорога не прощает ошибок, она учит держать удар и идти до конца..\n\nтвоя"
          " цель стоит того, чтобы рискнуть?"
      ),
      (
          "никто не придет и не сделает твою жизнь лучше за тебя..\n\nхватит"
          " откладывать себя на потом."
      ),
  ]
  ua_bases = [
      (
          "ти роками збираєш чужі інструкції та зберігаєш корисні гайди, але так"
          " і не робиш перший крок..\n\nпочнешь застосовувати знання на практиці"
          " чи знову прогорнеш.."
      ),
      (
          "ти обираєш сидіти в теплі і комфорті, підсвідомо ховаючи будь-які свої"
          " амбіції та цілі..\n\nвийдеш із зони комфорту чи знову прогорнеш.."
      ),
      (
          "час іде, а ты продовжуєш чекати на ідеальний момент..\n\nа він ніколи"
          " не настане, поки ты не почнеш."
      ),
      (
          "дорога не прощає помилок, вона вчить тримати удар і йти до кінця..\n\nтвоя"
          " мета варта того, щоб ризикнути?"
      ),
      (
          "ніхто не прийде і не зробить твоє життя кращим за тебе..\n\nдосить"
          " відкладати себе на потом."
      ),
  ]
  return {"ru": ru_bases, "ua": ua_bases}


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
        "bot_globally_disabled": (
            "🛠 Бот временно отключен администратором и находится на"
            " техническом обслуживании."
        ),
        "video_disabled_for_users": (
            "⛔ Создание видео временно отключено администратором."
        ),
        "feature_disabled": "⛔ Эта функция временно отключена администратором.",
        "active": (
            "🎬 Бот активен! Отправьте **минимум 3 фотографии**, чтобы бот"
            " собрал из них динамичное видео."
        ),
        "photo_saved": (
            "📥 Фото принято ({}/3). Отправьте еще, чтобы запустить создание"
            " видео."
        ),
        "lang_select": "🌐 Выберите язык / Оберіть мову:",
        "lang_changed": "✅ Язык успешно изменен на русский!",
        "rendering": (
            "⚡ Накопилось 3 фото! Создаю быстрые переходы и накладываю"
            " текст..."
        ),
        "error": "❌ Произошла ошибка при создании видео, попробуйте еще раз.",
    },
    "ua": {
        "access_denied": "⛔ У вас немає доступу до цього бота.",
        "bot_globally_disabled": (
            "🛠 Бот тимчасово вимкнений адміністратором на технічне обслуговування."
        ),
        "video_disabled_for_users": (
            "⛔ Створення відео тимчасово вимкнено адміністратором."
        ),
        "feature_disabled": "⛔ Цю функцію тимчасово вимкнено адміністратором.",
        "active": (
            "🎬 Бот активний! Надішліть **мінімум 3 фотографії**, щоб бот зібрав"
            " із них динамічне відео."
        ),
        "photo_saved": (
            "📥 Фото прийнято ({}/3). Надішліть ще, щоб запустити створення"
            " відео."
        ),
        "lang_select": "🌐 Оберіть мову / Выберите язык:",
        "lang_changed": "✅ Мову успішно змінено на українську!",
        "rendering": (
            "⚡ Зібралося 3 фото! Створюю швидкі переходи та накладаю текст..."
        ),
        "error": (
            "❌ Сталася помилка під час створення відео, спробуйте ще раз."
        ),
    },
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
  admin_ids = config.get("admin_chat_ids", [SUPER_ADMIN_ID])
  extra_admins = config.get("extra_admins", [])
  is_extra = False
  if username and username.lower().lstrip("@") in [
      str(x).lower().lstrip("@") for x in extra_admins
  ]:
    is_extra = True
  if user_id in [int(x) for x in extra_admins if str(x).isdigit()]:
    is_extra = True
  return (
      user_id in admin_ids
      or user_id == SUPER_ADMIN_ID
      or (username and username.lower() == SUPER_ADMIN)
      or is_extra
  )


def is_allowed(message):
  if is_super_admin(message):
    return True
  if not config.get("user_approval_required", True):
    return True
  username = message.from_user.username
  if not username:
    return str(message.from_user.id) in allowed_users.values()
  return username.lower() in allowed_users


def get_admin_keyboard(user_id=None):
  kb = ReplyKeyboardMarkup(resize_keyboard=True)
  is_on = config.get("bot_enabled", True)
  status_btn_text = (
      "🟢 Бот ВКЛЮЧЕН (Нажмите для откл)"
      if is_on
      else "🔴 Бот ВЫКЛЮЧЕН (Нажмите для вкл)"
  )
  kb.row(KeyboardButton(status_btn_text))
  kb.row(KeyboardButton("⚙️ Управление кнопками и функциями"))
  kb.row(KeyboardButton("👥 Управление пользователями"))
  kb.row(KeyboardButton("📜 Логи сообщений"))
  if user_id and user_id in admin_as_user_mode:
    kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))
  else:
    kb.row(KeyboardButton("👤 Вийти в режим юзера (Тест)"))
  return kb


def get_admin_panel_inline():
  kb = InlineKeyboardMarkup(row_width=1)
  is_video_on = config.get("video_creation_enabled", True)
  is_approval_on = config.get("user_approval_required", True)
  is_music_on = config.get("btn_music_enabled", True)
  is_lang_on = config.get("btn_lang_enabled", True)
  is_instruction_on = config.get("btn_instruction_enabled", True)
  is_support_on = config.get("btn_support_enabled", True)

  video_text = (
      "🟢 Генерація відео: УВІМКНЕНА"
      if is_video_on
      else "🔴 Генерація відео: ВИМКНЕНА"
  )
  approval_text = (
      "🟢 Запит доступу юзерів: УВІМКНЕН"
      if is_approval_on
      else "🔴 Запит доступу юзерів: ВИМКНЕН"
  )
  music_text = "🟢 Кнопка 'Музика': ВКЛ" if is_music_on else "🔴 Кнопка 'Музика': ВЫКЛ"
  lang_text = (
      "🟢 Кнопка 'Зміна мови': ВКЛ" if is_lang_on else "🔴 Кнопка 'Зміна мови': ВЫКЛ"
  )
  instruction_text = (
      "🟢 Кнопка 'Інструкція': ВКЛ"
      if is_instruction_on
      else "🔴 Кнопка 'Інструкція': ВЫКЛ"
  )
  support_text = (
      "🟢 Кнопка 'Скарга/Адмін': ВКЛ"
      if is_support_on
      else "🔴 Кнопка 'Скарга/Адмін': ВЫКЛ"
  )

  kb.add(
      InlineKeyboardButton(video_text, callback_data="toggle_video_generation")
  )
  kb.add(
      InlineKeyboardButton(
          approval_text, callback_data="toggle_approval_requirement"
      )
  )
  kb.add(InlineKeyboardButton(music_text, callback_data="toggle_btn_music"))
  kb.add(InlineKeyboardButton(lang_text, callback_data="toggle_btn_lang"))
  kb.add(
      InlineKeyboardButton(
          instruction_text, callback_data="toggle_btn_instruction"
      )
  )
  kb.add(InlineKeyboardButton(support_text, callback_data="toggle_btn_support"))
  kb.add(
      InlineKeyboardButton(
          "🔙 Назад в головне меню", callback_data="admin_back_main"
      )
  )
  return kb


def get_user_keyboard(lang, user_id=None):
  kb = ReplyKeyboardMarkup(resize_keyboard=True)
  if user_id and is_super_admin(
      type(
          "Obj",
          (object,),
          {
              "from_user": type(
                  "Usr", (object,), {"id": user_id, "username": None}
              )
          },
      )
  ):
    kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))

  row1 = []
  if config.get("btn_lang_enabled", True):
    row1.append(
        KeyboardButton(
            "🌐 Сменить язык" if lang == "ru" else "🌐 Змінити мову"
        )
    )
  if config.get("btn_instruction_enabled", True):
    row1.append(
        KeyboardButton("🎬 Инструкция" if lang == "ru" else "🎬 Інструкція")
    )
  if row1:
    kb.row(*row1)

  row2 = []
  if config.get("btn_music_enabled", True):
    row2.append(KeyboardButton("🎵 Музика"))
  if config.get("btn_support_enabled", True):
    row2.append(
        KeyboardButton(
            "⚠ Пожаловаться / Написать админу"
            if lang == "ru"
            else "⚠️ Поскаржитися / Написати адміну"
        )
    )
  if row2:
    kb.row(*row2)

  return kb


def prepare_photo_with_letterbox(photo_bytes, text):
  base_img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
  target_w, target_h = 1080, 1920
  img_w, img_h = base_img.size
  new_w = target_w
  new_h = int(img_h * (target_w / img_w))
  if new_h > target_h:
    new_h = target_h
    new_w = int(img_w * (target_h / img_h))
  base_img = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
  canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 255))
  paste_x = (target_w - new_w) // 2
  paste_y = (target_h - new_h) // 2
  canvas.paste(base_img, (paste_x, paste_y), base_img)
  draw = ImageDraw.Draw(canvas)
  font_path = os.path.join(BASE_DIR, "font.ttf")
  if not os.path.exists(font_path):
    font_path = "C:/Windows/Fonts/impact.ttf"
  try:
    font = ImageFont.truetype(font_path, 52)
  except:
    font = ImageFont.load_default()

  text_color = (255, 255, 255, 255)
  shadow_color = (0, 0, 0, 255)
  parts = text.split("\n\n")
  main_part = parts[0] if len(parts) > 0 else text
  sub_part = parts[1] if len(parts) > 1 else ""

  def wrap_text(text_block):
    paragraphs = text_block.split("\n")
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
  start_y_main = (target_h - total_main_height) / 2 - 100
  y = start_y_main
  for line in main_lines:
    if line == "":
      y += line_height / 2
      continue
    try:
      w = font.getlength(line)
    except:
      w = len(line) * 22
    x = (target_w - w) / 2
    shadow_offset = 3
    for dx, dy in [
        (-shadow_offset, -shadow_offset),
        (shadow_offset, -shadow_offset),
        (-shadow_offset, shadow_offset),
        (shadow_offset, shadow_offset),
        (-shadow_offset, 0),
        (shadow_offset, 0),
        (0, -shadow_offset),
        (0, shadow_offset),
    ]:
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
      x = (target_w - w) / 2
      shadow_offset = 3
      for dx, dy in [
          (-shadow_offset, -shadow_offset),
          (shadow_offset, -shadow_offset),
          (-shadow_offset, shadow_offset),
          (shadow_offset, shadow_offset),
          (-shadow_offset, 0),
          (shadow_offset, 0),
          (0, -shadow_offset),
          (0, shadow_offset),
      ]:
        draw.text((x + dx, y + dy), line, font=font, fill=shadow_color)
      draw.text((x, y), line, font=font, fill=text_color)
      y += line_height
  return canvas


@bot.message_handler(commands=["start"])
def start(message):
  user = message.from_user
  user_id = user.id
  lang = get_user_lang(user_id)

  track_user_changes(user)
  clear_previous_logs_message(message.chat.id, user_id)

  write_log(
      "КОМАНДА /START",
      f"@{user.username} (ID: {user_id}, Имя: {user.first_name})",
      "Запуск бота",
  )
  if user.username:
    uname = user.username.lower()
    if uname in allowed_users:
      allowed_users[uname] = user_id
      save_allowed_users(allowed_users)

  if is_super_admin(message) and user_id not in admin_as_user_mode:
    admin_chats = config.get("admin_chat_ids", [SUPER_ADMIN_ID])
    if message.chat.id not in admin_chats:
      admin_chats.append(message.chat.id)
      config["admin_chat_ids"] = admin_chats
      save_config(config)
    admin_panel_text = (
        "👑 **Панель администратора:**\n\nИспользуйте кнопки меню внизу для"
        " доступа к разделам:"
    )
    bot.send_message(
        message.chat.id,
        admin_panel_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  if not config.get("bot_enabled", True) and not is_super_admin(message):
    bot.send_message(message.chat.id, TEXTS[lang]["bot_globally_disabled"])
    return

  if not is_allowed(message):
    bot.send_message(message.chat.id, TEXTS[lang]["access_denied"])
    admin_chats = config.get("admin_chat_ids", [SUPER_ADMIN_ID])
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "💬 Написать", callback_data=f"chat_with_{user.id}"
        ),
        InlineKeyboardButton(
            "❌ Запретить",
            callback_data=f"deny_{user.id}_{user.username or 'noupname'}",
        ),
    )
    for admin_chat_id in admin_chats:
      try:
        bot.send_message(
            admin_chat_id,
            (
                "🔔 **Запрос доступа от пользователя:**\nИмя: "
                f"{user.first_name}\nЮзернейм: "
                f"@{user.username if user.username else 'нет'}\nID: `{user.id}`"
            ),
            parse_mode="Markdown",
            reply_markup=markup,
        )
      except Exception as e:
        print(f"Failed to notify admin {admin_chat_id}: {e}")
    return

  if user_id in user_support_mode:
    user_support_mode.remove(user_id)
  if user_id in user_music_states:
    user_music_states.remove(user_id)

  keyboard_music = InlineKeyboardMarkup()
  if config.get("btn_music_enabled", True):
    keyboard_music.row(
        InlineKeyboardButton("🎵 Музика", callback_data="btn_music_menu")
    )
  bot.send_message(
      user_id,
      TEXTS[lang]["active"],
      reply_markup=get_user_keyboard(lang, user_id),
  )
  if config.get("btn_music_enabled", True):
    bot.send_message(
        user_id,
        (
            "Також ви можете скористатися пошуком та завантаженням музики через"
            " кнопку нижче:"
        ),
        reply_markup=keyboard_music,
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
  user_id = call.from_user.id
  lang = get_user_lang(user_id)
  is_admin = is_super_admin(call) and user_id not in admin_as_user_mode

  if call.data != "close_logs":
    clear_previous_logs_message(call.message.chat.id, user_id)

  if call.data == "btn_music_menu":
    if not config.get("btn_music_enabled", True):
      bot.answer_callback_query(
          call.id, TEXTS[lang]["feature_disabled"], show_alert=True
      )
      return
    user_music_states.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "Введи назву треку або виконавця (можна з помилками, я знайду):",
    )
    return

  if call.data == "close_logs":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    clear_previous_logs_message(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id, "🗑 Логи скрыты и удалены!")
    return

  if call.data == "admin_manage_admins":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    markup = InlineKeyboardMarkup(row_width=1)
    extra_admins = config.get("extra_admins", [])
    markup.add(
        InlineKeyboardButton(
            "➕ Добавить админа", callback_data="admin_add_admin_prompt"
        )
    )
    for adm in extra_admins:
      markup.add(
          InlineKeyboardButton(
              f"❌ Удалить @{adm}", callback_data=f"del_admin_{adm}"
          )
      )
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_users_menu"))
    try:
      bot.edit_message_text(
          "🛡 **Список дополнительных администраторов:**",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except:
      pass
    return

  if call.data.startswith("del_admin_"):
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    adm_to_del = call.data.replace("del_admin_", "")
    extra_admins = config.get("extra_admins", [])
    if adm_to_del in extra_admins:
      extra_admins.remove(adm_to_del)
      config["extra_admins"] = extra_admins
      save_config(config)
    bot.answer_callback_query(call.id, f"✅ Администратор @{adm_to_del} удален!")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "➕ Добавить админа", callback_data="admin_add_admin_prompt"
        )
    )
    for adm in extra_admins:
      markup.add(
          InlineKeyboardButton(
              f"❌ Удалить @{adm}", callback_data=f"del_admin_{adm}"
          )
      )
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_users_menu"))
    try:
      bot.edit_message_text(
          "🛡 **Список дополнительных администраторов:**",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except:
      pass
    return

  if call.data == "toggle_video_generation":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    current_status = config.get("video_creation_enabled", True)
    config["video_creation_enabled"] = not current_status
    save_config(config)
    updated_kb = get_admin_panel_inline()
    alert_text = (
        "✅ Генерація відео ввімкнена!"
        if config["video_creation_enabled"]
        else "❌ Генерація відео вимкнена!"
    )
    try:
      bot.answer_callback_query(call.id, alert_text)
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=updated_kb,
      )
    except:
      pass
    return

  if call.data == "toggle_approval_requirement":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    current_status = config.get("user_approval_requirement", True)
    config["user_approval_requirement"] = not current_status
    save_config(config)
    updated_kb = get_admin_panel_inline()
    alert_text = (
        "✅ Запит доступу ввімкнено!"
        if config["user_approval_requirement"]
        else "❌ Запит доступу вимкнено (вільний вхід)!"
    )
    try:
      bot.answer_callback_query(call.id, alert_text)
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=updated_kb,
      )
    except:
      pass
    return

  if call.data == "toggle_btn_music":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    config["btn_music_enabled"] = not config.get("btn_music_enabled", True)
    save_config(config)
    try:
      bot.answer_callback_query(
          call.id,
          (
              "✅ Кнопка Музыка включена"
              if config["btn_music_enabled"]
              else "❌ Кнопка Музыка выключена"
          ),
      )
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=get_admin_panel_inline(),
      )
    except:
      pass
    return

  if call.data == "toggle_btn_lang":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    config["btn_lang_enabled"] = not config.get("btn_lang_enabled", True)
    save_config(config)
    try:
      bot.answer_callback_query(
          call.id,
          (
              "✅ Кнопка Смена языка включена"
              if config["btn_lang_enabled"]
              else "❌ Кнопка Смена языка выключена"
          ),
      )
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=get_admin_panel_inline(),
      )
    except:
      pass
    return

  if call.data == "toggle_btn_instruction":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    config["btn_instruction_enabled"] = not config.get(
        "btn_instruction_enabled", True
    )
    save_config(config)
    try:
      bot.answer_callback_query(
          call.id,
          (
              "✅ Кнопка Инструкция включена"
              if config["btn_instruction_enabled"]
              else "❌ Кнопка Инструкция выключена"
          ),
      )
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=get_admin_panel_inline(),
      )
    except:
      pass
    return

  if call.data == "toggle_btn_support":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    config["btn_support_enabled"] = not config.get("btn_support_enabled", True)
    save_config(config)
    try:
      bot.answer_callback_query(
          call.id,
          (
              "✅ Кнопка Жалобы включена"
              if config["btn_support_enabled"]
              else "❌ Кнопка Жалобы выключена"
          ),
      )
      bot.edit_message_reply_markup(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          reply_markup=get_admin_panel_inline(),
      )
    except:
      pass
    return

  if call.data.startswith("setlang_"):
    if not config.get("btn_lang_enabled", True) and not is_admin:
      bot.answer_callback_query(
          call.id, TEXTS[lang]["feature_disabled"], show_alert=True
      )
      return
    new_lang = call.data.split("_")[1]
    set_user_lang(user_id, new_lang)
    bot.answer_callback_query(call.id, "OK")
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=TEXTS[new_lang]["lang_changed"],
    )
    bot.send_message(
        call.message.chat.id,
        "Главное меню:",
        reply_markup=(
            get_admin_keyboard(user_id)
            if (is_super_admin(call) and user_id not in admin_as_user_mode)
            else get_user_keyboard(new_lang, user_id)
        ),
    )
    return

  if call.data == "admin_users_menu":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "📋 Список пользователей", callback_data="admin_user_list"
        ),
        InlineKeyboardButton(
            "✍️ Написать пользователю", callback_data="admin_write_user_prompt"
        ),
        InlineKeyboardButton(
            "🔍 История смены ников/ID",
            callback_data="admin_check_history_prompt",
        ),
        InlineKeyboardButton(
            "🛡 Управление админами", callback_data="admin_manage_admins"
        ),
        InlineKeyboardButton(
            "🔙 Назад в головне меню", callback_data="admin_back_main"
        ),
    )
    try:
      bot.edit_message_text(
          "👥 **Панель управления пользователями и администраторами:**",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except:
      bot.send_message(
          call.message.chat.id,
          "👥 **Панель управления пользователями и администраторами:**",
          parse_mode="Markdown",
          reply_markup=markup,
      )
    return

  if call.data == "admin_check_history_prompt":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    admin_history_waiting.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🔍 **Введите Telegram ID (номер) или username** пользователя для"
        " просмотра истории:",
        parse_mode="Markdown",
    )
    return

  if call.data == "admin_add_admin_prompt":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    admin_input_waiting.add(user_id)
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "✍️ **Введите юзернейм (ник) нового администратора** (без @):",
        parse_mode="Markdown",
    )
    return

  if call.data == "admin_back_main":
    if not is_super_admin(call):
      return
    try:
      bot.edit_message_text(
          "👑 **Главное меню администратора:**\n\nВыберите нужный раздел на панели"
          " управления внизу или используйте кнопки ниже:",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=InlineKeyboardMarkup().add(
              InlineKeyboardButton(
                  "⚙️ Керування налаштуваннями бота",
                  callback_data="admin_settings_menu_open",
              ),
              InlineKeyboardButton(
                  "👥 Управление пользователями",
                  callback_data="admin_users_menu",
              ),
          ),
      )
    except:
      pass
    return

  if call.data == "admin_settings_menu_open":
    if not is_super_admin(call):
      return
    try:
      bot.edit_message_text(
          "⚙ **Керування налаштуваннями бота та кнопками:**",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=get_admin_panel_inline(),
      )
    except:
      pass
    return

  if call.data == "admin_user_list":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    users_list = "\n".join([
        f"• @{u} (ID: {uid if uid != 0 else 'нет'})"
        for u, uid in allowed_users.items()
    ])
    bot.answer_callback_query(call.id, "Список сформирован")
    bot.send_message(
        call.message.chat.id,
        f"📋 **Список разрешенных пользователей:**\n\n{users_list}",
        parse_mode="Markdown",
    )
    return

  if call.data == "admin_write_user_prompt":
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    markup = InlineKeyboardMarkup()
    for u, uid in allowed_users.items():
      if u.lower() == SUPER_ADMIN:
        continue
      if uid and uid != 0:
        markup.row(
            InlineKeyboardButton(
                f"@{u} (ID: {uid})", callback_data=f"select_user_id_{uid}"
            )
        )
      else:
        markup.row(
            InlineKeyboardButton(f"@{u} (Нет ID)", callback_data=f"no_id_{u}")
        )
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_users_menu"))
    if len(markup.keyboard) == 1:
      bot.answer_callback_query(call.id, "Список пуст", show_alert=True)
    else:
      bot.edit_message_text(
          "👥 **Выберите пользователя для диалога:**",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    return

  if call.data.startswith("select_user_id_") or call.data.startswith(
      "chat_with_"
  ):
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    target_chat_id = int(call.data.split("_")[-1])
    admin_chat_states[user_id] = target_chat_id
    bot.answer_callback_query(call.id, "Режим диалога активирован")
    user_info_extra = f"🆔 ID: `{target_chat_id}`"
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "❌ Завершить этот диалог", callback_data="exit_chat"
        )
    )
    try:
      bot.edit_message_text(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          text=f"✍ **Режим диалога активен:**\n\n{user_info_extra}",
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except:
      bot.send_message(
          chat_id=call.message.chat.id,
          text=f"✍ **Режим диалога активен:**\n\n{user_info_extra}",
          parse_mode="Markdown",
          reply_markup=markup,
      )
    return

  if call.data.startswith("no_id_"):
    bot.answer_callback_query(
        call.id,
        "⚠ У этого пользователя нет ID. Попросите его нажать /start!",
        show_alert=True,
    )
    return

  if call.data == "exit_chat":
    if user_id in admin_chat_states:
      del admin_chat_states[user_id]
    bot.answer_callback_query(call.id, "Диалог завершен")
    try:
      bot.edit_message_text(
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          text="❌ Режим диалога с пользователем завершен.",
      )
    except:
      bot.send_message(
          call.message.chat.id, "❌ Режим диалога с пользователем завершен."
      )
    return

  if call.data.startswith("allow_") or call.data.startswith("deny_"):
    if not is_super_admin(call):
      bot.answer_callback_query(call.id, "⛔ У вас нет прав!", show_alert=True)
      return
    data_parts = call.data.split("_")
    action = data_parts[0]
    target_user_id = int(data_parts[1])
    username = data_parts[2] if len(data_parts) > 2 else ""
    if username == "noupname":
      username = ""
    else:
      username = username.lower()
    target_lang = get_user_lang(target_user_id)
    markup = InlineKeyboardMarkup()
    if action == "allow":
      if username:
        allowed_users[username] = target_user_id
      else:
        allowed_users[str(target_user_id)] = target_user_id
      save_allowed_users(allowed_users)
      bot.answer_callback_query(call.id, "✅ Доступ разрешен!")
      markup.row(
          InlineKeyboardButton(
              "💬 Написать", callback_data=f"chat_with_{target_user_id}"
          ),
          InlineKeyboardButton(
              "❌ Запретить",
              callback_data=f"deny_{target_user_id}_{username or 'noupname'}",
          ),
      )
      try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"✅ Запрос от @{username if username else target_user_id}"
                " **ОДОБРЕН**."
            ),
            parse_mode="Markdown",
            reply_markup=markup,
        )
      except:
        pass
      try:
        msg = (
            "🎉 Администратор одобрил ваш доступ! Нажмите /start."
            if target_lang == "ru"
            else "🎉 Адміністратор схвалив ваш доступ! Натисніть /start."
        )
        bot.send_message(target_user_id, msg)
      except:
        pass
    elif action == "deny":
      if username and username in allowed_users:
        del allowed_users[username]
      elif str(target_user_id) in allowed_users:
        del allowed_users[str(target_user_id)]
      save_allowed_users(allowed_users)
      bot.answer_callback_query(call.id, "❌ Доступ отклонен.")
      markup.row(
          InlineKeyboardButton(
              "✅ Разрешить",
              callback_data=f"allow_{target_user_id}_{username or 'noupname'}",
          )
      )
      try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"❌ Запрос от @{username if username else target_user_id}"
                " **ОТКЛОНЕН**."
            ),
            parse_mode="Markdown",
            reply_markup=markup,
        )
      except:
        pass
      try:
        msg = (
            "⛔ В доступе отказано."
            if target_lang == "ru"
            else "⛔ У доступі відмовлено."
        )
        bot.send_message(target_user_id, msg)
      except:
        pass


@bot.message_handler(
    func=lambda message: (
        is_super_admin(message) and message.from_user.id not in admin_as_user_mode
    ),
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "sticker",
    ],
)
def handle_admin_messages(message):
  user_id = message.from_user.id
  text = message.text

  clear_previous_logs_message(message.chat.id, user_id)

  # --- ЛОГИ ПЕРЕНЕСЕНЫ САМЫМИ ПЕРВЫМИ ДЛЯ СТОП-ГАРАНТИИ РАБОТЫ ---
  if text == "📜 Логи сообщений":
    logs_data = []
    if os.path.exists(LOGS_LIST_FILE):
      try:
        with open(LOGS_LIST_FILE, "r", encoding="utf-8") as lf:
          logs_data = json.load(lf)
      except:
        pass

    if logs_data:
      log_text = "📜 **Все логи (от начала / последние записи):**\n\n"
      for entry in logs_data:
        log_text += (
            f"🕒 `{entry['time']}`\n👤 {entry['user']}\n⚙"
            f" {entry['action']}\n💬 {entry['details']}\n-------------------\n"
        )
    else:
      log_text = "ℹ️ Логи пока пустые."

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "❌ Закрыть и удалить логи", callback_data="close_logs"
        )
    )

    sent_msg_ids = []
    if len(log_text) > 4000:
      chunks = [log_text[i : i + 4000] for i in range(0, len(log_text), 4000)]
      for idx, chunk in enumerate(chunks):
        if idx == len(chunks) - 1:
          m = bot.send_message(
              message.chat.id, chunk, parse_mode="Markdown", reply_markup=markup
          )
        else:
          m = bot.send_message(message.chat.id, chunk, parse_mode="Markdown")
        sent_msg_ids.append(m.message_id)
    else:
      m = bot.send_message(
          message.chat.id, log_text, parse_mode="Markdown", reply_markup=markup
      )
      sent_msg_ids.append(m.message_id)

    admin_last_logs_msg[user_id] = sent_msg_ids
    return
  # -------------------------------------------------------------

  if user_id in admin_history_waiting:
    admin_history_waiting.remove(user_id)
    query = text.strip().lstrip("@").lower()

    history_data = {}
    if os.path.exists(USER_HISTORY_FILE):
      try:
        with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
          history_data = json.load(f)
      except:
        pass

    found_user_id = None
    for uid_str, u_info in history_data.items():
      if uid_str == query or str(u_info.get("user_id")) == query:
        found_user_id = uid_str
        break
      for rec in u_info.get("records", []):
        if rec.get("username", "").lower() == query:
          found_user_id = uid_str
          break
      if found_user_id:
        break

    if not found_user_id or found_user_id not in history_data:
      bot.send_message(
          message.chat.id,
          f"❌ История для запроса `{text}` не найдена.",
          parse_mode="Markdown",
          reply_markup=get_admin_keyboard(user_id),
      )
      return

    u_data = history_data[found_user_id]
    real_player_id = u_data.get("user_id")
    resp_text = (
        f"🎯 **Игрок найден!**\n🆔 Номер игрока (ID): `{real_player_id}`\n\n📜"
        " **История изменений:**\n\n"
    )
    for idx, r in enumerate(u_data.get("records", []), start=1):
      uname_display = (
          f"@{r.get('username')}" if r.get("username") else "нет юзернейма"
      )
      name_display = r.get("first_name", "Без имени")
      resp_text += (
          f"📌 **№{idx}** | 🕒 `{r.get('time')}`\n   • Имя: `{name_display}`\n  "
          f" • Ник: `{uname_display}`\n-------------------\n"
      )

    bot.send_message(
        message.chat.id,
        resp_text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  if user_id in admin_input_waiting:
    admin_input_waiting.remove(user_id)
    target_username = text.strip().lstrip("@").lower()
    extra_admins = config.get("extra_admins", [])
    if target_username not in [
        str(x).lower().lstrip("@") for x in extra_admins
    ]:
      extra_admins.append(target_username)
      config["extra_admins"] = extra_admins
      save_config(config)
    bot.send_message(
        message.chat.id,
        f"✅ Пользователю **@{target_username}** успешно выданы права"
        " администратора!",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  if message.content_type == "photo" and user_id not in admin_chat_states:
    handle_user_messages(message)
    return

  if text in [
      "⚠ Пожаловаться / Написать админу",
      "⚠️ Поскаржитися / Написати адміну",
      "❌ Завершить диалог",
      "❌ Завершити діалог",
  ]:
    handle_user_messages(message)
    return

  if text and ("Бот ВКЛЮЧЕН" in text or "Бот ВЫКЛЮЧЕН" in text):
    config["bot_enabled"] = not config.get("bot_enabled", True)
    save_config(config)
    status_msg = (
        "🟢 **Бот ВКЛЮЧЕН!**"
        if config["bot_enabled"]
        else "🔴 **Бот ВЫКЛЮЧЕН!**"
    )
    bot.send_message(
        message.chat.id,
        status_msg,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  elif text == "👤 Вийти в режим юзера (Тест)":
    admin_as_user_mode.add(user_id)
    lang = get_user_lang(user_id)
    bot.send_message(
        message.chat.id,
        "👤 Ви в режимі користувача.",
        reply_markup=get_user_keyboard(lang, user_id),
    )
    return

  elif text == "👑 Повернутися в адмін-панель":
    if user_id in admin_as_user_mode:
      admin_as_user_mode.remove(user_id)
    bot.send_message(
        message.chat.id,
        "👑 Повернення в адмін-панель!",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  elif text == "⚙️ Управление кнопками и функциями":
    bot.send_message(
        message.chat.id,
        "⚙ **Керування налаштуваннями бота та кнопками:**",
        parse_mode="Markdown",
        reply_markup=get_admin_panel_inline(),
    )
    return

  elif text == "👥 Управление пользователями":
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "📋 Список пользователей", callback_data="admin_user_list"
        ),
        InlineKeyboardButton(
            "✍️ Написать пользователю", callback_data="admin_write_user_prompt"
        ),
        InlineKeyboardButton(
            "🔍 История смены ников/ID",
            callback_data="admin_check_history_prompt",
        ),
        InlineKeyboardButton(
            "🛡 Управление админами", callback_data="admin_manage_admins"
        ),
        InlineKeyboardButton(
            "🔙 Назад в головне меню", callback_data="admin_back_main"
        ),
    )
    bot.send_message(
        message.chat.id,
        "👥 **Панель управления пользователями и администраторами:**",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    return

  if user_id in admin_chat_states:
    target_chat_id = admin_chat_states[user_id]
    if text:
      write_log(
          "ОТВЕТ АДМИНА",
          f"Админ -> Пользователю {target_chat_id}",
          text,
      )
    try:
      bot.copy_message(
          chat_id=target_chat_id,
          from_chat_id=message.chat.id,
          message_id=message.message_id,
      )
    except Exception as e:
      bot.send_message(
          message.chat.id,
          f"❌ Ошибка отправки: {e}",
          reply_markup=get_admin_keyboard(user_id),
      )
  else:
    if text and not text.startswith("/"):
      handle_user_messages(message)
      return
    bot.send_message(
        message.chat.id,
        "ℹ️ Воспользуйтесь кнопкой внизу.",
        reply_markup=get_admin_keyboard(user_id),
    )


@bot.message_handler(
    func=lambda message: (
        not is_super_admin(message) or message.from_user.id in admin_as_user_mode
    ),
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "sticker",
    ],
)
def handle_user_messages(message):
  user = message.from_user
  user_id = user.id
  lang = get_user_lang(user_id)
  text = message.text
  is_admin = is_super_admin(message)

  track_user_changes(user)

  if text == "👑 Повернутися в адмін-панель" and is_admin:
    if user_id in admin_as_user_mode:
      admin_as_user_mode.remove(user_id)
    bot.send_message(
        message.chat.id,
        "👑 Повернення в адмін-панель!",
        reply_markup=get_admin_keyboard(user_id),
    )
    return

  if text:
    uname_str = f"@{user.username}" if user.username else f"ID:{user_id}"
    write_log(
        "СООБЩЕНИЕ ЮЗЕРА",
        f"{uname_str} (ID: {user_id}, Имя: {user.first_name})",
        text,
    )

  if not config.get("bot_enabled", True) and not is_admin:
    bot.send_message(message.chat.id, TEXTS[lang]["bot_globally_disabled"])
    return

  if not is_allowed(message):
    bot.send_message(message.chat.id, TEXTS[lang]["access_denied"])
    return

  ignored_texts = [
      "🌐 Сменить язык",
      "🌐 Змінити мову",
      "🎬 Инструкция",
      "🎬 Інструкція",
      "🎵 Музика",
      "⚠ Пожаловаться / Написать админу",
      "⚠ Поскаржитися / Написати адміну",
      "❌ Завершить диалог",
      "❌ Завершити діалог",
  ]

  if text == "🎵 Музика":
    if not config.get("btn_music_enabled", True) and not is_admin:
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    user_music_states.add(user_id)
    bot.send_message(
        message.chat.id,
        "Введи назву треку або виконавця (можна з помилками, я знайду):",
    )
    return

  if (
      user_id in user_music_states
      and text not in ignored_texts
      and not text.startswith("/")
  ):
    if not config.get("btn_music_enabled", True) and not is_admin:
      user_music_states.remove(user_id)
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    user_music_states.remove(user_id)
    user_query = text.strip()

    popular_tracks = [
        "Måneskin - ZITTI E BUONI",
        "Imagine Dragons - Believer",
        "The Weeknd - Blinding Lights",
        "Phonk - Drift Samping",
        "Billie Eilish - bad guy",
        "Eminem - Rap God",
        "DVRST - Close Eyes",
        "Kavinsky - Nightcall",
    ]

    match_result = process.extractOne(user_query, popular_tracks)
    if match_result and match_result[1] > 40:
      search_query = match_result[0]
      bot.send_message(
          message.chat.id,
          f"🔍 Виправлено запит (знайдено схоже): <b>{search_query}</b>",
          parse_mode="HTML",
      )
    else:
      search_query = user_query

    processing_msg = bot.send_message(
        message.chat.id, "⏳ Шукаю і завантажую аудіо, зачекай кілька секунд..."
    )

    file_base_name = f"audio_{user_id}"
    mp3_file_name = f"{file_base_name}.mp3"

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": file_base_name,
        "default_search": "ytsearch1:",
        "quiet": True,
    }

    def download_audio():
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([search_query])

    try:
      with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(download_audio)
        future.result()

      if os.path.exists(mp3_file_name):
        with open(mp3_file_name, "rb") as audio_file:
          bot.send_audio(
              message.chat.id,
              audio_file,
              caption=f"🎵 Запит: {user_query}",
              reply_markup=get_user_keyboard(lang, user_id),
          )
        os.remove(mp3_file_name)
      else:
        bot.send_message(
            message.chat.id,
            "❌ На жаль, не вдалося знайти або завантажити трек за цим запитом.",
            reply_markup=get_user_keyboard(lang, user_id),
        )
    except Exception as e:
      print(f"Music download error: {e}")
      bot.send_message(
          message.chat.id,
          "❌ Сталася помилка під час завантаження. Спробуй ще раз пізніше.",
          reply_markup=get_user_keyboard(lang, user_id),
      )
    finally:
      if os.path.exists(mp3_file_name):
        try:
          os.remove(mp3_file_name)
        except:
          pass
      try:
        bot.delete_message(message.chat.id, processing_msg.message_id)
      except:
        pass
    return

  if text in [
      "⚠ Пожаловаться / Написать админу",
      "⚠️ Поскаржитися / Написати адміну",
  ]:
    if not config.get("btn_support_enabled", True) and not is_admin:
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    user_support_mode.add(user_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    exit_btn = (
        "❌ Завершити діалог" if lang == "ua" else "❌ Завершить диалог"
    )
    kb.row(KeyboardButton(exit_btn))
    bot.send_message(
        message.chat.id,
        "✍ Режим діалогу активовано. Пишіть повідомлення:",
        reply_markup=kb,
    )
    return

  if text in ["❌ Завершить диалог", "❌ Завершити діалог"]:
    if user_id in user_support_mode:
      user_support_mode.remove(user_id)
    bot.send_message(
        message.chat.id,
        "✅ Діалог завершено.",
        reply_markup=get_user_keyboard(lang, user_id),
    )
    return

  admin_chats = config.get("admin_chat_ids", [SUPER_ADMIN_ID])
  is_active_chat = user_id in user_support_mode or any(
      admin_id
      for admin_id, target in admin_chat_states.items()
      if target == user_id
  )

  if (
      is_active_chat
      and text not in ignored_texts
      and not (text and text.startswith("/"))
  ):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💬 Ответить", callback_data=f"chat_with_{user_id}")
    )
    for admin_chat_id in admin_chats:
      try:
        bot.send_message(
            admin_chat_id,
            f"💬 **Сообщение від користувача ID `{user_id}`:**",
            parse_mode="Markdown",
        )
        bot.copy_message(
            chat_id=admin_chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=markup,
        )
      except:
        pass
    bot.send_message(
        message.chat.id,
        "✅ Надіслано адміну."
        if lang == "ua"
        else "✅ Отправлено администратору.",
    )
    return

  if text in ["🌐 Сменить язык", "🌐 Змінити мову"]:
    if not config.get("btn_lang_enabled", True) and not is_admin:
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🇺🇦 Українська", callback_data="setlang_ua"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
    )
    bot.send_message(
        message.chat.id, TEXTS[lang]["lang_select"], reply_markup=markup
    )
    return
  elif text in ["🎬 Инструкция", "🎬 Інструкція"]:
    if not config.get("btn_instruction_enabled", True) and not is_admin:
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    bot.send_message(
        message.chat.id,
        TEXTS[lang]["active"],
        reply_markup=get_user_keyboard(lang, user_id),
    )
    return

  if message.content_type == "photo":
    chat_id = message.chat.id
    uname_str = f"@{user.username}" if user.username else f"ID:{user_id}"
    write_log(
        "ОТПРАВКА ФОТО",
        f"{uname_str} (ID: {user_id}, Имя: {user.first_name})",
        "Пользователь загрузил фотографию в буфер",
    )
    if not config.get("video_creation_enabled", True) and not is_admin:
      bot.reply_to(
          message,
          TEXTS[lang]["video_disabled_for_users"],
          reply_markup=get_user_keyboard(lang, user_id),
      )
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
        bot.reply_to(
            message,
            msg_text,
            reply_markup=get_user_keyboard(lang, user_id),
        )
      else:
        sub_photos = user_photos_buffer[chat_id][:3]
        user_photos_buffer[chat_id] = []
        bot.reply_to(
            message,
            TEXTS[lang]["rendering"],
            reply_markup=get_user_keyboard(lang, user_id),
        )

        clips = []
        img_paths = []
        output_video_path = os.path.join(BASE_DIR, f"result_{user_id}.mp4")
        video = None

        try:
          quote_text = get_unique_quote(user_id, lang)
          for idx, p_data in enumerate(sub_photos):
            p_path = os.path.join(BASE_DIR, f"temp_{user_id}_{idx}.png")
            processed_img = prepare_photo_with_letterbox(p_data, quote_text)
            processed_img.save(p_path)
            img_paths.append(p_path)

          frame_duration = 0.2
          target_total_duration = 5.0
          num_loops = (
              int(target_total_duration / (len(img_paths) * frame_duration)) + 1
          )
          repeated_img_paths = img_paths * num_loops
          clips = [
              ImageClip(p).set_duration(frame_duration).resize(width=1080)
              for p in repeated_img_paths
          ]

          video = concatenate_videoclips(clips, method="compose")
          video = video.subclip(0, target_total_duration)
          video.write_videofile(
              output_video_path,
              fps=24,
              codec="libx264",
              audio=False,
              logger=None,
              preset="medium",
              bitrate="4000k",
          )
          if video:
            video.close()

          write_log(
              "ГЕНЕРАЦИЯ ВИДЕО",
              f"{uname_str} (ID: {user_id})",
              "Успешно создано и отправлено видео из 3 фото",
          )
          with open(output_video_path, "rb") as vid_file:
            bot.send_video(
                chat_id,
                vid_file,
                reply_markup=get_user_keyboard(lang, user_id),
            )
        except Exception as render_err:
          print(f"Rendering error: {render_err}")
          write_log(
              "ОШИБКА РЕНДЕРИНГ",
              f"{uname_str} (ID: {user_id})",
              str(render_err),
          )
          bot.send_message(
              chat_id,
              TEXTS[lang]["error"],
              reply_markup=get_user_keyboard(lang, user_id),
          )
        finally:
          if video:
            try:
              video.close()
            except:
              pass
          for clip in clips if "clips" in locals() else []:
            try:
              clip.close()
            except:
              pass
          for p in img_paths:
            if os.path.exists(p):
              try:
                os.remove(p)
              except:
                pass
          if os.path.exists(output_video_path):
            try:
              os.remove(output_video_path)
            except:
              pass
          gc.collect()
    except Exception as e:
      print(f"Error handling photo: {e}")


if __name__ == "__main__":
  web_thread = threading.Thread(target=run_web)
  web_thread.daemon = True
  web_thread.start()

  print("Bot is starting polling polling...")
  bot.infinity_polling()
