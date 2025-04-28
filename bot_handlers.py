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
    Crea un enlace de invitación para el grupo VIP.
    Utiliza la API de Telegram para crear un enlace temporal y único.
    """
    try:
        # Para un bot real, esto debería usar createChatInviteLink
        # En este ejemplo, usaremos un enlace estático o simulado
        if not GROUP_INVITE_LINK:
            logger.error("GROUP_INVITE_LINK no está configurado")
            return None
            
        # En un bot real, aquí llamaríamos a:
        # invite = bot.create_chat_invite_link(
        #     chat_id=-GROUP_CHAT_ID,  # ID del grupo VIP
        #     expire_date=int((datetime.datetime.now() + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)).timestamp()),
        #     member_limit=INVITE_LINK_MEMBER_LIMIT,
        #     name=f"Invite for user {user_id}",
        #     creates_join_request=False
        # )
        # invite_link = invite.invite_link
        
        # Para este ejemplo, simulamos el enlace
        invite_link = f"{GROUP_INVITE_LINK}?ref={user_id}_{sub_id}"
        
        # Calcular la fecha de expiración
        created_at = datetime.datetime.now()
        expires_at = created_at + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)
        
        # Guardar el enlace en la base de datos
        db.save_invite_link(
            sub_id=sub_id,
            invite_link=invite_link,
            created_at=created_at,
            expires_at=expires_at
        )
        
        logger.info(f"Enlace de invitación creado para usuario {user_id}, expira en {INVITE_LINK_EXPIRY_HOURS} horas")
        
        return invite_link
        
    except Exception as e:
        logger.error(f"Error al crear enlace de invitación: {str(e)}")
        return None

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
        
        # Generar enlace de invitación
        invite_link = generate_invite_link(bot, user_id, sub_id)
        
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
    """Crea los botones para el menú de planes"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Agregar tutorial de pagos
    markup.add(types.InlineKeyboardButton("🎥 Tutorial de Pagos", callback_data="tutorial"))
    
    # Agregar planes
    markup.add(
        types.InlineKeyboardButton("🗓️ Plan Semanal", callback_data="weekly_plan"),
        types.InlineKeyboardButton("📆 Plan Mensual", callback_data="monthly_plan")
    )
    
    # Agregar botón de volver
    markup.add(types.InlineKeyboardButton("🔙 Atrás", callback_data="back_to_main"))
    
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
        
        logger.info(f"Iniciando verificación automática de seguridad del grupo {group_id_str}")
        
        # Verificar que el bot tenga permisos necesarios
        try:
            bot_member = bot.get_chat_member(group_id, bot.get_me().id)
            
            if bot_member.status not in ['administrator', 'creator']:
                logger.error(f"CRÍTICO: El bot no tiene permisos de administrador en el grupo {group_id}")
                # Notificar a todos los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=f"⚠️ ALERTA DE SEGURIDAD CRÍTICA: El bot no tiene permisos de administrador en el grupo VIP.\n\nLa verificación automática de seguridad no puede ejecutarse. Por favor, haga al bot administrador del grupo."
                        )
                    except Exception as e:
                        logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                return False
            
            if not getattr(bot_member, 'can_restrict_members', False):
                logger.error(f"CRÍTICO: El bot no tiene permiso para expulsar usuarios en el grupo {group_id}")
                # Notificar a todos los administradores
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=f"⚠️ ALERTA DE SEGURIDAD CRÍTICA: El bot es administrador pero no tiene permiso específico para expulsar miembros en el grupo VIP.\n\nPor favor, edite los permisos del bot y active 'Expulsar usuarios'."
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
            chat_members = bot.get_chat_members(chat_id=group_id, offset=0, limit=200)
            members.extend(chat_members)
            logger.info(f"Obtenidos {len(members)} miembros del grupo para verificación")
        except Exception as e:
            logger.error(f"Error al obtener miembros del grupo: {e}")
            # Notificar a los administradores
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ Error en verificación automática: No se pudieron obtener miembros del grupo.\nError: {str(e)}"
                    )
                except:
                    pass
            return False
        
        # Identificar miembros no autorizados
        unauthorized_members = []
        
        for member in members:
            member_id = member.user.id
            username = member.user.username or f"User{member_id}"
            
            # Omitir bots
            if member.user.is_bot:
                logger.debug(f"Omitiendo bot: {username}")
                continue
                
            # Omitir administradores
            if member_id in admin_ids:
                logger.debug(f"Omitiendo administrador: {username}")
                continue
            
            # Verificar si tiene suscripción activa
            subscription = db.get_active_subscription(member_id)
            if not subscription:
                logger.warning(f"⚠️ MIEMBRO NO AUTORIZADO: {member_id} (@{username})")
                unauthorized_members.append((member_id, username))
                
                # Información del usuario para los logs
                first_name = getattr(member.user, 'first_name', '') or ''
                last_name = getattr(member.user, 'last_name', '') or ''
                full_name = f"{first_name} {last_name}".strip() or "Usuario"
                
                # Intentar expulsar de inmediato sin esperar
                try:
                    logger.info(f"Expulsando a usuario no autorizado: {member_id} (@{username})")
                    
                    # Notificar al grupo sobre la expulsión
                    bot.send_message(
                        chat_id=group_id,
                        text=f"🛑 SEGURIDAD: Usuario {full_name} (@{username}) no tiene suscripción activa y será expulsado automáticamente."
                    )
                    
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
                    db.record_expulsion(member_id, "Verificación automática - Sin suscripción activa")
                    
                    # Enviar mensaje privado al usuario
                    try:
                        bot.send_message(
                            chat_id=member_id,
                            text=f"❌ Has sido expulsado del grupo VIP porque no tienes una suscripción activa.\n\nPara volver a unirte, adquiere una suscripción en @VIPSubscriptionBot con el comando /start."
                        )
                    except Exception as e:
                        logger.error(f"No se pudo enviar mensaje privado a {member_id}: {e}")
                    
                    # Notificar a los administradores
                    for admin_id in ADMIN_IDS:
                        try:
                            bot.send_message(
                                chat_id=admin_id,
                                text=f"🛑 SEGURIDAD AUTOMÁTICA: Usuario {full_name} (@{username}) ID:{member_id} fue expulsado por no tener suscripción activa."
                            )
                        except Exception as e:
                            logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                    
                except Exception as e:
                    logger.error(f"ERROR al expulsar a usuario no autorizado {member_id}: {e}")
        
        # Resumen final
        logger.info(f"Verificación de seguridad completada: {len(unauthorized_members)} miembros no autorizados identificados y expulsados")
        
        # Notificar resultados a administradores
        if unauthorized_members:
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=f"✅ Verificación automática completada: Se expulsaron {len(unauthorized_members)} usuarios sin suscripción activa."
                    )
                except:
                    pass
        
        return True
        
    except Exception as e:
        logger.error(f"Error en verificación de seguridad: {e}")
        # Notificar a los administradores
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=f"❌ Error en verificación automática de seguridad: {str(e)}"
                )
            except:
                pass
        return False


# 2. MEJORA DEL COMANDO /verify_all
# Reemplaza la función handle_verify_all_members con esta versión mejorada:

def handle_verify_all_members(message, bot):
    """
    Comando para verificar y expulsar manualmente a todos los miembros no autorizados del grupo
    """
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Log para depuración
        logger.info(f"Comando /verify_all recibido de usuario {user_id} en chat {chat_id}")
        
        # Verificar que sea un administrador
        if user_id not in ADMIN_IDS:
            logger.info(f"Usuario {user_id} intentó usar /verify_all pero no es administrador")
            bot.reply_to(message, "⚠️ Este comando solo está disponible para administradores.")
            return
        
        # Verificar que el mensaje sea del grupo VIP o de un chat privado con el administrador
        from config import GROUP_CHAT_ID
        if str(chat_id) != str(GROUP_CHAT_ID) and message.chat.type != 'private':
            logger.info(f"Comando /verify_all usado en chat incorrecto {chat_id}")
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

def verify_bot_permissions():
    """Verifica que el bot tenga los permisos correctos en el grupo VIP"""
    try:
        from config import GROUP_CHAT_ID, ADMIN_IDS, BOT_TOKEN
        import requests
        import json
        
        if not GROUP_CHAT_ID:
            logger.warning("GROUP_CHAT_ID no está configurado, omitiendo verificación de permisos")
            return
        
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
            return
        
        chat_member = data.get("result", {})
        status = chat_member.get("status")
        
        if status not in ["administrator", "creator"]:
            logger.error(f"El bot no es administrador en el grupo VIP. Status: {status}")
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": f"⚠️ ALERTA: El bot no es administrador en el grupo VIP (ID: {GROUP_CHAT_ID}).\n\nPor favor, haga al bot administrador para que pueda expulsar usuarios no autorizados."
                    }
                )
            return
        
        # Verificar permiso específico para expulsar
        can_restrict = chat_member.get("can_restrict_members", False)
        
        if not can_restrict:
            logger.error("El bot es administrador pero no tiene permiso para expulsar miembros")
            for admin_id in ADMIN_IDS:
                requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    params={
                        "chat_id": admin_id,
                        "text": f"⚠️ ALERTA: El bot es administrador pero NO tiene permiso para EXPULSAR USUARIOS en el grupo VIP.\n\nPor favor, edite los permisos del bot y active 'Expulsar usuarios'."
                    }
                )
            return
        
        logger.info(f"✅ Permisos del bot verificados correctamente: {status}, can_restrict_members: {can_restrict}")
        
    except Exception as e:
        logger.error(f"Error al verificar permisos del bot: {e}")

def handle_new_chat_members(message, bot):
    """Maneja cuando nuevos miembros se unen al grupo"""
    try:
        from config import GROUP_CHAT_ID
        
        # Verificar que sea el grupo VIP
        if str(message.chat.id) != str(GROUP_CHAT_ID):
            return
            
        # Obtener los nuevos miembros
        for new_member in message.new_chat_members:
            # Omitir si es el propio bot
            if new_member.id == bot.get_me().id:
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
                logger.warning(f"Usuario sin suscripción detectado al unirse: {username} (ID: {user_id})")
                
                try:
                    # Enviar mensaje al grupo
                    bot.send_message(
                        chat_id=message.chat.id,
                        text=f"🛑 SEGURIDAD: Usuario {new_member.first_name} (@{username}) no tiene suscripción activa y será expulsado automáticamente."
                    )
                    
                    # Expulsar al usuario
                    bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
                    
                    # Desbanear inmediatamente para permitir que vuelva a unirse si obtiene suscripción
                    bot.unban_chat_member(
                        chat_id=message.chat.id,
                        user_id=user_id,
                        only_if_banned=True
                    )
                    
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
        logger.error(f"Error en handle_new_chat_members: {str(e)}")


# 4. MEJORA EN LA FUNCIÓN DE REGISTRO DE HANDLERS
# Actualiza esta función para incluir el handler /force_verify para uso de admins

def register_handlers(bot):
    """Registra todos los handlers con el bot"""
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
        
        logger.info(f"Usuario {user_id} ({username}) ha iniciado el bot")
    
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
    """Muestra los planes de suscripción disponibles"""
    try:
        plans_text = (
            "💸 Escoge tu plan de suscripción:\n\n"
            "🔹 Plan Semanal: $3.50 / 1 semana\n"
            "🔸 Plan Mensual: $5.00 / 1 mes\n\n"
            "🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇"
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
        
        # Construir mensaje con detalles del plan
        plan_text = (
            f"📦 {plan['display_name']}\n\n"
            f"{plan['description']}\n"
            f"Beneficios:\n"
            f"✅ Grupo VIP (Acceso)\n"
            f"✅ 21,000 archivos exclusivos 📁\n\n"
            f"💵 Precio: ${plan['price_usd']:.2f} USD\n"
            f"📆 Facturación: {'semanal' if plan_id == 'weekly' else 'mensual'} (recurrente)\n\n"
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
            invite_link = generate_invite_link(bot, user_id, subscription['sub_id'])
            
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
        invite_link = generate_invite_link(bot, target_user_id, sub_id)
        
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
        bot.send_message(
            chat_id=message.chat.id,
            text="No entiendo ese comando. Por favor, usa /start para ver las opciones disponibles."
        )
    except Exception as e:
        logger.error(f"Error en handle_unknown_message: {str(e)}")

def register_handlers(bot):
    """Registra todos los handlers con el bot"""
    # Handler para el comando /start
    bot.register_message_handler(lambda message: handle_start(message, bot), commands=['start'])
    
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
    
    # Callback handlers para los botones
    bot.register_callback_query_handler(lambda call: handle_main_menu_callback(call, bot), 
                                      func=lambda call: call.data in ['view_plans', 'bot_credits', 'terms'])
    
    bot.register_callback_query_handler(lambda call: handle_plans_callback(call, bot), 
                                      func=lambda call: call.data in ['tutorial', 'weekly_plan', 'monthly_plan', 'back_to_main'])
    
    bot.register_callback_query_handler(lambda call: handle_payment_method(call, bot), 
                                      func=lambda call: call.data.startswith('payment_'))
    
    # Handler por defecto para mensajes no reconocidos
    bot.register_message_handler(lambda message: handle_unknown_message(message, bot), func=lambda message: True)