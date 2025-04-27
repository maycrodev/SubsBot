from telebot import TeleBot
from telebot.types import Message, CallbackQuery
import dateparser
from datetime import datetime, timedelta
import logging

import config
from bot.keyboards.markup_creator import admin_whitelist_time_markup, admin_confirm_whitelist_markup
from bot.utils.messages import admin_whitelist_request, admin_whitelist_time_instructions, admin_whitelist_success, user_subscription_info
from db.repository.user_repo import UserRepository
from db.repository.subscription_repo import SubscriptionRepository
from db.database import SessionLocal

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

# Estado para el comando whitelist
admin_whitelist_state = {}

def is_admin(user_id):
    """Verifica si un usuario es administrador"""
    return user_id in config.ADMIN_IDS

def handle_whitelist_command(message: Message, bot: TeleBot):
    """
    Maneja el comando /whitelist para añadir usuarios a la whitelist.
    
    Args:
        message: Mensaje del comando
        bot: Instancia del bot
    """
    user_id = message.from_user.id
    
    # Verificar si es admin
    if not is_admin(user_id):
        bot.reply_to(message, "❌ No tienes permisos para usar este comando.")
        return
    
    # Verificar formato del comando
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Uso incorrecto. Formato: `/whitelist USER_ID`", parse_mode='Markdown')
        return
    
    try:
        # Obtener ID del usuario a añadir
        target_user_id = int(args[1])
        
        # Buscar usuario en la base de datos
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, target_user_id)
            username = None
            full_name = None
            
            if user:
                username = user.username
                full_name = user.full_name
            
            # Enviar mensaje de confirmación
            sent_msg = bot.reply_to(
                message,
                admin_whitelist_request(target_user_id, username, full_name),
                reply_markup=admin_whitelist_time_markup(target_user_id),
                parse_mode='HTML'
            )
            
            # Guardar estado
            admin_whitelist_state[user_id] = {
                'target_user_id': target_user_id,
                'waiting_for_time': False,
                'message_id': sent_msg.message_id
            }
            
        finally:
            db.close()
            
    except ValueError:
        bot.reply_to(message, "❌ El ID de usuario debe ser un número.")

def handle_whitelist_time_callback(call: CallbackQuery, bot: TeleBot):
    """Maneja el callback para solicitar tiempo de whitelist"""
    if not call.data.startswith("whitelist_time_"):
        return
    
    user_id = call.from_user.id
    
    # Verificar si es admin
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "No tienes permisos para esta acción")
        return
    
    # Obtener usuario objetivo del callback data
    target_user_id = int(call.data.split("_")[-1])
    
    # Responder al callback
    bot.answer_callback_query(call.id)
    
    # Actualizar mensaje pidiendo el tiempo
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=admin_whitelist_time_instructions(),
        parse_mode='Markdown'
    )
    
    # Actualizar estado
    admin_whitelist_state[user_id] = {
        'target_user_id': target_user_id,
        'waiting_for_time': True,
        'message_id': call.message.message_id
    }

def handle_whitelist_time_response(message: Message, bot: TeleBot):
    """Procesa la respuesta con el tiempo de whitelist"""
    user_id = message.from_user.id
    
    # Verificar si es admin y está en estado de espera
    if not is_admin(user_id) or user_id not in admin_whitelist_state:
        return False
    
    state = admin_whitelist_state[user_id]
    if not state.get('waiting_for_time'):
        return False
    
    # Intentar parsear el tiempo
    time_text = message.text.strip()
    try:
        # Parsear el tiempo usando dateparser
        duration = dateparser.parse(f"in {time_text}", settings={'PREFER_DATES_FROM': 'future'})
        
        if not duration:
            bot.reply_to(message, "❌ Formato de tiempo no válido. Intenta con: `7 days`, `1 month`, etc.", parse_mode='Markdown')
            return True
        
        # Calcular fecha de expiración
        now = datetime.utcnow()
        expiry_date = duration
        
        # Si la duración es en el pasado o igual al presente, es un error
        if expiry_date <= now:
            bot.reply_to(message, "❌ La duración debe ser positiva.", parse_mode='Markdown')
            return True
        
        # Añadir usuario a la whitelist
        target_user_id = state['target_user_id']
        
        db = SessionLocal()
        try:
            # Verificar si el usuario existe, sino crearlo
            user = UserRepository.get_user_by_telegram_id(db, target_user_id)
            if not user:
                # Crear usuario con información mínima
                user = UserRepository.create_user(db, target_user_id, f"User_{target_user_id}")
            
            # Añadir a whitelist (crear suscripción manual)
            subscription = UserRepository.add_to_whitelist(db, target_user_id, expiry_date)
            
            if subscription:
                # Calcular duración en texto
                delta = expiry_date - now
                days = delta.days
                
                duration_text = f"{days} días"
                if days >= 30:
                    months = days // 30
                    remaining_days = days % 30
                    duration_text = f"{months} mes(es)"
                    if remaining_days > 0:
                        duration_text += f" y {remaining_days} día(s)"
                
                # Enviar mensaje de éxito
                bot.reply_to(
                    message,
                    admin_whitelist_success(target_user_id, duration_text)
                )
                
                # Notificar al usuario que ha sido añadido a la whitelist
                try:
                    bot.send_message(
                        chat_id=target_user_id,
                        text=f"✅ Has sido añadido al grupo VIP por un administrador.\nDuración: {duration_text}\n\nAquí tienes tu enlace de acceso:\n{config.GROUP_INVITE_LINK}"
                    )
                except Exception:
                    # Ignorar errores al enviar mensaje al usuario
                    pass
            else:
                bot.reply_to(message, "❌ Error al añadir el usuario a la whitelist.")
        
        finally:
            db.close()
            # Limpiar estado
            if user_id in admin_whitelist_state:
                del admin_whitelist_state[user_id]
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
        # Limpiar estado en caso de error
        if user_id in admin_whitelist_state:
            del admin_whitelist_state[user_id]
    
    return True

def handle_subinfo_command(message: Message, bot: TeleBot):
    """
    Maneja el comando /subinfo para mostrar información de suscripción de un usuario.
    
    Args:
        message: Mensaje del comando
        bot: Instancia del bot
    """
    user_id = message.from_user.id
    
    # Verificar si es admin
    if not is_admin(user_id):
        bot.reply_to(message, "❌ No tienes permisos para usar este comando.")
        return
    
    # Verificar formato del comando
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Uso incorrecto. Formato: `/subinfo USER_ID`", parse_mode='Markdown')
        return
    
    try:
        # Obtener ID del usuario
        target_user_id = int(args[1])
        
        # Buscar usuario y suscripciones en la base de datos
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, target_user_id)
            
            if not user:
                bot.reply_to(message, f"❌ Usuario con ID {target_user_id} no encontrado.")
                return
            
            # Obtener suscripciones del usuario
            subscriptions = SubscriptionRepository.get_subscriptions_by_user_id(
                db, target_user_id, limit=5, order_by_desc=True
            )
            
            # Mostrar información
            bot.reply_to(
                message,
                user_subscription_info(user, subscriptions),
                parse_mode='HTML'
            )
            
        finally:
            db.close()
            
    except ValueError:
        bot.reply_to(message, "❌ El ID de usuario debe ser un número.")

def register_admin_handlers(bot: TeleBot):
    """
    Registra los handlers para comandos de administrador.
    
    Args:
        bot: Instancia del bot
    """
    # Comando whitelist
    bot.register_message_handler(
        callback=handle_whitelist_command,
        commands=['whitelist'],
        pass_bot=True
    )
    
    # Comando subinfo
    bot.register_message_handler(
        callback=handle_subinfo_command,
        commands=['subinfo'],
        pass_bot=True
    )
    
    # Callback de tiempo para whitelist
    bot.register_callback_query_handler(
        callback=handle_whitelist_time_callback,
        func=lambda call: call.data and call.data.startswith("whitelist_time_"),
        pass_bot=True
    )
    
    # Respuesta de tiempo para whitelist #
    bot.register_message_handler(
        callback=handle_whitelist_time_response,
        func=lambda message: True,
        content_types=['text'],
        pass_bot=True
    )