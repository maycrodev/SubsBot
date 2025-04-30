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

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inicializar el bot y la aplicación Flask
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Importar el sistema centralizado de handlers
import bot_handlers

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
            
            # Manejar chat_member actualizaciones
            if hasattr(update, 'chat_member'):
                try:
                    chat_id = update.chat_member.chat.id
                    from_user_id = update.chat_member.from_user.id 
                    user_id = update.chat_member.new_chat_member.user.id
                    status = update.chat_member.new_chat_member.status
                    
                    # Si un usuario se unió al grupo
                    if status == 'member' and update.chat_member.old_chat_member.status == 'left':
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
                    
                    return 'OK', 200
                    
                except Exception as e:
                    logger.error(f"Error al procesar chat_member: {str(e)}")
                    return 'Error en chat_member', 200
            
            # Registrar el tipo de actualización
            if update.message:
                if update.message.text:
                    logger.info(f"Mensaje recibido de {update.message.from_user.id}: {update.message.text}")
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
                
                # Continuar con el manejo del mensaje /start
                if update.message.text == '/start':
                    # [código existente para /start]
                    logger.info("¡Comando /start detectado! Enviando respuesta directa...")
                    
                    try:
                        # Usar la función handle_start mejorada
                        bot_handlers.handle_start(update.message, bot)
                        logger.info(f"Respuesta enviada al usuario {update.message.from_user.id}")
                        return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error al enviar respuesta directa: {str(e)}")
                
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
                            bot_handlers.handle_whitelist(update.message, bot)
                            logger.info(f"Comando whitelist procesado para {update.message.from_user.id}")
                            return 'OK', 200
                        elif update.message.text.startswith('/subinfo'):
                            bot_handlers.handle_subinfo(update.message, bot)
                            logger.info(f"Comando subinfo procesado para {update.message.from_user.id}")
                            return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error al procesar comando de administrador: {str(e)}")
                        # Intentar responder al usuario con el error
                        try:
                            bot.reply_to(update.message, f"❌ Error al procesar comando: {str(e)}")
                        except:
                            pass
                
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
            
            # Procesar a través de los handlers normales como respaldo
            bot.process_new_updates([update])
            
            return 'OK', 200
        else:
            return 'Error: Content type is not application/json', 403
    except Exception as e:
        logger.error(f"Error al procesar webhook: {str(e)}")
        return 'Error interno', 500

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
        
        # Obtener últimas 5 suscripciones
        cursor = conn.cursor()
        cursor.execute("""
        SELECT s.sub_id, s.user_id, u.username, s.plan, s.price_usd, s.start_date, s.end_date, s.status
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