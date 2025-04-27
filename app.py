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
            "usuarios": get_table_count(conn, "users"),
            "suscripciones": get_table_count(conn, "subscriptions"),
            "suscripciones_activas": get_active_subscriptions_count(conn),
            "enlaces_invitacion": get_table_count(conn, "invite_links")
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

@app.route('/admin/download-database', methods=['GET'])
def download_database():
    """Endpoint para descargar la base de datos"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Ruta al archivo de base de datos
        db_path = DB_PATH
        
        # Verificar que el archivo existe
        if not os.path.exists(db_path):
            return jsonify({"error": "Archivo de base de datos no encontrado"}), 404
        
        # Crear una copia temporal para evitar problemas de concurrencia
        temp_file = os.path.join(os.path.dirname(db_path), 'temp_download.db')
        
        # Copiar archivo con el módulo shutil
        import shutil
        shutil.copy2(db_path, temp_file)
        
        # Enviar el archivo temporal
        response = send_file(
            temp_file,
            as_attachment=True,
            download_name=f"vip_bot_db_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mimetype='application/octet-stream'
        )
        
        # Configurar un callback para eliminar el archivo temporal después de enviarlo
        @response.call_on_close
        def cleanup():
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        return response
        
    except Exception as e:
        logger.error(f"Error al descargar base de datos: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/panel', methods=['GET', 'POST'])
def admin_panel():
    """Panel de administración con interfaz web"""
    try:
        # Verificación básica de autenticación
        admin_id = request.args.get('admin_id')
        if not admin_id or int(admin_id) not in ADMIN_IDS:
            return jsonify({"error": "Acceso no autorizado"}), 401
        
        # Obtener conexión a la base de datos
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Variables para plantilla
        template_vars = {
            "admin_id": admin_id,
            "error": None,
            "message": None,
            "results": None,
            "columns": None,
            "count": 0,
            "query": None,
            "rows_affected": 0
        }
        
        # Procesar consulta SQL si se envió
        if request.method == 'POST':
            query = request.form.get('query', '')
            if query:
                try:
                    cursor.execute(query)
                    # Si es una consulta SELECT
                    if query.strip().upper().startswith('SELECT'):
                        columns = [description[0] for description in cursor.description]
                        results = cursor.fetchall()
                        results_list = [dict(zip(columns, row)) for row in results]
                        
                        template_vars["query"] = query
                        template_vars["columns"] = columns
                        template_vars["results"] = results_list
                        template_vars["count"] = len(results_list)
                    else:
                        conn.commit()
                        template_vars["query"] = query
                        template_vars["message"] = "Consulta ejecutada correctamente"
                        template_vars["rows_affected"] = cursor.rowcount
                except Exception as e:
                    template_vars["query"] = query
                    template_vars["error"] = str(e)
        
        # Obtener estadísticas
        stats = {
            "usuarios": get_table_count(conn, "users"),
            "suscripciones": get_table_count(conn, "subscriptions"),
            "suscripciones_activas": get_active_subscriptions_count(conn),
            "enlaces_invitacion": get_table_count(conn, "invite_links")
        }
        template_vars["stats"] = stats
        
        # Obtener últimas 5 suscripciones
        cursor.execute("""
        SELECT s.sub_id, s.user_id, u.username, s.plan, s.price_usd, s.start_date, s.end_date, s.status
        FROM subscriptions s
        LEFT JOIN users u ON s.user_id = u.user_id
        ORDER BY s.start_date DESC
        LIMIT 5
        """)
        recent_subscriptions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        template_vars["recent_subscriptions"] = recent_subscriptions
        
        conn.close()
        
        # Renderizar plantilla
        return render_template('admin_panel.html', **template_vars)
        
    except Exception as e:
        logger.error(f"Error en admin_panel: {str(e)}")
        return f"Error: {str(e)}", 500

def get_table_count(conn, table_name):
    """Obtiene el número de registros en una tabla"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]

def get_active_subscriptions_count(conn):
    """Obtiene el número de suscripciones activas"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'ACTIVE' AND end_date > datetime('now')")
    return cursor.fetchone()[0]

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
    @bot.callback_query_handler(func=lambda call: call.data in ['view_plans', 'bot_credits', 'terms', 'tutorial', 'weekly_plan', 'monthly_plan', 'back_to_main'] or call.data.startswith('payment_paypal_'))
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
                    reply_markup=markup
                )
            
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
            
            elif call.data in ["weekly_plan", "monthly_plan"]:
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
                else:
                    # Plan no encontrado (no debería ocurrir)
                    bot.answer_callback_query(call.id, "Plan no disponible")
                    
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
                import payments as pay
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
                    
            # Responder al callback para quitar el "reloj de espera" en el cliente
            bot.answer_callback_query(call.id)
            logger.info(f"Respuesta de callback enviada para: {call.data}")
            
        except Exception as e:
            logger.error(f"Error en handler directo de callback: {str(e)}")
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