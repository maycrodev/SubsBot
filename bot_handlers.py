import logging
from telebot import types
import database as db
from config import ADMIN_IDS, PLANS, INVITE_LINK_EXPIRY_HOURS, INVITE_LINK_MEMBER_LIMIT, GROUP_INVITE_LINK
import payments as pay
import datetime
import threading
import time
import os
import re
from typing import Dict, Optional, Tuple, Any

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Diccionario para almacenar estados de administradores
admin_states = {}

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
    
    # Comando de verificación de permisos para admins
    bot.register_message_handler(
        lambda message: verify_bot_permissions() and bot.reply_to(message, "✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles."),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/check_permissions'
    )
    
    logger.info("Comandos de administrador registrados correctamente")

# Funciones de utilidad
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

def start_processing_animation(bot, chat_id, message_id):
    """Inicia una animación de procesamiento mejorada en el mensaje"""
    try:
        # Secuencia de animación con estilo de ramas
        animation_frames = [
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ 🔄◼️◼️◼️◼️◼️**\n**└ Conectando...**",
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ ✅🔄◼️◼️◼️◼️**\n**└ Verificando datos...**",
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ ✅✅🔄◼️◼️◼️**\n**└ Preparando conexión...**",
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ ✅✅✅🔄◼️◼️**\n**└ Generando enlace seguro...**",
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ ✅✅✅✅🔄◼️**\n**└ Configurando opciones...**",
            "⚡ **PROCESANDO PAGO** ⚡\n\n**├ ✅✅✅✅✅🔄**\n**└ Finalizando...**",
        ]
        
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
                    text=animation_frames[current_index],
                    parse_mode='Markdown'
                )
                
                # Actualizar índice de animación
                current_index = (current_index + 1) % len(animation_frames)
                
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
            text="🔄 **Preparando tu acceso VIP...**\n\n**├ ⚙️ Generando enlace exclusivo**\n**└ ⏳ Por favor, espera un momento...**",
            parse_mode='Markdown'
        )
        
        # Generar enlace de invitación único
        invite_link = generate_invite_link(bot, user_id, sub_id)
        
        if not invite_link:
            logger.error(f"No se pudo generar enlace de invitación para usuario {user_id}")
            
            # MENSAJE MEJORADO
            bot.edit_message_text(
                chat_id=user_id,
                message_id=provisional_message.message_id,
                text=(
                    "⚠️ **SUSCRIPCIÓN ACTIVADA** ⚠️\n\n"
                    "**✅ ESTADO**\n"
                    "**├ ✓ Pago procesado correctamente**\n"
                    "**└ ✓ Membresía registrada**\n\n"
                    "**⚡ ATENCIÓN**\n"
                    "**└ ❌ Error al generar enlace de invitación**\n\n"
                    "**🔄 SOLUCIÓN**\n"
                    "**├ 🛠️ Usa /recover para un nuevo enlace**\n"
                    "**└ 👨‍💻 O contacta con soporte @admin_support**"
                ),
                parse_mode='Markdown'
            )
            
            # Notificar a los administradores del problema
            admin_error_notification = (
                "🚨 **ERROR CON ENLACE DE INVITACIÓN**\n\n"
                f"**👤 Usuario: {user.get('username', 'Sin username')} (id{user_id})**\n"
                f"**🆔 Suscripción: {sub_id}**\n"
                f"**❌ Error: No se pudo generar enlace de invitación**\n\n"
                f"**ℹ️ Usuario notificado para usar /recover**"
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
            # MENSAJE MEJORADO
            confirmation_text = (
                "🎉 **¡ACCESO VIP ACTIVADO!** 🎉\n\n"
                "**🔑 TU INVITACIÓN EXCLUSIVA**\n"
                f"**└ 🔗 [UNIRSE AL GRUPO VIP]({invite_link})**\n\n"
                "**⚠️ IMPORTANTE**\n"
                f"**├ 👤 Enlace personal único**\n"
                f"**├ ⏳ Expira en {INVITE_LINK_EXPIRY_HOURS} horas**\n"
                f"**└ 1️⃣ Válido para un solo uso**\n\n"
                "**❓ ¿PROBLEMAS DE ACCESO?**\n"
                "**└ 🔄 Usa /recover para generar nuevo enlace**\n\n"
                "**🌟 ¡BIENVENIDO AL CLUB EXCLUSIVO!** 🌟"
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
            "🎉 **¡NUEVA SUSCRIPCIÓN! (PayPal)**\n\n"
            "**📊 DETALLES**\n"
            f"**├ 🆔 ID pago: {paypal_sub_id}**\n"
            f"**├ 👤 Usuario: {username_display} (@{username_display}) (id{user_id})**\n"
            f"**├ 📝 Nombre: {full_name}**\n"
            f"**├ 📦 Plan: {plan['display_name']}**\n"
            f"**├ 💳 Facturación: ${plan['price_usd']:.2f} / "
            f"{'1 semana' if plan_id == 'weekly' else '1 mes'}**\n"
            f"**├ 📅 Fecha: {start_date.strftime('%d %b %Y %I:%M %p')}**\n"
            f"**├ ⏱️ Expira: {end_date.strftime('%d %b %Y')}**\n"
            f"**├ ✅ Estado: ACTIVO**\n"
            f"**└ 🔗 Enlace: {'Generado correctamente' if invite_link else 'Error al generar'}**"
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
            
            # MENSAJE MEJORADO - Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⛔ **SUSCRIPCIÓN CANCELADA** ⛔\n\n"
                        "**📢 INFORMACIÓN**\n"
                        "**├ 🚫 Acceso VIP cancelado**\n"
                        "**└ 🔒 Ya no tienes acceso al grupo**\n\n"
                        "**🔄 ¿QUIERES VOLVER?**\n"
                        "**└ 📲 Usa /start para ver planes disponibles**"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar cancelación al usuario {user_id}: {str(e)}")
            
            logger.info(f"Suscripción {sub_id} cancelada")
            
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
            # Marcar la suscripción como suspendida
            db.update_subscription_status(sub_id, "SUSPENDED")
            
            # MENSAJE MEJORADO - Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ **SUSCRIPCIÓN SUSPENDIDA** ⚠️\n\n"
                        "**📢 INFORMACIÓN**\n"
                        "**├ 🔄 Estado: SUSPENDIDA**\n"
                        "**└ 🚫 Acceso al grupo VIP restringido**\n\n"
                        "**🛠️ SOLUCIÓN**\n"
                        "**└ 💳 Verifica tu método de pago en PayPal**"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error al notificar suspensión al usuario {user_id}: {str(e)}")
            
            logger.info(f"Suscripción {sub_id} suspendida")
            
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            # MENSAJE MEJORADO - Notificar al usuario sobre el pago fallido
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ **PAGO FALLIDO** ❌\n\n"
                        "**⚠️ ATENCIÓN**\n"
                        "**└ No pudimos procesar tu pago**\n\n"
                        "**⏱️ IMPORTANTE**\n"
                        "**├ Tu acceso VIP está en riesgo**\n"
                        "**└ Si no se resuelve, perderás los beneficios**\n\n"
                        "**🛠️ SOLUCIÓN**\n"
                        "**└ 💳 Actualiza tu método de pago en PayPal**"
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
            
            # MENSAJE MEJORADO - Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ **¡SUSCRIPCIÓN RENOVADA!** ✅\n\n"
                        "**🎯 DETALLES**\n"
                        f"**├ 📦 Plan: {plan['display_name']}**\n"
                        f"**├ 💰 Monto: ${plan['price_usd']:.2f} USD**\n"
                        f"**└ 📅 Nueva expiración: {new_end_date.strftime('%d %b %Y')}**\n\n"
                        "**🌟 ¡GRACIAS POR CONTINUAR CON NOSOTROS!** 🌟\n"
                        "**└ 💎 Disfruta tu contenido premium**"
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
        types.InlineKeyboardButton("💎 Ver Planes Premium", callback_data="view_plans"),
        types.InlineKeyboardButton("ℹ️ Acerca del Bot", callback_data="bot_credits"),
        types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
    )
    return markup

def create_plans_markup():
    """Crea los botones para el menú de planes"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Agregar tutorial de pagos
    markup.add(types.InlineKeyboardButton("🎬 Tutorial de Pagos", callback_data="tutorial"))
    
    # Agregar planes
    markup.add(
        types.InlineKeyboardButton("🗓️ Plan Semanal", callback_data="weekly_plan"),
        types.InlineKeyboardButton("📆 Plan Mensual", callback_data="monthly_plan")
    )
    
    # Agregar botón de volver
    markup.add(types.InlineKeyboardButton("↩️ Volver al Menú", callback_data="back_to_main"))
    
    return markup

# 1. VERIFICACIÓN PERIÓDICA AUTOMÁTICA
# Añade esta función al archivo bot_handlers.py

def schedule_security_verification(bot):
    """
    Configura una verificación de seguridad periódica para ejecutarse cada 6 horas
    """
    import threading
    import time
    from config import GROUP_CHAT_ID, ADMIN_IDS
    
    def security_check_thread():
        """Hilo que ejecuta la verificación periódica de seguridad"""
        try:
            # Ejecutar una verificación inmediata al iniciar
            logger.info("Ejecutando verificación inicial de seguridad")
            if GROUP_CHAT_ID:
                perform_group_security_check(bot, GROUP_CHAT_ID)
            else:
                logger.error("GROUP_CHAT_ID no configurado para verificación inicial")
        except Exception as e:
            logger.error(f"Error en verificación inicial: {e}")
            
        # Ciclo de verificación periódica
        while True:
            try:
                # Esperar 6 horas entre verificaciones (en segundos)
                time.sleep(21600)  # 6 horas * 60 minutos * 60 segundos
                
                logger.info("Iniciando verificación periódica de seguridad programada")
                
                # No ejecutar si no hay un grupo configurado
                if not GROUP_CHAT_ID:
                    logger.error("No hay ID de grupo configurado para la verificación de seguridad")
                    continue
                
                # Ejecutar la verificación
                perform_group_security_check(bot, GROUP_CHAT_ID)
                
            except Exception as e:
                logger.error(f"Error en el hilo de verificación periódica: {e}")
                # Si hay un error, esperamos 1 hora antes de intentar de nuevo
                time.sleep(3600)
    
    # Iniciar el hilo de verificación
    security_thread = threading.Thread(target=security_check_thread)
    security_thread.daemon = True
    security_thread.start()
    
    logger.info("Sistema de verificación periódica de seguridad iniciado")


def perform_group_security_check(bot, group_id):
    """
    Realiza una verificación completa de seguridad del grupo
    Expulsa a todos los miembros que no tienen suscripción activa
    """
    try:
        from config import ADMIN_IDS
        
        # Convertir group_id a string para comparación consistente
        group_id_str = str(group_id)
        
        logger.info(f"Iniciando verificación de seguridad del grupo {group_id_str}")
        
        # Verificar que el bot tenga permisos necesarios
        try:
            bot_member = bot.get_chat_member(group_id, bot.get_me().id)
            
            if bot_member.status not in ['administrator', 'creator']:
                logger.error(f"CRÍTICO: El bot no tiene permisos de administrador en el grupo {group_id}")
                # MENSAJE MEJORADO - Notificar a todos los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=(
                                "⚠️ **ALERTA DE SEGURIDAD CRÍTICA** ⚠️\n\n"
                                "**🚨 PROBLEMA DETECTADO**\n"
                                "**└ El bot no tiene permisos de administrador en el grupo VIP**\n\n"
                                "**⚡ ACCIÓN REQUERIDA**\n"
                                "**└ Conceder permisos de administrador al bot inmediatamente**"
                            ),
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                return False
            
            if not getattr(bot_member, 'can_restrict_members', False):
                logger.error(f"CRÍTICO: El bot no tiene permiso para expulsar usuarios en el grupo {group_id}")
                # MENSAJE MEJORADO - Notificar a todos los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=(
                                "⚠️ **ALERTA DE SEGURIDAD CRÍTICA** ⚠️\n\n"
                                "**🚨 PROBLEMA DETECTADO**\n"
                                "**└ El bot no tiene permiso para expulsar miembros**\n\n"
                                "**⚡ ACCIÓN REQUERIDA**\n"
                                "**└ Editar permisos del bot y activar 'Expulsar usuarios'**"
                            ),
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                return False
                
            logger.info(f"El bot tiene los permisos necesarios para la verificación de seguridad")
            
        except Exception as e:
            logger.error(f"Error al verificar permisos del bot: {e}")
            return False
        
        # Lista de administradores que no debemos expulsar
        admin_ids = list(ADMIN_IDS)  # Convertir a lista nueva
        
        # Añadir administradores del grupo
        try:
            admins = bot.get_chat_administrators(chat_id=group_id)
            for admin in admins:
                if admin.user.id not in admin_ids:
                    admin_ids.append(admin.user.id)
            logger.info(f"Lista de administradores: {admin_ids}")
        except Exception as e:
            logger.error(f"Error al obtener administradores del grupo: {e}")
            # Continuamos con la lista de admins que tenemos
        
        # Obtener todos los miembros visibles del grupo
        members = []
        try:
            # Obtener miembros visibles (hasta 200, límite de Telegram)
            # Utilizar get_chat_members_count primero para saber cuántos miembros hay
            members_count = bot.get_chat_members_count(chat_id=group_id)
            logger.info(f"El grupo tiene aproximadamente {members_count} miembros")
            
            # Obtener miembros en lotes de 50
            offset = 0
            while offset < min(members_count, 1000):  # Límite de 1000 para evitar bucles infinitos
                chat_members = bot.get_chat_members(chat_id=group_id, offset=offset, limit=50)
                if not chat_members:
                    break
                members.extend(chat_members)
                offset += 50
                logger.info(f"Obtenidos {len(members)} miembros hasta ahora")
            
            logger.info(f"Obtenidos {len(members)} miembros del grupo para verificación")
        except Exception as e:
            logger.error(f"Error al obtener miembros del grupo: {e}")
            # MENSAJE MEJORADO - Notificar a los administradores
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=(
                            "⚠️ **ERROR EN VERIFICACIÓN** ⚠️\n\n"
                            "**🚨 PROBLEMA DETECTADO**\n"
                            "**└ No se pudieron obtener los miembros del grupo**\n\n"
                            f"**❌ ERROR: {str(e)}**"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass
            return False
        
        # Identificar miembros no autorizados
        unauthorized_members = []
        authorized_count = 0
        admin_count = 0
        bot_count = 0
        
        for member in members:
            member_id = member.user.id
            username = member.user.username or f"User{member_id}"
            
            # Omitir bots
            if member.user.is_bot:
                bot_count += 1
                logger.debug(f"Omitiendo bot: {username}")
                continue
                
            # Omitir administradores
            if member_id in admin_ids:
                admin_count += 1
                logger.debug(f"Omitiendo administrador: {username}")
                continue
            
            # Verificar si tiene suscripción activa
            subscription = db.get_active_subscription(member_id)
            if not subscription:
                logger.warning(f"⚠️ MIEMBRO NO AUTORIZADO: {member_id} (@{username})")
                unauthorized_members.append((member_id, username, member.user))
            else:
                authorized_count += 1
                logger.debug(f"Miembro autorizado: {username}")
        
        # Log resumen antes de empezar expulsiones
        logger.info(f"Resumen de verificación: {len(unauthorized_members)} no autorizados, {authorized_count} autorizados, {admin_count} administradores, {bot_count} bots")
        
        # MENSAJE MEJORADO - Mostrar lista de usuarios no autorizados a los administradores
        if unauthorized_members:
            # Crear lista formateada de usuarios no autorizados
            unauthorized_list = "\n".join([f"**├ 👤 @{user[1]} (ID: {user[0]})**" for user in unauthorized_members[:20]])
            if len(unauthorized_members) > 20:
                unauthorized_list += f"\n**└ ... y {len(unauthorized_members) - 20} más**"
            else:
                unauthorized_list = unauthorized_list.rsplit('\n', 1)[0] + "\n**└" + unauthorized_list.rsplit('\n', 1)[1][2:]
                
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=(
                            "⚠️ **VERIFICACIÓN DE SEGURIDAD** ⚠️\n\n"
                            f"**🚫 Se encontraron {len(unauthorized_members)} usuarios sin suscripción:**\n\n"
                            f"{unauthorized_list}\n\n"
                            "**⚙️ ACCIÓN**\n"
                            "**└ Se procederá con la expulsión automática**"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
            
            # MENSAJE MEJORADO - Enviar mensaje al grupo sobre la verificación
            try:
                bot.send_message(
                    chat_id=group_id,
                    text=(
                        "🛡️ **VERIFICACIÓN DE SEGURIDAD** 🛡️\n\n"
                        f"**⚙️ Sistema detectó {len(unauthorized_members)} usuarios sin suscripción activa**\n\n"
                        "**🚫 Usuarios no autorizados serán expulsados automáticamente**\n"
                        "**🔐 Mantener la exclusividad del grupo es nuestra prioridad**"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"No se pudo enviar mensaje al grupo: {e}")
        
        # Expulsar a los miembros no autorizados
        expulsion_count = 0
        expulsion_errors = 0
        
        for member_id, username, user_obj in unauthorized_members:
            try:
                # Información del usuario para los logs
                first_name = getattr(user_obj, 'first_name', '') or ''
                last_name = getattr(user_obj, 'last_name', '') or ''
                full_name = f"{first_name} {last_name}".strip() or "Usuario"
                
                logger.info(f"Expulsando a usuario no autorizado: {member_id} (@{username})")
                
                # Expulsar al usuario
                ban_result = bot.ban_chat_member(
                    chat_id=group_id,
                    user_id=member_id
                )
                
                # Desbanear inmediatamente para permitir que vuelva a unirse si obtiene suscripción
                unban_result = bot.unban_chat_member(
                    chat_id=group_id,
                    user_id=member_id,
                    only_if_banned=True
                )
                
                # Registrar la expulsión en la base de datos
                db.record_expulsion(member_id, "Verificación de seguridad - Sin suscripción activa")
                
                # MENSAJE MEJORADO - Enviar mensaje privado al usuario
                try:
                    bot.send_message(
                        chat_id=member_id,
                        text=(
                            "⛔ **ACCESO VIP REVOCADO** ⛔\n\n"
                            "**🚫 Has sido expulsado del grupo VIP**\n"
                            "**└ Motivo: No tienes una suscripción activa**\n\n"
                            "**💎 RECUPERAR ACCESO**\n"
                            "**└ 🔑 Adquiere una suscripción en @VIPSubscriptionBot**\n\n"
                            "**🚀 Usa /start para ver nuestros planes**"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"No se pudo enviar mensaje privado a {member_id}: {e}")
                
                expulsion_count += 1
                
            except Exception as e:
                logger.error(f"ERROR al expulsar a usuario no autorizado {member_id}: {e}")
                expulsion_errors += 1
        
        # Resumen final
        logger.info(f"Verificación de seguridad completada: {expulsion_count} miembros expulsados, {expulsion_errors} errores")
        
        # MENSAJE MEJORADO - Notificar resultados a administradores
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "✅ **VERIFICACIÓN COMPLETADA** ✅\n\n"
                        "**📊 RESULTADOS**\n"
                        f"**├ 🚫 {expulsion_count} usuarios expulsados**\n"
                        f"**├ ❌ {expulsion_errors} errores de expulsión**\n"
                        f"**└ ✅ {authorized_count} usuarios con suscripción válida**"
                    ),
                    parse_mode='Markdown'
                )
            except:
                pass
        
        # MENSAJE MEJORADO - Notificar al grupo sobre la finalización
        if expulsion_count > 0:
            try:
                bot.send_message(
                    chat_id=group_id,
                    text=(
                        "✅ **VERIFICACIÓN COMPLETADA** ✅\n\n"
                        f"**🛡️ {expulsion_count} usuarios sin suscripción han sido expulsados**\n"
                        "**🔐 Gracias por mantener la exclusividad del grupo**"
                    ),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"No se pudo enviar mensaje final al grupo: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error en verificación de seguridad: {e}")
        # MENSAJE MEJORADO - Notificar a los administradores
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "❌ **ERROR DE SEGURIDAD** ❌\n\n"
                        "**⚠️ La verificación de seguridad falló**\n"
                        f"**└ Error: {str(e)}**"
                    ),
                    parse_mode='Markdown'
                )
            except:
                pass
        return False

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
        
        # MENSAJE MEJORADO - Mensaje inicial
        status_message = bot.reply_to(
            message,
            "🔄 **VERIFICACIÓN INICIADA** 🔄\n\n"
            "**⚙️ PROCESO AUTOMÁTICO**\n"
            "**├ 🔍 Escaneando miembros**\n"
            "**├ 🔐 Verificando suscripciones**\n"
            "**└ ⏳ Por favor espera...**",
            parse_mode='Markdown'
        )
        
        # Iniciar verificación en un hilo separado para no bloquear
        def verification_thread():
            try:
                # Realizar la verificación
                result = perform_group_security_check(bot, target_group_id)
                
                # MENSAJE MEJORADO - Actualizar mensaje de estado con el resultado
                if result:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text=(
                            "✅ **VERIFICACIÓN EXITOSA** ✅\n\n"
                            "**🛡️ SEGURIDAD ACTUALIZADA**\n"
                            "**└ Miembros no autorizados expulsados**\n\n"
                            "**📊 Ver detalles en mensajes privados**"
                        ),
                        parse_mode='Markdown'
                    )
                else:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text=(
                            "⚠️ **VERIFICACIÓN INCOMPLETA** ⚠️\n\n"
                            "**❌ PROBLEMAS DETECTADOS**\n"
                            "**└ Consulta los logs para más detalles**"
                        ),
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error en hilo de verificación: {e}")
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message.message_id,
                        text=(
                            "❌ **ERROR EN VERIFICACIÓN** ❌\n\n"
                            f"**⚠️ {str(e)}**"
                        ),
                        parse_mode='Markdown'
                    )
                except:
                    pass
        
        # Iniciar hilo
        verify_thread = threading.Thread(target=verification_thread)
        verify_thread.daemon = True
        verify_thread.start()
        
    except Exception as e:
        logger.error(f"Error general en handle_verify_all_members: {e}")
        bot.reply_to(
            message, 
            f"❌ **ERROR AL INICIAR VERIFICACIÓN**\n\n**└ {str(e)}**", 
            parse_mode='Markdown'
        )


# 3. FUNCIÓN DE VERIFICACIÓN DE PERMISOS DEL BOT
# Añade esta función al archivo app.py, justo antes de set_webhook()

def verify_bot_permissions():
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
                # MENSAJE MEJORADO
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": (
                            "⚠️ **ALERTA DE SEGURIDAD** ⚠️\n\n"
                            f"**❌ El bot no puede acceder al grupo VIP (ID: {GROUP_CHAT_ID})**\n\n"
                            "**⚡ ACCIÓN REQUERIDA**\n"
                            "**├ Añadir el bot al grupo**\n"
                            "**└ Asignarle permisos de administrador**"
                        ),
                        "parse_mode": "Markdown"
                    }
                )
            return False
        
        chat_member = data.get("result", {})
        status = chat_member.get("status")
        
        if status not in ["administrator", "creator"]:
            logger.error(f"El bot no es administrador en el grupo VIP. Status: {status}")
            for admin_id in ADMIN_IDS:
                # MENSAJE MEJORADO
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": (
                            "⚠️ **ALERTA DE SEGURIDAD** ⚠️\n\n"
                            f"**❌ El bot no es administrador en el grupo VIP (ID: {GROUP_CHAT_ID})**\n\n"
                            "**⚡ FUNCIONES AFECTADAS**\n"
                            "**├ Generación de enlaces únicos**\n"
                            "**└ Expulsión de usuarios no autorizados**\n\n"
                            "**🛠️ SOLUCIÓN**\n"
                            "**└ Asignar permisos de administrador al bot**"
                        ),
                        "parse_mode": "Markdown"
                    }
                )
            return False
        
        # Verificar permisos específicos
        can_restrict = chat_member.get("can_restrict_members", False)
        can_invite = chat_member.get("can_invite_users", False)
        
        # Lista de mensajes de error para permisos faltantes
        permission_errors = []
        
        if not can_restrict:
            permission_errors.append("**❌ NO tiene permiso para EXPULSAR USUARIOS**")
        
        if not can_invite:
            permission_errors.append("**❌ NO tiene permiso para INVITAR USUARIOS**")
        
        if permission_errors:
            # MENSAJE MEJORADO
            error_msg = (
                "⚠️ **ALERTA DE PERMISOS** ⚠️\n\n"
                "**🛑 PERMISOS FALTANTES**\n" + 
                "\n".join(permission_errors) + 
                "\n\n**⚡ ACCIÓN REQUERIDA**\n"
                "**└ Editar permisos del bot en el grupo VIP**"
            )
            
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": error_msg,
                        "parse_mode": "Markdown"
                    }
                )
            return False
        
        # Si llegamos aquí, todos los permisos están correctos
        logger.info(f"✅ Permisos del bot verificados correctamente: {status}, can_restrict_members: {can_restrict}, can_invite_users: {can_invite}")
        return True
        
    except Exception as e:
        logger.error(f"Error al verificar permisos del bot: {e}")
        return False# Modificación de la función de animación en bot_handlers.py

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
                    # MENSAJE MEJORADO - Enviar mensaje al grupo
                    bot.send_message(
                        chat_id=message.chat.id,
                        text=f"🛑 **ACCESO DENEGADO**\n\n**└ Usuario {new_member.first_name} (@{username}) no tiene suscripción activa**\n\n**⚙️ Sistema de seguridad activado**",
                        parse_mode='Markdown'
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
                    
                    # MENSAJE MEJORADO - Enviar mensaje privado al usuario
                    try:
                        bot.send_message(
                            chat_id=user_id,
                            text=(
                                "⛔ **ACCESO DENEGADO** ⛔\n\n"
                                "**📛 MOTIVO**\n"
                                "**└ No tienes una suscripción activa**\n\n"
                                "**💎 SOLUCIÓN**\n"
                                "**├ 🔑 Adquiere acceso VIP**\n"
                                "**└ 🚀 Usa /start para ver planes**"
                            ),
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"No se pudo enviar mensaje privado a {user_id}: {e}")
                    
                except Exception as e:
                    logger.error(f"Error al expulsar nuevo miembro no autorizado {user_id}: {e}")
            else:
                # MENSAJE MEJORADO - Bienvenida a usuario con suscripción válida
                try:
                    bot.send_message(
                        chat_id=message.chat.id,
                        text=(
                            f"🎉 **¡BIENVENIDO/A {new_member.first_name}!** 🎉\n\n"
                            "**💎 Miembro VIP verificado**\n"
                            "**└ ✅ Suscripción activa confirmada**\n\n"
                            "**🔥 ¡Disfruta del contenido exclusivo!**"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error al enviar mensaje de bienvenida: {e}")
                
                logger.info(f"Usuario {username} (ID: {user_id}) se unió al grupo con suscripción válida")
    
    except Exception as e:
        logger.error(f"Error general en handle_new_chat_members: {str(e)}")

# 4. MEJORA EN LA FUNCIÓN DE REGISTRO DE HANDLERS
# Actualiza esta función para incluir el handler /force_verify para uso de admins

def register_handlers(bot):
    """Registra todos los handlers con el bot"""

    bot.register_message_handler(
    lambda message: check_and_fix_bot_permissions(message, bot),
    commands=['check_bot_permissions']
    )   
    # Handler para el comando /start
    bot.register_message_handler(lambda message: handle_start(message, bot), commands=['start'])
    
    # IMPORTANTE: El handler para verify_all debe ir ANTES que otros handlers
    bot.register_message_handler(lambda message: handle_verify_all_members(message, bot), 
                              commands=['verify_all', 'force_verify'])
    
    # Handler para nuevos miembros
    bot.register_message_handler(lambda message: handle_new_chat_members(message, bot), 
                              content_types=['new_chat_members'])
    
    # Handler para el comando de recuperación de acceso
    bot.register_message_handler(lambda message: handle_recover_access(message, bot), 
                              func=lambda message: message.text == '🎟️ Recuperar Acceso VIP' or 
                                                  message.text == '/recover')
    
    # Handlers para comandos de administrador
    bot.register_message_handler(lambda message: handle_whitelist(message, bot), 
                              func=lambda message: message.from_user.id in ADMIN_IDS and 
                                                  message.text.startswith('/whitelist'))
    
    bot.register_message_handler(lambda message: handle_subinfo(message, bot), 
                              func=lambda message: message.from_user.id in ADMIN_IDS and 
                                                  message.text.startswith('/subinfo'))
    
    # Comando de verificación de permisos para admins
    bot.register_message_handler(
        lambda message: verify_bot_permissions() and bot.reply_to(message, "✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles."),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/check_permissions'
    )
    
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
    schedule_security_verification(bot)

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
        
        # Enviar mensaje de bienvenida con botones (MENSAJE MEJORADO)
        welcome_text = (
            "🌟 **¡BIENVENIDO AL CLUB VIP!** 🌟\n\n"
            "**🔒 Acceso Exclusivo**\n"
            "**├ Contenido Premium**\n"
            "**├ Archivos Únicos**\n"
            "**└ Experiencia VIP**\n\n"
            "**⬇️ Selecciona una opción ⬇️**"
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
            # Mostrar créditos del bot - MENSAJE MEJORADO
            credits_text = (
                "🤖 **ACERCA DE NOSOTROS** 🤖\n\n"
                "**🧠 DESARROLLO**\n"
                "**└ 👨‍💻 Equipo Premium VIP**\n\n"
                "**⚙️ VERSIÓN**\n"
                "**└ 🔄 v1.5.2 (Abril 2025)**\n\n"
                "**📞 SOPORTE**\n"
                "**└ 💬 @admin_support**\n\n"
                "**©️ 2025 DERECHOS RESERVADOS**"
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
            # Mostrar términos de uso - Formato mejorado
            try:
                with open(os.path.join('static', 'terms.txt'), 'r', encoding='utf-8') as f:
                    terms_text = f.read()
                    # Mejoramos el formato para que se aplique el estilo de ramas
                    terms_text = terms_text.replace("1. *SUSCRIPCIÓN*", "**1. SUSCRIPCIÓN**\n**├")
                    terms_text = terms_text.replace("2. *ACCESO*", "**2. ACCESO**\n**├")
                    terms_text = terms_text.replace("3. *CONTENIDO*", "**3. CONTENIDO**\n**├")
                    terms_text = terms_text.replace("4. *CANCELACIÓN*", "**4. CANCELACIÓN**\n**├")
                    terms_text = terms_text.replace("5. *COMPORTAMIENTO*", "**5. COMPORTAMIENTO**\n**├")
                    terms_text = terms_text.replace("6. *LIMITACIÓN DE RESPONSABILIDAD*", "**6. LIMITACIÓN DE RESPONSABILIDAD**\n**├")
                    terms_text = terms_text.replace("7. *PRIVACIDAD*", "**7. PRIVACIDAD**\n**├")
                    terms_text = terms_text.replace("8. *MODIFICACIONES*", "**8. MODIFICACIONES**\n**├")
                    terms_text = terms_text.replace("   -", "**├")
                    terms_text = terms_text.replace(".\n", ".**\n")
                    terms_text = terms_text.replace(".", ".**\n**└")
            except:
                # Términos con formato mejorado en caso de error al leer el archivo
                terms_text = (
                    "📜 **TÉRMINOS DE USO - GRUPO VIP**\n\n"
                    "**1. SUSCRIPCIÓN**\n"
                    "**├ El acceso al grupo VIP está condicionado al pago.**\n"
                    "**├ La suscripción se renovará automáticamente.**\n"
                    "**└ Los precios pueden cambiar con previo aviso.**\n\n"
                    "**2. ACCESO**\n"
                    "**├ Enlaces personales e intransferibles.**\n"
                    "**├ Cada enlace es válido para un solo uso.**\n"
                    "**└ Prohibido compartir o revender accesos.**\n\n"
                    "**3. CONTENIDO**\n"
                    "**├ Material exclusivo del grupo VIP.**\n"
                    "**├ Prohibida redistribución o descarga masiva.**\n"
                    "**└ No responsables por uso indebido.**\n\n"
                    "**4. CANCELACIÓN**\n"
                    "**├ Puedes cancelar desde PayPal en cualquier momento.**\n"
                    "**├ No hay reembolsos por períodos no utilizados.**\n"
                    "**└ Al cancelar pierdes acceso inmediato.**\n\n"
                    "**5. COMPORTAMIENTO**\n"
                    "**├ Se exige respeto hacia otros miembros.**\n"
                    "**├ Prohibido spam y acoso.**\n"
                    "**└ Incumplimiento = expulsión sin reembolso.**"
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
    """Muestra los planes de suscripción disponibles"""
    try:
        # MENSAJE MEJORADO
        plans_text = (
            "💎 **PLANES PREMIUM** 💎\n\n"
            "**🔄 Plan Semanal**\n"
            "**├ 💰 $3.50 USD**\n"
            "**└ ⏱️ Duración: 7 días**\n\n"
            "**🔄 Plan Mensual**\n"
            "**├ 💰 $5.00 USD**\n"
            "**└ ⏱️ Duración: 30 días**\n\n"
            "**❓ ¿Primer pago?**\n"
            "**└ 🎬 Mira nuestro tutorial 👇**"
        )
        
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
    """Muestra los detalles de un plan específico"""
    try:
        plan = PLANS.get(plan_id)
        if not plan:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Plan no encontrado. Por favor, intenta nuevamente."
            )
            return
        
        # MENSAJE MEJORADO
        plan_text = (
            f"🌟 **{plan['display_name']}** 🌟\n\n"
            f"**✨ DESCRIPCIÓN**\n"
            f"**└ {plan['description']}**\n\n"
            f"**🎁 BENEFICIOS**\n"
            f"**├ 🔐 Acceso Grupo VIP**\n"
            f"**├ 📁 21,000+ Archivos Premium**\n"
            f"**└ 🔄 Actualizaciones Continuas**\n\n"
            f"**💰 DETALLES**\n"
            f"**├ 💵 Precio: ${plan['price_usd']:.2f} USD**\n"
            f"**└ 🔄 Renovación: {'Semanal' if plan_id == 'weekly' else 'Mensual'}**\n\n"
            f"**💳 SELECCIONA MÉTODO DE PAGO 👇**"
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
        # MENSAJE MEJORADO
        tutorial_text = (
            "🎬 **TUTORIAL DE PAGO** 🎬\n\n"
            "**1️⃣ SELECCIONA TU PLAN**\n"
            "**├ 🗓️ Semanal $3.50**\n"
            "**└ 📆 Mensual $5.00**\n\n"
            "**2️⃣ MÉTODO DE PAGO**\n"
            "**└ 💳 Clic en \"Pagar con PayPal\"**\n\n"
            "**3️⃣ COMPLETA TU PAGO**\n"
            "**├ 🔹 Cuenta PayPal**\n"
            "**└ 🔸 Tarjeta Crédito/Débito (sin cuenta)**\n\n"
            "**4️⃣ FINALIZA**\n"
            "**├ ✅ Completa el proceso**\n"
            "**└ 📱 Regresa a Telegram**\n\n"
            "**5️⃣ ACCESO VIP**\n"
            "**└ 🔗 Recibirás el enlace exclusivo**\n\n"
            "**⚠️ IMPORTANTE**\n"
            "**└ 🔄 Renovación automática (cancelable desde PayPal)**"
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
    """Maneja los callbacks relacionados con la selección de planes"""
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        if call.data == "tutorial":
            # Mostrar tutorial de pagos
            show_payment_tutorial(bot, chat_id, message_id)
            
        elif call.data == "weekly_plan":
            # Mostrar detalles del plan semanal
            show_plan_details(bot, chat_id, message_id, "weekly")
            
        elif call.data == "monthly_plan":
            # Mostrar detalles del plan mensual
            show_plan_details(bot, chat_id, message_id, "monthly")
            
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
        
        if method == "paypal":
            # Mostrar animación de "procesando"
            processing_message = bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="⚡ **PROCESANDO PAGO** ⚡\n\n**├ ⏳◼️◼️◼️◼️◼️**\n**└ Iniciando...**",
                parse_mode='Markdown',
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
                
                # MENSAJE MEJORADO
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=(
                        "✅ **¡ENLACE GENERADO!** ✅\n\n"
                        f"**🎯 RESUMEN**\n"
                        f"**├ 📋 Plan: {PLANS[plan_id]['display_name']}**\n"
                        f"**├ 💰 Precio: ${PLANS[plan_id]['price_usd']:.2f} USD**\n"
                        f"**└ ⏱️ Período: {'Semanal' if plan_id == 'weekly' else 'Mensual'}**\n\n"
                        f"**⬇️ PRÓXIMO PASO ⬇️**\n"
                        f"**├ 🔗 Clic en \"Ir a pagar\"**\n"
                        f"**└ 🔙 Regresarás automáticamente**"
                    ),
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
                logger.info(f"Enlace de pago PayPal creado para usuario {user_id}, plan {plan_id}")
            else:
                # Error al crear enlace de pago
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="view_plans"))
                
                # MENSAJE MEJORADO
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=processing_message.message_id,
                    text=(
                        "⚠️ **ERROR DE CONEXIÓN** ⚠️\n\n"
                        "**❌ PROBLEMA DETECTADO**\n"
                        "**└ No se pudo crear enlace de pago**\n\n"
                        "**🔄 SOLUCIÓN**\n"
                        "**├ 🕒 Intenta más tarde**\n"
                        "**└ 👨‍💻 O contacta a soporte**"
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
            # No tiene suscripción activa - MENSAJE MEJORADO
            no_subscription_text = (
                "⛔ **ACCESO DENEGADO** ⛔\n\n"
                "**📛 ESTADO DE CUENTA**\n"
                "**└ ❌ No tienes suscripción activa**\n\n"
                "**💎 SOLUCIÓN**\n"
                "**├ 🔑 Adquiere acceso premium**\n"
                "**└ 🚀 Usa /start para ver planes**"
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
            text="🔄 **GENERANDO NUEVO ACCESO**\n\n**├ ⏳ Creando enlace único**\n**└ 🔐 Configurando permisos...**",
            parse_mode='Markdown'
        )
        
        # Generar un nuevo enlace
        invite_link = generate_invite_link(bot, user_id, subscription['sub_id'])
        
        if invite_link:
            # Enlace generado correctamente - MENSAJE MEJORADO
            new_link_text = (
                "🔄 **¡ACCESO REGENERADO!** 🔄\n\n"
                "**🎫 NUEVO ENLACE VIP**\n"
                f"**└ 🔗 [UNIRSE AL GRUPO](${invite_link})**\n\n"
                "**⏱️ VALIDEZ**\n"
                f"**├ ⌛ Expira en {INVITE_LINK_EXPIRY_HOURS} horas**\n"
                "**└ 1️⃣ Un solo uso**\n\n"
                "**🔐 ACCESO SEGURO Y EXCLUSIVO**"
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
            # Error al generar el enlace - MENSAJE MEJORADO
            error_text = (
                "⚠️ **ERROR DE SISTEMA** ⚠️\n\n"
                "**🔧 PROBLEMA DETECTADO**\n"
                "**└ ❌ Imposible generar nuevo enlace**\n\n"
                "**🆘 SOPORTE INMEDIATO**\n"
                "**├ 👨‍💻 Contacta: @admin_support**\n"
                "**└ 📱 Indica: \"Error regeneración enlace\"**\n\n"
                "**🔍 Referencia: VIP-ERR-" + str(user_id)[-4:] + "**"
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

def handle_whitelist(message, bot):
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
        bot.register_next_step_handler(message, lambda msg: handle_whitelist_duration(msg, bot))
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text="❌ Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
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
            bot.register_next_step_handler(message, lambda msg: handle_whitelist_duration(msg, bot))
            return
        
        # Obtener información del estado
        target_user_id = admin_states[admin_id]['target_user_id']
        
        # Calcular fechas
        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=days)
        
        # Determinar el plan más cercano
        plan_id = 'weekly' if days <= 7 else 'monthly'
        
        # Enviar mensaje informativo mientras se procesa
        status_message = bot.send_message(
            chat_id=chat_id,
            text="🔄 **PROCESANDO SOLICITUD**\n\n**├ 🔍 Verificando usuario**\n**├ 🛠️ Generando acceso**\n**└ 🔗 Creando enlace único...**",
            parse_mode='Markdown'
        )
        
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
        
        # Preparar mensaje de confirmación - MENSAJE MEJORADO
        confirmation_text = (
            "✅ **USUARIO AGREGADO CON ÉXITO** ✅\n\n"
            "**👤 DATOS**\n"
            f"**├ 🆔 ID: {target_user_id}**\n"
            f"**├ 📆 Duración: {days} días**\n"
            f"**└ 🗓️ Expira: {end_date.strftime('%d %b %Y')}**\n\n"
        )
        
        if invite_link:
            confirmation_text += f"**🔗 ENLACE DE INVITACIÓN**\n**├ 🌐 [Acceso Directo]({invite_link})**\n**└ ⚠️ Expira en {INVITE_LINK_EXPIRY_HOURS} horas o tras un uso**"
        else:
            confirmation_text += "**⚠️ ADVERTENCIA**\n**└ ❌ No se pudo generar enlace. Usuario debe usar /recover**"
        
        # Actualizar el mensaje de estado
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=confirmation_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Notificar al usuario - MENSAJE MEJORADO
        try:
            user_notification = (
                "🏆 **¡ACCESO VIP CONCEDIDO!** 🏆\n\n"
                "**🎁 INVITACIÓN ESPECIAL**\n"
                "**├ 👑 Otorgada por Administrador**\n"
                f"**└ ⏳ Duración: {days} días**\n\n"
            )
            
            if invite_link:
                user_notification += (
                    "**🚪 ENLACE DE ACCESO**\n"
                    f"**└ 🔗 [UNIRSE AL GRUPO VIP]({invite_link})**\n\n"
                    "**📌 INFORMACIÓN**\n"
                    f"**├ ⏱️ Enlace válido por {INVITE_LINK_EXPIRY_HOURS} horas**\n"
                    "**├ 1️⃣ Un solo uso**\n"
                    "**└ 🔄 /recover para nuevo enlace**\n\n"
                    "**✨ ¡BIENVENIDO AL CLUB EXCLUSIVO!** ✨"
                )
            else:
                user_notification += (
                    "**🚪 ACCESO AL GRUPO**\n"
                    "**└ 🔄 Usa /recover para obtener tu enlace de invitación**\n\n"
                    "**✨ ¡BIENVENIDO AL CLUB EXCLUSIVO!** ✨"
                )
            
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
                text="⚠️ **ADVERTENCIA**\n\n**└ ❌ No se pudo notificar al usuario. Es posible que no haya iniciado el bot.**",
                parse_mode='Markdown'
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

def handle_unknown_message(message, bot):
    """Maneja mensajes que no coinciden con ningún comando conocido"""
    try:
        # MENSAJE MEJORADO
        bot.send_message(
            chat_id=message.chat.id,
            text=(
                "❓ **COMANDO NO RECONOCIDO** ❓\n\n"
                "**🔍 OPCIONES DISPONIBLES**\n"
                "**├ /start - Iniciar el bot**\n"
                "**└ /recover - Recuperar acceso**\n\n"
                "**🔄 Usa /start para ver el menú principal**"
            ),
            parse_mode='Markdown'
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
            "🔄 **RECOPILANDO DATOS**\n\n**├ 📊 Analizando estadísticas**\n**└ ⏳ Por favor, espera...**",
            parse_mode='Markdown'
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
        
        # MENSAJE MEJORADO - Construir mensaje de estadísticas
        stats_text = (
            "📊 **PANEL DE ESTADÍSTICAS** 📊\n\n"
            
            "**👥 USUARIOS**\n"
            f"**├ 🔢 Total: {stats['usuarios']}**\n"
            f"**└ 🆕 Últimas 24h: {stats['usuarios_nuevos_24h']}**\n\n"
            
            "**💳 SUSCRIPCIONES**\n"
            f"**├ 🔢 Total: {stats['suscripciones']}**\n"
            f"**├ ✅ Activas: {stats['suscripciones_activas']}**\n"
            f"**└ 🆕 Últimas 24h: {stats['suscripciones_nuevas_24h']}**\n\n"
            
            "**🔗 ENLACES**\n"
            f"**└ 🔢 Generados: {stats['enlaces_invitacion']}**\n\n"
            
            "**🛡️ SEGURIDAD**\n"
            f"**└ 🚫 Expulsiones: {stats['expulsiones_totales']}**\n\n"
        )
        
        # Añadir estadísticas de planes
        if plan_stats:
            stats_text += "**📑 PLANES POPULARES**\n"
            for plan_data in plan_stats:
                plan_id = plan_data[0]
                count = plan_data[1]
                plan_name = PLANS.get(plan_id, {}).get('display_name', plan_id)
                stats_text += f"**├ {plan_name}: {count}**\n"
            stats_text += "\n"
        
        # Añadir información del panel de administrador
        stats_text += (
            "**🔐 PANEL ADMIN**\n"
            f"**└ 🌐 [Acceder]({WEBHOOK_URL}/admin/panel?admin_id={user_id})**\n\n"
            
            f"**⏱️ Actualizado: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}**"
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
        
        # MENSAJE MEJORADO - Mensaje de estado mientras se procesa
        status_message = bot.reply_to(
            message,
            "🔄 **GENERANDO ENLACE DE PRUEBA**\n\n**├ 🛠️ Verificando permisos**\n**└ ⏳ Creando enlace único...**",
            parse_mode='Markdown'
        )
        
        # Verificar permisos del bot en el grupo
        from config import GROUP_CHAT_ID
        if not GROUP_CHAT_ID:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="❌ **ERROR DE CONFIGURACIÓN**\n\n**└ GROUP_CHAT_ID no está configurado**",
                parse_mode='Markdown'
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
                    text="❌ **ERROR DE PERMISOS**\n\n**└ El bot no es administrador en el grupo VIP**",
                    parse_mode='Markdown'
                )
                return
            
            if not chat_member.can_invite_users:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text="❌ **ERROR DE PERMISOS**\n\n**└ El bot no tiene permiso para invitar usuarios**",
                    parse_mode='Markdown'
                )
                return
                
        except Exception as e:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ **ERROR DE VERIFICACIÓN**\n\n**└ {str(e)}**",
                parse_mode='Markdown'
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
            
            # MENSAJE MEJORADO - Si llegamos aquí sin errores, la generación fue exitosa
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=(
                    "✅ **ENLACE GENERADO CORRECTAMENTE** ✅\n\n"
                    "**🔗 ENLACE ÚNICO**\n"
                    f"**└ {invite.invite_link}**\n\n"
                    "**ℹ️ INFORMACIÓN**\n"
                    "**├ ⏱️ Expira en 1 hora**\n"
                    "**├ 1️⃣ Un solo uso**\n"
                    "**└ 📝 No registrado en base de datos**"
                ),
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"Admin {user_id} generó un enlace de prueba exitosamente")
            
        except Exception as e:
            # MENSAJE MEJORADO - Error
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=(
                    "❌ **ERROR AL GENERAR ENLACE** ❌\n\n"
                    f"**⚠️ DETALLE**\n"
                    f"**└ {str(e)}**\n\n"
                    "**🔍 POSIBLES CAUSAS**\n"
                    "**├ ❌ Permisos insuficientes**\n"
                    "**├ ❌ ID de grupo incorrecto**\n"
                    "**└ ❌ Problema con API de Telegram**"
                ),
                parse_mode='Markdown'
            )
            
            logger.error(f"Error al generar enlace de prueba: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error en handle_test_invite: {str(e)}")
        bot.reply_to(message, f"❌ **ERROR INESPERADO**\n\n**└ {str(e)}**", parse_mode='Markdown')

def register_handlers(bot):
    """Registra todos los handlers con el bot"""

    # Handler para verificar permisos del bot
    bot.register_message_handler(
        lambda message: check_and_fix_bot_permissions(message, bot),
        commands=['check_bot_permissions']
    )
    
    # Handler para probar la generación de enlaces de invitación (solo admins)
    bot.register_message_handler(
        lambda message: handle_test_invite(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/test_invite'
    )
    
    # Handler para estadísticas del bot (solo admins)
    bot.register_message_handler(
        lambda message: handle_stats_command(message, bot),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text in ['/stats', '/estadisticas']
    )
    
    # Handler para el comando /start
    bot.register_message_handler(lambda message: handle_start(message, bot), commands=['start'])
    
    # IMPORTANTE: El handler para verify_all debe ir ANTES que otros handlers
    bot.register_message_handler(lambda message: handle_verify_all_members(message, bot), 
                              commands=['verify_all', 'force_verify'])
    
    # Handler para nuevos miembros
    bot.register_message_handler(lambda message: handle_new_chat_members(message, bot), 
                              content_types=['new_chat_members'])
    
    # Handler para el comando de recuperación de acceso
    bot.register_message_handler(lambda message: handle_recover_access(message, bot), 
                              func=lambda message: message.text == '🎟️ Recuperar Acceso VIP' or 
                                                  message.text == '/recover' or
                                                  message.text.startswith('/recover'))
    
    # Handlers para comandos de administrador
    bot.register_message_handler(lambda message: handle_whitelist(message, bot), 
                              func=lambda message: message.from_user.id in ADMIN_IDS and 
                                                  message.text.startswith('/whitelist'))
    
    bot.register_message_handler(lambda message: handle_subinfo(message, bot), 
                              func=lambda message: message.from_user.id in ADMIN_IDS and 
                                                  message.text.startswith('/subinfo'))
    
    # Comando de verificación de permisos para admins
    bot.register_message_handler(
        lambda message: verify_bot_permissions() and bot.reply_to(message, "✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles."),
        func=lambda message: message.from_user.id in ADMIN_IDS and message.text == '/check_permissions'
    )
    
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
    schedule_security_verification(bot)
    
    # Verificar permisos del bot al iniciar
    verify_bot_permissions()