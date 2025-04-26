from telebot import TeleBot
from telebot.types import CallbackQuery
import logging
import traceback

import config
from bot.keyboards.markup_creator import (
    welcome_markup, plans_markup, payment_methods_markup, back_markup
)
from bot.utils.messages import (
    welcome_message, plans_message, subscription_details,
    tutorial_message, terms_message, credits_message
)

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

def handle_callback(bot: TeleBot, call: CallbackQuery):
    """
    Maneja los callbacks de los botones inline.
    
    Args:
        bot: Instancia del bot
        call: Datos del callback
    """
    try:
        logger.info(f"Procesando callback: {call.data} de usuario {call.from_user.id}")
        
        # Evitar el reloj de espera
        try:
            bot.answer_callback_query(call.id)
            logger.info(f"Callback {call.id} respondido")
        except Exception as e:
            logger.error(f"Error al responder callback: {str(e)}")
        
        # Manejar diferentes callbacks
        if call.data == "plans":
            logger.info("Mostrando planes disponibles")
            try:
                plans_text = plans_message()
                markup = plans_markup()
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=plans_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                logger.info("Mensaje de planes enviado correctamente")
            except Exception as e:
                logger.error(f"Error al mostrar planes: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "back_to_start":
            logger.info("Volviendo al menú principal")
            try:
                welcome_text = welcome_message()
                markup = welcome_markup()
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=welcome_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                logger.info("Mensaje de bienvenida enviado correctamente")
            except Exception as e:
                logger.error(f"Error al volver al inicio: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "back_to_plans":
            logger.info("Volviendo al menú de planes")
            try:
                plans_text = plans_message()
                markup = plans_markup()
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=plans_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                logger.info("Mensaje de planes enviado correctamente")
            except Exception as e:
                logger.error(f"Error al volver a planes: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data.startswith("plan_"):
            plan_type = call.data.split("_")[1]  # weekly o monthly
            logger.info(f"Mostrando detalles del plan: {plan_type}")
            
            try:
                details_text = subscription_details(plan_type)
                markup = payment_methods_markup(plan_type)
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=details_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                logger.info(f"Detalles del plan {plan_type} enviados correctamente")
            except Exception as e:
                logger.error(f"Error al mostrar detalles del plan: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "tutorial":
            logger.info("Mostrando tutorial de pagos")
            try:
                tutorial_text = tutorial_message()
                markup = back_markup("back_to_plans")
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=tutorial_text,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                logger.info("Tutorial de pagos enviado correctamente")
            except Exception as e:
                logger.error(f"Error al mostrar tutorial: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "terms":
            logger.info("Mostrando términos de uso")
            try:
                terms_text = terms_message()
                markup = back_markup()
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=terms_text,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                logger.info("Términos de uso enviados correctamente")
            except Exception as e:
                logger.error(f"Error al mostrar términos: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "credits":
            logger.info("Mostrando créditos del bot")
            try:
                credits_text = credits_message()
                markup = back_markup()
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=credits_text,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                logger.info("Créditos del bot enviados correctamente")
            except Exception as e:
                logger.error(f"Error al mostrar créditos: {str(e)}")
                logger.error(traceback.format_exc())
        else:
            logger.warning(f"Callback no reconocido: {call.data}")
    
    except Exception as e:
        logger.error(f"Error general al procesar callback: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar enviar un mensaje de error al usuario
        try:
            bot.send_message(
                chat_id=call.message.chat.id,
                text="Lo siento, ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
            )
        except:
            pass

def register_callback_handlers(bot: TeleBot):
    """
    Registra los handlers para los callbacks de botones.
    
    Args:
        bot: Instancia del bot
    """
    try:
        logger.info("Registrando handlers de callback")
        
        # Handler principal para callbacks generales
        bot.register_callback_query_handler(
            lambda call: handle_callback(bot, call),
            lambda call: not call.data.startswith("pay_") and not call.data.startswith("whitelist_") and not call.data.startswith("confirm_"),
            pass_bot=True
        )
        
        # Handler explícito para cada tipo de callback (redundante pero útil para debugging)
        for callback_type in ["plans", "back_to_start", "back_to_plans", "tutorial", "terms", "credits"]:
            bot.register_callback_query_handler(
                lambda call, cb_type=callback_type: handle_callback(bot, call) if call.data == cb_type else None,
                lambda call, cb_type=callback_type: call.data == cb_type,
                pass_bot=True
            )
        
        # Handler para callbacks de plan
        bot.register_callback_query_handler(
            lambda call: handle_callback(bot, call) if call.data.startswith("plan_") else None,
            lambda call: call.data.startswith("plan_"),
            pass_bot=True
        )
        
        logger.info("Handlers de callback registrados correctamente")
    except Exception as e:
        logger.error(f"Error al registrar handlers de callback: {str(e)}")
        logger.error(traceback.format_exc())