import telebot
from telebot import types
import logging
import threading
import time
import datetime
from typing import Dict, Optional
import database as db
import payments as pay
from config import PLANS, ADMIN_IDS, INVITE_LINK_EXPIRY_HOURS, INVITE_LINK_MEMBER_LIMIT

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Diccionario para almacenar las animaciones de pago en curso
payment_animations = {}

def handle_payment_method(call):
    """Maneja la selección del método de pago"""
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user_id = call.from_user.id
        
        # Extraer el método de pago y plan del callback data
        _, method, plan_id = call.data.split('_')
        
        if method == "paypal":
            # Mostrar animación de "procesando"
            processing_message = bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="🔄 Preparando pago...\nAguarde por favor...",
                reply_markup=None
            )
            
            # Iniciar animación de "procesando"
            animation_thread = threading.Thread(
                target=start_processing_animation,
                args=(chat_id, processing_message.message_id)
            )
            animation_thread.daemon = True
            animation_thread.start()
            
            # Registrar la animación
            payment_animations[chat_id] = {
                'active': True,
                'message_id': processing_message.message_id
            }
            
            # Crear enlace de suscripción de PayPal
            subscription_url = pay.create_subscription_link(plan_id, user_id)
            
            # Detener la animación
            payment_animations[chat_id]['active'] = False
            
            if subscription_url:
                # Crear markup con botón para pagar
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("💳 Ir a pagar", url=subscription_url),
                    types.InlineKeyboardButton("🔙 Cancelar", callback_data="view_plans")
                )
                
                # Actualizar mensaje con el enlace de pago
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=(
                        "🔗 *Tu enlace de pago está listo*\n\n"
                        f"Plan: {PLANS[plan_id]['display_name']}\n"
                        f"Precio: ${PLANS[plan_id]['price_usd']:.2f} USD / "
                        f"{'semana' if plan_id == 'weekly' else 'mes'}\n\n"
                        "Por favor, haz clic en el botón de abajo para completar tu pago con PayPal.\n"
                        "Una vez completado, serás redirigido de vuelta aquí."
                    ),
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
                logger.info(f"Enlace de pago PayPal creado para usuario {user_id}, plan {plan_id}")
            else:
                # Error al crear enlace de pago
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="view_plans"))
                
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=(
                        "❌ *Error al crear enlace de pago*\n\n"
                        "Lo sentimos, no pudimos procesar tu solicitud en este momento.\n"
                        "Por favor, intenta nuevamente más tarde o contacta a soporte."
                    ),
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
                logger.error(f"Error al crear enlace de pago PayPal para usuario {user_id}, plan {plan_id}")
        
        # Responder al callback para quitar el "reloj de espera" en el cliente
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error en handle_payment_method: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
            
            # Detener cualquier animación en curso
            if chat_id in payment_animations:
                payment_animations[chat_id]['active'] = False
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="view_plans"))
                
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=payment_animations[chat_id]['message_id'],
                    text="❌ Ocurrió un error. Por favor, intenta nuevamente.",
                    reply_markup=markup
                )
        except:
            pass

def start_processing_animation(chat_id, message_id):
    """Inicia una animación de procesamiento en el mensaje"""
    try:
        animation_markers = ['/', '-', '|', '\\']
        current_index = 0
        
        while chat_id in payment_animations and payment_animations[chat_id]['active']:
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        "🔄 Confirmando Pago\n"
                        f"      {animation_markers[current_index]}      \n"
                        "Aguarde por favor..."
                    )
                )
                
                # Actualizar índice de animación
                current_index = (current_index + 1) % len(animation_markers)
                
                # Esperar antes de la siguiente actualización
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error en animación: {str(e)}")
                break
    except Exception as e:
        logger.error(f"Error en start_processing_animation: {str(e)}")

def process_successful_subscription(user_id: int, plan_id: str, paypal_sub_id: str, 
                                   subscription_details: Dict) -> bool:
    """Procesa una suscripción exitosa"""
    try:
        # Obtener detalles del plan
        plan = PLANS.get(plan_id)
        if not plan:
            logger.error(f"Plan no encontrado: {plan_id}")
            return False
        
        # Obtener información del usuario
        user = db.get_user(user_id)
        if not user:
            # Guardar usuario con información mínima si no existe
            db.save_user(user_id)
            user = {'user_id': user_id, 'username': None, 'first_name': None, 'last_name': None}
        
        # Calcular fechas
        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=plan['duration_days'])
        
        # Crear suscripción en la base de datos
        sub_id = db.create_subscription(
            user_id=user_id,
            plan=plan_id,
            price_usd=plan['price_usd'],
            start_date=start_date,
            end_date=end_date,
            status='ACTIVE',
            paypal_sub_id=paypal_sub_id
        )
        
        # Generar enlace de invitación
        invite_link = generate_invite_link(user_id, sub_id)
        
        if not invite_link:
            logger.error(f"No se pudo generar enlace de invitación para usuario {user_id}")
            # Aún continuamos con el proceso, solo que sin enlace
        
        # Enviar mensaje de confirmación al usuario
        confirmation_text = (
            "🎟️ ¡Acceso VIP Confirmado!\n\n"
            "Aquí tienes tu acceso exclusivo 👇\n"
        )
        
        if invite_link:
            confirmation_text += f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
            confirmation_text += f"⚠️ Nota: El enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso."
        else:
            confirmation_text += "❌ No se pudo generar el enlace de invitación. Por favor, contacta a soporte."
        
        bot.send_message(
            chat_id=user_id,
            text=confirmation_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Notificar a los administradores
        username_display = user.get('username', 'Sin username')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        admin_notification = (
            "🎉 ¡Nueva Suscripción! (PayPal)\n\n"
            "Detalles:\n"
            f"• ID pago: {paypal_sub_id}\n"
            f"• Usuario: {username_display} (@{username_display}) (id{user_id})\n"
            f"• Nombre: {full_name}\n"
            f"• Plan: {plan['display_name']}\n"
            f"• Facturación: ${plan['price_usd']:.2f} / "
            f"{'1 semana' if plan_id == 'weekly' else '1 mes'}\n"
            f"• Fecha: {start_date.strftime('%d %b %Y %I:%M %p')}\n"
            f"• Expira: {end_date.strftime('%d %b %Y')}\n"
            f"• Estado: ✅ ACTIVO"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=admin_notification,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar al admin {admin_id}: {str(e)}")
        
        logger.info(f"Suscripción exitosa procesada para usuario {user_id}, plan {plan_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error en process_successful_subscription: {str(e)}")
        return False

def generate_invite_link(user_id: int, sub_id: int) -> Optional[str]:
    """Genera un enlace de invitación para el grupo VIP"""
    try:
        from utils.invite_link import create_invite_link
        
        # Crear enlace con expiración y límite de miembros
        invite_link = create_invite_link(user_id, sub_id)
        
        if invite_link:
            logger.info(f"Enlace de invitación generado para usuario {user_id}")
            return invite_link
        else:
            logger.error(f"No se pudo generar enlace de invitación para usuario {user_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error en generate_invite_link: {str(e)}")
        return None

def update_subscription_from_webhook(event_data: Dict) -> bool:
    """Actualiza la suscripción en la base de datos según el evento de webhook de PayPal"""
    try:
        event_type = event_data.get("event_type")
        resource = event_data.get("resource", {})
        subscription_id = resource.get("id")
        
        if not subscription_id:
            logger.error("Evento de webhook sin ID de suscripción")
            return False
        
        # Obtener la suscripción de la base de datos
        subscription = db.get_subscription_by_paypal_id(subscription_id)
        if not subscription:
            logger.error(f"Suscripción no encontrada para PayPal ID: {subscription_id}")
            return False
        
        sub_id = subscription['sub_id']
        user_id = subscription['user_id']
        
        # Manejar los diferentes tipos de eventos
        if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            # Marcar la suscripción como activa
            db.update_subscription_status(sub_id, "ACTIVE")
            logger.info(f"Suscripción {sub_id} activada")
            
        elif event_type == "BILLING.SUBSCRIPTION.UPDATED":
            # Verificar si hay cambios en la fecha de expiración
            # Esto dependerá de la estructura exacta del evento
            pass
            
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            # Marcar la suscripción como cancelada
            db.update_subscription_status(sub_id, "CANCELLED")
            
            # Intentar expulsar al usuario del grupo
            try:
                from utils.invite_link import remove_user_from_group
                remove_user_from_group(user_id, "Suscripción cancelada")
            except Exception as e:
                logger.error(f"Error al expulsar al usuario {user_id}: {str(e)}")
            
            # Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ *Tu suscripción ha sido cancelada*\n\n"
                        "Has sido expulsado del grupo VIP. Si deseas volver a suscribirte, "
                        "utiliza el comando /start para ver nuestros planes disponibles."
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar cancelación al usuario {user_id}: {str(e)}")
            
            logger.info(f"Suscripción {sub_id} cancelada")
            
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
            # Marcar la suscripción como suspendida
            db.update_subscription_status(sub_id, "SUSPENDED")
            
            # Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ *Tu suscripción ha sido suspendida*\n\n"
                        "Tu acceso al grupo VIP puede verse afectado. Por favor, verifica tu método de pago "
                        "en PayPal para reactivar tu suscripción."
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar suspensión al usuario {user_id}: {str(e)}")
            
            logger.info(f"Suscripción {sub_id} suspendida")
            
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            # Notificar al usuario sobre el pago fallido
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ *Pago fallido*\n\n"
                        "No pudimos procesar el pago de tu suscripción. Por favor, verifica tu método de pago "
                        "en PayPal para evitar la cancelación de tu acceso al grupo VIP."
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar pago fallido al usuario {user_id}: {str(e)}")
            
            logger.info(f"Pago fallido para suscripción {sub_id}")
            
        elif event_type == "PAYMENT.SALE.COMPLETED":
            # Un pago fue completado exitosamente (renovación)
            plan_id = subscription['plan']
            plan = PLANS.get(plan_id)
            
            if not plan:
                logger.error(f"Plan no encontrado para suscripción {sub_id}")
                return False
            
            # Calcular nueva fecha de expiración
            current_end_date = datetime.datetime.fromisoformat(subscription['end_date'])
            new_end_date = current_end_date + datetime.timedelta(days=plan['duration_days'])
            
            # Extender la suscripción
            db.extend_subscription(sub_id, new_end_date)
            
            # Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ *Suscripción renovada exitosamente*\n\n"
                        f"Tu suscripción al grupo VIP ha sido renovada hasta el {new_end_date.strftime('%d %b %Y')}.\n"
                        "¡Gracias por tu continuado apoyo!"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar renovación al usuario {user_id}: {str(e)}")
            
            logger.info(f"Suscripción {sub_id} renovada hasta {new_end_date}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error en update_subscription_from_webhook: {str(e)}")
        return False