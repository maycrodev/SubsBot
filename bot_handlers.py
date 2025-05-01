import logging
from operator import itemgetter
from telebot import types
import database as db
from config import ADMIN_IDS, PLANS, INVITE_LINK_EXPIRY_HOURS, INVITE_LINK_MEMBER_LIMIT, GROUP_INVITE_LINK, WEBHOOK_URL, GROUP_CHAT_ID
import payments as pay
import datetime
import threading
import time
import os
import re
from typing import Dict, Optional, Tuple, Any

global security_thread_running
security_thread_running = False

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# admin_states será asignado desde app.py
admin_states = None  # Será asignado desde app.py

# Diccionario para almacenar las animaciones de pago en curso
payment_animations = {}

def register_admin_commands(bot):
    """Registra comandos exclusivos para administradores"""
    from config import ADMIN_IDS
    
    # Handler para estadísticas del bot (solo admins)
    bot.register_message_handler(
        lambda message: handle_stats_command(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and 
                           (message.text == '/stats' or message.text == '/estadisticas')
    )
    
    # Handler para probar la generación de enlaces de invitación (solo admins)
    bot.register_message_handler(
        lambda message: handle_test_invite(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/test_invite'
    )
    
    # Handler para verificar permisos del bot
    bot.register_message_handler(
        lambda message: check_and_fix_bot_permissions(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/check_bot_permissions'
    )
    
    # Handler para whitelist
    bot.register_message_handler(
        lambda message: handle_whitelist(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text.startswith('/whitelist')
    )
    
    # Handler para subinfo
    bot.register_message_handler(
        lambda message: handle_subinfo(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text.startswith('/subinfo')
    )
    
    # Comando de verificación de permisos para admins
    bot.register_message_handler(
        lambda message: verify_bot_permissions(bot) and bot.reply_to(message, "✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles."),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/check_permissions'
    )
    
    logger.info("Comandos de administrador registrados correctamente")

# Funciones de utilidad
def parse_duration(duration_text: str) -> Optional[float]:
    """
    Parsea una duración en texto y la convierte a días.
    Ejemplos: '7 days', '1 week', '1 month', '3 months', '10 minutes', '2 hours'
    Retorna None si no se puede parsear.
    """
    try:
        if not duration_text:
            return None
            
        duration_text = duration_text.lower().strip()
        logger.info(f"Parseando duración: '{duration_text}'")
        
        # Definir diccionarios de mapeo para unidades
        minute_keywords = ['minute', 'min', 'minuto', 'minutos']
        hour_keywords = ['hour', 'hr', 'hora', 'horas']
        day_keywords = ['day', 'día', 'dias', 'days']
        week_keywords = ['week', 'semana', 'semanas']
        month_keywords = ['month', 'mes', 'meses']
        
        # Casos especiales predefinidos
        special_cases = {
            "10 minutes": 10 / (24 * 60),
            "10 minutos": 10 / (24 * 60),
            "1 minute": 1 / (24 * 60),
            "1 minuto": 1 / (24 * 60)
        }
        
        # Verificar casos especiales primero
        if duration_text in special_cases:
            return special_cases[duration_text]
        
        # Extraer números y unidades
        numbers = ''.join(c if c.isdigit() else ' ' for c in duration_text).split()
        if not numbers:
            return None
        
        try:
            num = int(numbers[0])  # Tomar el primer número
        except ValueError:
            logger.warning(f"No se pudo convertir '{numbers[0]}' a número")
            return None
        
        # Determinar la unidad
        for keyword in minute_keywords:
            if keyword in duration_text:
                return num / (24 * 60)
        
        for keyword in hour_keywords:
            if keyword in duration_text:
                return num / 24
        
        for keyword in day_keywords:
            if keyword in duration_text:
                return num
        
        for keyword in week_keywords:
            if keyword in duration_text:
                return num * 7
        
        for keyword in month_keywords:
            if keyword in duration_text:
                return num * 30
        
        # Si es solo un número, intentar interpretarlo como días
        if duration_text.replace(' ', '').isdigit():
            try:
                return int(duration_text)
            except ValueError:
                pass
        
        # Si no se reconoce ninguna unidad
        logger.warning(f"Unidad no reconocida en '{duration_text}'")
        return None
        
    except Exception as e:
        logger.error(f"Error al parsear duración '{duration_text}': {str(e)}")
        return None

def create_invite_link(bot, user_id, sub_id):
    """
    Crea un enlace de invitación único para el grupo VIP.
    Utiliza la API de Telegram para crear un enlace temporal y único.
    """
    try:
        from config import GROUP_CHAT_ID, INVITE_LINK_EXPIRY_HOURS, INVITE_LINK_MEMBER_LIMIT
        
        if not GROUP_CHAT_ID:
            logger.error("GROUP_CHAT_ID no está configurado")
            return None
            
        # Calcular la fecha de expiración
        current_time = datetime.datetime.now()
        expire_date = int((current_time + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)).timestamp())
        
        # Crear un enlace de invitación único usando la API de Telegram
        logger.info(f"Generando enlace de invitación único para usuario {user_id}")
        
        invite = bot.create_chat_invite_link(
            chat_id=GROUP_CHAT_ID,
            expire_date=expire_date,
            member_limit=INVITE_LINK_MEMBER_LIMIT,
            name=f"Invitación para usuario {user_id}",
            creates_join_request=False
        )
        
        # Obtener el enlace de la respuesta
        invite_link = invite.invite_link
        
        # Guardar el enlace en la base de datos
        created_at = current_time
        expires_at = current_time + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)
        
        db.save_invite_link(
            sub_id=sub_id,
            invite_link=invite_link,
            created_at=created_at,
            expires_at=expires_at
        )
        
        logger.info(f"Enlace de invitación único creado para usuario {user_id}, expira en {INVITE_LINK_EXPIRY_HOURS} horas")
        
        return invite_link
        
    except Exception as e:
        logger.error(f"Error al crear enlace de invitación: {str(e)}")
        return None

def generate_plans_text():
    """
    Genera el texto de descripción de planes dinámicamente 
    basado en la configuración de PLANS
    """
    # Ordenar planes por el campo 'order'
    sorted_plans = sorted(PLANS.items(), key=lambda x: x[1].get('order', 999))
    
    # Iniciar con el encabezado
    plans_text = "💸 Escoge tu plan de suscripción:\n\n"
    
    # Añadir cada plan ordenadamente
    for plan_id, plan in sorted_plans:
        emoji = plan.get('button_emoji', '🔹')
        # Usar short_description o generar una descripción automática
        description = plan.get('short_description', 
                              f"{plan['name']}: ${plan['price_usd']} / {plan['duration_days']} días")
        plans_text += f"{emoji} {description}\n"
    
    # Añadir mensaje del tutorial
    plans_text += "\n🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇"
    
    return plans_text

def start_processing_animation(bot, chat_id, message_id):
    """Inicia una animación de procesamiento en el mensaje"""
    try:
        animation_markers = ['/', '-', '|', '\\']
        current_index = 0
        
        # Registrar la animación
        payment_animations[chat_id] = {
            'active': True,
            'message_id': message_id
        }
        
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

def generate_invite_link(bot, user_id, sub_id):
    """Genera un enlace de invitación para el grupo VIP"""
    try:
        # Crear enlace con expiración y límite de miembros
        invite_link = create_invite_link(bot, user_id, sub_id)
        
        if invite_link:
            logger.info(f"Enlace de invitación generado para usuario {user_id}")
            return invite_link
        else:
            logger.error(f"No se pudo generar enlace de invitación para usuario {user_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error en generate_invite_link: {str(e)}")
        return None

def process_successful_subscription(bot, user_id: int, plan_id: str, paypal_sub_id: str, 
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
        
        # Enviar mensaje provisional mientras se genera el enlace
        provisional_message = bot.send_message(
            chat_id=user_id,
            text="🔄 *Preparando tu acceso VIP...*\n\nEstamos generando tu enlace de invitación exclusivo. Por favor, espera un momento.",
            parse_mode='Markdown'
        )
        
        # Generar enlace de invitación único
        invite_link = generate_invite_link(bot, user_id, sub_id)
        
        if not invite_link:
            logger.error(f"No se pudo generar enlace de invitación para usuario {user_id}")
            bot.edit_message_text(
                chat_id=user_id,
                message_id=provisional_message.message_id,
                text=(
                    "⚠️ *Suscripción activada, pero hay un problema con el enlace*\n\n"
                    "Tu suscripción se ha registrado correctamente, pero no pudimos generar el enlace de invitación.\n"
                    "Por favor, usa el comando /recover para solicitar un nuevo enlace o contacta con soporte."
                ),
                parse_mode='Markdown'
            )
            
            # Notificar a los administradores del problema
            admin_error_notification = (
                "🚨 *ERROR CON ENLACE DE INVITACIÓN*\n\n"
                f"Usuario: {user.get('username', 'Sin username')} (id{user_id})\n"
                f"Suscripción: {sub_id}\n"
                "Error: No se pudo generar enlace de invitación\n\n"
                "El usuario ha sido notificado para que use /recover"
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=admin_error_notification,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error al notificar al admin {admin_id}: {str(e)}")
        else:
            # Enviar mensaje de confirmación con el enlace
            confirmation_text = (
                "🎟️ *¡Acceso VIP Confirmado!*\n\n"
                "Aquí tienes tu acceso exclusivo 👇\n\n"
                f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
                f"⚠️ Nota: Este enlace es único, personal e intransferible. Expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso.\n\n"
                "Si sales del grupo por accidente y necesitas un nuevo enlace, puedes usar el comando /recover"
            )
            
            bot.edit_message_text(
                chat_id=user_id,
                message_id=provisional_message.message_id,
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
            "🎉 *¡Nueva Suscripción! (PayPal)*\n\n"
            "Detalles:\n"
            f"• ID pago: {paypal_sub_id}\n"
            f"• Usuario: {username_display} (@{username_display}) (id{user_id})\n"
            f"• Nombre: {full_name}\n"
            f"• Plan: {plan['display_name']}\n"
            f"• Facturación: ${plan['price_usd']:.2f} / "
            f"{'1 semana' if plan_id == 'weekly' else '1 mes'}\n"
            f"• Fecha: {start_date.strftime('%d %b %Y %I:%M %p')}\n"
            f"• Expira: {end_date.strftime('%d %b %Y')}\n"
            f"• Estado: ✅ ACTIVO\n"
            f"• Enlace: Generado correctamente"
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

def update_subscription_from_webhook(bot, event_data: Dict) -> bool:
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

# Handlers de Telegram
def create_main_menu_markup():
    """Crea los botones para el menú principal"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"),
        types.InlineKeyboardButton("🧠 Créditos del Bot", callback_data="bot_credits"),
        types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
    )
    return markup

def create_plans_markup():
    """
    Crea dinámicamente el markup de botones para los planes
    basado en la configuración de PLANS
    """
    markup = types.InlineKeyboardMarkup()
    
    # Añadir botón de tutorial primero
    markup.add(types.InlineKeyboardButton("🎥 Tutorial de Pagos", callback_data="tutorial"))
    
    # Ordenar planes por 'order'
    sorted_plans = sorted(PLANS.items(), key=lambda x: x[1].get('order', 999))
    
    # Agrupar planes por filas
    rows = {}
    for plan_id, plan in sorted_plans:
        row_num = plan.get('row', 1)
        if row_num not in rows:
            rows[row_num] = []
        
        # Crear botón para el plan
        button_text = f"{plan.get('button_emoji', '📦')} {plan.get('button_text', plan['name'])}"
        callback_data = f"{plan_id}_plan"
        
        # Añadir botón a la fila correspondiente
        rows[row_num].append(types.InlineKeyboardButton(button_text, callback_data=callback_data))
    
    # Añadir filas al markup en orden
    for row_num in sorted(rows.keys()):
        markup.add(*rows[row_num])  # Desempaquetar la lista de botones
    
    # Añadir botón de volver
    markup.add(types.InlineKeyboardButton("🔙 Atrás", callback_data="back_to_main"))
    
    return markup

def get_plan_from_callback(callback_data):
    """
    Extrae el ID del plan desde el callback_data
    Ejemplo: "weekly_plan" -> "weekly"
    """
    if "_plan" in callback_data:
        return callback_data.split("_")[0]
    return None

def perform_group_security_check(bot, group_id, expired_subscriptions=None):
    """Realiza verificación de seguridad y expulsa usuarios no autorizados"""
    try:
        start_time = datetime.datetime.now()
        logger.info(f"🛡️ INICIANDO VERIFICACIÓN DE SEGURIDAD DEL GRUPO en {start_time}")
        
        # PASO 1: Verificar permisos del bot en el grupo
        try:
            bot_info = bot.get_chat_member(group_id, bot.get_me().id)
            logger.info(f"Bot status en grupo: {bot_info.status}")
            logger.info(f"Can restrict members: {getattr(bot_info, 'can_restrict_members', False)}")
            
            if bot_info.status not in ['administrator', 'creator']:
                logger.error(f"⚠️ CRÍTICO: El bot no tiene permisos de administrador en el grupo {group_id}")
                return False
                
            if not getattr(bot_info, 'can_restrict_members', False):
                logger.error(f"⚠️ CRÍTICO: El bot no tiene permisos para expulsar miembros en el grupo {group_id}")
                return False
                
            logger.info(f"✅ Permisos del bot verificados: {bot_info.status}, puede expulsar: {getattr(bot_info, 'can_restrict_members', False)}")
        except Exception as e:
            logger.error(f"⚠️ CRÍTICO: Error al verificar permisos del bot: {e}")
            return False
        
        # PASO 2: Si no hay suscripciones expiradas proporcionadas, obtenerlas con FORCE=True
        if expired_subscriptions is None:
            logger.info("Obteniendo suscripciones expiradas de la base de datos...")
            expired_subscriptions = db.check_and_update_subscriptions(force=True)
        
        # PASO 3: Procesar suscripciones expiradas
        total_count = len(expired_subscriptions)
        logger.info(f"Procesando {total_count} suscripciones expiradas")
        
        if not expired_subscriptions:
            logger.info("No hay suscripciones expiradas que procesar")
            return True
        
        # Contadores para estadísticas
        processed = 0
        success = 0
        errors = 0
        skipped = 0
        
        # PASO 4: Procesar cada usuario con suscripción expirada
        for user_data in expired_subscriptions:
            processed += 1
            user_id, sub_id, plan = user_data
            
            # Excluir administradores
            if user_id in ADMIN_IDS:
                logger.info(f"Ignorando admin {user_id}")
                skipped += 1
                continue
            
            is_whitelist = db.is_whitelist_subscription(sub_id)
            sub_type = "Whitelist" if is_whitelist else "Pagada"
            
            logger.info(f"PROCESANDO: Usuario {user_id}, SubID {sub_id}, Plan {plan}, Tipo {sub_type}")
            
            # Implementación de reintentos (hasta 3 veces)
            max_retries = 3
            retry_count = 0
            retry_delay = 2  # segundos
            
            while retry_count < max_retries:
                try:
                    # Verificar si el usuario está en el grupo
                    try:
                        logger.info(f"Verificando si usuario {user_id} está en el grupo {group_id}")
                        chat_member = bot.get_chat_member(group_id, user_id)
                        logger.info(f"Estado del usuario {user_id} en el grupo: {chat_member.status}")
                        
                        # Si ya no está en el grupo, omitir
                        if chat_member.status in ['left', 'kicked']:
                            logger.info(f"Usuario {user_id} ya no está en el grupo. Omitiendo.")
                            skipped += 1
                            break  # Salir del bucle de reintentos
                        
                        # PASO 5: EXPULSAR AL USUARIO
                        logger.info(f"🔴 EXPULSANDO a usuario {user_id} por suscripción expirada (intento {retry_count+1}/{max_retries})...")
                        
                        # Nueva estrategia de expulsión más robusta
                        try:
                            # Intentar con kick_chat_member o ban_chat_member según disponibilidad
                            try:
                                # Método 1: ban_chat_member (nuevo método recomendado)
                                logger.info(f"Intentando ban_chat_member para usuario {user_id}...")
                                
                                # Usar un bloque try para evitar que errores paren el proceso
                                try:
                                    # Primero intentar desalojar al usuario
                                    bot.ban_chat_member(
                                        chat_id=group_id,
                                        user_id=user_id,
                                        revoke_messages=False
                                    )
                                    logger.info(f"ban_chat_member ejecutado para usuario {user_id}")
                                except Exception as ban_error:
                                    logger.error(f"Error en ban_chat_member: {ban_error}")
                                    raise  # Re-lanzar la excepción para probar el método alternativo
                                
                                # Desbanear para permitir reingreso futuro (en otro bloque try)
                                try:
                                    bot.unban_chat_member(
                                        chat_id=group_id,
                                        user_id=user_id,
                                        only_if_banned=True
                                    )
                                    logger.info(f"unban_chat_member ejecutado para usuario {user_id}")
                                except Exception as unban_error:
                                    logger.error(f"Error en unban_chat_member (no crítico): {unban_error}")
                                    # No re-lanzar esta excepción, ya que el usuario ya fue expulsado
                                
                                # Si llegamos aquí, la expulsión fue exitosa
                                success += 1
                                logger.info(f"✅ Usuario {user_id} expulsado exitosamente")
                                
                            except Exception as ban_method_error:
                                # Método 2: Si ban_chat_member falla, intentar con kick_chat_member
                                logger.warning(f"ban_chat_member falló, intentando método alternativo kick_chat_member: {ban_method_error}")
                                
                                try:
                                    # Intentar el método alternativo
                                    bot.kick_chat_member(
                                        chat_id=group_id,
                                        user_id=user_id
                                    )
                                    logger.info(f"kick_chat_member ejecutado para usuario {user_id}")
                                    
                                    # Intentar desbanear (no crítico)
                                    try:
                                        bot.unban_chat_member(
                                            chat_id=group_id,
                                            user_id=user_id
                                        )
                                        logger.info(f"unban_chat_member ejecutado con método alternativo para usuario {user_id}")
                                    except Exception as alt_unban_error:
                                        logger.error(f"Error en unban_chat_member alternativo (no crítico): {alt_unban_error}")
                                    
                                    # Si llegamos aquí, la expulsión alternativa fue exitosa
                                    success += 1
                                    logger.info(f"✅ Usuario {user_id} expulsado con método alternativo")
                                    
                                except Exception as kick_error:
                                    # Si ambos métodos fallan, registrar el error
                                    logger.error(f"❌ Ambos métodos de expulsión fallaron para usuario {user_id}: {kick_error}")
                                    raise  # Re-lanzar para que se maneje en el bloque catch principal
                            
                            # Registrar expulsión en la base de datos (solo si no hay excepciones)
                            db.record_expulsion(
                                user_id,
                                f"Expulsión automática - Plan: {plan}, Tipo: {sub_type}"
                            )
                            
                            # Notificar al usuario (no crítico)
                            try:
                                bot.send_message(
                                    chat_id=user_id,
                                    text=(
                                        f"❌ Tu suscripción ({sub_type}) ha expirado.\n\n"
                                        "Has sido expulsado del grupo VIP. Para recuperar el acceso, "
                                        "usa el comando /start para ver nuestros planes disponibles."
                                    )
                                )
                                logger.info(f"Notificación enviada a usuario {user_id}")
                            except Exception as notify_error:
                                logger.error(f"No se pudo notificar al usuario {user_id} (no crítico): {notify_error}")
                            
                            # Si llegamos aquí, todo el proceso fue exitoso
                            break  # Salir del bucle de reintentos
                            
                        except Exception as expulsion_error:
                            logger.error(f"❌ Error en el proceso de expulsión para usuario {user_id}: {expulsion_error}")
                            
                            # Incrementar el contador de reintentos
                            retry_count += 1
                            
                            if retry_count < max_retries:
                                logger.info(f"Reintentando expulsión ({retry_count}/{max_retries}) para usuario {user_id} en {retry_delay} segundos...")
                                time.sleep(retry_delay)
                            else:
                                logger.error(f"❌ Se agotaron los reintentos para expulsar al usuario {user_id}")
                                errors += 1
                        
                    except Exception as check_error:
                        if "user not found" in str(check_error).lower():
                            logger.info(f"Usuario {user_id} no encontrado en el grupo. Omitiendo.")
                            skipped += 1
                            break  # Salir del bucle de reintentos
                        else:
                            logger.error(f"Error al verificar usuario {user_id} en el grupo: {check_error}")
                            
                            # Incrementar el contador de reintentos
                            retry_count += 1
                            
                            if retry_count < max_retries:
                                logger.info(f"Reintentando verificación ({retry_count}/{max_retries}) para usuario {user_id} en {retry_delay} segundos...")
                                time.sleep(retry_delay)
                            else:
                                logger.error(f"❌ Se agotaron los reintentos para verificar al usuario {user_id}")
                                errors += 1
                    
                except Exception as cycle_error:
                    logger.error(f"Error general al procesar usuario {user_id}: {cycle_error}")
                    
                    # Incrementar el contador de reintentos
                    retry_count += 1
                    
                    if retry_count < max_retries:
                        logger.info(f"Reintentando procesamiento ({retry_count}/{max_retries}) para usuario {user_id} en {retry_delay} segundos...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"❌ Se agotaron los reintentos para usuario {user_id}")
                        errors += 1
                        break  # Salir del bucle de reintentos
            
        # Estadísticas finales
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = f"""
        === RESUMEN DE VERIFICACIÓN ===
        Duración: {duration:.2f} segundos
        Procesados: {processed}/{total_count}
        Exitosos: {success}
        Omitidos: {skipped}
        Errores: {errors}
        ============================
        """
        
        logger.info(summary)
        
        # Si hay errores, pero también hay éxitos, consideramos que la operación fue parcialmente exitosa
        if errors > 0 and success > 0:
            logger.warning("⚠️ Verificación parcialmente exitosa (algunos usuarios no pudieron ser expulsados)")
            return True
        
        # Si no hay errores o todo son errores
        return errors == 0
        
    except Exception as e:
        logger.error(f"ERROR CRÍTICO en verificación de seguridad: {e}")
        return False
    
# Añade esta nueva función al archivo:

def check_security_thread_status(bot):
    """
    Verifica el estado del hilo de seguridad y lo reinicia si es necesario.
    Esta función debe llamarse periódicamente para garantizar que el hilo esté activo.
    """
    global security_thread_running
    
    # Si el hilo no está ejecutándose, reiniciarlo
    if not security_thread_running:
        logger.warning("⚠️ Hilo de seguridad no detectado. Iniciando uno nuevo...")
        
        # Esperar un momento por si el hilo está en proceso de inicialización
        time.sleep(2)
        
        # Si aún no está ejecutándose, iniciar uno nuevo
        if not security_thread_running:
            new_thread = schedule_security_verification(bot)
            
            if new_thread:
                logger.info("✅ Hilo de seguridad reiniciado exitosamente")
                
                # Notificar a los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text="🔄 El sistema de seguridad se ha reiniciado automáticamente"
                        )
                    except Exception:
                        pass
                
                return True
            else:
                logger.error("❌ No se pudo reiniciar el hilo de seguridad")
                return False
    
    return True


# Modificación 4: Añadir una función para forzar la expulsión inmediata de todos los usuarios con suscripciones expiradas
# Añade esta nueva función al archivo:

def force_security_check(bot):
    """
    Fuerza una verificación de seguridad inmediata y expulsa a todos los usuarios con suscripciones expiradas.
    """
    try:
        logger.info("🔍 Iniciando verificación de seguridad forzada...")
        
        # Verificar los permisos primero
        has_permissions = verify_bot_permissions(bot)
        if not has_permissions:
            logger.error("❌ El bot no tiene los permisos necesarios para realizar expulsiones")
            return False
        
        # Forzar la actualización de suscripciones expiradas
        expired_subscriptions = db.check_and_update_subscriptions(force=True)
        
        if not expired_subscriptions:
            logger.info("✅ No hay suscripciones expiradas que procesar")
            return True
        
        logger.info(f"Encontradas {len(expired_subscriptions)} suscripciones expiradas")
        
        # Realizar expulsión de usuarios con suscripciones expiradas
        if GROUP_CHAT_ID:
            result = perform_group_security_check(bot, GROUP_CHAT_ID, expired_subscriptions)
            
            if result:
                logger.info("✅ Verificación forzada completada exitosamente")
                
                # Notificar a los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=f"✅ Verificación forzada completada: {len(expired_subscriptions)} suscripciones expiradas procesadas"
                        )
                    except Exception:
                        pass
                
                return True
            else:
                logger.error("❌ Verificación forzada falló")
                return False
        else:
            logger.error("❌ GROUP_CHAT_ID no está configurado. No se puede realizar verificación")
            return False
    
    except Exception as e:
        logger.error(f"Error en verificación forzada: {e}")
        return False
    
# 1. VERIFICACIÓN PERIÓDICA AUTOMÁTICA
def schedule_security_verification(bot):
    """Inicia el hilo de verificación periódica de seguridad"""
    global security_thread_running
    
    if security_thread_running:
        logger.info("⚠️ Hilo de verificación ya está en ejecución. No se iniciará otro.")
        return None
    
    def security_check_thread():
        global security_thread_running
        security_thread_running = True
        verify_count = 0
        failures_count = 0
        max_failures = 3  # Permitir hasta 3 fallos consecutivos
        
        # Crear archivo de seguimiento para diagnóstico
        heartbeat_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'security_heartbeat.txt')
        
        try:
            os.makedirs(os.path.dirname(heartbeat_file), exist_ok=True)
            with open(heartbeat_file, 'w') as f:
                f.write(f"Hilo de seguridad iniciado: {datetime.datetime.now()}\n")
        except Exception as e:
            logger.error(f"No se pudo crear archivo de heartbeat: {e}")
        
        logger.info("🔐 HILO DE SEGURIDAD INICIADO - Verificación periódica activada")
        
        # Registro inicial de actividad del hilo
        try:
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text="🔐 Sistema de seguridad activado: Se realizará verificación periódica de suscripciones"
                    )
                except Exception:
                    pass  # Ignorar errores al notificar
        except Exception:
            pass  # Continuar incluso si los mensajes fallan
        
        # Intervalo de verificación configurable (en segundos)
        # Aumentado a 60 segundos para reducir la carga y posibles errores
        check_interval = 60  
        
        while security_thread_running:
            try:
                verify_count += 1
                current_time = datetime.datetime.now()
                
                # Actualizar archivo de heartbeat
                try:
                    with open(heartbeat_file, 'a') as f:
                        f.write(f"Verificación #{verify_count}: {current_time}\n")
                except Exception as e:
                    pass  # No interrumpir el proceso si no se puede escribir el heartbeat
                
                logger.info(f"🔍 VERIFICACIÓN #{verify_count} INICIADA en {current_time}")
                
                # 1. Verificar permisos del bot primero
                try:
                    has_permissions = verify_bot_permissions(bot)
                    if not has_permissions:
                        logger.error("🚨 El bot no tiene los permisos necesarios para expulsar usuarios")
                        # Enviar alerta a todos los administradores
                        for admin_id in ADMIN_IDS:
                            try:
                                bot.send_message(
                                    chat_id=admin_id, 
                                    text="🚨 ALERTA DE SEGURIDAD: El bot no tiene permisos para realizar expulsiones automáticas. Por favor, verifique los permisos del bot en el grupo."
                                )
                            except Exception:
                                pass  # Continuar incluso si los mensajes fallan
                except Exception as perm_error:
                    logger.error(f"Error al verificar permisos: {perm_error}")
                
                # 2. Verificar y obtener suscripciones expiradas
                try:
                    # Usamos FORCE=True para garantizar que se detecten todas las suscripciones expiradas
                    expired_subscriptions = db.check_and_update_subscriptions(force=True)
                    logger.info(f"Suscripciones expiradas encontradas: {len(expired_subscriptions)}")
                    
                    # 3. Si hay expiradas, expulsar usuarios
                    if expired_subscriptions:
                        logger.info(f"🚨 EXPULSANDO {len(expired_subscriptions)} USUARIOS CON SUSCRIPCIONES EXPIRADAS")
                        
                        # Realizar expulsión de usuarios con suscripciones expiradas
                        if GROUP_CHAT_ID:
                            result = perform_group_security_check(
                                bot,
                                GROUP_CHAT_ID,
                                expired_subscriptions
                            )
                            
                            if result:
                                logger.info("✅ Verificación completada exitosamente")
                                failures_count = 0  # Reiniciar contador de fallos
                            else:
                                failures_count += 1
                                logger.error(f"❌ Verificación fallida (intento #{failures_count})")
                                
                                # Si hay fallos consecutivos, notificar a los admins
                                if failures_count >= max_failures:
                                    for admin_id in ADMIN_IDS:
                                        try:
                                            bot.send_message(
                                                chat_id=admin_id,
                                                text=f"🚨 ALERTA: Han ocurrido {failures_count} fallos consecutivos en el sistema de expulsión automática. Por favor, revise los registros."
                                            )
                                        except Exception:
                                            pass
                        else:
                            logger.error("⚠️ GROUP_CHAT_ID no está configurado. No se puede realizar expulsión automática.")
                    else:
                        logger.info("✅ No hay suscripciones expiradas para procesar")
                        failures_count = 0  # Reiniciar contador de fallos
                        
                except Exception as exp_error:
                    failures_count += 1
                    logger.error(f"Error al verificar suscripciones expiradas: {exp_error}")
                
                # Esperar antes de la próxima verificación
                logger.info(f"Hilo de seguridad esperando {check_interval} segundos para próxima verificación...")
                
                # Dividir el sleep en intervalos más pequeños para poder responder rápido a señales de parada
                for _ in range(check_interval):
                    if not security_thread_running:
                        break
                    time.sleep(1)
                
            except Exception as cycle_error:
                failures_count += 1
                logger.error(f"🔥 ERROR EN CICLO DE VERIFICACIÓN: {cycle_error}")
                # En caso de error, esperar y continuar
                time.sleep(5)
                
                # Reiniciar el ciclo si hay demasiados fallos
                if failures_count >= 10:
                    logger.critical("🔥 DEMASIADOS FALLOS CONSECUTIVOS. REINICIANDO EL CICLO DE VERIFICACIÓN.")
                    # Notificar a los admins
                    for admin_id in ADMIN_IDS:
                        try:
                            bot.send_message(
                                chat_id=admin_id,
                                text="🚨 ALERTA CRÍTICA: El sistema de seguridad ha detectado errores graves y está intentando recuperarse. Se recomienda revisar los logs."
                            )
                        except Exception:
                            pass
                    
                    # Reiniciar contadores
                    failures_count = 0
                    
                    # Guardar registro del reinicio
                    try:
                        with open(heartbeat_file, 'a') as f:
                            f.write(f"REINICIO DE EMERGENCIA: {datetime.datetime.now()}\n")
                    except Exception:
                        pass
        
        logger.warning("⚠️ HILO DE SEGURIDAD TERMINADO - La verificación periódica se ha detenido")
        security_thread_running = False
        
        # Intentar reiniciar automáticamente
        try:
            logger.info("🔄 Intentando reiniciar el hilo de seguridad automáticamente...")
            security_thread_running = False
            time.sleep(2)
            # Crear un nuevo hilo
            new_thread = threading.Thread(target=security_check_thread, daemon=True)
            new_thread.start()
            logger.info("✅ Hilo de seguridad reiniciado automáticamente")
        except Exception as restart_error:
            logger.critical(f"❌ No se pudo reiniciar el hilo de seguridad: {restart_error}")
            # Notificar a los admins
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text="🚨 ALERTA CRÍTICA: El sistema de seguridad ha fallado y no se pudo reiniciar automáticamente. Por favor, reinicie el bot."
                    )
                except Exception:
                    pass
    
    # Crear y arrancar hilo en modo daemon
    thread = threading.Thread(target=security_check_thread, daemon=True)
    thread.start()
    logger.info("✅ Hilo de verificación periódica iniciado en segundo plano")
    
    return thread
    
def handle_force_expire(message, bot):
    """
    Comando de fuerza para verificar y expulsar usuarios con suscripciones expiradas
    Uso: /force_expire
    """
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            return
            
        # Mensaje de estado
        status_message = bot.reply_to(
            message,
            "🔄 Forzando verificación y expulsión de suscripciones expiradas..."
        )
        
        # 1. Actualizar suscripciones expiradas en la BD
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text="🔄 Verificando suscripciones expiradas en la base de datos..."
        )
        
        expired_subscriptions = db.check_and_update_subscriptions()
        
        if not expired_subscriptions:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="✅ No se encontraron suscripciones expiradas en la base de datos."
            )
            return
            
        # 2. Hay suscripciones expiradas, mostrar detalles
        users_detail = ""
        for idx, (user_id, sub_id, plan) in enumerate(expired_subscriptions[:10]):  # Mostrar los primeros 10
            is_whitelist = db.is_whitelist_subscription(sub_id)
            user_info = db.get_user(user_id)
            username = user_info.get('username', 'Sin username') if user_info else 'Desconocido'
            users_detail += f"{idx+1}. Usuario {user_id} (@{username}) - {plan} {'(Whitelist)' if is_whitelist else ''}\n"
        
        if len(expired_subscriptions) > 10:
            users_detail += f"... y {len(expired_subscriptions) - 10} más\n"
            
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"🔍 Se encontraron {len(expired_subscriptions)} suscripciones expiradas:\n\n{users_detail}\n🔄 Procesando expulsiones..."
        )
        
        # 3. Realizar las expulsiones
        result = perform_group_security_check(bot, GROUP_CHAT_ID, expired_subscriptions)
        
        # 4. Mostrar resultado final
        if result:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"✅ Verificación forzada completada.\n\nSe procesaron {len(expired_subscriptions)} suscripciones expiradas.\n\nConsulta los logs para ver los detalles de cada usuario."
            )
        else:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"⚠️ Error al procesar la verificación forzada.\n\nRevisa los logs del sistema para más información."
            )
            
    except Exception as e:
        logger.error(f"Error en handle_force_expire: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ Error: {str(e)}"
            )
        except:
            bot.reply_to(message, f"❌ Error: {str(e)}")
    
def check_and_fix_bot_permissions(message, bot):
    """Verifica y corrige los permisos del bot en el grupo VIP"""
    try:
        user_id = message.from_user.id
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            return
            
        from config import GROUP_CHAT_ID
        if not GROUP_CHAT_ID:
            bot.reply_to(message, "❌ Error: GROUP_CHAT_ID no está configurado")
            return
            
        # Obtener información del bot en el grupo
        try:
            bot_member = bot.get_chat_member(GROUP_CHAT_ID, bot.get_me().id)
            
            status_message = f"📊 Estado del bot en el grupo:\n"
            
            # Verificar si es administrador
            if bot_member.status not in ['administrator', 'creator']:
                status_message += "❌ El bot NO es administrador del grupo. Debe ser promovido a administrador.\n"
            else:
                status_message += "✅ El bot es administrador del grupo.\n"
                
                # Verificar permisos específicos
                if not getattr(bot_member, 'can_restrict_members', False):
                    status_message += "❌ El bot NO tiene permiso para expulsar usuarios. Este permiso es OBLIGATORIO.\n"
                else:
                    status_message += "✅ El bot tiene permiso para expulsar usuarios.\n"
                    
                if not getattr(bot_member, 'can_invite_users', False):
                    status_message += "⚠️ El bot no tiene permiso para invitar usuarios (recomendado).\n"
                else:
                    status_message += "✅ El bot tiene permiso para invitar usuarios.\n"
            
            # Enviar mensaje con el estado
            bot.reply_to(message, status_message)
            
        except Exception as e:
            bot.reply_to(message, f"❌ Error al verificar permisos: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error en check_and_fix_bot_permissions: {str(e)}")

# 2. MEJORA DEL COMANDO /verify_all
# Reemplaza la función handle_verify_all_members con esta versión mejorada:

# Esta función ya existe en el código pero asegúrate de que esté correctamente configurada
def handle_verify_all_members(message, bot):
    """
    Comando para verificar y expulsar manualmente a todos los miembros no autorizados del grupo
    """
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Log para depuración
        logger.info(f"Comando {message.text} recibido de usuario {user_id} en chat {chat_id}")
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            logger.info(f"Usuario {user_id} intentó usar {message.text} pero no es administrador")
            bot.reply_to(message, "⚠️ Este comando solo está disponible para administradores.")
            return
        
        # Verificar que el mensaje sea del grupo VIP o de un chat privado con el administrador
        from config import GROUP_CHAT_ID
        if str(chat_id) != str(GROUP_CHAT_ID) and message.chat.type != 'private':
            logger.info(f"Comando {message.text} usado en chat incorrecto {chat_id}")
            bot.reply_to(message, f"⚠️ Este comando solo funciona en el grupo VIP o en chat privado con el bot.")
            return
        
        # Si es en privado, usar el GROUP_CHAT_ID configurado
        target_group_id = GROUP_CHAT_ID if message.chat.type == 'private' else chat_id
        
        # Mensaje inicial
        status_message = bot.reply_to(message, "🔄 Iniciando verificación completa de todos los miembros del grupo...")
        
        # Iniciar verificación en un hilo separado para no bloquear
        def verification_thread():
            try:
                # Realizar la verificación
                result = perform_group_security_check(bot, target_group_id)
                
                # Actualizar mensaje de estado con el resultado
                if result:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text="✅ Verificación completada exitosamente. Todos los miembros no autorizados han sido expulsados."
                    )
                else:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text="⚠️ Hubo problemas durante la verificación. Revisa los logs para más detalles."
                    )
            except Exception as e:
                logger.error(f"Error en hilo de verificación: {e}")
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text=f"❌ Error durante la verificación: {str(e)}"
                    )
                except:
                    pass
        
        # Iniciar hilo
        verify_thread = threading.Thread(target=verification_thread)
        verify_thread.daemon = True
        verify_thread.start()
        
    except Exception as e:
        logger.error(f"Error general en handle_verify_all_members: {e}")
        bot.reply_to(message, f"❌ Error al iniciar verificación: {str(e)}")


# 3. FUNCIÓN DE VERIFICACIÓN DE PERMISOS DEL BOT
# Añade esta función al archivo app.py, justo antes de set_webhook()

def verify_bot_permissions(bot):
    """Verifica que el bot tenga los permisos correctos en el grupo VIP"""
    try:
        from config import GROUP_CHAT_ID, ADMIN_IDS, BOT_TOKEN
        import requests
        import json
        
        if not GROUP_CHAT_ID:
            logger.warning("GROUP_CHAT_ID no está configurado, omitiendo verificación de permisos")
            return False
        
        # Usar la API directamente para evitar circularidad de importaciones
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        params = {
            "chat_id": GROUP_CHAT_ID,
            "user_id": bot.get_me().id
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if not data.get("ok"):
            logger.error(f"Error al verificar permisos del bot: {data.get('description')}")
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": f"⚠️ ALERTA: El bot no puede acceder al grupo VIP (ID: {GROUP_CHAT_ID}).\n\nPor favor, añada el bot al grupo y asígnele permisos de administrador."
                    }
                )
            return False
        
        chat_member = data.get("result", {})
        status = chat_member.get("status")
        
        if status not in ["administrator", "creator"]:
            logger.error(f"El bot no es administrador en el grupo VIP. Status: {status}")
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": f"⚠️ ALERTA: El bot no es administrador en el grupo VIP (ID: {GROUP_CHAT_ID}).\n\nPara poder generar enlaces de invitación únicos y expulsar usuarios no autorizados, el bot debe ser administrador del grupo."
                    }
                )
            return False
        
        # Verificar permisos específicos
        can_restrict = chat_member.get("can_restrict_members", False)
        can_invite = chat_member.get("can_invite_users", False)
        
        # Lista de mensajes de error para permisos faltantes
        permission_errors = []
        
        if not can_restrict:
            permission_errors.append("❌ NO tiene permiso para EXPULSAR USUARIOS")
        
        if not can_invite:
            permission_errors.append("❌ NO tiene permiso para INVITAR USUARIOS")
        
        if permission_errors:
            error_msg = f"⚠️ ALERTA: El bot es administrador pero le faltan permisos esenciales en el grupo VIP:\n\n" + "\n".join(permission_errors) + "\n\nPor favor, edite los permisos del bot y active estos permisos para que funcione correctamente."
            
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": error_msg
                    }
                )
            return False
        
        # Si llegamos aquí, todos los permisos están correctos
        logger.info(f"✅ Permisos del bot verificados correctamente: {status}, can_restrict_members: {can_restrict}, can_invite_users: {can_invite}")
        return True
        
    except Exception as e:
        logger.error(f"Error al verificar permisos del bot: {e}")
        return False

def handle_new_chat_members(message, bot):
    """Maneja cuando nuevos miembros se unen al grupo"""
    try:
        from config import GROUP_CHAT_ID
        
        logger.info(f"Procesando nuevos miembros en el chat {message.chat.id}")
        
        # Verificar que sea el grupo VIP
        if str(message.chat.id) != str(GROUP_CHAT_ID):
            logger.info(f"Chat {message.chat.id} no es el grupo VIP ({GROUP_CHAT_ID}), ignorando")
            return
            
        # Obtener los nuevos miembros
        for new_member in message.new_chat_members:
            # Omitir si es el propio bot
            if new_member.id == bot.get_me().id:
                logger.info("El bot se unió al grupo, ignorando")
                continue
                
            # Verificar si el usuario tiene suscripción activa
            user_id = new_member.id
            username = new_member.username or f"User{user_id}"
            
            # Omitir administradores
            if user_id in ADMIN_IDS:
                logger.info(f"Administrador {username} (ID: {user_id}) se unió al grupo")
                continue
                
            subscription = db.get_active_subscription(user_id)
            
            if not subscription:
                # No tiene suscripción activa, expulsar
                logger.warning(f"⚠️ USUARIO SIN SUSCRIPCIÓN DETECTADO: {user_id} (@{username})")
                
                try:
                    # Enviar mensaje al grupo
                    bot.send_message(
                        chat_id=message.chat.id,
                        text=f"🛑 SEGURIDAD: Usuario {new_member.first_name} (@{username}) no tiene suscripción activa y será expulsado automáticamente."
                    )
                    
                    # Expulsar al usuario
                    logger.info(f"Expulsando a usuario sin suscripción: {user_id}")
                    ban_result = bot.ban_chat_member(
                        chat_id=message.chat.id,
                        user_id=user_id
                    )
                    logger.info(f"Resultado de expulsión: {ban_result}")
                    
                    # Desbanear inmediatamente para permitir que vuelva a unirse si obtiene suscripción
                    unban_result = bot.unban_chat_member(
                        chat_id=message.chat.id,
                        user_id=user_id,
                        only_if_banned=True
                    )
                    logger.info(f"Resultado de desbaneo: {unban_result}")
                    
                    # Registrar la expulsión
                    db.record_expulsion(user_id, "Verificación de nuevo miembro - Sin suscripción activa")
                    
                    # Enviar mensaje privado al usuario
                    try:
                        bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Has sido expulsado del grupo VIP porque no tienes una suscripción activa.\n\nPara unirte, adquiere una suscripción en @VIPSubscriptionBot con el comando /start."
                        )
                    except Exception as e:
                        logger.error(f"No se pudo enviar mensaje privado a {user_id}: {e}")
                    
                except Exception as e:
                    logger.error(f"Error al expulsar nuevo miembro no autorizado {user_id}: {e}")
            else:
                logger.info(f"Usuario {username} (ID: {user_id}) se unió al grupo con suscripción válida")
    
    except Exception as e:
        logger.error(f"Error general en handle_new_chat_members: {str(e)}")

def handle_start(message, bot):
    """Maneja el comando /start"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        # Verificar si el usuario ya existía en la base de datos
        existing_user = db.get_user(user_id)
        is_new_user = existing_user is None
        
        # Guardar usuario en la base de datos
        db.save_user(user_id, username, first_name, last_name)
        
        # Enviar mensaje de bienvenida con botones
        welcome_text = (
            "👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\n"
            "Este es un grupo exclusivo con contenido premium y acceso limitado.\n\n"
            "Selecciona una opción 👇"
        )
        
        bot.send_message(
            chat_id=user_id,
            text=welcome_text,
            parse_mode='Markdown',
            reply_markup=create_main_menu_markup()
        )
        
        # Notificar a los administradores si es un usuario nuevo
        if is_new_user:
            user_display_name = f"{first_name or ''} {last_name or ''}".strip() or "Sin nombre"
            user_handle = f"@{username}" if username else "Sin username"
            
            admin_notification = (
                "👤 *Nuevo Usuario Registrado*\n\n"
                f"• ID: `{user_id}`\n"
                f"• Nombre: {user_display_name}\n"
                f"• Username: {user_handle}\n"
                f"• Fecha: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            
            # Enviar notificación a todos los administradores
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=admin_notification,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error al notificar al admin {admin_id} sobre nuevo usuario: {str(e)}")
        
        logger.info(f"Usuario {user_id} ({username}) ha iniciado el bot. Nuevo usuario: {is_new_user}")
    
    except Exception as e:
        logger.error(f"Error en handle_start: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error. Por favor, intenta nuevamente más tarde."
        )

def handle_main_menu_callback(call, bot):
    """Maneja los callbacks del menú principal"""
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        if call.data == "view_plans":
            # Editar mensaje para mostrar planes
            show_plans(bot, chat_id, message_id)
            
        elif call.data == "bot_credits":
            # Mostrar créditos del bot
            credits_text = (
                "🧠 *Créditos del Bot*\n\n"
                "Este bot fue desarrollado por el equipo de desarrollo VIP.\n\n"
                "© 2025 Todos los derechos reservados.\n\n"
                "Para contacto o soporte: @admin_support"
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="back_to_main"))
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=credits_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        elif call.data == "terms":
            # Mostrar términos de uso
            try:
                with open(os.path.join('static', 'terms.txt'), 'r', encoding='utf-8') as f:
                    terms_text = f.read()
            except:
                terms_text = (
                    "📜 *Términos de Uso*\n\n"
                    "1. El contenido del grupo VIP es exclusivo para suscriptores.\n"
                    "2. No se permiten reembolsos una vez activada la suscripción.\n"
                    "3. Está prohibido compartir el enlace de invitación.\n"
                    "4. No se permite redistribuir el contenido fuera del grupo.\n"
                    "5. El incumplimiento de estas normas resultará en expulsión sin reembolso.\n\n"
                    "Al suscribirte, aceptas estos términos."
                )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="back_to_main"))
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=terms_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        
        # Responder al callback para quitar el "reloj de espera" en el cliente
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error en handle_main_menu_callback: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
        except:
            pass

def show_plans(bot, chat_id, message_id=None):
    """
    Muestra los planes de suscripción disponibles de forma dinámica
    """
    try:
        # Generar texto de planes dinámicamente
        plans_text = generate_plans_text()
        
        # Generar markup dinámicamente
        markup = create_plans_markup()
        
        if message_id:
            # Editar mensaje existente
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plans_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            # Enviar nuevo mensaje
            bot.send_message(
                chat_id=chat_id,
                text=plans_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        
        logger.info(f"Se mostraron planes al usuario {chat_id}")
        
    except Exception as e:
        logger.error(f"Error en show_plans: {str(e)}")
        try:
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ Ocurrió un error al mostrar los planes. Por favor, intenta nuevamente con /start."
                )
            else:
                bot.send_message(
                    chat_id=chat_id,
                    text="❌ Ocurrió un error al mostrar los planes. Por favor, intenta nuevamente con /start."
                )
        except:
            pass

def show_plan_details(bot, chat_id, message_id, plan_id):
    """
    Muestra los detalles de un plan específico de forma dinámica
    basado en la configuración
    """
    try:
        plan = PLANS.get(plan_id)
        if not plan:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Plan no encontrado. Por favor, intenta nuevamente."
            )
            return
        
        # Generar texto de beneficios
        benefits_text = ""
        for benefit in plan.get('benefits', ['Acceso al grupo VIP']):
            benefits_text += f"✅ {benefit}\n"
        
        # Obtener tipo de facturación según duración
        if plan['duration_days'] >= 30:
            billing_type = "mensual"
        elif plan['duration_days'] >= 7:
            billing_type = "semanal"
        else:
            billing_type = "diaria"
        
        # Construir mensaje con detalles del plan
        plan_text = (
            f"📦 {plan['display_name']}\n\n"
            f"{plan['description']}\n"
            f"Beneficios:\n"
            f"{benefits_text}\n"
            f"💵 Precio: ${plan['price_usd']:.2f} USD\n"
            f"📆 Facturación: {billing_type} (recurrente)\n\n"
            f"Selecciona un método de pago 👇"
        )
        
        # Crear markup con botones de pago
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🅿️ Pagar con PayPal", callback_data=f"payment_paypal_{plan_id}"),
            types.InlineKeyboardButton("🔙 Atrás", callback_data="view_plans")
        )
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plan_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        logger.info(f"Usuario {chat_id} está viendo detalles del plan {plan_id}")
        
    except Exception as e:
        logger.error(f"Error en show_plan_details: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Ocurrió un error al mostrar los detalles del plan. Por favor, intenta nuevamente."
            )
        except:
            pass

def show_payment_tutorial(bot, chat_id, message_id):
    """Muestra el tutorial de pagos"""
    try:
        tutorial_text = (
            "🎥 *Tutorial de Pagos*\n\n"
            "Para suscribirte a nuestro grupo VIP, sigue estos pasos:\n\n"
            "1️⃣ Selecciona el plan que deseas (Semanal o Mensual)\n\n"
            "2️⃣ Haz clic en 'Pagar con PayPal'\n\n"
            "3️⃣ Serás redirigido a la página de PayPal donde puedes pagar con:\n"
            "   - Cuenta de PayPal\n"
            "   - Tarjeta de crédito/débito (sin necesidad de cuenta)\n\n"
            "4️⃣ Completa el pago y regresa a Telegram\n\n"
            "5️⃣ Recibirás un enlace de invitación al grupo VIP\n\n"
            "⚠️ Importante: Tu suscripción se renovará automáticamente. Puedes cancelarla en cualquier momento desde tu cuenta de PayPal."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Volver a los Planes", callback_data="view_plans"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=tutorial_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        logger.info(f"Usuario {chat_id} está viendo el tutorial de pagos")
        
    except Exception as e:
        logger.error(f"Error en show_payment_tutorial: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Ocurrió un error al mostrar el tutorial. Por favor, intenta nuevamente."
            )
        except:
            pass

def handle_plans_callback(call, bot):
    """
    Maneja los callbacks relacionados con la selección de planes de forma dinámica
    """
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        if call.data == "tutorial":
            # Mostrar tutorial de pagos
            show_payment_tutorial(bot, chat_id, message_id)
            
        elif call.data.endswith("_plan"):
            # Extraer el ID del plan desde el callback_data
            plan_id = get_plan_from_callback(call.data)
            if plan_id and plan_id in PLANS:
                # Mostrar detalles del plan
                show_plan_details(bot, chat_id, message_id, plan_id)
            else:
                bot.answer_callback_query(call.id, "Plan no disponible")
                # Volver a mostrar todos los planes
                show_plans(bot, chat_id, message_id)
            
        elif call.data == "view_plans":
            # Volver a la vista de planes
            show_plans(bot, chat_id, message_id)
            
        elif call.data == "back_to_main":
            # Volver al menú principal
            welcome_text = (
                "👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\n"
                "Este es un grupo exclusivo con contenido premium y acceso limitado.\n\n"
                "Selecciona una opción 👇"
            )
            
            # Usar create_main_menu_markup() que debe existir en el código original
            from bot_handlers import create_main_menu_markup
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=welcome_text,
                parse_mode='Markdown',
                reply_markup=create_main_menu_markup()
            )
        
        # Responder al callback para quitar el "reloj de espera" en el cliente
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error en handle_plans_callback: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
        except:
            pass

def handle_payment_method(call, bot):
    """Maneja la selección del método de pago"""
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        user_id = call.from_user.id
        
        # Extraer el método de pago y plan del callback data
        _, method, plan_id = call.data.split('_')
        
        # Verificar que el plan existe en la configuración
        from config import PLANS
        if plan_id not in PLANS:
            bot.answer_callback_query(call.id, "Plan no disponible actualmente")
            logger.error(f"Usuario {user_id} solicitó plan inexistente: {plan_id}")
            
            # Volver a mostrar planes disponibles
            show_plans(bot, chat_id, message_id)
            return
        
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
                args=(bot, chat_id, processing_message.message_id)
            )
            animation_thread.daemon = True
            animation_thread.start()
            
            # Crear enlace de suscripción de PayPal
            subscription_url = pay.create_subscription_link(plan_id, user_id)
            
            # Detener la animación
            if chat_id in payment_animations:
                payment_animations[chat_id]['active'] = False
            
            if subscription_url:
                # Crear markup con botón para pagar
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("💳 Ir a pagar", url=subscription_url),
                    types.InlineKeyboardButton("🔙 Cancelar", callback_data="view_plans")
                )
                
                # Crear descripción del plan dinámicamente
                plan = PLANS[plan_id]
                
                # Determinar periodo de facturación basado en duración
                if plan['duration_days'] <= 7:
                    period = 'semana'
                elif plan['duration_days'] <= 30:
                    period = 'mes'
                elif plan['duration_days'] <= 90:
                    period = '3 meses'
                elif plan['duration_days'] <= 180:
                    period = '6 meses'
                else:
                    period = 'año'
                
                # Actualizar mensaje con el enlace de pago
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=(
                        "🔗 *Tu enlace de pago está listo*\n\n"
                        f"Plan: {plan['display_name']}\n"
                        f"Precio: ${plan['price_usd']:.2f} USD / "
                        f"{period}\n\n"
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
        
def handle_recover_access(message, bot):
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
        
        # Independientemente de si tiene un enlace activo o no, generar uno nuevo
        # Esto asegura que siempre tenga un enlace válido, incluso si el anterior expiró
        
        # Enviar mensaje informativo mientras se genera el enlace
        status_message = bot.send_message(
            chat_id=chat_id,
            text="🔄 Generando nuevo enlace de invitación... Por favor, espera un momento."
        )
        
        # Generar un nuevo enlace
        invite_link = generate_invite_link(bot, user_id, subscription['sub_id'])
        
        if invite_link:
            # Enlace generado correctamente
            new_link_text = (
                "🎟️ *Nuevo Acceso VIP Generado*\n\n"
                "Hemos creado un nuevo enlace de invitación para ti:\n"
                f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
                f"⚠️ Este enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o después de un solo uso."
            )
            
            # Actualizar el mensaje de estado con el nuevo enlace
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
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
            
            # Actualizar el mensaje de estado con el error
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
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
def handle_whitelist_duration(message, bot):
    """Procesa la duración para la whitelist"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Depuración - registra si el admin tiene estado pendiente
        logger.info(f"Manejando duración para admin {admin_id}. Estado: {admin_id in admin_states}")
        if admin_id in admin_states:
            logger.info(f"Detalles del estado: {admin_states[admin_id]}")
        
        # Verificar que el admin tenga un estado pendiente
        if admin_id not in admin_states or admin_states[admin_id]['action'] != 'whitelist':
            bot.send_message(
                chat_id=chat_id,
                text="❌ No hay una solicitud de whitelist pendiente. Usa /whitelist USER_ID para comenzar."
            )
            return
        
        # Extraer la duración del mensaje
        duration_text = message.text.strip().lower()
        logger.info(f"Texto de duración recibido: '{duration_text}'")
        
        # Verificar si es un comando para cancelar
        if duration_text in ['cancelar', 'cancel', '/cancel', 'stop']:
            # Editar mensaje original
            try:
                original_message_id = admin_states[admin_id]['message_id']
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text="🚫 *Operación de whitelist cancelada.*\n\nLa operación ha sido cancelada por el administrador.",
                    parse_mode='Markdown',
                    reply_markup=None
                )
            except Exception as edit_error:
                logger.error(f"Error al editar mensaje: {str(edit_error)}")
                # Si falla la edición, enviar un nuevo mensaje
                bot.send_message(
                    chat_id=chat_id,
                    text="🚫 *Operación de whitelist cancelada.*",
                    parse_mode='Markdown'
                )
                
            # Limpiar estado
            del admin_states[admin_id]
            return
        
        # Calcular fechas
        start_date = datetime.datetime.now()
        
        # Ajustar parseo de duración para ser más preciso
        days = parse_duration(duration_text)
        
        # Añadir registro de depuración
        logger.info(f"""
        Whitelist añadida:
        - Duración solicitada: {duration_text}
        - Días calculados: {days}
        - Hora de inicio: {start_date}
        """)
        
        if not days or days <= 0:
            bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ *Formato de duración no reconocido.*\n\n"
                    "Por favor, utiliza alguno de estos formatos:\n"
                    "• `10 minutes` (minutos)\n"
                    "• `5 hours` (horas)\n"
                    "• `2 days` (días)\n"
                    "• `1 week` (semanas)\n"
                    "• `1 month` (meses)\n\n"
                    "O escribe `cancelar` para abortar la operación."
                ),
                parse_mode='Markdown'
            )
            return
        
        # Calcular fecha de fin con mayor precisión
        end_date = start_date + datetime.timedelta(days=days)
        
        # Información adicional de depuración
        logger.info(f"""
        Detalles de whitelist:
        - Hora de fin: {end_date}
        - Diferencia de tiempo: {end_date - start_date}
        """)
        
        # Obtener información del estado
        target_user_id = admin_states[admin_id]['target_user_id']
        
        # Determinar el plan más cercano
        plan_id = 'weekly' if days <= 7 else 'monthly'
        
        # Formatear el texto de duración para mostrar
        if days < 1:  # Menos de un día
            hours = int(days * 24)
            minutes = int((days * 24 * 60) % 60)
            if hours > 0:
                duration_display = f"{hours} hora{'s' if hours != 1 else ''}"
                if minutes > 0:
                    duration_display += f" y {minutes} minuto{'s' if minutes != 1 else ''}"
            else:
                duration_display = f"{minutes} minuto{'s' if minutes != 1 else ''}"
        elif days < 7:  # Menos de una semana
            duration_display = f"{int(days)} día{'s' if int(days) != 1 else ''}"
        elif days < 30:  # Menos de un mes
            weeks = int(days) // 7
            remaining_days = int(days) % 7
            duration_display = f"{weeks} semana{'s' if weeks != 1 else ''}"
            if remaining_days > 0:
                duration_display += f" y {remaining_days} día{'s' if remaining_days != 1 else ''}"
        elif days < 365:  # Menos de un año
            months = int(days) // 30
            remaining_days = int(days) % 30
            duration_display = f"{months} mes{'es' if months != 1 else ''}"
            if remaining_days > 0:
                duration_display += f" y {remaining_days} día{'s' if remaining_days != 1 else ''}"
        else:  # Años
            years = int(days) // 365
            remaining_days = int(days) % 365
            duration_display = f"{years} año{'s' if years != 1 else ''}"
            if remaining_days > 30:
                months = remaining_days // 30
                duration_display += f" y {months} mes{'es' if months != 1 else ''}"
        
        # Enviar mensaje de estado
        try:
            bot.send_message(
                chat_id=chat_id,
                text="🔄 *Procesando solicitud...*\nPor favor espere mientras se configura el acceso y se genera el enlace de invitación.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error al enviar mensaje de estado: {str(e)}")
        
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
        
        # Generar enlace de invitación único
        invite_link = generate_invite_link(bot, target_user_id, sub_id)
        
        # Obtener información del usuario para mensaje personalizado
        user = db.get_user(target_user_id)
        username_display = user.get('username', 'Sin username') if user else 'Sin username'
        first_name = user.get('first_name', '') if user else ''
        last_name = user.get('last_name', '') if user else ''
        full_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        # Preparar mensaje de confirmación
        confirmation_text = (
            "✅ *Usuario agregado a la whitelist exitosamente*\n\n"
            f"👤 *Usuario:* {full_name}\n"
            f"🔤 *Username:* @{username_display}\n"
            f"🆔 *ID:* `{target_user_id}`\n\n"
            f"⏱️ *Duración:* {duration_display}\n"
            f"📅 *Fecha de inicio:* {start_date.strftime('%d/%m/%Y %H:%M')}\n"
            f"🗓️ *Fecha de expiración:* {end_date.strftime('%d/%m/%Y %H:%M')}\n"
        )
        
        if invite_link:
            confirmation_text += f"\n🔗 *Enlace de invitación:* [Enlace Único]({invite_link})\n⚠️ Este enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso."
        else:
            confirmation_text += "\n⚠️ *Advertencia:* No se pudo generar enlace de invitación. El usuario puede usar /recover para solicitar uno."
        
        # Enviar mensaje de confirmación
        bot.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Notificar al usuario
        try:
            # Saludo personalizado
            greeting = f"Hola {first_name}" if first_name else "Hola"
            
            user_notification = (
                f"🎟️ *¡{greeting}! Has sido agregado al grupo VIP*\n\n"
                f"Un administrador te ha concedido acceso por {duration_display}.\n\n"
            )
            
            if invite_link:
                user_notification += (
                    f"Aquí tienes tu enlace de invitación único:\n"
                    f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
                    f"⚠️ Este enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso.\n"
                    "Si sales del grupo por accidente, usa el comando /recover para solicitar un nuevo enlace."
                )
            else:
                user_notification += "Usa el comando /recover para solicitar tu enlace de invitación."
            
            bot.send_message(
                chat_id=target_user_id,
                text=user_notification,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            # Mensaje adicional de éxito para el admin
            bot.send_message(
                chat_id=chat_id,
                text=f"✅ *Notificación enviada*\nSe ha notificado al usuario {full_name} sobre su acceso VIP.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error al notificar al usuario {target_user_id}: {str(e)}")
            
            # Informar al admin que no se pudo notificar
            bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ *Advertencia*\nNo se pudo notificar al usuario. Es posible que no haya iniciado el bot.",
                parse_mode='Markdown'
            )
        
        # Limpiar el estado
        del admin_states[admin_id]
        
        logger.info(f"Admin {admin_id} agregó a usuario {target_user_id} a la whitelist por {duration_display}")
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist_duration: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ *Error en el proceso*\nOcurrió un error al procesar la duración. Por favor, intenta nuevamente con /whitelist.",
            parse_mode='Markdown'
        )

def handle_whitelist_duration(message, bot):
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
        
        # Verificar si es un comando para cancelar
        if duration_text in ['cancelar', 'cancel', '/cancel', 'stop']:
            # Editar mensaje original
            try:
                original_message_id = admin_states[admin_id]['message_id']
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=original_message_id,
                    text="🚫 *Operación de whitelist cancelada.*\n\nLa operación ha sido cancelada por el administrador.",
                    parse_mode='Markdown',
                    reply_markup=None
                )
            except Exception as edit_error:
                logger.error(f"Error al editar mensaje: {str(edit_error)}")
                # Si falla la edición, enviar un nuevo mensaje
                bot.send_message(
                    chat_id=chat_id,
                    text="🚫 *Operación de whitelist cancelada.*",
                    parse_mode='Markdown'
                )
                
            # Limpiar estado
            del admin_states[admin_id]
            return
        
        # Parsear la duración con la función mejorada
        days = parse_duration(duration_text)
        
        if not days or days <= 0:
            bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ *Formato de duración no reconocido.*\n\n"
                    "Por favor, utiliza alguno de estos formatos:\n"
                    "• `X minutes` (minutos)\n"
                    "• `X hours` (horas)\n"
                    "• `X days` (días)\n"
                    "• `X weeks` (semanas)\n"
                    "• `X months` (meses)\n\n"
                    "O escribe `cancelar` para abortar la operación."
                ),
                parse_mode='Markdown'
            )
            # Volver a solicitar la duración - aquí modificamos para no registrar un nuevo handler
            # en su lugar, confiamos en el estado guardado del admin
            return
        
        # Obtener información del estado
        target_user_id = admin_states[admin_id]['target_user_id']
        
        # Calcular fechas
        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=days)
        
        # Determinar el plan más cercano
        plan_id = 'weekly' if days <= 7 else 'monthly'
        
        # Formatear el texto de duración para mostrar
        if days < 1:  # Menos de un día
            hours = int(days * 24)
            minutes = int((days * 24 * 60) % 60)
            if hours > 0:
                duration_display = f"{hours} hora{'s' if hours != 1 else ''}"
                if minutes > 0:
                    duration_display += f" y {minutes} minuto{'s' if minutes != 1 else ''}"
            else:
                duration_display = f"{minutes} minuto{'s' if minutes != 1 else ''}"
        elif days < 7:  # Menos de una semana
            duration_display = f"{int(days)} día{'s' if int(days) != 1 else ''}"
        elif days < 30:  # Menos de un mes
            weeks = int(days) // 7
            remaining_days = int(days) % 7
            duration_display = f"{weeks} semana{'s' if weeks != 1 else ''}"
            if remaining_days > 0:
                duration_display += f" y {remaining_days} día{'s' if remaining_days != 1 else ''}"
        elif days < 365:  # Menos de un año
            months = int(days) // 30
            remaining_days = int(days) % 30
            duration_display = f"{months} mes{'es' if months != 1 else ''}"
            if remaining_days > 0:
                duration_display += f" y {remaining_days} día{'s' if remaining_days != 1 else ''}"
        else:  # Años
            years = int(days) // 365
            remaining_days = int(days) % 365
            duration_display = f"{years} año{'s' if years != 1 else ''}"
            if remaining_days > 30:
                months = remaining_days // 30
                duration_display += f" y {months} mes{'es' if months != 1 else ''}"
        
        # Enviar mensaje de estado
        try:
            bot.send_message(
                chat_id=chat_id,
                text="🔄 *Procesando solicitud...*\nPor favor espere mientras se configura el acceso y se genera el enlace de invitación.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error al enviar mensaje de estado: {str(e)}")
        
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
        
        # Generar enlace de invitación único
        invite_link = generate_invite_link(bot, target_user_id, sub_id)
        
        # Obtener información del usuario para mensaje personalizado
        user = db.get_user(target_user_id)
        username_display = user.get('username', 'Sin username') if user else 'Sin username'
        first_name = user.get('first_name', '') if user else ''
        last_name = user.get('last_name', '') if user else ''
        full_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        # Preparar mensaje de confirmación
        confirmation_text = (
            "✅ *Usuario agregado a la whitelist exitosamente*\n\n"
            f"👤 *Usuario:* {full_name}\n"
            f"🔤 *Username:* @{username_display}\n"
            f"🆔 *ID:* `{target_user_id}`\n\n"
            f"⏱️ *Duración:* {duration_display}\n"
            f"📅 *Fecha de inicio:* {start_date.strftime('%d/%m/%Y %H:%M')}\n"
            f"🗓️ *Fecha de expiración:* {end_date.strftime('%d/%m/%Y %H:%M')}\n"
        )
        
        if invite_link:
            confirmation_text += f"\n🔗 *Enlace de invitación:* [Enlace Único]({invite_link})\n⚠️ Este enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso."
        else:
            confirmation_text += "\n⚠️ *Advertencia:* No se pudo generar enlace de invitación. El usuario puede usar /recover para solicitar uno."
        
        # Enviar mensaje de confirmación
        bot.send_message(
            chat_id=chat_id,
            text=confirmation_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Notificar al usuario
        try:
            # Saludo personalizado
            greeting = f"Hola {first_name}" if first_name else "Hola"
            
            user_notification = (
                f"🎟️ *¡{greeting}! Has sido agregado al grupo VIP*\n\n"
                f"Un administrador te ha concedido acceso por {duration_display}.\n\n"
            )
            
            if invite_link:
                user_notification += (
                    f"Aquí tienes tu enlace de invitación único:\n"
                    f"🔗 [Únete al Grupo VIP]({invite_link})\n\n"
                    f"⚠️ Este enlace expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un solo uso.\n"
                    "Si sales del grupo por accidente, usa el comando /recover para solicitar un nuevo enlace."
                )
            else:
                user_notification += "Usa el comando /recover para solicitar tu enlace de invitación."
            
            bot.send_message(
                chat_id=target_user_id,
                text=user_notification,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            # Mensaje adicional de éxito para el admin
            bot.send_message(
                chat_id=chat_id,
                text=f"✅ *Notificación enviada*\nSe ha notificado al usuario {full_name} sobre su acceso VIP.",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error al notificar al usuario {target_user_id}: {str(e)}")
            
            # Informar al admin que no se pudo notificar
            bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ *Advertencia*\nNo se pudo notificar al usuario. Es posible que no haya iniciado el bot.",
                parse_mode='Markdown'
            )
        
        # Limpiar el estado
        del admin_states[admin_id]
        
        logger.info(f"Admin {admin_id} agregó a usuario {target_user_id} a la whitelist por {duration_display}")
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist_duration: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ *Error en el proceso*\nOcurrió un error al procesar la duración. Por favor, intenta nuevamente con /whitelist.",
            parse_mode='Markdown'
        )

def log_admin_state(admin_id):
    """Función de diagnóstico para registrar el estado actual de un administrador"""
    try:
        if admin_id in admin_states:
            state = admin_states[admin_id]
            logger.info(f"Estado actual del admin {admin_id}: {state}")
        else:
            logger.info(f"El admin {admin_id} no tiene un estado guardado actualmente")
    except Exception as e:
        logger.error(f"Error al registrar estado de admin: {str(e)}")

def debug_whitelist_flow(message, action="check"):
    """Función de diagnóstico para la funcionalidad de whitelist"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        if action == "check":
            log_admin_state(admin_id)
            logger.info(f"Mensaje actual: '{message.text}'")
            
        elif action == "setup":
            log_admin_state(admin_id)
            logger.info(f"Configurando estado para admin {admin_id}")
            
        elif action == "process":
            log_admin_state(admin_id)
            logger.info(f"Procesando duración: '{message.text}'")
            
            # Intentar parsear la duración para diagnóstico
            days = parse_duration(message.text)
            logger.info(f"Resultado de parse_duration: {days} días")
            
        elif action == "complete":
            logger.info(f"Completando proceso de whitelist para admin {admin_id}")
    except Exception as e:
        logger.error(f"Error en debug_whitelist_flow: {str(e)}")

def handle_subinfo(message, bot):
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
            # Mostrar instrucciones de uso
            bot.send_message(
                chat_id=chat_id,
                text="❌ Uso incorrecto. Por favor, usa /subinfo USER_ID\n\nEjemplo: /subinfo 1234567890"
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

def handle_whitelist_list(message, bot):
    """Muestra la lista de usuarios en whitelist"""
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if admin_id not in ADMIN_IDS:
            return
        
        # Obtener suscripciones activas (whitelist son todas las suscripciones manuales)
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Consulta para obtener usuarios en whitelist (donde paypal_sub_id es NULL)
        cursor.execute('''
        SELECT s.user_id, u.username, u.first_name, u.last_name, 
               s.start_date, s.end_date, s.status
        FROM subscriptions s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.paypal_sub_id IS NULL AND 
              s.status = 'ACTIVE' AND 
              s.end_date > datetime('now')
        ORDER BY s.end_date ASC
        ''')
        
        whitelist_users = cursor.fetchall()
        conn.close()
        
        if not whitelist_users:
            bot.send_message(
                chat_id=chat_id,
                text="📋 *Lista de Whitelist*\n\nNo hay usuarios en la whitelist actualmente.",
                parse_mode='Markdown'
            )
            return
        
        # Formatear la lista de usuarios
        current_time = datetime.datetime.now()
        whitelist_entries = []
        
        for user in whitelist_users:
            user_id, username, first_name, last_name, start_date_str, end_date_str, status = user
            
            # Nombre para mostrar
            display_name = f"{first_name or ''} {last_name or ''}".strip() or "Sin nombre"
            display_username = f"@{username}" if username else "Sin username"
            
            # Calcular tiempo restante
            try:
                end_date = datetime.datetime.fromisoformat(end_date_str)
                start_date = datetime.datetime.fromisoformat(start_date_str)
                remaining = end_date - current_time
                total_duration = end_date - start_date
                
                # Calcular porcentaje de tiempo transcurrido
                total_seconds = total_duration.total_seconds()
                remaining_seconds = remaining.total_seconds()
                
                # Formatear tiempo restante con más precisión
                if remaining.total_seconds() > 0:
                    if total_seconds > 3600:  # Más de una hora
                        if remaining.days > 0:
                            days_left = remaining.days
                            days_total = total_duration.days
                            status_text = f"{days_left} de {days_total} días restantes"
                        else:
                            hours_left = int(remaining.total_seconds() / 3600)
                            hours_total = int(total_seconds / 3600)
                            status_text = f"{hours_left} de {hours_total} horas restantes"
                    else:
                        # Para duraciones cortas, mostrar minutos
                        minutes_left = int(remaining.total_seconds() / 60)
                        minutes_total = int(total_seconds / 60)
                        status_text = f"{minutes_left} de {minutes_total} minutos restantes"
                else:
                    status_text = "Expirado"
                
            except Exception as e:
                logger.error(f"Error al procesar fecha {end_date_str}: {e}")
                status_text = f"Fecha: {end_date_str}"
            
            # Crear entrada para la lista
            entry = f"• {display_name} ({display_username})\n  ID: `{user_id}` - {status_text}"
            whitelist_entries.append(entry)
        
        # Enviar mensaje con la lista
        whitelist_text = "📋 *Lista de Whitelist*\n\n" + "\n\n".join(whitelist_entries)
        
        bot.send_message(
            chat_id=chat_id,
            text=whitelist_text,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist_list: {str(e)}")
        bot.send_message(
            chat_id=chat_id,
            text=f"❌ Error al obtener la lista de whitelist: {str(e)}"
        )

# Añade este nuevo handler para los botones de duración de whitelist
def handle_whitelist_callback(call, bot):
    """Maneja los callbacks relacionados con whitelist"""
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "⛔ No tienes permisos para esta acción")
            return
        
        # Procesar botón de cancelar
        if call.data == "whitelist_cancel":
            # Mostrar mensaje de cancelación
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="🚫 *Operación de whitelist cancelada.*\n\nLa operación ha sido cancelada por el administrador.",
                parse_mode='Markdown',
                reply_markup=None
            )
            
            # Limpiar estado si existe
            if user_id in admin_states:
                del admin_states[user_id]
                
            bot.answer_callback_query(call.id, "Operación cancelada")
            return
            
    except Exception as e:
        logger.error(f"Error en handle_whitelist_callback: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "❌ Error al procesar la solicitud")
        except:
            pass

def handle_unknown_message(message, bot):
    """Maneja mensajes que no coinciden con ningún comando conocido"""
    try:
        bot.send_message(
            chat_id=message.chat.id,
            text="No entiendo ese comando. Por favor, usa /start para ver las opciones disponibles."
        )
    except Exception as e:
        logger.error(f"Error en handle_unknown_message: {str(e)}")

def handle_stats_command(message, bot):
    """
    Comando para administradores que muestra estadísticas del bot
    Uso: /stats
    """
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            logger.info(f"Usuario no autorizado {user_id} intentó usar /stats")
            return
        
        # Mensaje de estado mientras se procesan las estadísticas
        status_message = bot.reply_to(
            message,
            "🔄 Recopilando estadísticas..."
        )
        
        # Obtener conexión a la base de datos
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Estadísticas principales
        stats = {
            "usuarios": db.get_table_count(conn, "users"),
            "suscripciones": db.get_table_count(conn, "subscriptions"),
            "suscripciones_activas": db.get_active_subscriptions_count(conn),
            "enlaces_invitacion": db.get_table_count(conn, "invite_links")
        }
        
        # Estadísticas adicionales
        
        # Usuarios nuevos en las últimas 24 horas
        cursor.execute("""
        SELECT COUNT(*) FROM users
        WHERE created_at > datetime('now', '-1 day')
        """)
        stats["usuarios_nuevos_24h"] = cursor.fetchone()[0]
        
        # Suscripciones nuevas en las últimas 24 horas
        cursor.execute("""
        SELECT COUNT(*) FROM subscriptions
        WHERE start_date > datetime('now', '-1 day')
        """)
        stats["suscripciones_nuevas_24h"] = cursor.fetchone()[0]
        
        # Cantidad de expulsiones
        cursor.execute("SELECT COUNT(*) FROM expulsions")
        stats["expulsiones_totales"] = cursor.fetchone()[0]
        
        # Planes más populares
        cursor.execute("""
        SELECT plan, COUNT(*) as total
        FROM subscriptions
        GROUP BY plan
        ORDER BY total DESC
        """)
        plan_stats = cursor.fetchall()
        
        # Cerrar conexión
        conn.close()
        
        # Construir mensaje de estadísticas
        stats_text = (
            "📊 *Estadísticas del Bot*\n\n"
            
            "👥 *Usuarios*\n"
            f"• Totales: {stats['usuarios']}\n"
            f"• Nuevos (24h): {stats['usuarios_nuevos_24h']}\n\n"
            
            "💳 *Suscripciones*\n"
            f"• Totales: {stats['suscripciones']}\n"
            f"• Activas: {stats['suscripciones_activas']}\n"
            f"• Nuevas (24h): {stats['suscripciones_nuevas_24h']}\n\n"
            
            "🔗 *Enlaces de Invitación*\n"
            f"• Generados: {stats['enlaces_invitacion']}\n\n"
            
            "🛡️ *Seguridad*\n"
            f"• Expulsiones: {stats['expulsiones_totales']}\n\n"
        )
        
        # Añadir estadísticas de planes
        if plan_stats:
            stats_text += "📑 *Planes*\n"
            for plan_data in plan_stats:
                plan_id = plan_data[0]
                count = plan_data[1]
                plan_name = PLANS.get(plan_id, {}).get('display_name', plan_id)
                stats_text += f"• {plan_name}: {count}\n"
            stats_text += "\n"
        
        # Añadir información del panel de administrador
        from config import WEBHOOK_URL
        stats_text += (
            "🔐 *Panel de Administración*\n"
            f"• URL: {WEBHOOK_URL}/admin/panel?admin_id={user_id}\n\n"
            
            "📅 Actualizado: " + datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        )
        
        # Enviar estadísticas
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=stats_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        logger.info(f"Admin {user_id} solicitó estadísticas del bot")
        
    except Exception as e:
        logger.error(f"Error en handle_stats_command: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ Error al obtener estadísticas: {str(e)}"
            )
        except:
            bot.reply_to(message, f"❌ Error al obtener estadísticas: {str(e)}")

def handle_test_invite(message, bot):
    """
    Comando para administradores que permite probar la generación de enlaces de invitación
    Uso: /test_invite
    """
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            logger.info(f"Usuario no autorizado {user_id} intentó usar /test_invite")
            return
        
        # Mensaje de estado mientras se procesa
        status_message = bot.reply_to(
            message,
            "🔄 Generando enlace de invitación de prueba..."
        )
        
        # Verificar permisos del bot en el grupo
        from config import GROUP_CHAT_ID
        if not GROUP_CHAT_ID:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="❌ Error: GROUP_CHAT_ID no está configurado. No se puede generar enlace."
            )
            return
        
        # Verificar que el bot tenga los permisos necesarios
        try:
            # Obtener información del bot en el grupo
            chat_member = bot.get_chat_member(GROUP_CHAT_ID, bot.get_me().id)
            
            if chat_member.status not in ['administrator', 'creator']:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text="❌ Error: El bot no es administrador en el grupo VIP. No puede generar enlaces."
                )
                return
            
            if not chat_member.can_invite_users:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text="❌ Error: El bot no tiene permiso para invitar usuarios en el grupo VIP."
                )
                return
                
        except Exception as e:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ Error al verificar permisos: {str(e)}"
            )
            return
        
        # Intentar generar un enlace de prueba directamente
        try:
            # Calcular fecha de expiración (1 hora)
            expire_date = int((datetime.datetime.now() + datetime.timedelta(hours=1)).timestamp())
            
            # Crear enlace directo para 1 solo uso
            invite = bot.create_chat_invite_link(
                chat_id=GROUP_CHAT_ID,
                expire_date=expire_date,
                member_limit=1,
                name=f"Test invite by admin {user_id}",
                creates_join_request=False
            )
            
            # Si llegamos aquí sin errores, la generación fue exitosa
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=(
                    "✅ Enlace de invitación generado exitosamente\n\n"
                    f"🔗 {invite.invite_link}\n\n"
                    "ℹ️ Este es un enlace de prueba que expira en 1 hora y permite un solo uso.\n"
                    "📝 No se ha registrado en la base de datos."
                ),
                disable_web_page_preview=True
            )
            
            logger.info(f"Admin {user_id} generó un enlace de prueba exitosamente")
            
        except Exception as e:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=(
                    f"❌ Error al generar enlace: {str(e)}\n\n"
                    "Posibles causas:\n"
                    "• El bot no tiene permisos suficientes en el grupo\n"
                    "• El ID del grupo es incorrecto\n"
                    "• La API de Telegram está teniendo problemas"
                )
            )
            
            logger.error(f"Error al generar enlace de prueba: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error en handle_test_invite: {str(e)}")
        bot.reply_to(message, f"❌ Error inesperado: {str(e)}")

def admin_force_security_check(message, bot):
    """
    Manejador para el comando /force_security_check
    Permite a los administradores forzar una verificación de seguridad inmediata
    """
    try:
        admin_id = message.from_user.id
        chat_id = message.chat.id
        
        # Verificar que sea un administrador
        if admin_id not in ADMIN_IDS:
            return
        
        # Enviar mensaje de estado
        status_message = bot.reply_to(
            message,
            "🔄 Iniciando verificación de seguridad forzada. Por favor espere..."
        )
        
        # Forzar verificación
        result = force_security_check(bot)
        
        if result:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="✅ Verificación de seguridad completada exitosamente"
            )
        else:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="❌ La verificación de seguridad falló. Por favor, revise los logs para más detalles."
            )
        
    except Exception as e:
        logger.error(f"Error en admin_force_security_check: {e}")
        try:
            bot.reply_to(message, f"❌ Error: {str(e)}")
        except:
            pass

def register_handlers(bot):
    """Registra todos los handlers con el bot"""
    
    # Registrar comandos de administrador primero
    register_admin_commands(bot)

    # Handler para verificar permisos del bot
    bot.register_message_handler(
        lambda message: check_and_fix_bot_permissions(message, bot),
        commands=['check_bot_permissions']
    )
    
    # Handler para el comando /start
    bot.register_message_handler(lambda message: handle_start(message, bot), commands=['start'])
    
    # IMPORTANTE: El handler para verify_all debe ir ANTES que otros handlers
    bot.register_message_handler(lambda message: handle_verify_all_members(message, bot), 
                              commands=['verify_all', 'force_verify'])
    
    # Añadir nuevo comando para forzar verificación de seguridad
    bot.register_message_handler(
        lambda message: admin_force_security_check(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/force_security_check'
    )
    
    # Handler para nuevos miembros
    bot.register_message_handler(lambda message: handle_new_chat_members(message, bot), 
                              content_types=['new_chat_members'])
    
    # Handler para el comando de recuperación de acceso
    bot.register_message_handler(lambda message: handle_recover_access(message, bot), 
                              func=lambda message: message.text == '🎟️ Recuperar Acceso VIP' or 
                                                  message.text == '/recover' or
                                                  message.text.startswith('/recover'))
    
    # Callback handlers para los botones
    bot.register_callback_query_handler(lambda call: handle_main_menu_callback(call, bot), 
                                      func=lambda call: call.data in ['view_plans', 'bot_credits', 'terms'])
    
    bot.register_callback_query_handler(lambda call: handle_plans_callback(call, bot), 
                                      func=lambda call: call.data in ['tutorial', 'weekly_plan', 'monthly_plan', 'back_to_main'])
    
    bot.register_callback_query_handler(lambda call: handle_payment_method(call, bot), 
                                      func=lambda call: call.data.startswith('payment_'))
    
    # Handler por defecto para mensajes no reconocidos
    bot.register_message_handler(lambda message: handle_unknown_message(message, bot), func=lambda message: True)
    
    # Iniciar verificación periódica automática
    security_thread = schedule_security_verification(bot)
    
    # Forzar una verificación inicial completa
    force_security_check(bot)
    
    # Programar verificaciones periódicas del estado del hilo
    def check_thread_periodically():
        while True:
            time.sleep(300)  # Comprobar cada 5 minutos
            try:
                check_security_thread_status(bot)
            except Exception as e:
                logger.error(f"Error en la verificación periódica del hilo: {e}")
    
    # Iniciar hilo de supervisión
    monitor_thread = threading.Thread(target=check_thread_periodically, daemon=True)
    monitor_thread.start()