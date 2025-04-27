# main.py
import os
import logging
import traceback
from flask import Flask, request, abort, Response, jsonify
import telebot
from telebot.types import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
if WEBHOOK_URL.endswith('/'):
    WEBHOOK_URL = WEBHOOK_URL[:-1]
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
PORT = int(os.getenv("PORT", 10000))

# Admin configuration
try:
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
    logger.info(f"Administrators configured: {ADMIN_IDS}")
except Exception as e:
    logger.error(f"Error processing ADMIN_IDS: {str(e)}")
    ADMIN_IDS = []

# Group invitation link
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "")

# Subscription plans
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

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# -------------------- Database simulation --------------------
# Since we're simplifying, we'll use in-memory storage
users = {}
subscriptions = {}
next_sub_id = 1

# -------------------- Helper Functions --------------------
def is_admin(user_id):
    """Check if a user is an admin"""
    return user_id in ADMIN_IDS

def get_user(user_id):
    """Get user from in-memory database"""
    return users.get(user_id)

def create_user(user_id, full_name, username=None):
    """Create a new user"""
    user = {
        "telegram_id": user_id,
        "full_name": full_name,
        "username": username,
        "join_date": datetime.utcnow(),
        "is_admin": user_id in ADMIN_IDS,
        "is_blocked": False
    }
    users[user_id] = user
    return user

def get_active_subscription(user_id):
    """Get active subscription for a user"""
    now = datetime.utcnow()
    for sub_id, sub in subscriptions.items():
        if sub["user_id"] == user_id and sub["is_active"] and sub["expiry_date"] > now:
            return sub
    return None

def create_subscription(user_id, plan_type, payment_method, payment_id, amount, expiry_date):
    """Create a new subscription"""
    global next_sub_id
    
    # Deactivate current subscriptions
    for sub_id, sub in subscriptions.items():
        if sub["user_id"] == user_id and sub["is_active"]:
            sub["is_active"] = False
    
    # Create new subscription
    subscription = {
        "id": next_sub_id,
        "user_id": user_id,
        "plan_type": plan_type,
        "payment_method": payment_method,
        "payment_id": payment_id,
        "amount": amount,
        "start_date": datetime.utcnow(),
        "expiry_date": expiry_date,
        "is_active": True,
        "auto_renew": True
    }
    
    subscriptions[next_sub_id] = subscription
    next_sub_id += 1
    return subscription

def add_to_whitelist(user_id, expiry_date):
    """Add a user to whitelist with a manual subscription"""
    # Create subscription
    payment_id = f"admin_wl_{user_id}_{int(datetime.utcnow().timestamp())}"
    return create_subscription(
        user_id=user_id,
        plan_type="manual",
        payment_method="admin_whitelist",
        payment_id=payment_id,
        amount=0.0,
        expiry_date=expiry_date
    )

def is_in_whitelist(user_id):
    """Check if user has an active subscription"""
    return get_active_subscription(user_id) is not None

# -------------------- Message Templates --------------------
def welcome_message():
    """Welcome message"""
    return """
👋 ¡Bienvenido al Bot de Suscripciones VIP!

Este es un grupo exclusivo con contenido premium y acceso limitado.

Selecciona una opción 👇
""".strip()

def plans_message():
    """Message with available plans"""
    return """
💸 Escoge tu plan de suscripción:

🔹 Plan Semanal: $3.50 / 1 semana  
🔸 Plan Mensual: $5.00 / 1 mes

🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇
""".strip()

def subscription_details(plan_type):
    """Generate subscription details message"""
    plan = SUBSCRIPTION_PLANS.get(plan_type)
    if not plan:
        return "Plan no válido"
    
    return f"""
📦 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {plan['name'].split()[-1]}

Acceso: {plan['duration']} al grupo VIP  
Beneficios:
✅ GrupoA1 VIP (Acceso)  
✅ 21,000 archivos exclusivos 📁

💵 Precio: ${plan['price']:.2f} USD  
📆 Facturación: {plan['duration'].lower()} (recurrente)

Selecciona un método de pago 👇
""".strip()

def payment_processing():
    """Initial payment processing message"""
    return """
🔄 Confirmando Pago  
      /  
Aguarde por favor...
""".strip()

def payment_success(subscription, payment_method):
    """Successful payment message"""
    return f"""
✅ ¡Pago completado con éxito!

Tu suscripción ha sido activada.

📦 Plan: {subscription["plan_type"]}
💵 Precio: ${subscription["amount"]:.2f} USD
📆 Duración: {SUBSCRIPTION_PLANS[subscription["plan_type"]]['duration']}
🗓️ Expira: {subscription["expiry_date"].strftime('%d/%m/%Y %H:%M:%S')}

🚪 Aquí tienes tu enlace de acceso al grupo VIP:
{GROUP_INVITE_LINK}
""".strip()

def tutorial_message():
    """Payment tutorial message"""
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

def terms_message():
    """Terms of use message"""
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

def credits_message():
    """Bot credits message"""
    return """
🧠 **Créditos del Bot**

Este bot de suscripciones VIP fue desarrollado utilizando:

🤖 Framework: pyTelegramBotAPI
💾 Base de datos: SQLite
💳 Pasarela de pago: PayPal

Desarrollado con ❤️ para gestionar suscripciones de forma automática y segura.

© 2025 - Todos los derechos reservados
""".strip()

def admin_new_subscription_notification(subscription, user, payment_method):
    """Notification for admins about new subscription"""
    local_tz = pytz.timezone('America/Mexico_City')
    start_date = subscription["start_date"].astimezone(local_tz)
    expiry_date = subscription["expiry_date"].astimezone(local_tz)
    
    return f"""
🎉 ¡Nueva Suscripción! ({payment_method})

Detalles:
* ID: {subscription["payment_id"]}
* Usuario: {user["full_name"]} (id{user["telegram_id"]})
* Plan: 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {subscription["plan_type"].upper()}📦
* Facturación: ${subscription["amount"]:.2f} / {SUBSCRIPTION_PLANS[subscription["plan_type"]]['duration']}
* Fecha: {start_date.strftime('%a, %b %d, %Y %I:%M %p')}
* Expira: {expiry_date.strftime('%a, %b %d, %Y %I:%M %p')}
* Estado: ✅ ACTIVO
""".strip()

def admin_whitelist_request(user_id, username=None, full_name=None):
    """Message requesting whitelist confirmation"""
    user_info = f"{full_name} (@{username})" if username else full_name
    
    return f"""
🛡️ Querido Administrador,

¿Deseas agregar a:
👤 {user_info}  
🆔 ID: {user_id} ?

⏱️ Define el tiempo que estará en whitelist:
""".strip()

def admin_whitelist_time_instructions():
    """Instructions for whitelist time format"""
    return """
Por favor, ingresa el tiempo con formato:

👉 Ejemplo: `1 days`, `7 days`, `1 month`
""".strip()

def admin_whitelist_success(user_id, duration):
    """Success message for adding user to whitelist"""
    return f"""
✅ Usuario {user_id} añadido a la whitelist con éxito.
Duración: {duration}
""".strip()

def user_subscription_info(user, subscriptions_list):
    """Generate detailed subscription information for a user"""
    if not subscriptions_list:
        return f"""
👤 ID: {user["telegram_id"]}  
🧑 Nombre: {user["full_name"]}  
📊 Estado: 🔴 Sin suscripciones activas

❌ Sin acceso a: GrupoA1

💳 Pagos: No hay registros
""".strip()
    
    # Get most recent subscription
    latest_sub = subscriptions_list[0]
    
    status = "🟢 Activo" if latest_sub["is_active"] else "🔴 Cancelado"
    if not latest_sub["is_active"] and latest_sub["expiry_date"] < datetime.utcnow():
        status = "🟡 Expirado"
    
    local_tz = pytz.timezone('America/Mexico_City')
    start_date = latest_sub["start_date"].astimezone(local_tz)
    
    return f"""
👤 ID: {user["telegram_id"]}  
🧑 Nombre: {user["full_name"]}  
📊 Estado: {status}

📥 Suscrito a: {"GrupoA1" if latest_sub["is_active"] else "Ninguno"}  
{"✅ Con acceso a: GrupoA1" if latest_sub["is_active"] else "❌ Sin acceso a: GrupoA1"}

💳 Pagos:  
{latest_sub["payment_method"]} ID: {latest_sub["payment_id"]}
Monto: ${latest_sub["amount"]:.2f}

🧾 Suscripciones:  
🅿️ {status} {latest_sub["payment_method"].capitalize()} subscription  
en 𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 {latest_sub["plan_type"].upper()} 📦  
Inició: {start_date.strftime('%d de %B de %Y')}
""".strip()

# -------------------- Markup Creators --------------------
def welcome_markup():
    """Create welcome markup with buttons"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📦 Ver Planes", callback_data="plans")
    )
    markup.row(
        InlineKeyboardButton("🧠 Créditos del Bot", callback_data="credits"),
        InlineKeyboardButton("📜 Términos de Uso", callback_data="terms")
    )
    return markup

def plans_markup():
    """Create markup with subscription plans"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🎥 Tutorial de Pagos", callback_data="tutorial")
    )
    markup.row(
        InlineKeyboardButton("🗓️ Plan Semanal", callback_data="plan_weekly"),
        InlineKeyboardButton("📆 Plan Mensual", callback_data="plan_monthly")
    )
    markup.row(
        InlineKeyboardButton("🔙 Atrás", callback_data="back_to_start")
    )
    return markup

def payment_methods_markup(plan_type):
    """Create markup with payment methods for a specific plan"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🅿️ Pagar con PayPal", callback_data=f"pay_paypal_{plan_type}")
    )
    markup.row(
        InlineKeyboardButton("🔙 Atrás", callback_data="back_to_plans")
    )
    return markup

def back_markup(callback_data="back_to_start"):
    """Create markup with just a back button"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔙 Atrás", callback_data=callback_data)
    )
    return markup

def admin_whitelist_time_markup(user_id):
    """Create markup for admin to select whitelist time"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⏳ Tiempo de Whitelist", callback_data=f"whitelist_time_{user_id}")
    )
    return markup

# -------------------- Admin state --------------------
admin_whitelist_state = {}

# -------------------- Command Handlers --------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle the /start command"""
    try:
        # Log for debugging
        logger.info(f"/start command received from user {message.from_user.id}")
        
        # Get user information
        user_id = message.from_user.id
        username = message.from_user.username
        full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        
        logger.info(f"Processing /start command for: {full_name} (@{username}) [ID: {user_id}]")
        
        # Register user if doesn't exist
        user = get_user(user_id)
        if not user:
            logger.info(f"Registering new user: {user_id}")
            user = create_user(user_id, full_name, username)
        else:
            logger.info(f"Existing user: {user_id}")
        
        # Prepare welcome message
        welcome_text = welcome_message()
        logger.info(f"Welcome message: {welcome_text[:50]}...")
        
        # Create markup
        markup = welcome_markup()
        logger.info("Welcome markup created")
        
        # Send welcome message with main buttons
        logger.info(f"Sending message to chat_id: {message.chat.id}")
        
        try:
            sent_msg = bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            logger.info(f"Welcome message sent successfully. ID: {sent_msg.message_id}")
        except Exception as e:
            logger.error(f"Error sending message to Telegram: {str(e)}")
            logger.error(traceback.format_exc())
            # Try with a simplified version
            try:
                sent_msg = bot.send_message(
                    chat_id=message.chat.id,
                    text="¡Bienvenido al Bot de Suscripciones VIP!"
                )
                logger.info(f"Simplified message sent. ID: {sent_msg.message_id}")
            except Exception as inner_e:
                logger.error(f"Error sending simplified message: {str(inner_e)}")
    
    except Exception as e:
        logger.error(f"General error processing /start command: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Try to send a simplified message in case of error
        try:
            bot.send_message(
                chat_id=message.chat.id,
                text="👋 ¡Bienvenido! Estamos experimentando problemas técnicos. Por favor, intenta nuevamente en unos momentos."
            )
        except Exception as reply_error:
            logger.error(f"Could not send error message: {str(reply_error)}")

@bot.message_handler(commands=['whitelist'])
def handle_whitelist_command(message):
    """Handle the /whitelist command to add users to the whitelist"""
    user_id = message.from_user.id
    
    # Verify if admin
    if not is_admin(user_id):
        bot.reply_to(message, "❌ No tienes permisos para usar este comando.")
        return
    
    # Verify command format
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Uso incorrecto. Formato: `/whitelist USER_ID`", parse_mode='Markdown')
        return
    
    try:
        # Get target user ID
        target_user_id = int(args[1])
        
        # Look for user in database
        user = get_user(target_user_id)
        username = None
        full_name = None
        
        if user:
            username = user["username"]
            full_name = user["full_name"]
        
        # Send confirmation message
        sent_msg = bot.reply_to(
            message,
            admin_whitelist_request(target_user_id, username, full_name),
            reply_markup=admin_whitelist_time_markup(target_user_id),
            parse_mode='HTML'
        )
        
        # Save state
        admin_whitelist_state[user_id] = {
            'target_user_id': target_user_id,
            'waiting_for_time': False,
            'message_id': sent_msg.message_id
        }
        
    except ValueError:
        bot.reply_to(message, "❌ El ID de usuario debe ser un número.")

@bot.message_handler(commands=['subinfo'])
def handle_subinfo_command(message):
    """Handle the /subinfo command to show user subscription information"""
    user_id = message.from_user.id
    
    # Verify if admin
    if not is_admin(user_id):
        bot.reply_to(message, "❌ No tienes permisos para usar este comando.")
        return
    
    # Verify command format
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Uso incorrecto. Formato: `/subinfo USER_ID`", parse_mode='Markdown')
        return
    
    try:
        # Get target user ID
        target_user_id = int(args[1])
        
        # Look for user and subscriptions
        user = get_user(target_user_id)
        
        if not user:
            bot.reply_to(message, f"❌ Usuario con ID {target_user_id} no encontrado.")
            return
        
        # Get user subscriptions
        user_subs = []
        for sub_id, sub in sorted(subscriptions.items(), key=lambda x: x[1]["start_date"], reverse=True):
            if sub["user_id"] == target_user_id:
                user_subs.append(sub)
                if len(user_subs) >= 5:  # Limit to 5 subscriptions
                    break
        
        # Show information
        bot.reply_to(
            message,
            user_subscription_info(user, user_subs),
            parse_mode='HTML'
        )
        
    except ValueError:
        bot.reply_to(message, "❌ El ID de usuario debe ser un número.")

# -------------------- Callback Handlers --------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle all callback queries"""
    try:
        # Log for debugging
        logger.info(f"Callback received: {call.data} from user {call.from_user.id}")
        
        # Avoid the waiting clock
        bot.answer_callback_query(call.id)
        
        # Handle different callbacks
        if call.data == "plans":
            logger.info("Processing 'plans' callback")
            # Show available plans
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=plans_message(),
                reply_markup=plans_markup(),
                parse_mode='HTML'
            )
            logger.info("Plans message sent successfully")
        
        elif call.data == "back_to_start":
            logger.info("Processing 'back_to_start' callback")
            # Return to main menu
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=welcome_message(),
                reply_markup=welcome_markup(),
                parse_mode='HTML'
            )
            logger.info("Welcome message sent successfully")
        
        elif call.data == "back_to_plans":
            logger.info("Processing 'back_to_plans' callback")
            # Return to plans menu
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=plans_message(),
                reply_markup=plans_markup(),
                parse_mode='HTML'
            )
            logger.info("Plans message sent successfully")
        
        elif call.data.startswith("plan_"):
            plan_type = call.data.split("_")[1]  # weekly or monthly
            logger.info(f"Processing 'plan_{plan_type}' callback")
            
            # Show selected plan details
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=subscription_details(plan_type),
                reply_markup=payment_methods_markup(plan_type),
                parse_mode='HTML'
            )
            logger.info(f"Plan {plan_type} details sent successfully")
        
        elif call.data.startswith("pay_"):
            parts = call.data.split("_")
            if len(parts) != 3:
                return
            
            _, payment_method, plan_type = parts
            
            # Verify that it's PayPal
            if payment_method != "paypal":
                bot.answer_callback_query(call.id, "Solo pagos con PayPal están disponibles")
                return
            
            # Get plan details
            plan = SUBSCRIPTION_PLANS.get(plan_type)
            if not plan:
                bot.answer_callback_query(call.id, "Plan no válido")
                return
            
            # Show processing message
            bot.answer_callback_query(call.id)
            payment_msg = bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=payment_processing(),
                reply_markup=None
            )
            
            # Process payment (simulate in this case)
            try:
                user_id = call.from_user.id
                
                # Create/update subscription
                user = get_user(user_id)
                if not user:
                    # Create user if doesn't exist
                    full_name = f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip()
                    user = create_user(user_id, full_name, call.from_user.username)
                
                # Calculate expiry date
                expiry_date = datetime.utcnow() + timedelta(days=plan['duration_days'])
                
                # Create new subscription
                payment_id = f"PP-{user_id}-{int(datetime.utcnow().timestamp())}"
                subscription = create_subscription(
                    user_id=user_id,
                    plan_type=plan_type,
                    payment_method=payment_method,
                    payment_id=payment_id,
                    amount=plan['price'],
                    expiry_date=expiry_date
                )
                
                # Simulate a delay for processing
                import time
                time.sleep(2)
                
                # Show success message
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=payment_msg.message_id,
                    text=payment_success(subscription, payment_method),
                    reply_markup=back_markup(),
                    parse_mode='HTML'
                )
                
                # Notify admins
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=admin_new_subscription_notification(subscription, user, payment_method),
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        # Ignore errors when sending to admins
                        logger.error(f"Error notifying admin {admin_id}: {str(e)}")
                        
            except Exception as e:
                # Show error message
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=payment_msg.message_id,
                    text=f"❌ Error inesperado: {str(e)}",
                    reply_markup=back_markup("back_to_plans")
                )
                
                # Log error
                logger.error(f"Error in payment processing: {str(e)}")
                logger.error(traceback.format_exc())
        
        elif call.data == "tutorial":
            logger.info("Processing 'tutorial' callback")
            # Show payment tutorial
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=tutorial_message(),
                reply_markup=back_markup("back_to_plans"),
                parse_mode='Markdown'
            )
            logger.info("Tutorial sent successfully")
        
        elif call.data == "terms":
            logger.info("Processing 'terms' callback")
            # Show terms of use
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=terms_message(),
                reply_markup=back_markup(),
                parse_mode='Markdown'
            )
            logger.info("Terms sent successfully")
        
        elif call.data == "credits":
            logger.info("Processing 'credits' callback")
            # Show bot credits
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=credits_message(),
                reply_markup=back_markup(),
                parse_mode='Markdown'
            )
            logger.info("Credits sent successfully")
        
        elif call.data.startswith("whitelist_time_"):
            # Verify if admin
            user_id = call.from_user.id
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "No tienes permisos para esta acción")
                return
            
            # Get target user ID from callback data
            target_user_id = int(call.data.split("_")[-1])
            
            # Respond to callback
            bot.answer_callback_query(call.id)
            
            # Update message asking for time
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=admin_whitelist_time_instructions(),
                parse_mode='Markdown'
            )
            
            # Update state
            admin_whitelist_state[user_id] = {
                'target_user_id': target_user_id,
                'waiting_for_time': True,
                'message_id': call.message.message_id
            }
        
        else:
            logger.warning(f"Unrecognized callback: {call.data}")
            
    except Exception as e:
        logger.error(f"Error processing callback '{call.data}': {str(e)}")
        logger.error(traceback.format_exc())
        
        # Try to respond to the user that there was an error
        try:
            bot.answer_callback_query(call.id, "Hubo un error procesando tu solicitud. Intenta nuevamente.")
        except Exception:
            pass

# -------------------- Text Message Handlers --------------------
@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and 
                           message.from_user.id in admin_whitelist_state and
                           admin_whitelist_state.get(message.from_user.id, {}).get('waiting_for_time', False),
                     content_types=['text'])
def handle_whitelist_time_response(message):
    """Process whitelist time response"""
    user_id = message.from_user.id
    state = admin_whitelist_state[user_id]
    
    # Try to parse the time
    time_text = message.text.strip()
    try:
        # Import dateparser for time parsing
        import dateparser
        
        # Parse time using dateparser
        duration = dateparser.parse(f"in {time_text}", settings={'PREFER_DATES_FROM': 'future'})
        
        if not duration:
            bot.reply_to(message, "❌ Formato de tiempo no válido. Intenta con: `7 days`, `1 month`, etc.", parse_mode='Markdown')
            return
        
        # Calculate expiry date
        now = datetime.utcnow()
        expiry_date = duration
        
        # If duration is in the past or equal to present, it's an error
        if expiry_date <= now:
            bot.reply_to(message, "❌ La duración debe ser positiva.", parse_mode='Markdown')
            return
        
        # Add user to whitelist
        target_user_id = state['target_user_id']
        
        # Check if user exists, otherwise create it
        user = get_user(target_user_id)
        if not user:
            # Create user with minimal information
            user = create_user(target_user_id, f"User_{target_user_id}")
        
        # Add to whitelist (create manual subscription)
        subscription = add_to_whitelist(target_user_id, expiry_date)
        
        if subscription:
            # Calculate duration text
            delta = expiry_date - now
            days = delta.days
            
            duration_text = f"{days} días"
            if days >= 30:
                months = days // 30
                remaining_days = days % 30
                duration_text = f"{months} mes(es)"
                if remaining_days > 0:
                    duration_text += f" y {remaining_days} día(s)"
            
            # Send success message
            bot.reply_to(
                message,
                admin_whitelist_success(target_user_id, duration_text)
            )
            
            # Notify user they've been added to whitelist
            try:
                bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ Has sido añadido al grupo VIP por un administrador.\nDuración: {duration_text}\n\nAquí tienes tu enlace de acceso:\n{GROUP_INVITE_LINK}"
                )
            except Exception:
                # Ignore errors when sending message to user
                pass
        else:
            bot.reply_to(message, "❌ Error al añadir el usuario a la whitelist.")
    
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
    
    # Clean state
    if user_id in admin_whitelist_state:
        del admin_whitelist_state[user_id]

# -------------------- Webhook Routes --------------------
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    try:
        logger.info("Telegram webhook request received")
        
        if request.headers.get('content-type') != 'application/json':
            logger.warning(f"Invalid content type: {request.headers.get('content-type')}")
            return Response(status=403)
        
        json_string = request.get_data().decode('utf-8')
        
        # Validate JSON
        try:
            update = Update.de_json(json_string)
            logger.info(f"Processing update_id: {update.update_id}")
            
            # Show more details for diagnosis
            if update.message:
                logger.info(f"Message received from: {update.message.from_user.id}, text: {update.message.text}")
            elif update.callback_query:
                logger.info(f"Callback received from: {update.callback_query.from_user.id}, data: {update.callback_query.data}")
                
            # Process the update
            bot.process_new_updates([update])
            return Response(status=200)
            
        except Exception as json_error:
            logger.error(f"Error processing JSON: {str(json_error)}")
            logger.error(f"Received JSON: {json_string}")
            logger.error(traceback.format_exc())
            return Response(status=400)  # Bad request
            
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(status=500)  # Internal error

@app.route('/')
def index():
    try:
        me = bot.get_me()
        status_msg = f"Bot @{me.username} is running! (ID: {me.id})"
        logger.info(status_msg)
        return status_msg
    except Exception as e:
        error_msg = f"Error connecting to Telegram API: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return jsonify({"error": error_msg}), 500

# -------------------- Initialize --------------------
def setup_app():
    """Initial application setup"""
    try:
        logger.info("Initializing application...")
        
        # Configure webhook in production
        if os.environ.get('ENVIRONMENT') != 'development':
            bot.remove_webhook()
            webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
            logger.info(f"Configuring webhook at URL: {webhook_url}")
            bot.set_webhook(url=webhook_url)
            logger.info("Webhook configured successfully")
    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        logger.error(traceback.format_exc())

# Run setup immediately
setup_app()

# Main entry point
if __name__ == "__main__":
    # If in local development, use polling instead of webhook
    if os.environ.get('ENVIRONMENT') == 'development':
        logger.info("Starting in development mode (polling)")
        bot.remove_webhook()
        bot.polling(none_stop=True)
    else:
        # In production, webhook is already configured in setup_app()
        # Start Flask server
        port = int(os.environ.get('PORT', PORT))
        logger.info(f"Starting server on port: {port}")
        app.run(host='0.0.0.0', port=port, debug=False)