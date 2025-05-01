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

# ID del grupo VIP (debe ser un valor negativo para grupos)
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID'))
if GROUP_CHAT_ID >= 0:
    logger.warning("ADVERTENCIA: GROUP_CHAT_ID no es un valor negativo. Grupos de Telegram siempre tienen ID negativo.")
else:
    logger.info(f"Grupo VIP configurado con ID: {GROUP_CHAT_ID}")

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
# Estructura mejorada con información para UI
'''
Parámetros para cada plan:
- name: Nombre interno del plan
- price_usd: Precio en dólares
- duration_days: Duración en días
- display_name: Nombre que se muestra en la UI
- description: Descripción detallada del plan
- short_description: Descripción corta para listado de planes
- button_text: Texto para el botón
- button_emoji: Emoji para el botón
- benefits: Lista de beneficios específicos del plan
- order: Orden de aparición en la UI (menor número = aparece primero)
- row: Fila en la que aparecerá el botón (1, 2, etc.)
- highlight: Si el plan debe destacarse (True/False)
'''
PLANS = {
    'weekly': {
        'name': 'Plan Semanal',
        'price_usd': 3.50,
        'duration_days': 7,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙎𝙀𝙈𝘼𝙉𝘼𝙇',
        'description': 'Acceso: 1 semana al grupo VIP',
        'short_description': 'Plan Semanal: $3.50 / 1 semana',
        'button_text': 'Plan Semanal',
        'button_emoji': '🗓️',
        'benefits': [
            'Acceso al grupo VIP',
            '21,000 archivos exclusivos 📁'
        ],
        'order': 1,
        'row': 1,
        'highlight': False
    },
    'monthly': {
        'name': 'Plan Mensual',
        'price_usd': 5.00,
        'duration_days': 30,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙈𝙀𝙉𝙎𝙐𝘼𝙇',
        'description': 'Acceso: 1 mes al grupo VIP',
        'short_description': 'Plan Mensual: $5.00 / 1 mes',
        'button_text': 'Plan Mensual',
        'button_emoji': '📆',
        'benefits': [
            'Acceso al grupo VIP',
            '21,000 archivos exclusivos 📁',
            'Prioridad en soporte'
        ],
        'order': 2,
        'row': 1,
        'highlight': True
    },
    'prueba': {
        'name': 'Plan prueba',
        'price_usd': 12.00,
        'duration_days': 0.00138889,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙏𝙍𝙄𝙈𝙀𝙎𝙏𝙍𝘼𝙇',
        'description': 'Acceso: 3 meses al grupo VIP con descuento',
        'short_description': 'Plan Trimestral: $12.00 / 3 meses',
        'button_text': 'Plan Trimestral',
        'button_emoji': '📅',
        'benefits': [
            'Acceso al grupo VIP',
            '21,000 archivos exclusivos 📁',
            'Prioridad en soporte',
            'Contenido exclusivo para suscriptores trimestrales'
        ],
        'order': 3,
        'row': 2,
        'highlight': True
    }
}

# Verifica y establece valores predeterminados para campos faltantes en la configuración de planes
for plan_id, plan in PLANS.items():
    # Valores predeterminados para campos opcionales
    if 'short_description' not in plan:
        plan['short_description'] = f"{plan['name']}: ${plan['price_usd']} / {plan['duration_days']} días"
    if 'button_text' not in plan:
        plan['button_text'] = plan['name']
    if 'button_emoji' not in plan:
        plan['button_emoji'] = '📦'
    if 'benefits' not in plan:
        plan['benefits'] = ['Acceso al grupo VIP']
    if 'order' not in plan:
        plan['order'] = 999  # Por defecto, último lugar
    if 'row' not in plan:
        plan['row'] = 1  # Por defecto, primera fila
    if 'highlight' not in plan:
        plan['highlight'] = False  # Por defecto, sin destacar

logger.info(f"Planes configurados: {', '.join(PLANS.keys())}")

# Configuración de invitaciones
INVITE_LINK_EXPIRY_HOURS = 2  # Enlaces expiran en 24 horas
INVITE_LINK_MEMBER_LIMIT = 1  # Enlaces de un solo uso