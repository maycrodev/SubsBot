from telebot import TeleBot
from telebot.types import Message

from bot.keyboards.markup_creator import welcome_markup
from bot.utils.messages import welcome_message
from db.repository.user_repo import UserRepository
from db.database import SessionLocal

def start_command(bot: TeleBot, message: Message):
    """
    Maneja el comando /start del bot.
    Muestra el mensaje de bienvenida y los botones principales.
    
    Args:
        bot: Instancia del bot
        message: Mensaje del usuario
    """
    # Obtener información del usuario
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    
    # Registrar usuario en la base de datos si no existe
    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, user_id)
        if not user:
            UserRepository.create_user(db, user_id, full_name, username)
    finally:
        db.close()
    
    # Enviar mensaje de bienvenida con los botones principales
    bot.send_message(
        chat_id=message.chat.id,
        text=welcome_message(),
        reply_markup=welcome_markup(),
        parse_mode='HTML'
    )

def register_start_handlers(bot: TeleBot):
    """
    Registra todos los handlers relacionados con el inicio del bot.
    
    Args:
        bot: Instancia del bot
    """
    bot.register_message_handler(
        lambda message: start_command(bot, message),
        commands=['start'],
        pass_bot=True
    )