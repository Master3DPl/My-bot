import concurrent.futures
import gc
import json
import logging
import os
import random
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
import yt_dlp

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)


@app.route("/")
def home():
  return "Bot is alive and running!"


def run_web():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


TOKEN = "8750078142:AAFc7_kQNV4Vv532T2E0ocmKmj_qSBFbncQ"
bot = telebot.TeleBot(TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOGS_LIST_FILE = os.path.join(BASE_DIR, "bot_logs_list.json")
USER_HISTORY_FILE = os.path.join(BASE_DIR, "user_history.json")

SUPER_ADMIN = "drborys".lower()
SUPER_ADMIN_ID = 1049082814

admin_last_logs_msg = {}
admin_input_waiting = set()
admin_history_waiting = set()
user_music_waiting = set()  # Режим очікування назви треку від користувача


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
      "user_approval_required": True,
      "btn_lang_enabled": True,
      "btn_support_enabled": True,
      "btn_music_enabled": True,
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
if "user_approval_required" not in config:
  config["user_approval_required"] = True
if "btn_lang_enabled" not in config:
  config["btn_lang_enabled"] = True
if "btn_support_enabled" not in config:
  config["btn_support_enabled"] = True
if "btn_music_enabled" not in config:
  config["btn_music_enabled"] = True
if "admin_chat_ids" not in config:
  config["admin_chat_ids"] = [SUPER_ADMIN_ID]
if "extra_admins" not in config:
  config["extra_admins"] = []
save_config(config)

admin_chat_states = {}
admin_as_user_mode = set()
user_support_mode = set()

TEXTS = {
    "ru": {
        "access_denied": "⛔ У вас нет доступа к этому боту.",
        "bot_globally_disabled": (
            "🛠 Бот временно отключен администратором и находится на"
            " техническом обслуживании."
        ),
        "feature_disabled": "⛔ Эта функция временно отключена администратором.",
        "active": "🤖 Бот успешно запущен и готов к работе!",
        "lang_select": "🌐 Выберите язык / Оберіть мову:",
        "lang_changed": "✅ Язык успешно изменен на русский!",
    },
    "ua": {
        "access_denied": "⛔ У вас немає доступу до цього бота.",
        "bot_globally_disabled": (
            "🛠 Бот тимчасово вимкнений адміністратором на технічне обслуговування."
        ),
        "feature_disabled": "⛔ Цю функцію тимчасово вимкнено адміністратором.",
        "active": "🤖 Бот успішно запущено та готовий до роботи!",
        "lang_select": "🌐 Оберіть мову / Выберите язык:",
        "lang_changed": "✅ Мову успішно змінено на українську!",
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
  kb.row(KeyboardButton("⚙ Управление кнопками и функциями"))
  kb.row(KeyboardButton("👥 Управление пользователями"))
  kb.row(KeyboardButton("📜 Логи сообщений"))
  if user_id and user_id in admin_as_user_mode:
    kb.row(KeyboardButton("👑 Повернутися в адмін-панель"))
  else:
    kb.row(KeyboardButton("👤 Вийти в режим юзера (Тест)"))
  return kb


def get_admin_panel_inline():
  kb = InlineKeyboardMarkup(row_width=1)
  is_approval_on = config.get("user_approval_required", True)
  is_lang_on = config.get("btn_lang_enabled", True)
  is_support_on = config.get("btn_support_enabled", True)
  is_music_on = config.get("btn_music_enabled", True)

  approval_text = (
      "🟢 Запит доступу юзерів: УВІМКНЕН"
      if is_approval_on
      else "🔴 Запит доступу юзерів: ВИМКНЕН"
  )
  lang_text = (
      "🟢 Кнопка 'Зміна мови': ВКЛ" if is_lang_on else "🔴 Кнопка 'Зміна мови': ВЫКЛ"
  )
  support_text = (
      "🟢 Кнопка 'Скарга/Адмін': ВКЛ"
      if is_support_on
      else "🔴 Кнопка 'Скарга/Адмін': ВЫКЛ"
  )
  music_text = (
      "🟢 Кнопка 'Музика': ВКЛ" if is_music_on else "🔴 Кнопка 'Музика': ВЫКЛ"
  )

  kb.add(
      InlineKeyboardButton(
          approval_text, callback_data="toggle_approval_requirement"
      )
  )
  kb.add(InlineKeyboardButton(lang_text, callback_data="toggle_btn_lang"))
  kb.add(InlineKeyboardButton(support_text, callback_data="toggle_btn_support"))
  kb.add(InlineKeyboardButton(music_text, callback_data="toggle_btn_music"))
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
  if config.get("btn_music_enabled", True):
    row1.append(
        KeyboardButton(
            "🎵 Найти музыку" if lang == "ru" else "🎵 Знайти музику"
        )
    )
  if row1:
    kb.row(*row1)

  row2 = []
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


@bot.message_handler(commands=["restart", "update"])
def restart_bot(message):
  if not is_super_admin(message):
    return
  bot.send_message(
      message.chat.id, "🔄 Бот перезавантажується для оновлення..."
  )
  os._exit(42)


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
  if user_id in user_music_waiting:
    user_music_waiting.remove(user_id)

  bot.send_message(
      user_id,
      TEXTS[lang]["active"],
      reply_markup=get_user_keyboard(lang, user_id),
  )


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
  user_id = call.from_user.id
  lang = get_user_lang(user_id)
  is_admin = is_super_admin(call) and user_id not in admin_as_user_mode

  if call.data != "close_logs":
    clear_previous_logs_message(call.message.chat.id, user_id)

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
        "✍ **Введите юзернейм (ник) нового администратора** (без @):",
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
    content_types=["text"],
)
def handle_admin_messages(message):
  user_id = message.from_user.id
  text = message.text

  clear_previous_logs_message(message.chat.id, user_id)

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

  if text in [
      "⚠ Пожаловаться / Написать админу",
      "⚠ Поскаржитися / Написати адміну",
      "❌ Завершить диалог",
      "❌ Завершити діалог",
      "🎵 Найти музыку",
      "🎵 Знайти музику",
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
    content_types=["text"],
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
      "⚠ Пожаловаться / Написать админу",
      "⚠ Поскаржитися / Написати адміну",
      "🎵 Найти музыку",
      "🎵 Знайти музику",
      "❌ Завершить диалог",
      "❌ Завершити діалог",
  ]

  if text in ["🎵 Найти музыку", "🎵 Знайти музику"]:
    if not config.get("btn_music_enabled", True) and not is_admin:
      bot.send_message(message.chat.id, TEXTS[lang]["feature_disabled"])
      return
    user_music_waiting.add(user_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    exit_btn = (
        "❌ Завершити діалог" if lang == "ua" else "❌ Завершить диалог"
    )
    kb.row(KeyboardButton(exit_btn))
    bot.send_message(
        message.chat.id,
        (
            "🎵 Введіть назву треку або виконавця, і я знайду та надішлю"
            " музику:"
            if lang == "ua"
            else "🎵 Введите название трека или исполнителя, и я найду и отправлю"
            " музыку:"
        ),
        reply_markup=kb,
    )
    return

  if text in [
      "⚠ Пожаловаться / Написать админу",
      "⚠ Поскаржитися / Написати адміну",
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
    if user_id in user_music_waiting:
      user_music_waiting.remove(user_id)
    bot.send_message(
        message.chat.id,
        "✅ Діалог завершено.",
        reply_markup=get_user_keyboard(lang, user_id),
    )
    return

  # Обробка пошуку та надсилання музики з видаленням файлу
  if user_id in user_music_waiting and text not in ignored_texts:
    search_query = text.strip()
    wait_msg = bot.send_message(
        message.chat.id,
        "🔍 Шукаю музику..." if lang == "ua" else "🔍 Ищу музыку...",
    )

    audio_file_path = None
    try:
      ydl_opts = {
          "format": "bestaudio/best",
          "default_search": "ytsearch1",
          "postprocessors": [{
              "key": "FFmpegExtractAudio",
              "preferredcodec": "mp3",
              "preferredquality": "192",
          }],
          "outtmpl": f"temp_music_{user_id}_%(id)s.%(ext)s",
          "quiet": True,
      }

      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_query, download=True)
        if "entries" in info:
          info = info["entries"][0]
        filename = ydl.prepare_filename(info)
        audio_file_path = os.path.splitext(filename)[0] + ".mp3"

      if audio_file_path and os.path.exists(audio_file_path):
        with open(audio_file_path, "rb") as audio:
          bot.send_audio(
              message.chat.id,
              audio,
              caption=f"🎵 {info.get('title', search_query)}",
          )
        bot.delete_message(message.chat.id, wait_msg.message_id)
      else:
        bot.edit_message_text(
            "❌ Не вдалося знайти трек."
            if lang == "ua"
            else "❌ Не удалось найти трек.",
            message.chat.id,
            wait_msg.message_id,
        )
    except Exception as e:
      print(f"Music download error: {e}")
      try:
        bot.edit_message_text(
            "❌ Сталася помилка при завантаженні музики."
            if lang == "ua"
            else "❌ Произошла ошибка при загрузке музыки.",
            message.chat.id,
            wait_msg.message_id,
        )
      except:
        pass
    finally:
      # ВИДАЛЕННЯ ФАЙЛУ З ПАМ'ЯТІ СЕРВЕРА (щоб не заповнювати диск)
      if audio_file_path and os.path.exists(audio_file_path):
        try:
          os.remove(audio_file_path)
        except Exception as e:
          print(f"File remove error: {e}")
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

  bot.send_message(
      message.chat.id,
      "ℹ️ Скористайтеся меню нижче.",
      reply_markup=get_user_keyboard(lang, user_id),
  )


if __name__ == "__main__":
  web_thread = threading.Thread(target=run_web)
  web_thread.daemon = True
  web_thread.start()

  print("Бот запущено та готовий до роботи...")
  bot.infinity_polling()
