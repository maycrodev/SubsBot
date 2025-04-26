import os
from dotenv import load_dotenv
import logging
import sys

# Cargar variables de entorno desde .env si existe (para desarrollo local)
load_dotenv()

# Configuración de logging mejorada
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout  # Asegurar que los logs sean visibles en Render.com
)
logger = logging.getLogger(__name__)

# Verificar variables de entorno críticas
required_env_vars = ["BOT_TOKEN", "WEBHOOK_URL", "ADMIN_IDS", "GROUP_INVITE_LINK"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"ERROR: Faltan variables de entorno requeridas: {', '.join(missing_vars)}")
    # No detenemos la ejecución, pero lo logueamos claramente

# Configuración del bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN:
    logger.info(f"Token configurado: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")  # Solo mostrar parte del token por seguridad

# Puerto - usar 10000 como valor por defecto mencionado
PORT = int(os.getenv("PORT", 10000))
logger.info(f"Puerto configurado: {PORT}")

# URL del webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
if WEBHOOK_URL:
    # Asegurar que no termina en /
    if WEBHOOK_URL.endswith('/'):
        WEBHOOK_URL = WEBHOOK_URL[:-1]
    logger.info(f"URL de webhook configurada: {WEBHOOK_URL}")

# IDs de administradores
try:
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
    logger.info(f"Administradores configurados: {ADMIN_IDS}")
except Exception as e:
    logger.error(f"Error al procesar ADMIN_IDS: {str(e)}")
    ADMIN_IDS = []

# Enlaces y configuración del grupo
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "")
if GROUP_INVITE_LINK:
    logger.info(f"Enlace de invitación configurado: {GROUP_INVITE_LINK}")

# Configuración de pagos - PayPal
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox o live
logger.info(f"Modo PayPal configurado: {PAYPAL_MODE}")

# Planes de suscripción
SUBSCRIPTION_PLANS = {
    "weekly": {
        "name": "SUSCRIPCIÓN SEMANAL",
        "price": 3.50,
        "duration": "1 semana",
        "duration_days": 7,
    },
    "monthly": {
        "name": "SUSCRIPCIÓN MENSUAL",
        "price": 5.00,
        "duration": "1 mes",
        "duration_days": 30,
    }
}

# Configuración de rutas para webhooks
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
logger.info(f"Ruta de webhook: {WEBHOOK_PATH}")
PAYPAL_WEBHOOK_PATH = "/webhook/paypal"

# Configuración de la base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'vip_bot.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
logger.info(f"Base de datos configurada en: {DB_PATH}")