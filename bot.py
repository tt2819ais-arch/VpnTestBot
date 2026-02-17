import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import datetime
import uuid

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8564174406:AAH4ZyWDPWDTSXxJ4BpJfGzQLn8VrhlWG8M"
ADMIN_ID = 5426581017
VPN_PASSWORD = "a7F9k2Pq4LmX"
SERVER_IP = "89.111.184.23"
SERVER_NAME = "готовцев.рф"

user_states = {}

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER UNIQUE,
                  username TEXT,
                  first_name TEXT,
                  udid TEXT,
                  uuid TEXT,
                  is_authorized INTEGER DEFAULT 0,
                  registered_at TIMESTAMP,
                  last_active TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_config
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  vpn_password TEXT,
                  help_text TEXT)''')
    
    # Проверяем есть ли запись с паролем
    c.execute("SELECT * FROM bot_config WHERE id=1")
    if not c.fetchone():
        c.execute("INSERT INTO bot_config (id, vpn_password, help_text) VALUES (1, ?, ?)",
                  (VPN_PASSWORD, "Инструкция по подключению..."))
    
    conn.commit()
    conn.close()

def generate_config_link(uuid):
    return (f"vless://{uuid}@{SERVER_IP}:443?"
            f"encryption=none&security=tls&sni={SERVER_NAME}&type=tcp#VPN_{uuid[:8]}")

async def set_commands(app):
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Инструкция"),
        BotCommand("config", "Получить конфиг")
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT is_authorized FROM users WHERE telegram_id=?", (user_id,))
    user = c.fetchone()
    
    if user and user[0] == 1:
        await show_main_menu(update, context)
    else:
        keyboard = [[InlineKeyboardButton("Ввести пароль", callback_data='enter_password')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Добро пожаловать в VPN бот.\n\n"
            "Для доступа к функциям необходимо ввести пароль.",
            reply_markup=reply_markup
        )
    conn.close()

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT is_authorized, uuid FROM users WHERE telegram_id=?", (user_id,))
    result = c.fetchone()
    
    if result and result[0] == 1 and result[1]:
        config_link = generate_config_link(result[1])
        await update.message.reply_text(
            f"Ваша конфигурация:\n\n<code>{config_link}</code>\n\n"
            "Скопируйте ссылку и импортируйте в приложение.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text("Сначала авторизуйтесь через /start")
    conn.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT help_text FROM bot_config WHERE id=1")
    help_text = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(help_text, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'enter_password':
        user_states[user_id] = 'waiting_password'
        await query.edit_message_text("Введите пароль:")
    
    elif data == 'get_config':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT uuid FROM users WHERE telegram_id=? AND is_authorized=1", (user_id,))
        result = c.fetchone()
        
        if result and result[0]:
            config_link = generate_config_link(result[0])
            await query.edit_message_text(
                f"Ваша конфигурация:\n\n<code>{config_link}</code>\n\n"
                "Скопируйте ссылку и импортируйте в приложение.",
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text("Конфиг не найден. Обратитесь к администратору.")
        conn.close()
    
    elif data == 'help':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT help_text FROM bot_config WHERE id=1")
        help_text = c.fetchone()[0]
        conn.close()
        await query.edit_message_text(help_text, parse_mode='HTML')
    
    elif data == 'admin_panel' and user_id == ADMIN_ID:
        await show_admin_panel(query)
    
    elif data == 'admin_users':
        await show_users_list(query)
    
    elif data == 'admin_change_password':
        user_states[user_id] = 'admin_waiting_new_password'
        await query.edit_message_text("Введите новый пароль для доступа к боту:")
    
    elif data == 'admin_broadcast':
        user_states[user_id] = 'admin_waiting_broadcast'
        await query.edit_message_text("Введите текст для рассылки:")
    
    elif data == 'admin_edit_help':
        user_states[user_id] = 'admin_waiting_help'
        await query.edit_message_text("Введите новый текст инструкции (можно с HTML-тегами):")
    
    elif data == 'back_to_menu':
        await show_main_menu(update, context, query=query)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    keyboard = [
        [InlineKeyboardButton("Получить конфиг", callback_data='get_config')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("Админ панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Главное меню:"
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("Пользователи", callback_data='admin_users')],
        [InlineKeyboardButton("Сменить пароль", callback_data='admin_change_password')],
        [InlineKeyboardButton("Рассылка", callback_data='admin_broadcast')],
        [InlineKeyboardButton("Редактировать помощь", callback_data='admin_edit_help')],
        [InlineKeyboardButton("Назад", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Админ панель:", reply_markup=reply_markup)

async def show_users_list(query):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT telegram_id, username, first_name, udid, uuid, is_authorized, registered_at FROM users")
    users = c.fetchall()
    
    if not users:
        text = "Нет зарегистрированных пользователей."
    else:
        text = "Список пользователей:\n\n"
        for user in users:
            status = "✅" if user[5] == 1 else "❌"
            reg_date = user[6][:16] if user[6] else "неизвестно"
            udid_info = f"UDID: {user[3]}" if user[3] else "UDID: не указан"
            uuid_info = f"UUID: {user[4]}" if user[4] else "UUID: не назначен"
            
            text += f"{status} {user[2]} (@{user[1]})\n"
            text += f"ID: {user[0]}\n"
            text += f"{udid_info}\n"
            text += f"{uuid_info}\n"
            text += f"Зарегистрирован: {reg_date}\n\n"
    
    conn.close()
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in user_states:
        state = user_states[user_id]
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        if state == 'waiting_password':
            c.execute("SELECT vpn_password FROM bot_config WHERE id=1")
            current_password = c.fetchone()[0]
            
            if text == current_password:
                c.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
                user = c.fetchone()
                
                if not user:
                    c.execute("""INSERT INTO users 
                                (telegram_id, username, first_name, registered_at, is_authorized)
                                VALUES (?, ?, ?, ?, 1)""",
                             (user_id, update.effective_user.username, 
                              update.effective_user.first_name, datetime.datetime.now()))
                    conn.commit()
                    
                    user_states[user_id] = 'waiting_udid'
                    await update.message.reply_text(
                        "✅ Пароль верный.\n\n"
                        "Теперь отправьте ваш UDID iPhone.\n\n"
                        "Получить UDID можно в боте: @UDiD_dlbot\n\n"
                        "(Просто отправьте мне UDID который получите)"
                    )
                else:
                    c.execute("UPDATE users SET is_authorized=1, last_active=? WHERE telegram_id=?",
                             (datetime.datetime.now(), user_id))
                    conn.commit()
                    await update.message.reply_text("✅ С возвращением!")
                    del user_states[user_id]
                    await show_main_menu(update, context)
            else:
                await update.message.reply_text("❌ Неверный пароль. Попробуйте снова.")
        
        elif state == 'waiting_udid':
            # Принимаем любой текст как UDID
            user_uuid = str(uuid.uuid4())
            
            c.execute("""UPDATE users 
                        SET udid=?, uuid=?, last_active=?
                        WHERE telegram_id=?""",
                     (text, user_uuid, datetime.datetime.now(), user_id))
            conn.commit()
            
            config_link = generate_config_link(user_uuid)
            
            await update.message.reply_text(
                f"✅ UDID сохранен.\n\n"
                f"Ваш UUID: <code>{user_uuid}</code>\n\n"
                f"Ссылка для подключения:\n<code>{config_link}</code>\n\n"
                f"Скопируйте ссылку и импортируйте в приложение.",
                parse_mode='HTML'
            )
            
            del user_states[user_id]
            await show_main_menu(update, context)
        
        elif state == 'admin_waiting_new_password' and user_id == ADMIN_ID:
            c.execute("UPDATE bot_config SET vpn_password=? WHERE id=1", (text,))
            conn.commit()
            await update.message.reply_text(f"✅ Пароль доступа изменен на: {text}")
            del user_states[user_id]
        
        elif state == 'admin_waiting_broadcast' and user_id == ADMIN_ID:
            c.execute("SELECT telegram_id FROM users WHERE is_authorized=1")
            users = c.fetchall()
            
            success = 0
            for user in users:
                try:
                    await context.bot.send_message(chat_id=user[0], text=text)
                    success += 1
                except:
                    pass
            
            await update.message.reply_text(f"✅ Рассылка отправлена {success} из {len(users)} пользователям.")
            del user_states[user_id]
        
        elif state == 'admin_waiting_help' and user_id == ADMIN_ID:
            c.execute("UPDATE bot_config SET help_text=? WHERE id=1", (text,))
            conn.commit()
            await update.message.reply_text("✅ Инструкция обновлена.")
            del user_states[user_id]
        
        conn.close()
    else:
        # Если просто сообщение без состояния
        await update.message.reply_text("Используйте /start для начала работы")

def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем хэндлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Устанавливаем команды
    application.post_init = set_commands
    
    application.run_polling()

if __name__ == '__main__':
    main()
