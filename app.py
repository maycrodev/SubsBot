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
from config import BOT_TOKEN, PORT, WEBHOOK_URL, ADMIN_IDS, PLANS, DB_PATH

admin_states = {}

# Luego importa bot_handlers
import bot_handlers

# Y asigna admin_states en bot_handlers
bot_handlers.admin_states = admin_states

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                        # Mostrar planes
                        plans_text = (
                            "💸 Escoge tu plan de suscripción:\n\n"
                            "🔹 Plan Semanal: $3.50 / 1 semana\n"
                            "🔸 Plan Mensual: $5.00 / 1 mes\n\n"
                            "🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇"
                        )
                        
                        markup = types.InlineKeyboardMarkup(row_width=2)
                        markup.add(types.InlineKeyboardButton("🎥 Tutorial de Pagos", callback_data="tutorial"))
                        markup.add(
                            types.InlineKeyboardButton("🗓️ Plan Semanal", callback_data="weekly_plan"),
                            types.InlineKeyboardButton("📆 Plan Mensual", callback_data="monthly_plan")
                        )
                        markup.add(types.InlineKeyboardButton("🔙 Atrás", callback_data="back_to_main"))
                        
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=plans_text,
                            reply_markup=markup
                        )
                        logger.info(f"Planes mostrados a usuario {chat_id}")
                    
                    elif call.data == "tutorial":
                        # Mostrar tutorial de pagos
                        tutorial_text = (
                            "🎥 Tutorial de Pagos\n\n"
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
                            reply_markup=markup
                        )
                        logger.info(f"Tutorial mostrado a usuario {chat_id}")
                    
                    elif call.data == "weekly_plan" or call.data == "monthly_plan":
                        # Mostrar detalles del plan seleccionado
                        plan_id = call.data.split("_")[0]  # "weekly" o "monthly"
                        
                        plan = PLANS.get(plan_id)
                        
                        if plan:
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
                            
                            markup = types.InlineKeyboardMarkup(row_width=1)
                            markup.add(
                                types.InlineKeyboardButton("🅿️ Pagar con PayPal", callback_data=f"payment_paypal_{plan_id}"),
                                types.InlineKeyboardButton("🔙 Atrás", callback_data="view_plans")
                            )
                            
                            bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=plan_text,
                                reply_markup=markup
                            )
                            logger.info(f"Detalles del plan {plan_id} mostrados a usuario {chat_id}")
                        else:
                            # Plan no encontrado (no debería ocurrir)
                            bot.answer_callback_query(call.id, "Plan no disponible")
                            logger.error(f"Plan {plan_id} no encontrado")
                        
                    elif call.data == "bot_credits":
                        # Mostrar créditos - SIN formato Markdown para evitar errores
                        credits_text = (
                            "🧠 Créditos del Bot\n\n"
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
                        markup = types.InlineKeyboardMarkup(row_width=1)
                        markup.add(
                            types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"),
                            types.InlineKeyboardButton("🧠 Créditos del Bot", callback_data="bot_credits"),
                            types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
                        )
                        
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text="👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\nEste es un grupo exclusivo con contenido premium y acceso limitado.\n\nSelecciona una opción 👇",
                            reply_markup=markup
                        )
                        logger.info(f"Vuelto al menú principal para usuario {chat_id}")
                    
                    elif call.data.startswith("payment_paypal_"):
                        # Manejar pago con PayPal
                        plan_id = call.data.split("_")[-1]  # Extraer el ID del plan
                        
                        # Mostrar animación de "procesando"
                        processing_text = "🔄 Preparando pago...\nAguarde por favor..."
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=processing_text
                        )
                        
                        # Crear enlace de suscripción de PayPal
                        subscription_url = pay.create_subscription_link(plan_id, chat_id)
                        
                        if subscription_url:
                            # Crear markup con botón para pagar
                            markup = types.InlineKeyboardMarkup()
                            markup.add(
                                types.InlineKeyboardButton("💳 Ir a pagar", url=subscription_url),
                                types.InlineKeyboardButton("🔙 Cancelar", callback_data="view_plans")
                            )
                            
                            payment_text = (
                                "🔗 Tu enlace de pago está listo\n\n"
                                f"Plan: {PLANS[plan_id]['display_name']}\n"
                                f"Precio: ${PLANS[plan_id]['price_usd']:.2f} USD / "
                                f"{'semana' if plan_id == 'weekly' else 'mes'}\n\n"
                                "Por favor, haz clic en el botón de abajo para completar tu pago con PayPal.\n"
                                "Una vez completado, serás redirigido de vuelta aquí."
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
                                    "❌ Error al crear enlace de pago\n\n"
                                    "Lo sentimos, no pudimos procesar tu solicitud en este momento.\n"
                                    "Por favor, intenta nuevamente más tarde o contacta a soporte."
                                ),
                                reply_markup=markup
                            )
                            logger.error(f"Error al crear enlace de pago PayPal para usuario {chat_id}")
                    
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
                                            text=f"❌ Has sido expulsado del grupo VIP porque no tienes una suscripción activa.\n\nPara unirte, adquiere una suscripción en @VIPSubscriptionBot con el comando /start."
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

@app.route('/paypal/webhook', methods=['POST'])
def paypal_webhook():
    """Maneja los webhooks de PayPal"""
    try:
        event_data = request.json
        logger.info(f"PayPal webhook recibido: {event_data.get('event_type', 'DESCONOCIDO')}")
        
        # Procesar el evento PayPal
        success, message = pay.process_webhook_event(event_data)
        
        # Actualizar la suscripción en la base de datos según el evento
        bot_handlers.update_subscription_from_webhook(bot, event_data)
        
        return jsonify({"status": "success", "message": message}), 200
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
            CASE 
                WHEN s.status = 'ACTIVE' AND datetime(s.end_date) <= datetime('now') THEN 'EXPIRED' 
                ELSE s.status 
            END as status
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
        
        # Renderizar el template con los datos
        return render_template('admin_panel.html', 
                               admin_id=admin_id,
                               stats=stats,
                               recent_subscriptions=recent_subscriptions,
                               recent_users=recent_users)
        
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
    """Maneja el retorno desde PayPal después de una suscripción exitosa"""
    try:
        # Obtener los parámetros
        user_id = request.args.get('user_id')
        plan_id = request.args.get('plan_id')
        subscription_id = request.args.get('subscription_id')
        
        if not all([user_id, plan_id, subscription_id]):
            return render_template('webhook_success.html', 
                                  message="Parámetros incompletos. Por favor, contacta a soporte."), 400
        
        # Verificar la suscripción con PayPal
        subscription_details = pay.verify_subscription(subscription_id)
        if not subscription_details:
            return render_template('webhook_success.html', 
                                  message="No se pudo verificar la suscripción. Por favor, contacta a soporte."), 400
        
        # Procesar la suscripción exitosa
        success = bot_handlers.process_successful_subscription(
            bot, int(user_id), plan_id, subscription_id, subscription_details
        )
        
        if success:
            return render_template('webhook_success.html', 
                                  message="¡Suscripción exitosa! Puedes volver a Telegram."), 200
        else:
            return render_template('webhook_success.html', 
                                  message="Error al procesar la suscripción. Por favor, contacta a soporte."), 500
    
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
    
from bot_handlers import schedule_security_verification, force_security_check

@app.before_first_request
def initialize_security():
    """Inicializa el sistema de seguridad al recibir la primera solicitud"""
    try:
        logger.info("🔐 Inicializando sistema de seguridad...")
        
        # Registrar handlers del bot - IMPORTANTE: Añade esta línea
        bot_handlers.register_handlers(bot)
        logger.info("✅ Handlers registrados correctamente")
        
        # Realizar verificación inicial completa de membresías - IMPORTANTE: Añade esta línea
        verify_all_memberships_on_startup()
        logger.info("✅ Verificación inicial de membresías completada")
        
        # Iniciar hilo de verificación periódica
        schedule_security_verification(bot)
        
        # Forzar una verificación inicial
        force_security_check(bot)
        
        logger.info("✅ Sistema de seguridad inicializado correctamente")
        
        # Notificar a los administradores
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text="🔐 Bot reiniciado y sistema de seguridad inicializado correctamente.\n"
                         "Se ha iniciado la verificación periódica de suscripciones expiradas."
                )
            except Exception as e:
                logger.error(f"No se pudo notificar al admin {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Error al inicializar sistema de seguridad: {e}")
        
        # Intentar notificar a los administradores sobre el error
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ ERROR AL INICIALIZAR SEGURIDAD: {e}\n"
                         "El bot está activo pero el sistema de expulsión automática podría no funcionar correctamente."
                )
            except:
                pass