import os
from dotenv import load_dotenv
import logging

# Cargar variables de entorno desde .env si existe (para desarrollo local)
load_dotenv()

# Configuración del bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8443))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # URL completa proporcionada por Render

# IDs de administradores (lista de IDs de Telegram de admins)
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# Enlaces y configuración del grupo
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "")

# Configuración de pagos
# PayPal
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox o live

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

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
PAYPAL_WEBHOOK_PATH = "/webhook/paypal"
STRIPE_WEBHOOK_PATH = "/webhook/stripe"

# Configuración de la base de datos
DB_PATH = os.path.join(os.path.dirname(__file__), 'vip_bot.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)