import telebot
from telebot import types
import logging
import datetime
import database as db

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def handle_recover_access(message):
    """Maneja la solicitud de recuperación de acceso VIP"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar si el usuario tiene una suscripción activa
        subscription = db.get_active_subscription(user_id)
        
        if not subscription:
            # No tiene suscripción activa
            no_subscription_text = (
                "❌ *No tienes una suscripción activa*\n\n"
                "Para acceder al grupo VIP, necesitas adquirir una suscripción.\n"
                "Usa el comando /start para ver nuestros planes disponibles."
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"))
            
            bot.send_message(
                chat_id=chat_id,
                text=no_subscription_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
            logger.info(f"Usuario {user_id} intentó recuperar acceso sin suscripción activa")
            return
        
        # Tiene suscripción activa, verificar si tiene un enlace de invitación válido
        link = db.get_active_invite_link(subscription['sub_id'])
        
        if link:
            # Tiene un enlace activo, enviarlo
            recovery_text = (
                "🎟️ *Recuperación de Acceso VIP*\n\n"
                "Aquí tienes tu enlace de invitación al grupo VIP:\n"
                f"🔗 [Únete al Grupo VIP]({link['invite_link']})\n\n"
                f"⚠️ Este enlace expira el {datetime.datetime.fromisoformat(link['expires_at']).strftime('%d %b %Y %I:%M %p')} "
                "o después de un solo uso."
            )
            
            bot.send_message(
                chat_id=chat_id,
                text=recovery_text,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"Usuario {user_id} recuperó su enlace de acceso existente")
        else:
            # No tiene un enlace activo, generar uno nuevo
            from handlers.payment_flow import generate_invite_link
            invite_link = generate_invite_link(user_id, subscription['sub_id'])
            
            if invite_link:
                # Enlace generado correctamente
                new_link_text = (
                    "🎟️ *Nuevo Acceso VIP Generado*\n\n"
                    "Hemos creado un nuevo enlace de invitación para ti:\n"
                    f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
                    "⚠️ Este enlace expira en 24 horas o después de un solo uso."
                )
                
                bot.send_message(
                    chat_id=chat_id,
                    text=new_link_text,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                
                logger.info(f"Usuario {user_id} generó un nuevo enlace de acceso")
            else:
                # Error al generar el enlace
                error_text = (
                    "❌ *Error al generar enlace*\n\n"
                    "No pudimos generar un nuevo enlace de invitación en este momento.\n"
                    "Por favor, contacta a soporte para recibir asistencia."
                )
                
                bot.send_message(
                    chat_id=chat_id,
                    text=error_text,
                    parse_mode='Markdown'
                )
                
                logger.error(f"Error al generar nuevo enlace para usuario {user_id}")
    
    except Exception as e:
        logger.error(f"Error en handle_recover_access: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente más tarde."
        )