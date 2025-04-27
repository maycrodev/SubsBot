import logging
import telebot
from flask import Flask, request, jsonify, render_template
import threading
import time
import os
import json
import datetime
from telebot import types
import database as db
import payments as pay
from config import BOT_TOKEN, PORT, WEBHOOK_URL, ADMIN_IDS

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
            
            # Registrar el tipo de actualización
            if update.message:
                logger.info(f"Mensaje recibido de {update.message.from_user.id}: {update.message.text}")
                
                # Manejar directamente el comando /start aquí por ahora
                if update.message.text == '/start':
                    logger.info("¡Comando /start detectado! Enviando respuesta directa...")
                    
                    try:
                        # Enviar un mensaje simple sin usar los handlers complejos
                        markup = types.InlineKeyboardMarkup(row_width=1)
                        markup.add(
                            types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"),
                            types.InlineKeyboardButton("🧠 Créditos del Bot", callback_data="bot_credits"),
                            types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
                        )
                        
                        bot.send_message(
                            chat_id=update.message.chat.id,
                            text="👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\nEste es un grupo exclusivo con contenido premium y acceso limitado.\n\nSelecciona una opción 👇",
                            reply_markup=markup
                        )
                        logger.info(f"Respuesta enviada al usuario {update.message.from_user.id}")
                        return 'OK', 200
                    except Exception as e:
                        logger.error(f"Error al enviar respuesta directa: {str(e)}")
            
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
                        
                    elif call.data == "bot_credits":
                        # Mostrar créditos
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
                        logger.info(f"Créditos mostrados a usuario {chat_id}")
                        
                    elif call.data == "terms":
                        # Mostrar términos
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

@app.route('/diagnostico')
def diagnostico():
    """Ruta para diagnóstico del bot"""
    try:
        # Obtener información del bot
        bot_info = bot.get_me()
        
        # Verificar webhook
        webhook_info = bot.get_webhook_info()
        
        # Crear información de diagnóstico
        info = {
            "bot_name": bot_info.first_name,
            "bot_username": bot_info.username,
            "webhook_url": webhook_info.url,
            "pending_updates": webhook_info.pending_update_count,
            "last_error": webhook_info.last_error_message if hasattr(webhook_info, 'last_error_message') else None,
            "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "environment": os.environ.get('ENVIRONMENT', 'production')
        }
        
        return jsonify(info), 200
    except Exception as e:
        logger.error(f"Error en diagnóstico: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    """Página simple para confirmar que el servidor está funcionando"""
    return "Bot Server Running!", 200

def set_webhook():
    """Configura el webhook de Telegram"""
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        webhook_url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook configurado en {webhook_url}")
        return True
    except Exception as e:
        logger.error(f"Error al configurar webhook: {str(e)}")
        return False

def run_bot_polling():
    """Ejecuta el bot en modo polling (para desarrollo local)"""
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        logger.info("Iniciando bot en modo polling...")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Error en polling: {str(e)}")

if __name__ == "__main__":
    # Agregar logs para diagnóstico
    logger.info(f"BOT_TOKEN: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")
    logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
    
    # Registrar los handlers directamente aquí para mayor control
    logger.info("Registrando handlers del bot...")
    
    # Registrar handler básico para /start
    @bot.message_handler(commands=['start'])
    def direct_start_handler(message):
        logger.info(f"Handler directo de /start llamado por usuario {message.from_user.id}")
        try:
            # Crear markup con botones
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"),
                types.InlineKeyboardButton("🧠 Créditos del Bot", callback_data="bot_credits"),
                types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
            )
            
            # Enviar mensaje de bienvenida
            bot.send_message(
                chat_id=message.chat.id,
                text="👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\nEste es un grupo exclusivo con contenido premium y acceso limitado.\n\nSelecciona una opción 👇",
                reply_markup=markup
            )
            
            logger.info(f"Mensaje de bienvenida enviado a {message.from_user.id}")
            
            # Guardar usuario en la base de datos
            db.save_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name
            )
        except Exception as e:
            logger.error(f"Error en handler directo de /start: {str(e)}")
            bot.send_message(
                chat_id=message.chat.id,
                text="❌ Ocurrió un error. Por favor, intenta nuevamente más tarde."
            )
    
    # Manejar callbacks de los botones del menú principal
    @bot.callback_query_handler(func=lambda call: call.data in ['view_plans', 'bot_credits', 'terms'])
    def direct_main_menu_callback(call):
        logger.info(f"Callback handler directo llamado: {call.data}")
        try:
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
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                
            elif call.data == "bot_credits":
                # Mostrar créditos
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
                # Mostrar términos
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
            logger.info(f"Respuesta de callback enviada para: {call.data}")
            
        except Exception as e:
            logger.error(f"Error en handler directo de callback: {str(e)}")
            try:
                bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
            except:
                pass
    
    # Manejar botón "Volver al menú principal"
    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def direct_back_to_main(call):
        try:
            # Volver al menú principal
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📦 Ver Planes", callback_data="view_plans"),
                types.InlineKeyboardButton("🧠 Créditos del Bot", callback_data="bot_credits"),
                types.InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
            )
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\nEste es un grupo exclusivo con contenido premium y acceso limitado.\n\nSelecciona una opción 👇",
                reply_markup=markup
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error en handler volver al menú: {str(e)}")
            try:
                bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
            except:
                pass
    
    # Registramos también el handler para otros comandos
    bot_handlers.register_handlers(bot)
    
    # Verificar si estamos en desarrollo local o en producción
    if os.environ.get('ENVIRONMENT') == 'development':
        # Modo desarrollo: usar polling
        threading.Thread(target=run_bot_polling).start()
        app.run(host='0.0.0.0', port=PORT, debug=True, use_reloader=False)
    else:
        # Modo producción: usar webhook
        set_webhook()
        app.run(host='0.0.0.0', port=PORT)