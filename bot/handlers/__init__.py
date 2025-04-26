from telebot import TeleBot
from .start_handler import register_start_handlers
from .admin_handler import register_admin_handlers
from .payment_handler import register_payment_handlers
from .callback_handler import register_callback_handlers

def register_all_handlers(bot: TeleBot):
    """Registra todos los handlers del bot"""
    # El orden importa - handlers más específicos primero
    register_admin_handlers(bot)
    register_payment_handlers(bot)
    register_callback_handlers(bot)
    register_start_handlers(bot)  # Este debe ser el último (más general)