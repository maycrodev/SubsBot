import os
import logging
import telebot
from flask import Flask, request, abort
from telebot.types import Update

# Importaciones internas
import config
from bot.bot_instance import bot
from bot.handlers import register_all_handlers
from db.database import init_db

# Configuración de logging
logger = logging.getLogger(__name__)

# Inicializar la aplicación Flask
app = Flask(__name__)

# Inicializar la base de datos
init_db()

# Configurar todos los handlers del bot
register_all_handlers(bot)

# Ruta para el webhook del bot de Telegram
@app.route(config.WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

# Ruta para verificar que el servidor está funcionando
@app.route('/')
def index():
    return 'Bot is running'

# Ruta para webhooks de PayPal
@app.route(config.PAYPAL_WEBHOOK_PATH, methods=['POST'])
def paypal_webhook():
    # Aquí implementaremos la lógica del webhook de PayPal
    logger.info("Recibido webhook de PayPal")
    return '', 200

# Ruta para webhooks de Stripe
@app.route(config.STRIPE_WEBHOOK_PATH, methods=['POST'])
def stripe_webhook():
    # Aquí implementaremos la lógica del webhook de Stripe
    logger.info("Recibido webhook de Stripe")
    return '', 200

if __name__ == "__main__":
    # Si estamos en desarrollo local, podemos usar polling en lugar de webhook
    if os.environ.get('ENVIRONMENT') == 'development':
        bot.remove_webhook()
        bot.polling(none_stop=True)
    else:
        # En producción, configuramos el webhook
        bot.remove_webhook()
        webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"
        bot.set_webhook(url=webhook_url)
        
        # Iniciar servidor Flask
        app.run(host='0.0.0.0', port=config.PORT)