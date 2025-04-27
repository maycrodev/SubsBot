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
        
        # El orden importa - handlers más específicos primero
        logger.info("Registrando handlers de callback")
        register_callback_handlers(bot)  # Mover al inicio para priorizar
        
        logger.info("Registrando handlers de administrador")
        register_admin_handlers(bot)
        
        logger.info("Registrando handlers de pagos")
        register_payment_handlers(bot)
        
        logger.info("Registrando handlers de inicio")
        register_start_handlers(bot)
        
        # Verificar que los handlers están registrados
        logger.info("Verificando handlers registrados")
        callback_handlers_count = 0
        
        # Verificar handlers de callback
        for handler_group in bot.callback_query_handlers:
            for handler in handler_group:
                callback_handlers_count += 1
                handler_name = handler.__name__ if hasattr(handler, '__name__') else 'anónimo'
                logger.info(f"Handler de callback registrado: {handler_name}")
        
        logger.info(f"Total de handlers de callback registrados: {callback_handlers_count}")
        
        # Verificar explícitamente el comando /start
        logger.info("Registrando handler de /start manualmente")
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