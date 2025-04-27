from telebot.types import CallbackQuery
import logging
import traceback

# Importar la instancia del bot directamente
from bot.bot_instance import bot
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

def handle_callback(call):
    """
    Maneja los callbacks de los botones inline.
    
    Args:
        call: Datos del callback
    """
    try:
        # Registrar información para depuración
        logger.info(f"Callback recibido: {call.data} de usuario {call.from_user.id}")
        
        # Evitar el reloj de espera
        bot.answer_callback_query(call.id)
        
        # Manejar diferentes callbacks
        if call.data == "plans":
            logger.info("Procesando callback 'plans'")
            # Mostrar planes disponibles
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=plans_message(),
                reply_markup=plans_markup(),
                parse_mode='HTML'
            )
            logger.info("Mensaje de planes enviado correctamente")
        
        elif call.data == "back_to_start":
            logger.info("Procesando callback 'back_to_start'")
            # Volver al menú principal
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=welcome_message(),
                reply_markup=welcome_markup(),
                parse_mode='HTML'
            )
            logger.info("Mensaje de bienvenida enviado correctamente")
        
        elif call.data == "back_to_plans":
            logger.info("Procesando callback 'back_to_plans'")
            # Volver al menú de planes
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=plans_message(),
                reply_markup=plans_markup(),
                parse_mode='HTML'
            )
            logger.info("Mensaje de planes enviado correctamente")
        
        elif call.data.startswith("plan_"):
            plan_type = call.data.split("_")[1]  # weekly o monthly
            logger.info(f"Procesando callback 'plan_{plan_type}'")
            
            # Mostrar detalles del plan seleccionado
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=subscription_details(plan_type),
                reply_markup=payment_methods_markup(plan_type),
                parse_mode='HTML'
            )
            logger.info(f"Detalles del plan {plan_type} enviados correctamente")
        
        elif call.data == "tutorial":
            logger.info("Procesando callback 'tutorial'")
            # Mostrar tutorial de pagos
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=tutorial_message(),
                reply_markup=back_markup("back_to_plans"),
                parse_mode='Markdown'
            )
            logger.info("Tutorial enviado correctamente")
        
        elif call.data == "terms":
            logger.info("Procesando callback 'terms'")
            # Mostrar términos de uso
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=terms_message(),
                reply_markup=back_markup(),
                parse_mode='Markdown'
            )
            logger.info("Términos enviados correctamente")
        
        elif call.data == "credits":
            logger.info("Procesando callback 'credits'")
            # Mostrar créditos del bot
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=credits_message(),
                reply_markup=back_markup(),
                parse_mode='Markdown'
            )
            logger.info("Créditos enviados correctamente")
        else:
            logger.warning(f"Callback no reconocido: {call.data}")
            
    except Exception as e:
        logger.error(f"Error al procesar callback '{call.data}': {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar responder al usuario que hubo un error
        try:
            bot.answer_callback_query(call.id, "Hubo un error procesando tu solicitud. Intenta nuevamente.")
        except Exception:
            pass

def register_callback_handlers(bot_instance):
    """
    Registra los handlers para los callbacks de botones.
    
    Args:
        bot_instance: Instancia del bot
    """
    logger.info("Registrando handler para callbacks generales")
    
    # Registrar manejador para todos los callbacks - FORMA CORRECTA
    bot_instance.register_callback_query_handler(
        handle_callback,
        func=lambda call: True  # Manejar todos los callbacks
    )
    
    logger.info("Handler para callbacks registrado correctamente")