from telebot import TeleBot
from telebot.types import Message
import logging
import traceback

from bot.keyboards.markup_creator import welcome_markup
from bot.utils.messages import welcome_message
from db.repository.user_repo import UserRepository
from db.database import SessionLocal

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

def start_command(bot: TeleBot, message: Message):
    """
    Maneja el comando /start del bot.
    Muestra el mensaje de bienvenida y los botones principales.
    
    Args:
        bot: Instancia del bot
        message: Mensaje del usuario
    """
    try:
        # Log para depuración
        logger.info(f"Comando /start recibido de usuario {message.from_user.id}")
        logger.info(f"Contenido completo del mensaje: {message}")
        
        # Obtener información del usuario
        user_id = message.from_user.id
        username = message.from_user.username
        full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        
        logger.info(f"Procesando comando /start para: {full_name} (@{username}) [ID: {user_id}]")
        
        # Registrar usuario en la base de datos si no existe
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                logger.info(f"Registrando nuevo usuario: {user_id}")
                UserRepository.create_user(db, user_id, full_name, username)
            else:
                logger.info(f"Usuario ya existente: {user_id}")
        except Exception as e:
            logger.error(f"Error al acceder a la base de datos: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            db.close()
        
        # Preparar mensaje de bienvenida
        welcome_text = welcome_message()
        logger.info(f"Mensaje de bienvenida: {welcome_text[:50]}...")
        
        # Crear markup
        markup = welcome_markup()
        logger.info("Markup de bienvenida creado")
        
        # Enviar mensaje de bienvenida con los botones principales
        logger.info(f"Enviando mensaje a chat_id: {message.chat.id}")
        
        try:
            sent_msg = bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            logger.info(f"Mensaje de bienvenida enviado correctamente. ID: {sent_msg.message_id}")
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Telegram: {str(e)}")
            logger.error(traceback.format_exc())
            # Intentar con una versión simplificada
            try:
                sent_msg = bot.send_message(
                    chat_id=message.chat.id,
                    text="¡Bienvenido al Bot de Suscripciones VIP!"
                )
                logger.info(f"Mensaje simplificado enviado. ID: {sent_msg.message_id}")
            except Exception as inner_e:
                logger.error(f"Error al enviar mensaje simplificado: {str(inner_e)}")
        
    except Exception as e:
        logger.error(f"Error general al procesar comando /start: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar enviar un mensaje simplificado en caso de error
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text="👋 ¡Bienvenido! Estamos experimentando problemas técnicos. Por favor, intenta nuevamente en unos momentos."
            )
        except Exception as reply_error:
            logger.error(f"No se pudo enviar mensaje de error: {str(reply_error)}")

def register_start_handlers(bot: TeleBot):
    """
    Registra todos los handlers relacionados con el inicio del bot.
    
    Args:
        bot: Instancia del bot
    """
    logger.info("Registrando handler para comando /start")
    
    # Registrar el handler del comando /start
    bot.register_message_handler(
        callback=lambda message: start_command(bot, message),
        commands=['start'],
        pass_bot=True
    )
    
    logger.info("Handler para comando /start registrado correctamente")