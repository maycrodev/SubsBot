import logging
import telebot
from flask import Flask, request, jsonify, render_template
import threading
import time
import os
import json
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

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Recibe las actualizaciones de Telegram a través de webhook"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Error: Content type is not application/json', 403

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

@app.route('/')
def index():
    """Página simple para confirmar que el servidor está funcionando"""
    return "Bot Server Running!", 200

def set_webhook():
    """Configura el webhook de Telegram"""
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info(f"Webhook configurado en {WEBHOOK_URL}/{BOT_TOKEN}")
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
    # Registrar los handlers
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