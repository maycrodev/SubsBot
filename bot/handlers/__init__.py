from telebot import TeleBot
import logging
import traceback

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

def register_all_handlers(bot: TeleBot):
    """Registra todos los handlers del bot"""
    try:
        logger.info("Iniciando registro de todos los handlers")
        
        # Importar aquí para evitar importaciones circulares
        from .start_handler import register_start_handlers
        from .admin_handler import register_admin_handlers
        from .payment_handler import register_payment_handlers
        from .callback_handler import register_callback_handlers
        
        # Registrar handlers en orden específico - el orden importa
        # Handler de callbacks primero - es el más general
        logger.info("Registrando handlers de callback")
        register_callback_handlers(bot)
        
        # Luego handlers específicos
        logger.info("Registrando handlers de pagos")
        register_payment_handlers(bot)
        
        logger.info("Registrando handlers de administrador")
        register_admin_handlers(bot)
        
        logger.info("Registrando handlers de inicio")
        register_start_handlers(bot)
        
        # Diagnóstico - verificar handlers registrados
        logger.info("Verificando handlers registrados:")
        
        # Contar handlers de callback
        callback_count = sum(len(handlers) for handlers in bot.callback_query_handlers)
        logger.info(f"  - Handlers de callback: {callback_count}")
        
        # Contar handlers de mensaje
        message_count = sum(len(handlers) for handlers in bot.message_handlers)
        logger.info(f"  - Handlers de mensaje: {message_count}")
        
        # Verificar explícitamente el comando /start
        logger.info("Registrando handler de /start manualmente para asegurar")
        from .start_handler import start_command
        bot.register_message_handler(
            lambda message: start_command(bot, message),
            commands=['start'],
            pass_bot=True
        )
        
        logger.info("Todos los handlers registrados correctamente")
    except Exception as e:
        logger.error(f"Error al registrar los handlers: {str(e)}")
        logger.error(traceback.format_exc())