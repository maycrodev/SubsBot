import os
import logging
import traceback
import telebot
from flask import Flask, request, abort, jsonify
from telebot.types import Update

# Importaciones internas
import config
from bot.bot_instance import bot
from bot.handlers import register_all_handlers
from db.database import init_db

# Configuración de logging mejorada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializar la aplicación Flask
app = Flask(__name__)

# Inicializar la base de datos y configurar handlers antes de comenzar
def setup_app():
    """Configuración inicial de la aplicación"""
    try:
        logger.info("Inicializando aplicación...")
        # Inicializar la base de datos
        init_db()
        logger.info("Base de datos inicializada correctamente")
        
        # Configurar todos los handlers del bot
        register_all_handlers(bot)
        logger.info("Handlers del bot registrados correctamente")
        
        # Configurar webhook en producción
        if os.environ.get('ENVIRONMENT') != 'development':
            bot.remove_webhook()
            webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"
            logger.info(f"Configurando webhook en URL: {webhook_url}")
            bot.set_webhook(url=webhook_url)
            logger.info("Webhook configurado correctamente")
    except Exception as e:
        logger.error(f"Error durante la inicialización: {str(e)}")
        logger.error(traceback.format_exc())

# Ejecutar setup inmediatamente
setup_app()

# Ruta para el webhook del bot de Telegram
@app.route(config.WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        logger.info("Recibida petición al webhook de Telegram")
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            logger.debug(f"Datos recibidos: {json_string[:200]}...")  # Loguear primeros 200 caracteres
            update = Update.de_json(json_string)
            logger.info(f"Procesando update_id: {update.update_id}")
            
            bot.process_new_updates([update])
            return ''
        else:
            logger.warning(f"Contenido no válido: {request.headers.get('content-type')}")
            abort(403)
    except Exception as e:
        logger.error(f"Error procesando webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# Ruta para verificar que el servidor está funcionando
@app.route('/')
def index():
    try:
        me = bot.get_me()
        status_msg = f"Bot @{me.username} is running! (ID: {me.id})"
        logger.info(status_msg)
        return status_msg
    except Exception as e:
        error_msg = f"Error al conectar con la API de Telegram: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return error_msg, 500

# Ruta para webhooks de PayPal
@app.route(config.PAYPAL_WEBHOOK_PATH, methods=['POST'])
def paypal_webhook():
    try:
        logger.info("Recibido webhook de PayPal")
        # Aquí implementaremos la lógica del webhook de PayPal
        return '', 200
    except Exception as e:
        logger.error(f"Error procesando webhook de PayPal: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Punto de entrada principal
if __name__ == "__main__":
    # Inicialización ya realizada previamente en setup_app()
    
    # Si estamos en desarrollo local, podemos usar polling en lugar de webhook
    if os.environ.get('ENVIRONMENT') == 'development':
        logger.info("Iniciando en modo desarrollo (polling)")
        bot.remove_webhook()
        bot.polling(none_stop=True)
    else:
        # En producción, el webhook ya está configurado en setup_app()
        # Iniciar servidor Flask
        port = int(os.environ.get('PORT', config.PORT))
        logger.info(f"Iniciando servidor en puerto: {port}")
        app.run(host='0.0.0.0', port=port)