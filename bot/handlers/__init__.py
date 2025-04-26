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
        logger.info("Registrando handlers de administrador")
        register_admin_handlers(bot)
        
        logger.info("Registrando handlers de pagos")
        register_payment_handlers(bot)
        
        # Registrar callbacks como prioritarios
        logger.info("Registrando handlers de callbacks")
        register_callback_handlers(bot)
        
        logger.info("Registrando handlers de inicio")
        register_start_handlers(bot)  # Este debe ser el último (más general)
        
        # Verificar que los handlers están registrados
        handlers_info = "Message handlers:\n"
        for i, handler_group in enumerate(bot.message_handlers):
            handlers_info += f"Group {i}: {len(handler_group)} handlers\n"
        
        handlers_info += "\nCallback handlers:\n"
        for i, handler_group in enumerate(bot.callback_query_handlers):
            handlers_info += f"Group {i}: {len(handler_group)} handlers\n"
        
        logger.info(handlers_info)
        
        # Registrar handlers directamente si es necesario
        from .callback_handler import handle_callback
        logger.info("Registrando handler de callback manualmente")
        bot.register_callback_query_handler(
            lambda call: handle_callback(bot, call),
            func=lambda call: True,  # Manejar todos los callbacks
            pass_bot=True
        )
        
        logger.info("Todos los handlers registrados correctamente")
    except Exception as e:
        logger.error(f"Error al registrar los handlers: {str(e)}")
        logger.error(traceback.format_exc())