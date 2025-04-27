import telebot
from telebot import types
import logging
from config import PLANS

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_plans_markup():
    """Crea los botones para el menú de planes"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Agregar tutorial de pagos
    markup.add(types.InlineKeyboardButton("🎥 Tutorial de Pagos", callback_data="tutorial"))
    
    # Agregar planes
    markup.add(
        types.InlineKeyboardButton("🗓️ Plan Semanal", callback_data="weekly_plan"),
        types.InlineKeyboardButton("📆 Plan Mensual", callback_data="monthly_plan")
    )
    
    # Agregar botón de volver
    markup.add(types.InlineKeyboardButton("🔙 Atrás", callback_data="back_to_main"))
    
    return markup

def show_plans(chat_id, message_id=None):
    """Muestra los planes de suscripción disponibles"""
    try:
        plans_text = (
            "💸 Escoge tu plan de suscripción:\n\n"
            "🔹 Plan Semanal: $3.50 / 1 semana\n"
            "🔸 Plan Mensual: $5.00 / 1 mes\n\n"
            "🧑‍🏫 ¿No sabes cómo pagar? Mira el tutorial 👇"
        )
        
        markup = create_plans_markup()
        
        if message_id:
            # Editar mensaje existente
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plans_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            # Enviar nuevo mensaje
            bot.send_message(
                chat_id=chat_id,
                text=plans_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        
        logger.info(f"Se mostraron planes al usuario {chat_id}")
        
    except Exception as e:
        logger.error(f"Error en show_plans: {str(e)}")
        try:
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ Ocurrió un error al mostrar los planes. Por favor, intenta nuevamente con /start."
                )
            else:
                bot.send_message(
                    chat_id=chat_id,
                    text="❌ Ocurrió un error al mostrar los planes. Por favor, intenta nuevamente con /start."
                )
        except:
            pass

def show_plan_details(chat_id, message_id, plan_id):
    """Muestra los detalles de un plan específico"""
    try:
        plan = PLANS.get(plan_id)
        if not plan:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Plan no encontrado. Por favor, intenta nuevamente."
            )
            return
        
        # Construir mensaje con detalles del plan
        plan_text = (
            f"📦 {plan['display_name']}\n\n"
            f"{plan['description']}\n"
            f"Beneficios:\n"
            f"✅ Grupo VIP (Acceso)\n"
            f"✅ 21,000 archivos exclusivos 📁\n\n"
            f"💵 Precio: ${plan['price_usd']:.2f} USD\n"
            f"📆 Facturación: {'semanal' if plan_id == 'weekly' else 'mensual'} (recurrente)\n\n"
            f"Selecciona un método de pago 👇"
        )
        
        # Crear markup con botones de pago
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🅿️ Pagar con PayPal", callback_data=f"payment_paypal_{plan_id}"),
            types.InlineKeyboardButton("🔙 Atrás", callback_data="view_plans")
        )
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plan_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        logger.info(f"Usuario {chat_id} está viendo detalles del plan {plan_id}")
        
    except Exception as e:
        logger.error(f"Error en show_plan_details: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Ocurrió un error al mostrar los detalles del plan. Por favor, intenta nuevamente."
            )
        except:
            pass

def show_payment_tutorial(chat_id, message_id):
    """Muestra el tutorial de pagos"""
    try:
        tutorial_text = (
            "🎥 *Tutorial de Pagos*\n\n"
            "Para suscribirte a nuestro grupo VIP, sigue estos pasos:\n\n"
            "1️⃣ Selecciona el plan que deseas (Semanal o Mensual)\n\n"
            "2️⃣ Haz clic en 'Pagar con PayPal'\n\n"
            "3️⃣ Serás redirigido a la página de PayPal donde puedes pagar con:\n"
            "   - Cuenta de PayPal\n"
            "   - Tarjeta de crédito/débito (sin necesidad de cuenta)\n\n"
            "4️⃣ Completa el pago y regresa a Telegram\n\n"
            "5️⃣ Recibirás un enlace de invitación al grupo VIP\n\n"
            "⚠️ Importante: Tu suscripción se renovará automáticamente. Puedes cancelarla en cualquier momento desde tu cuenta de PayPal."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Volver a los Planes", callback_data="view_plans"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=tutorial_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        logger.info(f"Usuario {chat_id} está viendo el tutorial de pagos")
        
    except Exception as e:
        logger.error(f"Error en show_payment_tutorial: {str(e)}")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Ocurrió un error al mostrar el tutorial. Por favor, intenta nuevamente."
            )
        except:
            pass

def handle_plans_callback(call):
    """Maneja los callbacks relacionados con la selección de planes"""
    try:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        if call.data == "tutorial":
            # Mostrar tutorial de pagos
            show_payment_tutorial(chat_id, message_id)
            
        elif call.data == "weekly_plan":
            # Mostrar detalles del plan semanal
            show_plan_details(chat_id, message_id, "weekly")
            
        elif call.data == "monthly_plan":
            # Mostrar detalles del plan mensual
            show_plan_details(chat_id, message_id, "monthly")
            
        elif call.data == "view_plans":
            # Volver a la vista de planes
            show_plans(chat_id, message_id)
            
        elif call.data == "back_to_main":
            # Volver al menú principal
            from handlers.start_handler import create_main_menu_markup
            
            welcome_text = (
                "👋 ¡Bienvenido al Bot de Suscripciones VIP!\n\n"
                "Este es un grupo exclusivo con contenido premium y acceso limitado.\n\n"
                "Selecciona una opción 👇"
            )
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=welcome_text,
                parse_mode='Markdown',
                reply_markup=create_main_menu_markup()
            )
        
        # Responder al callback para quitar el "reloj de espera" en el cliente
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error en handle_plans_callback: {str(e)}")
        try:
            bot.answer_callback_query(call.id, "❌ Ocurrió un error. Intenta nuevamente.")
        except:
            pass