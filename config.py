import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno si hay un archivo .env (desarrollo local)
load_dotenv()

# Bot Token de Telegram
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("CRÍTICO: BOT_TOKEN no está definido en las variables de entorno")

# IDs de administradores (convertir a lista de enteros)
admin_ids_str = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id) for admin_id in admin_ids_str.split(',') if admin_id]
if not ADMIN_IDS:
    logger.warning("ADVERTENCIA: No hay administradores definidos en ADMIN_IDS")

# Enlace de invitación al grupo VIP
GROUP_INVITE_LINK = os.getenv('GROUP_INVITE_LINK')
if not GROUP_INVITE_LINK:
    logger.warning("ADVERTENCIA: GROUP_INVITE_LINK no está definido")

# Configuración de PayPal
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'sandbox')  # sandbox o live

# Verificar configuración de PayPal
if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
    logger.error("CRÍTICO: Credenciales de PayPal no configuradas")
else:
    # Mostrar versión truncada para verificación sin exponer datos sensibles
    client_id_masked = f"{PAYPAL_CLIENT_ID[:5]}...{PAYPAL_CLIENT_ID[-5:]}" if len(PAYPAL_CLIENT_ID) > 10 else "[DEMASIADO CORTO]"
    client_secret_masked = f"{PAYPAL_CLIENT_SECRET[:3]}...{PAYPAL_CLIENT_SECRET[-3:]}" if len(PAYPAL_CLIENT_SECRET) > 10 else "[DEMASIADO CORTO]"
    
    logger.info(f"PayPal modo: {PAYPAL_MODE}")
    logger.info(f"PayPal Client ID: {client_id_masked}")
    logger.info(f"PayPal Client Secret: {client_secret_masked}")

# Puerto para el servidor web
PORT = int(os.getenv('PORT', 10000))

# URL para webhooks
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
if not WEBHOOK_URL:
    logger.error("CRÍTICO: WEBHOOK_URL no está definido en las variables de entorno")
else:
    logger.info(f"Webhook URL: {WEBHOOK_URL}")

# Ruta de la base de datos SQLite
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'vip_bot.db')

# Asegurar que el directorio de datos existe
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
logger.info(f"Ruta de la base de datos: {DB_PATH}")

# Configuración de planes
PLANS = {
    'weekly': {
        'name': 'Plan Semanal',
        'price_usd': 3.50,
        'duration_days': 7,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙎𝙀𝙈𝘼𝙉𝘼𝙇',
        'description': 'Acceso: 1 semana al grupo VIP'
    },
    'monthly': {
        'name': 'Plan Mensual',
        'price_usd': 5.00,
        'duration_days': 30,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙈𝙀𝙉𝙎𝙐𝘼𝙇',
        'description': 'Acceso: 1 mes al grupo VIP'
    }
}

logger.info(f"Planes configurados: {', '.join(PLANS.keys())}")

# Configuración de invitaciones
INVITE_LINK_EXPIRY_HOURS = 24  # Enlaces expiran en 24 horas
INVITE_LINK_MEMBER_LIMIT = 1  # Enlaces de un solo uso