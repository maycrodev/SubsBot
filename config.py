import os
from dotenv import load_dotenv

# Cargar variables de entorno si hay un archivo .env (desarrollo local)
load_dotenv()

# Bot Token de Telegram
BOT_TOKEN = os.getenv('BOT_TOKEN')

# IDs de administradores (convertir a lista de enteros)
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv('ADMIN_IDS', '').split(',') if admin_id]

# Enlace de invitación al grupo VIP
GROUP_INVITE_LINK = os.getenv('GROUP_INVITE_LINK')

# Configuración de PayPal
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'sandbox')  # sandbox o live

# Puerto para el servidor web
PORT = int(os.getenv('PORT', 10000))

# URL para webhooks
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Ruta de la base de datos SQLite
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'vip_bot.db')

# Asegurar que el directorio de datos existe
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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

# Configuración de invitaciones
INVITE_LINK_EXPIRY_HOURS = 24  # Enlaces expiran en 24 horas
INVITE_LINK_MEMBER_LIMIT = 1  # Enlaces de un solo uso