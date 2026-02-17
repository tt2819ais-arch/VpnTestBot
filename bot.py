import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import datetime
import uuid
import json
import re

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
    
    # Таблица пользователей
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
    
    # Таблица исключений пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS user_exceptions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  site TEXT,
                  added_at TIMESTAMP,
                  FOREIGN KEY(user_id) REFERENCES users(telegram_id))''')
    
    # Таблица конфигов бота
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

def generate_config_link(user_uuid, exceptions=None):
    """Генерирует ссылку для импорта в приложения"""
    base_link = f"vless://{user_uuid}@{SERVER_IP}:443?encryption=none&security=tls&sni={SERVER_NAME}&type=tcp#VPN_{user_uuid[:8]}"
    return base_link

def parse_sites_list(text):
    """Парсит список сайтов из сообщения"""
    # Разделяем по запятой, пробелу или переносу строки
    sites = re.split(r'[,\s\n]+', text)
    # Очищаем и фильтруем
    sites = [site.strip().lower() for site in sites if site.strip()]
    # Убираем дубликаты
    return list(dict.fromkeys(sites))

async def set_commands(app):
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Инструкция"),
        BotCommand("config", "Получить конфиг"),
        BotCommand("exceptions", "Управление исключениями")
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT is_authorized FROM users WHERE telegram_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user and user[0] == 1:
        await show_main_menu(update, context)
    else:
        keyboard = [[InlineKeyboardButton("🔑 Ввести пароль", callback_data='enter_password')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "   Добро пожаловать в VPN бот\n"
            "╚══════════════════════════╝\n\n"
            "Для доступа к функциям необходимо ввести пароль.",
            reply_markup=reply_markup
        )

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT is_authorized, uuid FROM users WHERE telegram_id=?", (user_id,))
    result = c.fetchone()
    
    if result and result[0] == 1 and result[1]:
        config_link = generate_config_link(result[1])
        
        # Получаем список исключений пользователя
        c.execute("SELECT site FROM user_exceptions WHERE user_id=?", (user_id,))
        exceptions = [row[0] for row in c.fetchall()]
        
        text = "╔══════════════════════════╗\n"
        text += "    ВАША КОНФИГУРАЦИЯ\n"
        text += "╚══════════════════════════╝\n\n"
        text += f"<code>{config_link}</code>\n\n"
        text += "Нажмите на ссылку выше для импорта в приложение\n\n"
        
        if exceptions:
            text += "Ваши исключения:\n"
            for site in exceptions:
                text += f"• {site}\n"
        
        text += "\nПоддерживаемые приложения:\n"
        text += "• iOS: FoXray, Shadowrocket, Sing-Box\n"
        text += "• Android: v2rayNG, NekoBox\n"
        text += "• Windows: v2rayN, Qv2ray\n"
        text += "• MacOS: V2RayU, FoXray"
        
        await update.message.reply_text(text, parse_mode='HTML')
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

async def exceptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT is_authorized FROM users WHERE telegram_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user and user[0] == 1:
        await show_exceptions_menu(update, context)
    else:
        await update.message.reply_text("Сначала авторизуйтесь через /start")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    keyboard = [
        [InlineKeyboardButton("📱 Получить конфиг", callback_data='get_config')],
        [InlineKeyboardButton("🌐 Управление исключениями", callback_data='exceptions_menu')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "╔══════════════════════════╗\n"
    text += "        ГЛАВНОЕ МЕНЮ\n"
    text += "╚══════════════════════════╝\n\n"
    text += "Выберите действие:"
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_exceptions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить исключения", callback_data='add_exception')],
        [InlineKeyboardButton("📋 Мои исключения", callback_data='list_exceptions')],
        [InlineKeyboardButton("🗑 Удалить исключение", callback_data='remove_exception_menu')],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "╔══════════════════════════╗\n"
    text += "   УПРАВЛЕНИЕ ИСКЛЮЧЕНИЯМИ\n"
    text += "╚══════════════════════════╝\n\n"
    text += "Исключения - сайты которые будут открываться\n"
    text += "напрямую, минуя VPN (например: school.ru, s7.ru)\n\n"
    text += "Выберите действие:"
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("👥 Список пользователей", callback_data='admin_users')],
        [InlineKeyboardButton("🔑 Сменить пароль", callback_data='admin_change_password')],
        [InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')],
        [InlineKeyboardButton("📝 Редактировать помощь", callback_data='admin_edit_help')],
        [InlineKeyboardButton("🌐 Все исключения", callback_data='admin_all_exceptions')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "╔══════════════════════════╗\n"
    text += "        АДМИН ПАНЕЛЬ\n"
    text += "╚══════════════════════════╝\n\n"
    text += f"ID администратора: {ADMIN_ID}\n\n"
    text += "Выберите действие:"
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def show_users_list(query):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT telegram_id, username, first_name, udid, uuid, is_authorized, registered_at FROM users")
    users = c.fetchall()
    
    if not users:
        text = "Нет зарегистрированных пользователей."
    else:
        text = "╔══════════════════════════╗\n"
        text += "    СПИСОК ПОЛЬЗОВАТЕЛЕЙ\n"
        text += "╚══════════════════════════╝\n\n"
        
        for user in users:
            status = "✅" if user[5] == 1 else "❌"
            reg_date = user[6][:16] if user[6] else "неизвестно"
            
            text += f"{status} {user[2]} (@{user[1]})\n"
            text += f"ID: {user[0]}\n"
            text += f"UUID: {user[4]}\n\n"
    
    conn.close()
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def show_all_exceptions(query):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Получаем всех пользователей и их исключения
    c.execute("""
        SELECT u.username, u.first_name, u.telegram_id, e.site, e.added_at 
        FROM users u 
        LEFT JOIN user_exceptions e ON u.telegram_id = e.user_id
        WHERE u.is_authorized = 1
        ORDER BY u.telegram_id, e.added_at DESC
    """)
    data = c.fetchall()
    
    if not data:
        text = "Нет пользователей или исключений."
    else:
        text = "╔══════════════════════════╗\n"
        text += "      ВСЕ ИСКЛЮЧЕНИЯ\n"
        text += "╚══════════════════════════╝\n\n"
        
        current_user = None
        for row in data:
            if row[2] != current_user:
                current_user = row[2]
                text += f"\n👤 {row[1]} (@{row[0]})\n"
            if row[3]:
                text += f"  • {row[3]} (добавлен: {row[4][:16]})\n"
    
    conn.close()
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'enter_password':
        user_states[user_id] = 'waiting_password'
        await query.edit_message_text("Введите пароль для доступа к боту:")
    
    elif data == 'get_config':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT uuid FROM users WHERE telegram_id=? AND is_authorized=1", (user_id,))
        result = c.fetchone()
        
        if result and result[0]:
            config_link = generate_config_link(result[0])
            await query.edit_message_text(
                f"<code>{config_link}</code>\n\n"
                "Нажмите на ссылку для импорта в приложение.",
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
    
    elif data == 'exceptions_menu':
        await show_exceptions_menu(update, context, query=query)
    
    elif data == 'add_exception':
        user_states[user_id] = 'waiting_exception'
        await query.edit_message_text(
            "Отправьте список сайтов для исключения.\n\n"
            "Можно отправлять:\n"
            "• Один сайт: school.ru\n"
            "• Несколько через запятую: school.ru, s7.ru, gosuslugi.ru\n"
            "• Список с новой строки:\n"
            "school.ru\ns7.ru\ngosuslugi.ru\n\n"
            "После добавления вы получите новую ссылку для подключения."
        )
    
    elif data == 'list_exceptions':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT site FROM user_exceptions WHERE user_id=?", (user_id,))
        sites = c.fetchall()
        conn.close()
        
        if sites:
            text = "╔══════════════════════════╗\n"
            text += "      ВАШИ ИСКЛЮЧЕНИЯ\n"
            text += "╚══════════════════════════╝\n\n"
            for site in sites:
                text += f"• {site[0]}\n"
        else:
            text = "У вас нет исключений"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='exceptions_menu')]]
        await query.edit_message_text(text, reply_markup=keyboard)
    
    elif data == 'remove_exception_menu':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT site FROM user_exceptions WHERE user_id=?", (user_id,))
        sites = c.fetchall()
        conn.close()
        
        if sites:
            keyboard = []
            for site in sites:
                keyboard.append([InlineKeyboardButton(f"❌ {site[0]}", callback_data=f"remove_{site[0]}")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='exceptions_menu')])
            
            await query.edit_message_text("Выберите исключение для удаления:", reply_markup=keyboard)
        else:
            await query.edit_message_text("У вас нет исключений")
    
    elif data.startswith('remove_'):
        site = data.replace('remove_', '')
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("DELETE FROM user_exceptions WHERE user_id=? AND site=?", (user_id, site))
        conn.commit()
        conn.close()
        
        # Отправляем уведомление о необходимости обновить конфиг
        await query.edit_message_text(
            f"✅ Исключение {site} удалено.\n\n"
            "⚠️ ВАЖНО: Получите новую ссылку для подключения!"
        )
        
        # Показываем кнопку для получения нового конфига
        keyboard = [[InlineKeyboardButton("📱 Получить новый конфиг", callback_data='get_config')]]
        await query.message.reply_text("Нажмите кнопку ниже чтобы получить обновленную ссылку:", reply_markup=keyboard)
    
    elif data == 'admin_panel' and user_id == ADMIN_ID:
        await show_admin_panel(query)
    
    elif data == 'admin_users' and user_id == ADMIN_ID:
        await show_users_list(query)
    
    elif data == 'admin_all_exceptions' and user_id == ADMIN_ID:
        await show_all_exceptions(query)
    
    elif data == 'admin_change_password' and user_id == ADMIN_ID:
        user_states[user_id] = 'admin_waiting_new_password'
        await query.edit_message_text("Введите новый пароль для доступа к боту:")
    
    elif data == 'admin_broadcast' and user_id == ADMIN_ID:
        user_states[user_id] = 'admin_waiting_broadcast'
        await query.edit_message_text("Введите текст для рассылки:")
    
    elif data == 'admin_edit_help' and user_id == ADMIN_ID:
        user_states[user_id] = 'admin_waiting_help'
        await query.edit_message_text("Введите новый текст инструкции (можно с HTML-тегами):")
    
    elif data == 'back_to_menu':
        await show_main_menu(update, context, query=query)

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
            # Генерируем UUID для пользователя
            user_uuid = str(uuid.uuid4())
            
            c.execute("""UPDATE users 
                        SET udid=?, uuid=?, last_active=?
                        WHERE telegram_id=?""",
                     (text, user_uuid, datetime.datetime.now(), user_id))
            conn.commit()
            
            config_link = generate_config_link(user_uuid)
            
            await update.message.reply_text(
                f"✅ UDID сохранен.\n\n"
                f"<code>{config_link}</code>\n\n"
                f"Нажмите на ссылку для импорта в приложение.",
                parse_mode='HTML'
            )
            
            del user_states[user_id]
            await show_main_menu(update, context)
        
        elif state == 'waiting_exception':
            # Парсим список сайтов
            sites = parse_sites_list(text)
            
            if not sites:
                await update.message.reply_text("❌ Не удалось распознать сайты. Попробуйте снова.")
                return
            
            # Сохраняем исключения
            added = []
            existed = []
            
            for site in sites:
                try:
                    c.execute("""INSERT INTO user_exceptions 
                                (user_id, site, added_at) 
                                VALUES (?, ?, datetime('now'))""",
                             (user_id, site))
                    conn.commit()
                    added.append(site)
                except sqlite3.IntegrityError:
                    existed.append(site)
            
            conn.close()
            
            # Формируем ответ
            response = ""
            if added:
                response += f"✅ Добавлены: {', '.join(added)}\n"
            if existed:
                response += f"⚠️ Уже были: {', '.join(existed)}\n"
            
            response += "\n⚠️ ВАЖНО: Получите новую ссылку для подключения!"
            
            await update.message.reply_text(response)
            
            # Получаем UUID пользователя для новой ссылки
            c = conn.cursor()
            c.execute("SELECT uuid FROM users WHERE telegram_id=?", (user_id,))
            user_uuid = c.fetchone()[0]
            conn.close()
            
            config_link = generate_config_link(user_uuid)
            
            keyboard = [[InlineKeyboardButton("📱 Получить новый конфиг", callback_data='get_config')]]
            await update.message.reply_text(
                f"Ваша новая ссылка:\n\n<code>{config_link}</code>",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
            del user_states[user_id]
        
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
    application.add_handler(CommandHandler("exceptions", exceptions_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Устанавливаем команды
    application.post_init = set_commands
    
    application.run_polling()

if __name__ == '__main__':
    main()
