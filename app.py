import logging
import telebot
from flask import Flask, request, jsonify, render_template, send_file
import threading
import time
import os
import json
import datetime
import requests
from telebot import types
import database as db
import payments as pay
from config import BOT_TOKEN, PORT, WEBHOOK_URL, ADMIN_IDS, PLANS, DB_PATH, RECURRING_PAYMENTS_ENABLED, SUBSCRIPTION_GRACE_PERIOD_HOURS

admin_states = {}

# Luego importa bot_handlers
import bot_handlers

# Y asigna admin_states en bot_handlers
bot_handlers.admin_states = admin_states

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

processed_payment_ids = set()

def log_webhook_data(update):
    """Registra información detallada sobre una actualización de Telegram para diagnóstico"""
    try:
        log_parts = ["Diagnóstico de actualización:"]
        
        # Verificar tipo básico
        if hasattr(update, 'message') and update.message:
            log_parts.append("Tipo: message")
            
            # Verificar si tiene texto
            if hasattr(update.message, 'text') and update.message.text:
                log_parts.append(f"Texto: {update.message.text}")
            else:
                log_parts.append("Sin texto")
            
            # Verificar remitente
            if hasattr(update.message, 'from_user') and update.message.from_user:
                log_parts.append(f"De: {update.message.from_user.id}")
            
            # Verificar tipo de contenido
            content_types = []
            for attr in ['audio', 'document', 'photo', 'sticker', 'video', 'voice', 'contact', 'location', 'venue', 'new_chat_members', 'left_chat_member']:
                if hasattr(update.message, attr) and getattr(update.message, attr):
                    content_types.append(attr)
            
            if content_types:
                log_parts.append(f"Tipos de contenido: {', '.join(content_types)}")
        
        elif hasattr(update, 'callback_query') and update.callback_query:
            log_parts.append("Tipo: callback_query")
            
            if hasattr(update.callback_query, 'data') and update.callback_query.data:
                log_parts.append(f"Datos: {update.callback_query.data}")
        
        elif hasattr(update, 'chat_member') and update.chat_member:
            log_parts.append("Tipo: chat_member")
            
            if hasattr(update.chat_member, 'new_chat_member') and update.chat_member.new_chat_member:
                log_parts.append(f"Estado nuevo: {update.chat_member.new_chat_member.status}")
            
            if hasattr(update.chat_member, 'old_chat_member') and update.chat_member.old_chat_member:
                log_parts.append(f"Estado anterior: {update.chat_member.old_chat_member.status}")
        
        # Registrar la información recopilada
        logger.info(" | ".join(log_parts))
    except Exception as e:
        logger.error(f"Error en log_webhook_data: {str(e)}")

# Inicializar el bot y la aplicación Flask
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

admin_states = {}

# Importar el sistema centralizado de handlers
import bot_handlers

bot_handlers.admin_states = admin_states

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Recibe las actualizaciones de Telegram a través de webhook"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            
            # Registrar el contenido de la actualización
            logger.info(f"Actualización recibida: {json_string}")
            
            # Procesar la actualización
            update = telebot.types.Update.de_json(json_string)
            
            # Registrar el tipo de actualización
            if update.message:
                if update.message.text:
                    logger.info(f"Mensaje recibido de {update.message.from_user.id}: {update.message.text}")
                    
                    # Verificar si es una respuesta a un estado de whitelist
                    if update.message.from_user.id in admin_states and admin_states[update.message.from_user.id]['action'] == 'whitelist':
                        bot_handlers.handle_whitelist_duration(update.message, bot)
                        logger.info(f"Procesando duración de whitelist para admin {update.message.from_user.id}")
                        return 'OK', 200
                        
                    # Manejar comandos de administrador
                    if update.message.from_user.id in ADMIN_IDS:
                        try:
                            # Procesar comandos de administrador
                            if update.message.text == '/stats' or update.message.text == '/estadisticas':
                                bot_handlers.handle_stats_command(update.message, bot)
                                logger.info(f"Comando de administrador {update.message.text} procesado para {update.message.from_user.id}")
                                return 'OK', 200
                            elif update.message.text == '/check_permissions':
                                bot_handlers.verify_bot_permissions(bot) and bot.reply_to(update.message, "✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles.")
                                logger.info(f"Verificación de permisos procesada para {update.message.from_user.id}")
                                return 'OK', 200
                            elif update.message.text == '/test_invite':
                                bot_handlers.handle_test_invite(update.message, bot)
                                logger.info(f"Comando de test_invite procesado para {update.message.from_user.id}")
                                return 'OK', 200
                            elif update.message.text.startswith('/whitelist'):
                                if ' list' in update.message.text:
                                    bot_handlers.handle_whitelist_list(update.message, bot)
                                else:
                                    # Manejar directamente en app.py
                                    handle_whitelist_command(update.message, bot)
                                logger.info(f"Comando whitelist procesado para {update.message.from_user.id}")
                                return 'OK', 200
                            elif update.message.text.startswith('/subinfo'):
                                bot_handlers.handle_subinfo(update.message, bot)
                                logger.info(f"Comando subinfo procesado para {update.message.from_user.id}")
                                return 'OK', 200
                            # NUEVO: Manejar comando para forzar verificación de seguridad
                            elif update.message.text == '/force_security_check':
                                bot_handlers.admin_force_security_check(update.message, bot)
                                logger.info(f"Comando force_security_check procesado para {update.message.from_user.id}")
                                return 'OK', 200
                        except Exception as e:
                            logger.error(f"Error al procesar comando de administrador: {str(e)}")
                            # Intentar responder al usuario con el error
                            try:
                                bot.reply_to(update.message, f"❌ Error al procesar comando: {str(e)}")
                            except:
                                pass
                
                # Verificar si el mensaje no tiene texto pero es un evento
                else:
                    logger.info(f"Evento recibido de {update.message.from_user.id}")
                    
                # Manejar directamente new_chat_members aquí
                if update.message.new_chat_members:
                    logger.info(f"Nuevos miembros detectados: {[m.id for m in update.message.new_chat_members]}")
                    try:
                        bot_handlers.handle_new_chat_members(update.message, bot)
                        return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error procesando nuevos miembros: {str(e)}")
                
                # Manejar left_chat_member - Añadida esta verificación
                if hasattr(update.message, 'left_chat_member') and update.message.left_chat_member is not None:
                    logger.info(f"Usuario abandonó el chat: {update.message.left_chat_member.id}")
                    return 'OK', 200
                
                # Continuar con el manejo del mensaje /start
                if update.message.text == '/start':
                    logger.info("¡Comando /start detectado! Enviando respuesta directa...")
                    
                    try:
                        # Usar la función handle_start mejorada
                        bot_handlers.handle_start(update.message, bot)
                        logger.info(f"Respuesta enviada al usuario {update.message.from_user.id}")
                        return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error al enviar respuesta directa: {str(e)}")
                
                # Manejar comando recover
                if update.message.text == '/recover' or update.message.text.startswith('/recover'):
                    try:
                        bot_handlers.handle_recover_access(update.message, bot)
                        logger.info(f"Comando /recover procesado para {update.message.from_user.id}")
                        return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error al procesar comando /recover: {str(e)}")
            
            elif update.callback_query:
                logger.info(f"Callback recibido de {update.callback_query.from_user.id}: {update.callback_query.data}")
                
                # Manejar directamente los callbacks aquí
                try:
                    call = update.callback_query
                    chat_id = call.message.chat.id
                    message_id = call.message.message_id
                    
                    # Manejar directamente callback de whitelist
                    if call.data == "whitelist_cancel":
                        try:
                            bot_handlers.handle_whitelist_callback(call, bot)
                            logger.info(f"Callback de whitelist procesado para {call.from_user.id}")
                            bot.answer_callback_query(call.id)
                            return 'OK', 200
                        except Exception as e:
                            logger.error(f"Error al procesar callback whitelist: {str(e)}")
                    
                    if call.data == "view_plans":
                        # Usar la nueva función para mostrar planes dinámicamente
                        bot_handlers.show_plans(bot, chat_id, message_id)
                        logger.info(f"Planes mostrados a usuario {chat_id}")
                    
                    elif call.data == "tutorial":
                        # Mostrar tutorial de pagos
                        bot_handlers.show_payment_tutorial(bot, chat_id, message_id)
                        logger.info(f"Tutorial mostrado a usuario {chat_id}")
                        
                    elif call.data == "bot_credits":
                        # Mostrar créditos - SIN formato Markdown para evitar errores
                        credits_text = (
                            "🧠 Créditos del Bot\n\n"
                            "Este bot fue desarrollado por el equipo de desarrollo VIP.\n\n"
                            "Si deseas realizar tu propio bot de suscripciones contactate con @NuryOwO.\n\n"
                            "© 2025 Todos los derechos reservados.\n\n"
                        )
                        
                        markup = types.InlineKeyboardMarkup()
                        markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="back_to_main"))
                        
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=credits_text,
                            reply_markup=markup
                        )
                        logger.info(f"Créditos mostrados a usuario {chat_id}")
                        
                    elif call.data == "terms":
                        # Mostrar términos - SIN formato Markdown para evitar errores
                        try:
                            with open(os.path.join('static', 'terms.txt'), 'r', encoding='utf-8') as f:
                                # Eliminar los asteriscos que causan problemas de formato Markdown
                                terms_text = f.read().replace('*', '')
                        except:
                            terms_text = (
                                "📜 Términos de Uso\n\n"
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
                            reply_markup=markup
                        )
                        logger.info(f"Términos mostrados a usuario {chat_id}")
                        
                    elif call.data == "back_to_main":
                        # Volver al menú principal
                        markup = bot_handlers.create_main_menu_markup()
                        
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text = (
                                "👋 ¡𝗢𝗵𝗮𝘆𝗼𝘂~! ヾ(๑╹◡╹)ﾉ 𝗦𝗼𝘆 𝗹𝗮 𝗽𝗼𝗿𝘁𝗲𝗿𝗮 𝗱𝗲𝗹 𝗴𝗿𝘂𝗽𝗼 𝗩𝗜𝗣\n\n"
                                "Este grupo es un espacio exclusivo con contenido premium y acceso limitado.\n\n"
                                "Estoy aquí para ayudarte a ingresar correctamente al grupo 💫\n\n"
                                "Por favor, elige una opción para continuar 👇"
                            ),
                            reply_markup=markup
                        )
                        logger.info(f"Vuelto al menú principal para usuario {chat_id}")
                    
                    elif "_plan" in call.data:
                        # Manejar selección de plan usando la función dinámica
                        plan_id = bot_handlers.get_plan_from_callback(call.data)
                        if plan_id and plan_id in PLANS:
                            bot_handlers.show_plan_details(bot, chat_id, message_id, plan_id)
                            logger.info(f"Detalles del plan {plan_id} mostrados a usuario {chat_id}")
                        else:
                            bot.answer_callback_query(call.id, "Plan no disponible")
                            logger.error(f"Plan {plan_id} no encontrado")
                    
                    elif call.data.startswith("payment_paypal_"):
                        # Manejar pago con PayPal
                        plan_id = call.data.split("_")[-1]  # Extraer el ID del plan
                        
                        # Verificar que el plan existe
                        if plan_id not in PLANS:
                            bot.answer_callback_query(call.id, "❌ Plan no válido")
                            logger.error(f"Intento de pago con plan inválido: {plan_id}")
                            return 'OK', 200
                        
                        # Mostrar mensaje inicial kawaii
                        processing_message = bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text="✨ Preparando algo especial para ti... ✨"
                        )
                        
                        # Variable para controlar la animación
                        animation_active = True
                        
                        # Iniciar hilo de animación
                        def animate_kawaii_messages():
                            messages = [
                                "🌸 Preparando tu entrada VIP... 🌸",
                                "📝 Anotando tu nombre en mi lista secreta~",
                                "✨ Qué nombre tan lindo... jeje~ ✨",
                                "🎀 Abriendo las puertas del club VIP~",
                                "🌟 Un momento más... ¡Todo listo! 🌟",
                                "💰 Oh casi lo olvido, falta el pago... 💰"
                            ]
                            
                            # Variable para rastrear el frame actual
                            current_frame = 0
                            
                            # Primera fase: mostrar cada mensaje una vez
                            for i, message_text in enumerate(messages):
                                if not animation_active:
                                    break
                                    
                                try:
                                    bot.edit_message_text(
                                        chat_id=chat_id,
                                        message_id=message_id,
                                        text=message_text
                                    )
                                    current_frame = i
                                    # Tiempo más largo entre mensajes (3 segundos)
                                    time.sleep(3)
                                except Exception as e:
                                    logger.error(f"Error en animación fase 1: {e}")
                                    break
                            
                            # Segunda fase: continuar ciclo hasta que se desactive
                            while animation_active:
                                next_frame = (current_frame + 1) % len(messages)
                                try:
                                    bot.edit_message_text(
                                        chat_id=chat_id,
                                        message_id=message_id,
                                        text=messages[next_frame]
                                    )
                                    current_frame = next_frame
                                    time.sleep(3)
                                except Exception as e:
                                    logger.error(f"Error en ciclo de animación fase 2: {e}")
                                    break
                        
                        # Iniciar hilo de animación
                        animation_thread = threading.Thread(target=animate_kawaii_messages)
                        animation_thread.daemon = True
                        animation_thread.start()
                        
                        # Pausa para asegurar que el hilo de animación inicie correctamente
                        time.sleep(1)
                        
                        try:
                            # Crear enlace de suscripción de PayPal
                            subscription_url = pay.create_subscription_link(plan_id, chat_id)
                            
                            # Detener animación y dar tiempo para finalizar
                            animation_active = False
                            time.sleep(1.5)  # Tiempo suficiente para que termine su ciclo actual
                            
                            if subscription_url:
                                # Crear markup con botón para pagar
                                markup = types.InlineKeyboardMarkup()
                                markup.add(
                                    types.InlineKeyboardButton("💳 Ir a pagar", url=subscription_url),
                                    types.InlineKeyboardButton("🔙 Cancelar", callback_data="view_plans")
                                )
                                
                                # Determinar tipo de plan
                                is_recurring = RECURRING_PAYMENTS_ENABLED
                                if 'recurring' in PLANS[plan_id]:
                                    is_recurring = PLANS[plan_id]['recurring']
                                
                                payment_type = "suscripción" if is_recurring else "pago único"
                                
                                # Determinar período basado en la duración
                                if PLANS[plan_id]['duration_days'] <= 7:
                                    period = 'semana'
                                else:
                                    period = 'mes'
                                
                                renewal_text = "(renovación automática)" if is_recurring else "(sin renovación automática)"
                                
                                # Mensaje kawaii para el enlace de pago listo - sin caracteres especiales problemáticos
                                payment_text = (
                                    f"💌 𝗧𝘂 𝗲𝗻𝘁𝗿𝗮𝗱𝗮 𝗲𝘀𝘁á 𝗰𝗮𝘀𝗶 𝗹𝗶𝘀𝘁𝗮 ദ്ദി ˉ꒳ˉ )\n\n"
                                    f"📦 𝗣𝗹𝗮𝗻: {PLANS[plan_id]['display_name']}\n"
                                    f"💰 𝗣𝗿𝗲𝗰𝗶𝗼:【＄{PLANS[plan_id]['price_usd']:.2f} USD 】/ {period} {renewal_text}\n\n"
                                    f"Por favor, haz clic en el botón de aquí abajo para completar tu {payment_type} con PayPal.\n\n"
                                    "Una vez que termines, te daré tu entrada y te dejaré entrar 💌 (˶ˆᗜˆ˵)"
                                )
                                
                                bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    text=payment_text,
                                    reply_markup=markup
                                )
                                logger.info(f"Enlace de pago PayPal creado para usuario {chat_id}, plan {plan_id}")
                            else:
                                # Error al crear enlace de pago
                                markup = types.InlineKeyboardMarkup()
                                markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="view_plans"))
                                
                                bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    text=(
                                        "❌ Lo siento mucho, no pude crear el enlace de pago (ᵒ̴̶̷́ㅿᵒ̴̶̷̀)\n\n"
                                        "Por favor, intenta nuevamente más tarde o contacta a soporte."
                                    ),
                                    reply_markup=markup
                                )
                                logger.error(f"Error al crear enlace de pago PayPal para usuario {chat_id}")
                        except Exception as e:
                            # Asegurar que se detenga la animación en caso de error
                            animation_active = False
                            time.sleep(1)
                            
                            # Mostrar mensaje de error con estilo kawaii
                            markup = types.InlineKeyboardMarkup()
                            markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="view_plans"))
                            
                            bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=f"❌ Ocurrió un error inesperado (。•́︿•̀。)\n\nPor favor, intenta nuevamente más tarde.",
                                reply_markup=markup
                            )
                            logger.error(f"Excepción en proceso de pago: {e}")
                    
                    # Responder al callback para quitar el "reloj de espera" en el cliente
                    bot.answer_callback_query(call.id)
                    logger.info(f"Callback respondido: {call.data}")
                    
                    return 'OK', 200
                    
                except Exception as e:
                    logger.error(f"Error al procesar callback directamente: {str(e)}")
            
            # Código seguro para manejar chat_member
            elif hasattr(update, 'chat_member') and update.chat_member is not None:
                try:
                    chat_id = update.chat_member.chat.id
                    user_id = update.chat_member.new_chat_member.user.id
                    status = update.chat_member.new_chat_member.status
                    old_status = update.chat_member.old_chat_member.status
                    
                    # Si un usuario se unió al grupo
                    if status == 'member' and old_status == 'left':
                        from config import GROUP_CHAT_ID
                        
                        # Verificar si es el grupo VIP
                        if str(chat_id) == str(GROUP_CHAT_ID):
                            # Verificar si el usuario tiene suscripción activa
                            subscription = db.get_active_subscription(user_id)
                            
                            # Omitir administradores
                            if user_id in ADMIN_IDS:
                                logger.info(f"Administrador {user_id} se unió al grupo")
                                return 'OK', 200
                            
                            if not subscription:
                                # No tiene suscripción activa, expulsar
                                logger.warning(f"⚠️ USUARIO SIN SUSCRIPCIÓN DETECTADO: {user_id}")
                                
                                try:
                                    username = update.chat_member.new_chat_member.user.username
                                    first_name = update.chat_member.new_chat_member.user.first_name
                                    
                                    # Enviar mensaje al grupo
                                    bot.send_message(
                                        chat_id=chat_id,
                                        text=f"🛑 SEGURIDAD: Usuario {first_name} (@{username or 'Sin username'}) no tiene suscripción activa y será expulsado automáticamente."
                                    )
                                    
                                    # Expulsar al usuario
                                    logger.info(f"Expulsando a usuario sin suscripción: {user_id}")
                                    bot.ban_chat_member(
                                        chat_id=chat_id,
                                        user_id=user_id
                                    )
                                    
                                    # Desbanear inmediatamente para permitir que vuelva a unirse si obtiene suscripción
                                    bot.unban_chat_member(
                                        chat_id=chat_id,
                                        user_id=user_id,
                                        only_if_banned=True
                                    )
                                    
                                    # Registrar la expulsión
                                    db.record_expulsion(user_id, "Verificación de nuevo miembro - Sin suscripción activa")
                                    
                                    # Enviar mensaje privado al usuario
                                    try:
                                        bot.send_message(
                                            chat_id=user_id,
                                            text=f"SEGURIDAD! 🚨"
                                        )
                                    except Exception as e:
                                        logger.error(f"No se pudo enviar mensaje privado a {user_id}: {e}")
                                        
                                except Exception as e:
                                    logger.error(f"Error al expulsar nuevo miembro no autorizado {user_id}: {e}")
                            else:
                                logger.info(f"Usuario {user_id} se unió al grupo con suscripción válida")
                    
                    # AÑADIR ESTA NUEVA SECCIÓN: Verificar usuarios ya existentes en el grupo
                    elif status == 'member' and old_status == 'member':
                        # Este es un buen momento para verificar si algún usuario con suscripción expirada
                        # sigue en el grupo (puede ocurrir si el bot se reinició)
                        
                        # Usar un hilo separado para no bloquear la respuesta
                        def verify_expired_thread():
                            try:
                                from bot_handlers import force_security_check
                                force_security_check(bot)
                            except Exception as e:
                                logger.error(f"Error en verificación automática: {e}")
                        
                        # Ejecutar la verificación en segundo plano
                        threading.Thread(target=verify_expired_thread, daemon=True).start()
                        logger.info("Iniciada verificación automática en segundo plano")
                
                    return 'OK', 200
                    
                except Exception as e:
                    logger.error(f"Error al procesar chat_member: {str(e)}")
                    return 'OK', 200
            
            # Procesar a través de los handlers normales como respaldo
            bot.process_new_updates([update])
            
            return 'OK', 200
        else:
            return 'Error: Content type is not application/json', 403
    except Exception as e:
        logger.error(f"Error al procesar webhook: {str(e)}")
        return 'Error interno', 500

def verify_all_memberships_on_startup():
    """
    Verifica todas las suscripciones al iniciar el bot y expulsa a los usuarios que ya no deberían estar en el grupo.
    Esta función se llama una sola vez al iniciar el bot.
    """
    try:
        logger.info("🔍 Verificando todas las suscripciones al iniciar...")
        
        # Importar las funciones necesarias
        from bot_handlers import perform_group_security_check
        import database as db
        from config import GROUP_CHAT_ID
        
        # Obtener todas las suscripciones expiradas
        expired_subscriptions = db.check_and_update_subscriptions(force=True)
        
        if expired_subscriptions:
            logger.info(f"Encontradas {len(expired_subscriptions)} suscripciones expiradas")
            
            # Realizar expulsión de usuarios con suscripciones expiradas
            if GROUP_CHAT_ID:
                result = perform_group_security_check(bot, GROUP_CHAT_ID, expired_subscriptions)
                
                if result:
                    logger.info(f"✅ Verificación inicial completada: {len(expired_subscriptions)} suscripciones procesadas")
                else:
                    logger.error("❌ Verificación inicial falló")
            else:
                logger.error("❌ GROUP_CHAT_ID no está configurado. No se puede realizar verificación inicial")
        else:
            logger.info("✅ No hay suscripciones expiradas al iniciar")
            
    except Exception as e:
        logger.error(f"Error en verificación inicial: {e}")


# Añade esta función a app.py, justo antes o después de la función webhook
def handle_whitelist_command(message, bot):
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
        
        # Extraer el comando
        command_parts = message.text.split()
        
        # Si es solo "/whitelist", mostrar instrucciones
        if len(command_parts) == 1:
            help_text = (
                "ℹ️ *Comandos de Whitelist*\n\n"
                "Para añadir un usuario:\n"
                "`/whitelist USER_ID` - Añade un usuario a la whitelist\n\n"
                "Para ver usuarios en whitelist:\n"
                "`/whitelist list` - Muestra los usuarios en whitelist\n\n"
                "Ejemplo: `/whitelist 1234567890`"
            )
            bot.send_message(
                chat_id=chat_id,
                text=help_text,
                parse_mode='Markdown'
            )
            return
            
        # Si es "/whitelist list", redireccionar a la función específica
        if len(command_parts) == 2 and command_parts[1].lower() == 'list':
            bot_handlers.handle_whitelist_list(message, bot)
            return
            
        # Comando para añadir a un usuario
        if len(command_parts) >= 2:
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
                "🛡️ *Administración - Añadir a Whitelist*\n\n"
                f"👤 Usuario: {full_name}\n"
                f"🔤 Username: @{username_display}\n"
                f"🆔 ID: `{target_user_id}`\n\n"
                "⏱️ Por favor, ingresa la duración del acceso:\n"
                "Ejemplos: `10 minutes`, `5 hours`, `2 days`, `1 week`, `1 month`"
            )
            
            # Crear markup con solo botón de cancelar
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="whitelist_cancel"))
            
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
                parse_mode='Markdown',
                reply_markup=markup
            )
            
            # Guardar ID del mensaje enviado
            admin_states[admin_id]['message_id'] = sent_message.message_id
            
            # Registrar el próximo paso: esperar duración
            bot.register_next_step_handler(message, lambda msg: bot_handlers.handle_whitelist_duration(msg, bot))
            
        else:
            bot.send_message(
                chat_id=chat_id,
                text="❌ Uso incorrecto. Por favor, usa `/whitelist USER_ID`",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Error en handle_whitelist_command: {str(e)}")
        bot.send_message(
            chat_id=message.chat.id,
            text=f"❌ Ocurrió un error al procesar tu solicitud: {str(e)}. Por favor, intenta nuevamente."
        )

@app.route('/admin/reset-webhook')
def reset_webhook_endpoint():
    """Endpoint para reiniciar el webhook (solo uso administrativo)"""
    try:
        # Importar y ejecutar las funciones del script reset_webhook.py
        from reset_webhook import verify_bot, delete_webhook, set_new_webhook, get_webhook_info
        
        results = {
            "bot_verified": verify_bot(),
            "webhook_deleted": delete_webhook(),
            "webhook_set": set_new_webhook(),
            "webhook_info": get_webhook_info()
        }
        
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error al reiniciar webhook: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/get-telegram-user', methods=['GET'])
def get_telegram_user():
    """Endpoint para obtener información de un usuario de Telegram"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            logger.warning(f"Intento de acceso no autorizado: {admin_id}")
            return jsonify({"success": False, "error": "Acceso no autorizado"}), 401
        
        # Este endpoint puede usarse para obtener información de cualquier usuario de Telegram
        target_user_id = request.args.get('user_id', admin_id)  # Si no se especifica user_id, usa admin_id
        
        # Verificar si el BOT_TOKEN está configurado
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN no está configurado para acceder a la API de Telegram")
            return jsonify({
                "success": False, 
                "error": "Configuración del bot incorrecta"
            })
        
        # Usar la API de Telegram para obtener información del usuario
        import requests
        
        # Primero intentamos obtener información del chat
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
        params = {"chat_id": target_user_id}
        
        logger.info(f"Consultando API de Telegram para usuario {target_user_id}")
        response = requests.get(api_url, params=params)
        
        if response.status_code != 200:
            logger.error(f"Error al consultar API de Telegram: {response.status_code}, {response.text}")
            return jsonify({
                "success": False,
                "error": f"Error API Telegram: {response.text[:100]}..."
            })
        
        # Procesar la respuesta
        chat_data = response.json()
        
        if not chat_data.get('ok'):
            logger.error(f"API de Telegram respondió error: {chat_data.get('description')}")
            return jsonify({
                "success": False,
                "error": chat_data.get('description', 'Error desconocido')
            })
            
        # Obtener los datos del usuario
        result = chat_data.get('result', {})
        
        # Preparar datos básicos
        user_info = {
            "success": True,
            "user_id": target_user_id,
            "username": result.get('username'),
            "first_name": result.get('first_name'),
            "last_name": result.get('last_name'),
            "photo_url": None
        }
        
        # Intentar obtener la foto de perfil
        try:
            # Solo si hay un objeto de foto de perfil
            if result.get('photo'):
                # Obtener la foto de perfil más reciente del usuario (foto pequeña)
                photos_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos"
                photos_params = {"user_id": target_user_id, "limit": 1}
                
                photos_response = requests.get(photos_url, params=photos_params)
                photos_data = photos_response.json()
                
                if photos_data.get('ok') and photos_data.get('result', {}).get('total_count', 0) > 0:
                    # Obtener el file_id de la primera foto (la más reciente)
                    photo = photos_data['result']['photos'][0][0]  # [0][0] es la foto más pequeña
                    file_id = photo.get('file_id')
                    
                    # Obtener información del archivo
                    file_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile"
                    file_params = {"file_id": file_id}
                    
                    file_response = requests.get(file_url, params=file_params)
                    file_data = file_response.json()
                    
                    if file_data.get('ok'):
                        file_path = file_data['result']['file_path']
                        
                        # Construir URL de la foto
                        photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                        user_info["photo_url"] = photo_url
        except Exception as e:
            logger.error(f"Error al obtener foto de perfil: {str(e)}")
            # No fallamos todo el proceso si solo falla la foto
        
        return jsonify(user_info)
        
    except Exception as e:
        logger.error(f"Error en get_telegram_user: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500



    
@app.route('/admin/renewal-stats', methods=['GET'])
def admin_renewal_stats():
    """Endpoint para obtener estadísticas de renovaciones"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Obtener estadísticas de renovaciones
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Total de renovaciones
        cursor.execute("SELECT COUNT(*) FROM subscription_renewals")
        total_renewals = cursor.fetchone()[0]
        
        # Renovaciones en los últimos 30 días
        cursor.execute("""
        SELECT COUNT(*) FROM subscription_renewals
        WHERE renewal_date >= datetime('now', '-30 day')
        """)
        last_30_days = cursor.fetchone()[0]
        
        # Renovaciones en los últimos 7 días
        cursor.execute("""
        SELECT COUNT(*) FROM subscription_renewals
        WHERE renewal_date >= datetime('now', '-7 day')
        """)
        last_7_days = cursor.fetchone()[0]
        
        # Renovaciones por plan
        cursor.execute("""
        SELECT plan, COUNT(*) as count
        FROM subscription_renewals
        GROUP BY plan
        ORDER BY count DESC
        """)
        plans = {}
        for row in cursor.fetchall():
            plans[row[0]] = row[1]
        
        # Próximas renovaciones en los siguientes 7 días
        cursor.execute("""
        SELECT COUNT(*) FROM subscriptions
        WHERE status = 'ACTIVE'
        AND is_recurring = 1
        AND date(end_date) BETWEEN date('now') AND date('now', '+7 day')
        """)
        upcoming_7_days = cursor.fetchone()[0]
        
        # Últimas 10 renovaciones
        cursor.execute("""
        SELECT sr.*, u.username
        FROM subscription_renewals sr
        JOIN users u ON sr.user_id = u.user_id
        ORDER BY sr.renewal_date DESC
        LIMIT 10
        """)
        recent = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        conn.close()
        
        # Compilar estadísticas
        stats = {
            "total": total_renewals,
            "last_30_days": last_30_days,
            "last_7_days": last_7_days,
            "by_plan": plans,
            "upcoming_7_days": upcoming_7_days,
            "recent": recent
        }
        
        return jsonify({
            "success": True,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error al obtener estadísticas de renovaciones: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/paypal', methods=['POST'])
def paypal_webhook():
    """Maneja los webhooks de PayPal"""
    try:
        import datetime
        import database as db
        import json
        
        event_data = request.json
        event_type = event_data.get("event_type", "DESCONOCIDO")
        
        # Log detallado para diagnóstico
        logger.info(f"PayPal webhook recibido: {event_type}")
        logger.info(f"Contenido del webhook: {json.dumps(event_data, indent=2)}")
        
        # Extraer IDs relevantes para deduplicación
        resource = event_data.get("resource", {})
        
        # Extraer IDs de forma consistente para todos los tipos de eventos
        payment_id = resource.get("id", "")
        billing_agreement_id = resource.get("billing_agreement_id", "")
        
        # Si es BILLING.SUBSCRIPTION.ACTIVATED, usar el ID de resource directamente
        if not billing_agreement_id and event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            billing_agreement_id = resource.get("id", "")
            
        # CORRECCIÓN: Para eventos de cancelación, asegurarnos de obtener el ID correcto
        if not billing_agreement_id and event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            billing_agreement_id = resource.get("id", "")
            logger.info(f"Usando ID directo para cancelación: {billing_agreement_id}")
        
        # Usar billing_agreement_id como payment_id si existe, sino usar el ID del recurso
        payment_id = billing_agreement_id or payment_id
        
        if not payment_id:
            logger.error(f"No se pudo extraer un ID válido del evento {event_type}")
            return jsonify({"status": "error", "message": "ID de pago no encontrado"}), 400
        
        # Verificar si este evento ya fue procesado
        if db.is_payment_processed(payment_id, event_type):
            logger.info(f"Evento ya procesado anteriormente, omitiendo: {payment_id} ({event_type})")
            return jsonify({"status": "success", "message": "Evento ya procesado"}), 200
            
        # ----- Procesar BILLING.SUBSCRIPTION.CANCELLED -----
        if event_type == "BILLING.SUBSCRIPTION.CANCELLED" and billing_agreement_id:
            # Registrar evento de cancelación para diagnóstico
            logger.info(f"⚠️ EVENTO DE CANCELACIÓN RECIBIDO: {event_type} para suscripción {billing_agreement_id}")
            
            # Obtener la suscripción
            subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
            
            if subscription:
                logger.info(f"Procesando cancelación: Subscription ID {subscription['sub_id']}, User ID: {subscription['user_id']}")
                
                # 1. Actualizar estado en BD
                db.update_subscription_status(subscription['sub_id'], "CANCELLED")
                logger.info(f"Estado de suscripción {subscription['sub_id']} actualizado a CANCELLED")
                
                # 2. Expulsar usuario
                user_id = subscription['user_id']
                try:
                    from config import GROUP_CHAT_ID, ADMIN_IDS
                    
                    # No expulsar administradores
                    if user_id in ADMIN_IDS:
                        logger.info(f"No se expulsa al admin {user_id}")
                    elif GROUP_CHAT_ID:
                        logger.info(f"Intentando expulsar al usuario {user_id} del grupo {GROUP_CHAT_ID}")
                        
                        # MEJORA: Implementar mecanismo de reintentos más robusto
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                # Expulsar usuario directamente
                                logger.info(f"Intento {attempt+1}/{max_retries} de expulsión para usuario {user_id}")
                                bot.ban_chat_member(
                                    chat_id=GROUP_CHAT_ID,
                                    user_id=user_id,
                                    revoke_messages=False
                                )
                                logger.info(f"Usuario {user_id} expulsado exitosamente")
                                
                                # Desbanear para permitir reingreso futuro
                                bot.unban_chat_member(
                                    chat_id=GROUP_CHAT_ID,
                                    user_id=user_id,
                                    only_if_banned=True
                                )
                                logger.info(f"Usuario {user_id} desbaneado exitosamente")
                                
                                # Registrar expulsión
                                db.record_expulsion(user_id, "Cancelación de suscripción (webhook)")
                                logger.info(f"Expulsión registrada para usuario {user_id}")
                                break
                            except Exception as e:
                                logger.error(f"Error en intento {attempt+1} al expulsar usuario {user_id}: {e}")
                                if attempt < max_retries - 1:
                                    time.sleep(2)  # Esperar antes de reintentar
                        
                        # MEJORA: Si después de los reintentos no se pudo expulsar, registrar el fallo para procesamiento posterior
                        if attempt == max_retries - 1:
                            db.record_failed_expulsion(user_id, "Cancelación de suscripción", str(e))
                            logger.warning(f"Se registró la expulsión fallida del usuario {user_id} para procesamiento posterior")
                except Exception as e:
                    logger.error(f"Error general al intentar expulsar al usuario {user_id}: {e}")
                    # Registrar el fallo para procesamiento posterior
                    db.record_failed_expulsion(user_id, "Cancelación de suscripción", str(e))
                
                # 3. Notificar al usuario
                try:
                    bot.send_message(
                        chat_id=user_id,
                        text=(
                            "💔 *¡Oh no! Tu suscripción ha sido cancelada* (｡•́︿•̀｡)\n\n"
                            "Has sido removido del Grupo VIP... Te vamos a extrañar mucho (｡T ω T｡)\n\n"
                            "Si quieres regresar y ser parte otra vez del Grupo VIP, "
                            "usa el comando /start para ver los planes disponibles ✨💌\n"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error al notificar cancelación a usuario {user_id}: {e}")
                
                # 4. Forzar verificación de seguridad 
                try:
                    import bot_handlers
                    # MEJORA: Pasar el ID de usuario cancelado para priorizar su verificación
                    bot_handlers.force_security_check(bot, [user_id])
                    logger.info(f"Verificación de seguridad forzada después de cancelación de suscripción {subscription['sub_id']}")
                except Exception as e:
                    logger.error(f"Error al forzar verificación: {e}")
                
                # Marcar evento como procesado
                db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                
                return jsonify({"status": "success", "message": "Cancelación procesada exitosamente"}), 200
            else:
                logger.error(f"No se encontró suscripción para ID: {billing_agreement_id}")
                
        # ----- Procesar PAYMENT.SALE.COMPLETED (Renovaciones) -----        
        elif event_type == "PAYMENT.SALE.COMPLETED":
            if billing_agreement_id:
                subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
                
                if subscription:
                    logger.info(f"Procesando renovación para suscripción {subscription['sub_id']}")
                    
                    # Verificar que este pago específico no haya sido aplicado a esta suscripción
                    if not db.is_payment_processed(payment_id, event_type):
                        # IMPORTANTE: Verificar si este pago es para la creación inicial 
                        # o para una renovación real
                        start_date_str = subscription.get('start_date')
                        
                        # Asegurar que estamos manejando correctamente las zonas horarias
                        if start_date_str:
                            start_date = datetime.datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                            if '+' not in start_date_str and 'Z' not in start_date_str:
                                # Si no tiene zona horaria, asumimos que es UTC
                                start_date = start_date.replace(tzinfo=datetime.timezone.utc)
                        else:
                            # Si no hay start_date, usar la fecha actual
                            start_date = datetime.datetime.now(datetime.timezone.utc)
                        
                        now = datetime.datetime.now(datetime.timezone.utc)
                        time_difference = (now - start_date).total_seconds()
                        
                        # Si la suscripción se creó recientemente, es parte del proceso inicial
                        # Aumentamos el margen a 15 minutos para ser más conservadores
                        is_initial_payment = time_difference < 900  # 15 minutos
                        
                        if is_initial_payment:
                            logger.info(f"Este es el pago inicial de la suscripción {subscription['sub_id']}, NO extendiendo")
                            
                            # Marcar el evento como procesado para evitar duplicados
                            db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                            
                            return jsonify({"status": "success", "message": "Pago inicial procesado"}), 200
                        
                        # Si llegamos aquí, es una renovación real
                        from config import PLANS
                        plan_id = subscription['plan']
                        plan = PLANS.get(plan_id)
                        
                        if plan:
                            # IMPORTANTE: Usar el cálculo preciso de horas para evitar duplicaciones
                            plan_days = plan['duration_days']
                            plan_hours = int(plan_days * 24)
                            
                            # Determinar fecha base para extensión
                            end_date_str = subscription.get('end_date')
                            if end_date_str:
                                # Normalizar la fecha final para asegurar formato UTC
                                if '+' in end_date_str or 'Z' in end_date_str:
                                    # Ya tiene zona horaria, eliminar Z si existe y reemplazar con +00:00
                                    current_end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                                else:
                                    # No tiene zona horaria, asumimos que es UTC
                                    current_end_date = datetime.datetime.fromisoformat(end_date_str)
                                    current_end_date = current_end_date.replace(tzinfo=datetime.timezone.utc)
                            else:
                                # Si no hay end_date, usar la fecha actual + 1 día
                                current_end_date = now + datetime.timedelta(days=1)
                            
                            # Verificar si la fecha ya expiró
                            if current_end_date < now:
                                # Ya expiró, calcular desde ahora
                                new_end_date = now + datetime.timedelta(hours=plan_hours)
                                logger.info(f"Suscripción expirada: Calculando desde ahora, horas={plan_hours}")
                            else:
                                # Aún activa, extender desde la fecha actual
                                new_end_date = current_end_date + datetime.timedelta(hours=plan_hours)
                                logger.info(f"Suscripción activa: Extendiendo desde fecha actual, horas={plan_hours}")
                            
                            # Extender la suscripción
                            db.extend_subscription(subscription['sub_id'], new_end_date)
                            logger.info(f"Suscripción {subscription['sub_id']} extendida hasta {new_end_date}")
                            
                            # Intentar notificar al usuario
                            try:
                                import payments as pay
                                pay.notify_successful_renewal(bot, subscription['user_id'], subscription, new_end_date)
                            except Exception as notify_error:
                                logger.error(f"Error al notificar renovación: {notify_error}")
                            
                            # Registrar renovación en historial
                            try:
                                payment_amount = float(resource.get("amount", {}).get("total", plan['price_usd']))
                                db.record_subscription_renewal(
                                    subscription['sub_id'], 
                                    subscription['user_id'],
                                    plan_id,
                                    payment_amount,
                                    current_end_date,
                                    new_end_date,
                                    payment_id,
                                    "COMPLETED"
                                )
                            except Exception as record_error:
                                logger.error(f"Error al registrar renovación en historial: {record_error}")
                        else:
                            logger.error(f"Plan no encontrado: {plan_id}")
                        
                        # Marcar evento como procesado
                        db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                    else:
                        logger.info(f"Pago {payment_id} ya aplicado a suscripción {subscription['sub_id']}, omitiendo")
                    
                    return jsonify({"status": "success", "message": "Renovación procesada"}), 200
                else:
                    logger.warning(f"No se encontró suscripción para billing_id {billing_agreement_id}")
            else:
                logger.warning(f"Evento PAYMENT.SALE.COMPLETED sin billing_agreement_id")
        
        # ----- Procesar BILLING.SUBSCRIPTION.ACTIVATED -----
        elif event_type == "BILLING.SUBSCRIPTION.ACTIVATED" and billing_agreement_id:
            subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
            
            if subscription:
                logger.info(f"Procesando activación para suscripción {subscription['sub_id']}")
                
                # Verificar si el estatus actual no es ACTIVE
                if subscription.get('status') != 'ACTIVE':
                    # Actualizar a estado ACTIVE
                    db.update_subscription_status(subscription['sub_id'], "ACTIVE")
                    logger.info(f"Suscripción {subscription['sub_id']} actualizada a ACTIVE")
                
                # Marcar evento como procesado
                db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                
                return jsonify({"status": "success", "message": "Activación procesada exitosamente"}), 200
            else:
                logger.warning(f"No se encontró suscripción para ID: {billing_agreement_id}")
        
        # ----- Procesar BILLING.SUBSCRIPTION.SUSPENDED -----
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED" and billing_agreement_id:
            subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
            
            if subscription:
                logger.info(f"Procesando suspensión para suscripción {subscription['sub_id']}")
                
                # Actualizar estado en BD
                db.update_subscription_status(subscription['sub_id'], "SUSPENDED")
                
                # Notificar al usuario
                try:
                    user_id = subscription.get('user_id')
                    if user_id:
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
                    logger.error(f"Error al notificar suspensión a usuario: {e}")
                
                # Marcar evento como procesado
                db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                
                return jsonify({"status": "success", "message": "Suspensión procesada exitosamente"}), 200
            else:
                logger.warning(f"No se encontró suscripción para ID: {billing_agreement_id}")
        
        # ----- Procesar BILLING.SUBSCRIPTION.PAYMENT.FAILED -----
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED" and billing_agreement_id:
            subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
            
            if subscription:
                logger.info(f"Procesando fallo de pago para suscripción {subscription['sub_id']}")
                
                # Notificar al usuario sobre el pago fallido
                try:
                    user_id = subscription.get('user_id')
                    if user_id:
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
                    logger.error(f"Error al notificar pago fallido a usuario: {e}")
                
                # Marcar evento como procesado
                db.mark_payment_processed(payment_id, event_type, subscription['sub_id'])
                
                return jsonify({"status": "success", "message": "Fallo de pago procesado exitosamente"}), 200
            else:
                logger.warning(f"No se encontró suscripción para ID: {billing_agreement_id}")
        
        # ----- Procesar otros tipos de evento -----
        # Marcar el evento como procesado de todas formas
        db.mark_payment_processed(payment_id, event_type)
        
        return jsonify({"status": "success", "message": f"Evento {event_type} registrado"}), 200
        
    except Exception as e:
        logger.error(f"Error al procesar webhook de PayPal: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
        
@app.route('/admin/panel')
def admin_panel():
    """Renderiza el panel de administración"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Obtener estadísticas para el panel
        conn = db.get_db_connection()
        
        stats = {
            "usuarios": db.get_total_users_count(conn),
            "suscripciones": db.get_table_count(conn, "subscriptions"),
            "suscripciones_activas": db.get_active_subscriptions_count(conn),
            "enlaces_invitacion": db.get_table_count(conn, "invite_links")
        }
        
        # Obtener últimas 5 suscripciones con estado corregido
        cursor = conn.cursor()
        cursor.execute("""
        SELECT s.sub_id, s.user_id, u.username, s.plan, s.price_usd, s.start_date, s.end_date, 
            s.status, s.is_recurring, s.paypal_sub_id,
            (SELECT COUNT(*) FROM subscription_renewals sr 
            WHERE sr.sub_id = s.sub_id AND sr.renewal_date >= datetime('now', '-36 hour')) as renovaciones_recientes
        FROM subscriptions s
        LEFT JOIN users u ON s.user_id = u.user_id
        ORDER BY s.start_date DESC
        LIMIT 5
        """)
        recent_subscriptions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        # Obtener usuarios recientes
        cursor.execute("""
        SELECT user_id, username, first_name, last_name, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 5
        """)
        recent_users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        conn.close()
        
        import datetime
        now = datetime.datetime.now()

        # Renderizar el template con los datos
        return render_template('admin_panel.html', 
                               admin_id=admin_id,
                               stats=stats,
                               recent_subscriptions=recent_subscriptions,
                               recent_users=recent_users,
                               now=now, grace_period=SUBSCRIPTION_GRACE_PERIOD_HOURS) 
        
    except Exception as e:
        logger.error(f"Error en admin_panel: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/force-security-check', methods=['GET'])
def admin_force_security_check_endpoint():
    """Endpoint para forzar una verificación de seguridad"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Importar la función desde bot_handlers
        from bot_handlers import force_security_check
        
        # Ejecutar la verificación
        result = force_security_check(bot)
        
        if result:
            return jsonify({
                "success": True,
                "message": "Verificación de seguridad ejecutada exitosamente"
            })
        else:
            return jsonify({
                "success": False,
                "error": "La verificación de seguridad falló. Revise los logs para más detalles."
            }), 500
        
    except Exception as e:
        logger.error(f"Error en endpoint de verificación de seguridad: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Modificación 2: Añadir un endpoint para revisar y reiniciar el hilo de seguridad
# Añade esto después del endpoint anterior:

@app.route('/admin/check-security-thread', methods=['GET'])
def admin_check_security_thread():
    """Endpoint para verificar y reiniciar el hilo de seguridad si es necesario"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Importar la función desde bot_handlers
        from bot_handlers import check_security_thread_status, security_thread_running
        
        # Verificar el estado actual
        current_status = security_thread_running
        
        # Intentar reiniciar el hilo si es necesario
        if not current_status:
            result = check_security_thread_status(bot)
            new_status = security_thread_running
        else:
            result = True
            new_status = current_status
        
        return jsonify({
            "success": True,
            "previous_status": current_status,
            "current_status": new_status,
            "restarted": not current_status and new_status,
            "message": "Hilo de seguridad verificado" + (" y reiniciado" if not current_status and new_status else "")
        })
        
    except Exception as e:
        logger.error(f"Error en endpoint de verificación de hilo: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Modificación 3: Añadir una ruta para obtener el estado de las suscripciones expiradas
# Añade esto después del endpoint anterior:

@app.route('/admin/expired-subscriptions', methods=['GET'])
def admin_expired_subscriptions():
    """Endpoint para obtener información sobre suscripciones expiradas"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Importar la función desde database
        import database as db
        
        # Obtener las suscripciones expiradas
        expired_subscriptions = db.check_and_update_subscriptions(force=True)
        
        # Obtener información detallada de cada suscripción
        detailed_info = []
        for user_id, sub_id, plan in expired_subscriptions:
            # Obtener información del usuario
            user = db.get_user(user_id)
            
            # Obtener información de la suscripción
            subscription = db.get_subscription_info(sub_id)
            
            if user and subscription:
                detailed_info.append({
                    "user_id": user_id,
                    "username": user.get('username', 'Sin username'),
                    "first_name": user.get('first_name', ''),
                    "last_name": user.get('last_name', ''),
                    "sub_id": sub_id,
                    "plan": plan,
                    "start_date": subscription.get('start_date', ''),
                    "end_date": subscription.get('end_date', ''),
                    "status": subscription.get('status', ''),
                    "is_whitelist": db.is_whitelist_subscription(sub_id)
                })
        
        return jsonify({
            "success": True,
            "count": len(expired_subscriptions),
            "subscriptions": detailed_info
        })
        
    except Exception as e:
        logger.error(f"Error en endpoint de suscripciones expiradas: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Añadir endpoint para descargar base de datos
@app.route('/admin/download-database')
def download_database():
    """Permite descargar una copia de la base de datos"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Devolver el archivo de la base de datos
        return send_file(DB_PATH, 
                        mimetype='application/octet-stream',
                        as_attachment=True,
                        download_name='vip_bot_backup.db')
        
    except Exception as e:
        logger.error(f"Error al descargar base de datos: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/paypal/return', methods=['GET'])
def paypal_return():
    """Maneja el retorno desde PayPal después de un pago exitoso (suscripción o pago único)"""
    try:
        # Obtener parámetros
        user_id = request.args.get('user_id')
        plan_id = request.args.get('plan_id')
        payment_type = request.args.get('payment_type', 'subscription')  # Default to subscription for backward compatibility
        
        if not all([user_id, plan_id]):
            return render_template('webhook_success.html', 
                                  message="Parámetros incompletos. Por favor, contacta a soporte."), 400
        
        # Procesar de manera diferente según el tipo de pago
        if payment_type == 'subscription':
            # Verificar información de la suscripción
            subscription_id = request.args.get('subscription_id')
            
            if not subscription_id:
                return render_template('webhook_success.html', 
                                      message="ID de suscripción no proporcionado. Por favor, contacta a soporte."), 400
            
            # Verificar suscripción con PayPal
            subscription_details = pay.verify_subscription(subscription_id)
            if not subscription_details:
                return render_template('webhook_success.html', 
                                      message="No se pudo verificar la suscripción. Por favor, contacta a soporte."), 400
            
            # Determinar el tipo de pago
            payment_type_name = "suscripción" if payment_type == 'subscription' else "pago único"
            
            # Procesar la suscripción exitosa
            success = bot_handlers.process_successful_subscription(
                bot, int(user_id), plan_id, subscription_id, subscription_details, is_recurring=True
            )
            
        elif payment_type == 'order':
            # ... (código existente para pagos únicos)
            order_id = request.args.get('token')
            
            if not order_id:
                return render_template('webhook_success.html', 
                                      message="ID de orden no proporcionado. Por favor, contacta a soporte."), 400
            
            # Verificar y capturar la orden
            order_details = pay.verify_and_capture_order(order_id)
            if not order_details:
                return render_template('webhook_success.html', 
                                      message="No se pudo verificar o capturar el pago. Por favor, contacta a soporte."), 400
            
            # Verificar si el pago fue completado
            if order_details.get('status') != 'COMPLETED':
                return render_template('webhook_success.html', 
                                      message=f"El pago no está completo. Estado actual: {order_details.get('status')}. Por favor, contacta a soporte."), 400
            
            # Determinar el tipo de pago
            payment_type_name = "pago único"
            
            # Procesar el pago único exitoso
            success = bot_handlers.process_successful_subscription(
                bot, int(user_id), plan_id, order_id, order_details, is_recurring=False
            )
        
        else:
            return render_template('webhook_success.html', 
                                  message=f"Tipo de pago no reconocido: {payment_type}. Por favor, contacta a soporte."), 400
        
        if success:
            return render_template('webhook_success.html', 
                                  message=f"¡{payment_type_name.capitalize()} exitoso! Puedes volver a Telegram."), 200
        else:
            return render_template('webhook_success.html', 
                                  message=f"Error al procesar el {payment_type_name}. Por favor, contacta a soporte."), 500
    
    except Exception as e:
        logger.error(f"Error en el retorno de PayPal: {str(e)}")
        return render_template('webhook_success.html', 
                              message=f"Error: {str(e)}. Por favor, contacta a soporte."), 500

@app.route('/paypal/cancel', methods=['GET'])
def paypal_cancel():
    """Maneja la cancelación de suscripción desde PayPal"""
    try:
        # Obtener los parámetros
        user_id = request.args.get('user_id')
        
        # Informar al usuario que canceló la suscripción
        if user_id:
            try:
                bot.send_message(int(user_id), 
                               "❌ Has cancelado el proceso de suscripción. Si deseas intentarlo nuevamente, usa el comando /start.")
            except Exception as e:
                logger.error(f"Error al enviar mensaje de cancelación: {str(e)}")
        
        return render_template('webhook_success.html', 
                              message="Suscripción cancelada. Puedes volver a Telegram."), 200
    
    except Exception as e:
        logger.error(f"Error en la cancelación de PayPal: {str(e)}")
        return render_template('webhook_success.html', 
                              message=f"Error: {str(e)}. Puedes volver a Telegram."), 500

@app.route('/admin/paypal-diagnostic', methods=['GET'])
def paypal_diagnostic():
    """Endpoint para diagnosticar la conexión con PayPal"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Comprobar credenciales de PayPal
        results = {
            "paypal_mode": pay.PAYPAL_MODE,
            "base_url": pay.BASE_URL,
            "client_id_valid": bool(pay.PAYPAL_CLIENT_ID) and len(pay.PAYPAL_CLIENT_ID) > 10,
            "client_secret_valid": bool(pay.PAYPAL_CLIENT_SECRET) and len(pay.PAYPAL_CLIENT_SECRET) > 10,
            "webhook_url": WEBHOOK_URL,
        }
        
        # Probar obtención de token
        token = pay.get_access_token()
        results["token_obtained"] = bool(token)
        
        if token:
            # Intentar listar productos existentes
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(f"{pay.BASE_URL}/v1/catalogs/products?page_size=10", headers=headers)
            results["products_api_status"] = response.status_code
            
            if response.status_code == 200:
                products = response.json().get('products', [])
                results["existing_products"] = [
                    {"id": p.get("id"), "name": p.get("name")} 
                    for p in products[:5]  # Mostrar solo los primeros 5
                ]
                
                # Si hay productos existentes, intentar forzar la reutilización
                if products:
                    product_id_file = os.path.join(os.path.dirname(DB_PATH), 'paypal_product_id.txt')
                    os.makedirs(os.path.dirname(product_id_file), exist_ok=True)
                    with open(product_id_file, 'w') as f:
                        f.write(products[0].get("id", ""))
                    results["product_id_saved"] = products[0].get("id", "")
            else:
                results["products_api_error"] = response.text[:200]
            
            # Probar creación de producto (solo si no hay productos existentes)
            if response.status_code != 200 or not response.json().get('products', []):
                product_id = pay.create_product_if_not_exists()
                results["product_creation"] = bool(product_id)
                if product_id:
                    results["created_product_id"] = product_id
                
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error en diagnóstico de PayPal: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/check-renewals', methods=['GET'])
def admin_check_renewals():
    """Endpoint para forzar una verificación de renovaciones pendientes"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Importar función desde payments
        import payments as pay
        
        # Ejecutar la verificación
        notified, errors = pay.process_subscription_renewals(bot)
        
        if notified >= 0:  # Consideramos éxito incluso si no hay notificaciones
            return jsonify({
                "success": True,
                "message": f"Verificación de renovaciones ejecutada: {notified} notificadas, {errors} errores"
            })
        else:
            return jsonify({
                "success": False,
                "error": "La verificación de renovaciones falló. Revise los logs para más detalles."
            }), 500
        
    except Exception as e:
        logger.error(f"Error en endpoint de verificación de renovaciones: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/database', methods=['GET', 'POST'])
def admin_database():
    """Endpoint para ver y consultar la base de datos"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Obtener todas las tablas de la base de datos
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Obtener lista de tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table[0] for table in cursor.fetchall()]
        
        if request.method == 'POST':
            # Si se envía una consulta SQL, ejecutarla
            query = request.form.get('query', '')
            if query:
                try:
                    cursor.execute(query)
                    # Verificar si es una consulta SELECT
                    if query.strip().upper().startswith('SELECT'):
                        columns = [description[0] for description in cursor.description]
                        results = cursor.fetchall()
                        results_list = [dict(zip(columns, row)) for row in results]
                        return jsonify({
                            "tables": tables,
                            "query": query,
                            "columns": columns,
                            "results": results_list,
                            "count": len(results_list)
                        })
                    else:
                        conn.commit()
                        return jsonify({
                            "tables": tables,
                            "query": query,
                            "message": "Consulta ejecutada correctamente",
                            "rows_affected": cursor.rowcount
                        })
                except Exception as e:
                    return jsonify({
                        "tables": tables,
                        "query": query,
                        "error": str(e)
                    }), 400
        
        # Consultas predefinidas
        stats = {
            "usuarios": db.get_total_users_count(conn),
            "suscripciones": db.get_table_count(conn, "subscriptions"),
            "suscripciones_activas": db.get_active_subscriptions_count(conn),
            "enlaces_invitacion": db.get_table_count(conn, "invite_links")
        }
        
        # Obtener últimas 5 suscripciones
        cursor.execute("""
        SELECT s.sub_id, s.user_id, u.username, s.plan, s.price_usd, s.start_date, s.end_date, s.status
        FROM subscriptions s
        LEFT JOIN users u ON s.user_id = u.user_id
        ORDER BY s.start_date DESC
        LIMIT 5
        """)
        recent_subscriptions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            "tables": tables,
            "stats": stats,
            "recent_subscriptions": recent_subscriptions
        })
        
    except Exception as e:
        logger.error(f"Error en admin_database: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
from bot_handlers import schedule_security_verification, force_security_check, schedule_renewal_checks,  register_handlers

# 3. Modificar la función initialize_security para iniciar también las renovaciones
def initialize_security():
    """Inicializa el sistema de seguridad y renovaciones al iniciar"""
    try:
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info("🔐 Inicializando sistema de seguridad y renovaciones...")
        
        # Registrar handlers del bot
        register_handlers(bot)
        logger.info("✅ Handlers registrados correctamente")
        
        # Realizar verificación inicial completa de membresías
        from app import verify_all_memberships_on_startup
        verify_all_memberships_on_startup()
        logger.info("✅ Verificación inicial de membresías completada")
        
        # Iniciar hilo de verificación periódica de seguridad
        schedule_security_verification(bot)
        
        # NUEVO: Iniciar hilo de verificación periódica de renovaciones
        schedule_renewal_checks(bot)
        
        # Forzar una verificación inicial
        force_security_check(bot)
        
        logger.info("✅ Sistema de seguridad y renovaciones inicializado correctamente")
        
        # Notificar a los administradores
        from config import ADMIN_IDS
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text="🔐 Bot reiniciado y sistema de seguridad inicializado correctamente.\n"
                         "Se ha iniciado la verificación periódica de suscripciones y renovaciones automáticas."
                )
            except Exception as e:
                logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Error al inicializar sistema de seguridad y renovaciones: {e}")
        
        # Intentar notificar a los administradores sobre el error
        from config import ADMIN_IDS
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ ERROR AL INICIALIZAR SEGURIDAD Y RENOVACIONES: {e}\n"
                         "El bot está activo pero los sistemas automáticos podrían no funcionar correctamente."
                )
            except:
                pass

# AÑADE esta línea al final del archivo para llamar a la función
# directamente cuando la aplicación arranca
initialize_security()