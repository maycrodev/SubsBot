from telebot import TeleBot
import logging
import traceback

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

def register_all_handlers(bot: TeleBot):
    """Registra todos los handlers del bot"""
    try:
        logger.info("Iniciando registro de todos los handlers")
        
        # Importar los módulos de handlers
        from .start_handler import register_start_handlers
        from .admin_handler import register_admin_handlers
        from .payment_handler import register_payment_handlers
        from .callback_handler import register_callback_handlers
        
        # Registrar los handlers en orden de prioridad
        logger.info("Registrando handlers de administrador")
        register_admin_handlers(bot)
        
        logger.info("Registrando handlers de pagos")
        register_payment_handlers(bot)
        
        logger.info("Registrando handlers de callbacks")
        register_callback_handlers(bot)
        
        logger.info("Registrando handlers de inicio")
        register_start_handlers(bot)
        
        # Verificar cuántos handlers se registraron
        start_handlers = sum(len(group) for group in bot.message_handlers)
        callback_handlers = sum(len(group) for group in bot.callback_query_handlers)
        
        logger.info(f"Total de message handlers registrados: {start_handlers}")
        logger.info(f"Total de callback handlers registrados: {callback_handlers}")
        
        logger.info("Todos los handlers registrados correctamente")
    except Exception as e:
        logger.error(f"Error al registrar los handlers: {str(e)}")
        logger.error(traceback.format_exc())