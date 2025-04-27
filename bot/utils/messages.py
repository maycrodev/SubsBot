import config
from datetime import datetime
import pytz
import logging
import traceback

# Configuración de logging para este módulo
logger = logging.getLogger(__name__)

def welcome_message():
    """Mensaje de bienvenida del bot"""
    try:
        logger.info("Generando mensaje de bienvenida")
        message = """
👋 ¡Bienvenido al Bot de Suscripciones VIP!

Este es un grupo exclusivo con contenido premium y acceso limitado.

Selecciona una opción 👇
"""
        logger.info("Mensaje de bienvenida generado correctamente")
        return message.strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de bienvenida: {str(e)}")
        logger.error(traceback.format_exc())
        return "👋 ¡Bienvenido al Bot de Suscripciones VIP!"

def plans_message():
    """Mensaje con los planes disponibles"""
    try:
        logger.info("Generando mensaje de planes")
        message = """
💸 Escoge tu plan de suscripción:

🔹 Plan Semanal: $3.50 / 1 semana  
🔸 Plan Mensual: $5.00 / 1 mes

🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇
"""
        logger.info("Mensaje de planes generado correctamente")
        return message.strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de planes: {str(e)}")
        logger.error(traceback.format_exc())
        return "💸 Escoge tu plan de suscripción"

def subscription_details(plan_type):
    """Genera el mensaje con detalles de la suscripción según el plan"""
    try:
        logger.info(f"Generando detalles de suscripción para plan: {plan_type}")
        plan = config.SUBSCRIPTION_PLANS.get(plan_type)
        if not plan:
            logger.error(f"Plan no válido: {plan_type}")
            return "Plan no válido"
        
        message = f"""
📦 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {plan['name'].split()[-1]}

Acceso: {plan['duration']} al grupo VIP  
Beneficios:
✅ GrupoA1 VIP (Acceso)  
✅ 21,000 archivos exclusivos 📁

💵 Precio: ${plan['price']:.2f} USD  
📆 Facturación: {plan['duration'].lower()} (recurrente)

Selecciona un método de pago 👇
"""
        logger.info(f"Detalles de suscripción generados correctamente para plan: {plan_type}")
        return message.strip()
    except Exception as e:
        logger.error(f"Error al generar detalles de suscripción: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Detalles del plan {plan_type}"

def payment_processing():
    """Mensaje inicial para procesamiento de pago"""
    return """
🔄 Confirmando Pago  
      /  
Aguarde por favor...
""".strip()

def payment_success(subscription, payment_method):
    """Mensaje de pago exitoso"""
    try:
        logger.info(f"Generando mensaje de pago exitoso para ID: {subscription.id}")
        return f"""
✅ ¡Pago completado con éxito!

Tu suscripción ha sido activada.

📦 Plan: {subscription.plan_type}
💵 Precio: ${subscription.amount:.2f} USD
📆 Duración: {config.SUBSCRIPTION_PLANS[subscription.plan_type]['duration']}
🗓️ Expira: {subscription.expiry_date.strftime('%d/%m/%Y %H:%M:%S')}

🚪 Aquí tienes tu enlace de acceso al grupo VIP:
{config.GROUP_INVITE_LINK}
""".strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de pago exitoso: {str(e)}")
        logger.error(traceback.format_exc())
        return "✅ ¡Pago completado con éxito! Tu suscripción ha sido activada."

def tutorial_message():
    """Mensaje con el tutorial de pagos"""
    try:
        logger.info("Generando mensaje de tutorial")
        return """
🎥 **Tutorial de Pagos**

Para completar tu suscripción sigue estos pasos:

**Para PayPal:**
1. Haz clic en "🅿️ Pagar con PayPal"
2. Serás redirigido a la página de PayPal
3. Inicia sesión en tu cuenta
4. Confirma la suscripción recurrente
5. Regresa al bot para confirmar

⚠️ Importante: Al completar el pago, serás añadido automáticamente a la whitelist y recibirás el enlace de invitación al grupo VIP.
""".strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de tutorial: {str(e)}")
        logger.error(traceback.format_exc())
        return "🎥 Tutorial de Pagos"

def terms_message():
    """Mensaje con los términos de uso"""
    try:
        logger.info("Generando mensaje de términos")
        return """
📜 **Términos de Uso**

1. La suscripción es recurrente y se renovará automáticamente.
2. Los pagos no son reembolsables.
3. El acceso es personal e intransferible.
4. Compartir el enlace de invitación está prohibido.
5. Cualquier uso indebido resultará en la cancelación sin reembolso.
6. El contenido del grupo es confidencial.
7. El bot puede recopilar datos necesarios para la gestión de suscripciones.

Al continuar con el proceso de pago, aceptas estos términos.
""".strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de términos: {str(e)}")
        logger.error(traceback.format_exc())
        return "📜 Términos de Uso"

def credits_message():
    """Mensaje con los créditos del bot"""
    try:
        logger.info("Generando mensaje de créditos")
        return """
🧠 **Créditos del Bot**

Este bot de suscripciones VIP fue desarrollado utilizando:

🤖 Framework: pyTelegramBotAPI
💾 Base de datos: SQLite
💳 Pasarela de pago: PayPal

Desarrollado con ❤️ para gestionar suscripciones de forma automática y segura.

© 2025 - Todos los derechos reservados
""".strip()
    except Exception as e:
        logger.error(f"Error al generar mensaje de créditos: {str(e)}")
        logger.error(traceback.format_exc())
        return "🧠 Créditos del Bot"

# El resto de las funciones se mantienen igual
def admin_new_subscription_notification(subscription, user, payment_method):
    """Notificación para admins de nueva suscripción"""
    try:
        local_tz = pytz.timezone('America/Mexico_City')  # Ajusta a tu zona horaria
        start_date = subscription.start_date.astimezone(local_tz)
        expiry_date = subscription.expiry_date.astimezone(local_tz)
        
        return f"""
🎉 ¡Nueva Suscripción! ({payment_method})

Detalles:
* ID: {subscription.payment_id}
* Usuario: {user.full_name} (id{user.telegram_id})
* Plan: 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {subscription.plan_type.upper()}📦
* Facturación: ${subscription.amount:.2f} / {config.SUBSCRIPTION_PLANS[subscription.plan_type]['duration']}
* Fecha: {start_date.strftime('%a, %b %d, %Y %I:%M %p')}
* Expira: {expiry_date.strftime('%a, %b %d, %Y %I:%M %p')}
* Estado: ✅ ACTIVO
""".strip()
    except Exception as e:
        logger.error(f"Error al generar notificación de nueva suscripción: {str(e)}")
        logger.error(traceback.format_exc())
        return f"🎉 ¡Nueva Suscripción! Usuario: {user.full_name}"

def admin_whitelist_request(user_id, username=None, full_name=None):
    """Mensaje para solicitar confirmación de whitelist"""
    user_info = f"{full_name} (@{username})" if username else full_name
    
    return f"""
🛡️ Querido Administrador,

¿Deseas agregar a:
👤 {user_info}  
🆔 ID: {user_id} ?

⏱️ Define el tiempo que estará en whitelist:
""".strip()

def admin_whitelist_time_instructions():
    """Instrucciones para formato de tiempo de whitelist"""
    return """
Por favor, ingresa el tiempo con formato:

👉 Ejemplo: `1 days`, `7 days`, `1 month`
""".strip()

def admin_whitelist_success(user_id, duration):
    """Mensaje de éxito al añadir usuario a whitelist"""
    return f"""
✅ Usuario {user_id} añadido a la whitelist con éxito.
Duración: {duration}
""".strip()

def user_subscription_info(user, subscriptions):
    """Genera información detallada de suscripción para un usuario"""
    try:
        if not subscriptions:
            return f"""
👤 ID: {user.telegram_id}  
🧑 Nombre: {user.full_name}  
📊 Estado: 🔴 Sin suscripciones activas

❌ Sin acceso a: GrupoA1

💳 Pagos: No hay registros
""".strip()
        
        # Obtener la suscripción más reciente
        latest_sub = subscriptions[0]
        
        status = "🟢 Activo" if latest_sub.is_active else "🔴 Cancelado"
        if not latest_sub.is_active and latest_sub.expiry_date < datetime.utcnow():
            status = "🟡 Expirado"
        
        local_tz = pytz.timezone('America/Mexico_City')
        start_date = latest_sub.start_date.astimezone(local_tz)
        
        return f"""
👤 ID: {user.telegram_id}  
🧑 Nombre: {user.full_name}  
📊 Estado: {status}

📥 Suscrito a: {"GrupoA1" if latest_sub.is_active else "Ninguno"}  
{"✅ Con acceso a: GrupoA1" if latest_sub.is_active else "❌ Sin acceso a: GrupoA1"}

💳 Pagos:  
{latest_sub.payment_method} ID: {latest_sub.payment_id}
Monto: ${latest_sub.amount:.2f}

🧾 Suscripciones:  
🅿️ {status} {latest_sub.payment_method.capitalize()} subscription  
en 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {latest_sub.plan_type.upper()} 📦  
Inició: {start_date.strftime('%d de %B de %Y')}
""".strip()
    except Exception as e:
        logger.error(f"Error al generar información de suscripción: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Información de usuario: {user.full_name} (ID: {user.telegram_id})"