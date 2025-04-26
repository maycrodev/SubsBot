from telebot import TeleBot
from telebot.types import CallbackQuery

import config
from bot.keyboards.markup_creator import (
    welcome_markup, plans_markup, payment_methods_markup, back_markup
)
from bot.utils.messages import (
    welcome_message, plans_message, subscription_details,
    tutorial_message, terms_message, credits_message
)

def handle_callback(bot: TeleBot, call: CallbackQuery):
    """
    Maneja los callbacks de los botones inline.
    
    Args:
        bot: Instancia del bot
        call: Datos del callback
    """
    # Evitar el reloj de espera
    bot.answer_callback_query(call.id)
    
    # Manejar diferentes callbacks
    if call.data == "plans":
        # Mostrar planes disponibles
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=plans_message(),
            reply_markup=plans_markup(),
            parse_mode='HTML'
        )
    
    elif call.data == "back_to_start":
        # Volver al menú principal
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=welcome_message(),
            reply_markup=welcome_markup(),
            parse_mode='HTML'
        )
    
    elif call.data == "back_to_plans":
        # Volver al menú de planes
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=plans_message(),
            reply_markup=plans_markup(),
            parse_mode='HTML'
        )
    
    elif call.data.startswith("plan_"):
        # Mostrar detalles del plan seleccionado
        plan_type = call.data.split("_")[1]  # weekly o monthly
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=subscription_details(plan_type),
            reply_markup=payment_methods_markup(plan_type),
            parse_mode='HTML'
        )
    
    elif call.data == "tutorial":
        # Mostrar tutorial de pagos
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tutorial_message(),
            reply_markup=back_markup("back_to_plans"),
            parse_mode='Markdown'
        )
    
    elif call.data == "terms":
        # Mostrar términos de uso
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=terms_message(),
            reply_markup=back_markup(),
            parse_mode='Markdown'
        )
    
    elif call.data == "credits":
        # Mostrar créditos del bot
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=credits_message(),
            reply_markup=back_markup(),
            parse_mode='Markdown'
        )
    
    # Delegamos los callbacks de pago al payment_handler

def register_callback_handlers(bot: TeleBot):
    """
    Registra los handlers para los callbacks de botones.
    
    Args:
        bot: Instancia del bot
    """
    bot.register_callback_query_handler(
        lambda call: handle_callback(bot, call),
        lambda call: not call.data.startswith("pay_") and not call.data.startswith("whitelist_") and not call.data.startswith("confirm_"),
        pass_bot=True
    )