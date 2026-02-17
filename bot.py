import logging
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Session, User, BotConfig
from config import BOT_TOKEN, ADMIN_ID, VPN_PASSWORD
import datetime
import subprocess

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния пользователей
user_states = {}

# Путь к конфигу sing-box
SING_BOX_CONFIG_PATH = "/etc/sing-box/config.json"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = Session()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    
    if user and user.is_authorized:
        await show_main_menu(update, context)
    else:
        keyboard = [[InlineKeyboardButton("Ввести пароль", callback_data='enter_password')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Добро пожаловать в VPN бот.\n\n"
            "Для доступа к функциям необходимо ввести пароль.",
            reply_markup=reply_markup
        )
    session.close()

def update_singbox_config(user_id, uuid, username):
    """Обновляет конфиг sing-box добавляя нового пользователя"""
    try:
        with open(SING_BOX_CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        # Добавляем нового пользователя в inbound
        new_user = {
            "name": f"user_{username}_{user_id}",
            "uuid": uuid,
            "flow": ""
        }
        
        # Проверяем, есть ли уже такой UUID
        existing_uuids = [u['uuid'] for u in config['inbounds'][0]['users']]
        if uuid not in existing_uuids:
            config['inbounds'][0]['users'].append(new_user)
            
            # Сохраняем обновленный конфиг
            with open(SING_BOX_CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Перезапускаем sing-box
            subprocess.run(['systemctl', 'restart', 'sing-box'])
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return False

def generate_config_link(uuid, server_ip="89.111.184.23", server_name="готовцев.рф"):
    """Генерирует ссылку для импорта конфига"""
    return (f"vless://{uuid}@{server_ip}:443?"
            f"encryption=none&security=tls&sni={server_name}&type=tcp#VPN_{uuid[:8]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'enter_password':
        user_states[user_id] = 'waiting_password'
        await query.edit_message_text("Введите пароль:")
    
    elif data == 'get_config':
        session = Session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if user and user.is_authorized:
            if user.uuid:
                config_link = generate_config_link(user.uuid)
                await query.edit_message_text(
                    f"Ваша конфигурация:\n\n<code>{config_link}</code>\n\n"
                    "Скопируйте эту ссылку и импортируйте в приложение Sing-Box или Streisand.\n\n"
                    "Как импортировать:\n"
                    "1. Откройте Sing-Box/Streisand\n"
                    "2. Нажмите + (Добавить)\n"
                    "3. Выберите 'Импорт из буфера'\n"
                    "4. Вставьте ссылку",
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text("Ошибка: UUID не найден. Обратитесь к администратору.")
        session.close()
    
    elif data == 'help':
        session = Session()
        config = session.query(BotConfig).first()
        help_text = config.help_text if config else "Инструкция по подключению..."
        await query.edit_message_text(help_text, parse_mode='HTML')
        session.close()
    
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
    
    elif data == 'admin_export_configs':
        await export_all_configs(query)
    
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
    
    if query:
        await query.edit_message_text("Главное меню:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("Пользователи", callback_data='admin_users')],
        [InlineKeyboardButton("Сменить пароль", callback_data='admin_change_password')],
        [InlineKeyboardButton("Рассылка", callback_data='admin_broadcast')],
        [InlineKeyboardButton("Редактировать помощь", callback_data='admin_edit_help')],
        [InlineKeyboardButton("Экспорт конфигов", callback_data='admin_export_configs')],
        [InlineKeyboardButton("Назад", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Админ панель:", reply_markup=reply_markup)

async def show_users_list(query):
    session = Session()
    users = session.query(User).all()
    
    if not users:
        text = "Нет зарегистрированных пользователей."
    else:
        text = "Список пользователей:\n\n"
        for user in users:
            status = "✅" if user.is_authorized else "❌"
            reg_date = user.registered_at.strftime("%d.%m.%Y %H:%M")
            last_active = user.last_active.strftime("%d.%m.%Y %H:%M") if user.last_active else "никогда"
            udid_info = f"UDID: {user.udid}" if user.udid else "UDID: не указан"
            uuid_info = f"UUID: {user.uuid}" if user.uuid else "UUID: не назначен"
            
            text += f"{status} {user.first_name} (@{user.username})\n"
            text += f"ID: {user.telegram_id}\n"
            text += f"{udid_info}\n"
            text += f"{uuid_info}\n"
            text += f"Зарегистрирован: {reg_date}\n"
            text += f"Активен: {last_active}\n\n"
    
    session.close()
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def export_all_configs(query):
    session = Session()
    users = session.query(User).filter(User.uuid.isnot(None)).all()
    
    if not users:
        await query.edit_message_text("Нет пользователей с конфигами.")
    else:
        text = "Все конфиги:\n\n"
        for user in users:
            if user.uuid:
                config_link = generate_config_link(user.uuid)
                text += f"@{user.username}: <code>{config_link}</code>\n\n"
        
        # Разбиваем на части если слишком длинное сообщение
        if len(text) > 4096:
            for x in range(0, len(text), 4096):
                await query.message.reply_text(text[x:x+4096], parse_mode='HTML')
            await query.edit_message_text("Конфиги отправлены частями.")
        else:
            await query.edit_message_text(text, parse_mode='HTML')
    
    session.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == 'waiting_password':
            session = Session()
            config = session.query(BotConfig).first()
            current_password = config.vpn_password if config else VPN_PASSWORD
            
            if text == current_password:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    user = User(
                        telegram_id=user_id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        is_authorized=True
                    )
                    session.add(user)
                    session.commit()
                    
                    # Запрашиваем UDID у нового пользователя
                    user_states[user_id] = 'waiting_udid'
                    await update.message.reply_text(
                        "✅ Пароль верный.\n\n"
                        "Теперь отправьте ваш UDID iPhone.\n"
                        "Как узнать UDID:\n"
                        "1. Подключите iPhone к компьютеру\n"
                        "2. Откройте Finder/iTunes\n"
                        "3. Нажмите на серийный номер - появится UDID\n"
                        "Или используйте приложение 'UDID' из App Store"
                    )
                else:
                    user.is_authorized = True
                    user.last_active = datetime.datetime.now()
                    session.commit()
                    await update.message.reply_text("✅ С возвращением!")
                    await show_main_menu(update, context)
                    del user_states[user_id]
            else:
                await update.message.reply_text("❌ Неверный пароль. Попробуйте снова.")
            
            session.close()
        
        elif state == 'waiting_udid':
            # Проверяем формат UDID (40 символов для нового формата)
            udid = text.strip()
            if len(udid) == 40 and all(c in '0123456789ABCDEFabcdef-' for c in udid):
                session = Session()
                user = session.query(User).filter_by(telegram_id=user_id).first()
                
                # Генерируем UUID для пользователя
                import uuid
                user_uuid = str(uuid.uuid4())
                
                user.udid = udid
                user.uuid = user_uuid
                session.commit()
                
                # Обновляем конфиг sing-box
                if update_singbox_config(user_id, user_uuid, update.effective_user.username or f"user_{user_id}"):
                    await update.message.reply_text(
                        f"✅ UDID сохранен.\n\n"
                        f"Ваш UUID: <code>{user_uuid}</code>\n\n"
                        f"Конфиг добавлен на сервер.",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(
                        f"✅ UDID сохранен, но ошибка при обновлении конфига сервера. Сообщите администратору."
                    )
                
                session.close()
                del user_states[user_id]
                await show_main_menu(update, context)
            else:
                await update.message.reply_text(
                    "❌ Неверный формат UDID.\n"
                    "UDID должен содержать 40 символов (цифры и буквы A-F).\n"
                    "Пример: 00008030-00145824117A802E\n\n"
                    "Попробуйте снова:"
                )
        
        elif state == 'admin_waiting_new_password' and user_id == ADMIN_ID:
            session = Session()
            config = session.query(BotConfig).first()
            if not config:
                config = BotConfig(vpn_password=text)
                session.add(config)
            else:
                config.vpn_password = text
            session.commit()
            session.close()
            
            del user_states[user_id]
            await update.message.reply_text(f"✅ Пароль доступа изменен на: {text}")
        
        elif state == 'admin_waiting_broadcast' and user_id == ADMIN_ID:
            session = Session()
            users = session.query(User).filter_by(is_authorized=True).all()
            
            success = 0
            for user in users:
                try:
                    await context.bot.send_message(chat_id=user.telegram_id, text=text)
                    success += 1
                except Exception as e:
                    logger.error(f"Failed to send to {user.telegram_id}: {e}")
            
            del user_states[user_id]
            await update.message.reply_text(f"✅ Рассылка отправлена {success} из {len(users)} пользователям.")
            session.close()
        
        elif state == 'admin_waiting_help' and user_id == ADMIN_ID:
            session = Session()
            config = session.query(BotConfig).first()
            if not config:
                config = BotConfig(help_text=text)
                session.add(config)
            else:
                config.help_text = text
            session.commit()
            session.close()
            
            del user_states[user_id]
            await update.message.reply_text("✅ Инструкция обновлена.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()
