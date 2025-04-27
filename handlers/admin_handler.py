import telebot
from telebot import types
import logging
import datetime
import re
from typing import Optional, Tuple
import database as db
from config import ADMIN_IDS, PLANS

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Almacén temporal para gestionar conversaciones en curso
admin_states = {}

def handle_whitelist(message):
    """Maneja el comando /whitelist para agregar un usuario a la whitelist manualmente"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if admin_id not in ADMIN_IDS:
            bot.send_message(
                chat_id=chat_id,
                text="⛔ No tienes permisos para usar este comando."
            )
            return
        
        # Extraer el ID de usuario del comando
        command_parts = message.text.split()
        
        if len(command_parts) < 2:
            bot.send_message(
                chat_id=chat_id,
                text="❌ Uso incorrecto. Por favor, usa /whitelist USER_ID"
            )
            return
        
        try:
            target_user_id = int(command_parts[1])
        except ValueError:
            bot.send_message(
                chat_id=chat_id,
                text="❌ ID de usuario inválido. Debe ser un número."
            )
            return
        
        # Obtener información del usuario
        user = db.get_user(target_user_id)
        
        # Si el usuario no existe en la BD, guardar con información mínima
        if not user:
            db.save_user(target_user_id)
            user = {'user_id': target_user_id, 'username': None, 'first_name': None, 'last_name': None}
        
        # Preparar mensaje de confirmación
        username_display = user.get('username', 'Sin username')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        confirmation_text = (
            "🛡️ Administración:\n\n"
            "¿Agregar a:\n"
            f"👤 {full_name} (@{username_display})\n"
            f"🆔 {target_user_id} ?\n\n"
            "⏱️ Define duración: (`7 days`, `1 month`, …)"
        )
        
        # Guardar estado para esperar la respuesta con la duración
        admin_states[admin_id] = {
            'action': 'whitelist',
            'target_user_id': target_user_id,
            'message_id': None
        }
        
        # Enviar mensaje de confirmación
        sent_message = bot.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode='Markdown'
        )
        
        # Guardar ID del mensaje enviado
        admin_states[admin_id]['message_id'] = sent_message.message_id
        
        # Registrar el próximo paso: esperar duración
        bot.register_next_step_handler(message, handle_whitelist_duration)
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
        )

def handle_whitelist_duration(message):
    """Procesa la duración para la whitelist"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que el admin tenga un estado pendiente
        if admin_id not in admin_states or admin_states[admin_id]['action'] != 'whitelist':
            bot.send_message(
                chat_id=chat_id,
                text="❌ No hay una solicitud de whitelist pendiente. Usa /whitelist USER_ID para comenzar."
            )
            return
        
        # Extraer la duración del mensaje
        duration_text = message.text.strip().lower()
        
        # Parsear la duración
        days = parse_duration(duration_text)
        
        if days is None:
            bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Formato de duración no reconocido.\n"
                    "Ejemplos válidos: '7 days', '1 week', '1 month', '3 months'"
                )
            )
            # Volver a solicitar la duración
            bot.register_next_step_handler(message, handle_whitelist_duration)
            return
        
        # Obtener información del estado
        target_user_id = admin_states[admin_id]['target_user_id']
        
        # Calcular fechas
        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=days)
        
        # Determinar el plan más cercano
        plan_id = 'weekly' if days <= 7 else 'monthly'
        
        # Crear suscripción en la base de datos
        sub_id = db.create_subscription(
            user_id=target_user_id,
            plan=plan_id,
            price_usd=0.00,  # Gratis por ser whitelist
            start_date=start_date,
            end_date=end_date,
            status='ACTIVE',
            paypal_sub_id=None
        )
        
        # Generar enlace de invitación
        from handlers.payment_flow import generate_invite_link
        invite_link = generate_invite_link(target_user_id, sub_id)
        
        # Enviar mensaje de confirmación
        confirmation_text = (
            "✅ *Usuario agregado a la whitelist exitosamente*\n\n"
            f"👤 ID: {target_user_id}\n"
            f"📆 Duración: {days} días\n"
            f"🗓️ Expira: {end_date.strftime('%d %b %Y')}\n"
        )
        
        if invite_link:
            confirmation_text += f"\n🔗 [Enlace de invitación]({invite_link})"
        
        bot.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Notificar al usuario
        try:
            user_notification = (
                "🎟️ *¡Has sido agregado al grupo VIP!*\n\n"
                f"Un administrador te ha concedido acceso por {days} días.\n\n"
            )
            
            if invite_link:
                user_notification += f"Aquí tienes tu enlace de invitación:\n🔗 [Únete al Grupo VIP]({invite_link})"
            
            bot.send_message(
                chat_id=target_user_id,
                text=user_notification,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error al notificar al usuario {target_user_id}: {str(e)}")
            
            # Informar al admin que no se pudo notificar
            bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ No se pudo notificar al usuario. Es posible que no haya iniciado el bot."
            )
        
        # Limpiar el estado
        del admin_states[admin_id]
        
        logger.info(f"Admin {admin_id} agregó a usuario {target_user_id} a la whitelist por {days} días")
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist_duration: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error al procesar la duración. Por favor, intenta nuevamente con /whitelist."
        )

def handle_subinfo(message):
    """Maneja el comando /subinfo para mostrar información de suscripción de un usuario"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if admin_id not in ADMIN_IDS:
            bot.send_message(
                chat_id=chat_id,
                text="⛔ No tienes permisos para usar este comando."
            )
            return
        
        # Extraer el ID de usuario del comando
        command_parts = message.text.split()
        
        if len(command_parts) < 2:
            bot.send_message(
                chat_id=chat_id,
                text="❌ Uso incorrecto. Por favor, usa /subinfo USER_ID"
            )
            return
        
        try:
            target_user_id = int(command_parts[1])
        except ValueError:
            bot.send_message(
                chat_id=chat_id,
                text="❌ ID de usuario inválido. Debe ser un número."
            )
            return
        
        # Obtener información del usuario
        user = db.get_user(target_user_id)
        
        if not user:
            bot.send_message(
                chat_id=chat_id,
                text=f"❌ Usuario con ID {target_user_id} no encontrado en la base de datos."
            )
            return
        
        # Obtener suscripción del usuario
        subscription = db.get_subscription_by_user_id(target_user_id)
        
        if not subscription:
            bot.send_message(
                chat_id=chat_id,
                text=f"❌ El usuario {target_user_id} no tiene ninguna suscripción registrada."
            )
            return
        
        # Preparar información a mostrar
        username_display = user.get('username', 'Sin username')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        status = subscription['status']
        status_emoji = "🟢" if status == "ACTIVE" else "🔴"
        
        start_date = datetime.datetime.fromisoformat(subscription['start_date'])
        end_date = datetime.datetime.fromisoformat(subscription['end_date'])
        
        plan_id = subscription['plan']
        plan_name = PLANS.get(plan_id, {}).get('display_name', plan_id)
        
        payment_method = "PayPal" if subscription['paypal_sub_id'] else "Manual (Whitelist)"
        
        # Crear mensaje con la información
        info_text = (
            f"👤 ID: {target_user_id}\n"
            f"🧑 Nombre: {full_name} (@{username_display})\n"
            f"📊 Estado: {status_emoji} {status}\n\n"
            f"📥 Plan: {plan_name}\n"
            f"🗓️ Inicio: {start_date.strftime('%d %b %Y')}\n"
            f"⏳ Expira: {end_date.strftime('%d %b %Y')}\n\n"
            f"💳 Pagos: {payment_method}\n"
        )
        
        if subscription['paypal_sub_id']:
            info_text += f"Subscription ID: {subscription['paypal_sub_id']}"
        
        # Enviar mensaje con la información
        bot.send_message(
            chat_id=chat_id,
            text=info_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} consultó información de suscripción del usuario {target_user_id}")
        
    except Exception as e:
        logger.error(f"Error en handle_subinfo: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error al consultar la información. Por favor, intenta nuevamente."
        )

def parse_duration(duration_text: str) -> Optional[int]:
    """
    Parsea una duración en texto y la convierte a días.
    Ejemplos: '7 days', '1 week', '1 month', '3 months'
    Retorna None si no se puede parsear.
    """
    try:
        # Patrones para diferentes formatos
        day_pattern = re.compile(r'(\d+)\s*(?:day|days|día|dias|d)', re.IGNORECASE)
        week_pattern = re.compile(r'(\d+)\s*(?:week|weeks|semana|semanas|w)', re.IGNORECASE)
        month_pattern = re.compile(r'(\d+)\s*(?:month|months|mes|meses|m)', re.IGNORECASE)
        year_pattern = re.compile(r'(\d+)\s*(?:year|years|año|años|y)', re.IGNORECASE)
        
        # Verificar cada patrón
        day_match = day_pattern.search(duration_text)
        if day_match:
            return int(day_match.group(1))
        
        week_match = week_pattern.search(duration_text)
        if week_match:
            return int(week_match.group(1)) * 7
        
        month_match = month_pattern.search(duration_text)
        if month_match:
            return int(month_match.group(1)) * 30
        
        year_match = year_pattern.search(duration_text)
        if year_match:
            return int(year_match.group(1)) * 365
        
        # Si es solo un número, asumir días
        if duration_text.isdigit():
            return int(duration_text)
        
        # No se pudo parsear
        return None
        
    except Exception as e:
        logger.error(f"Error al parsear duración '{duration_text}': {str(e)}")
        return None