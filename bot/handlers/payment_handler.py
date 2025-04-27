from telebot import TeleBot
from telebot.types import CallbackQuery, Message
import threading
import time
from datetime import datetime, timedelta

import config
from bot.keyboards.markup_creator import back_markup
from bot.utils.messages import payment_processing, payment_success, admin_new_subscription_notification
from bot.utils.animations import start_payment_animation
from db.repository.user_repo import UserRepository
from db.repository.subscription_repo import SubscriptionRepository
from db.database import SessionLocal

# Simulación de procesamiento de pago (en un escenario real se usarían las APIs reales)
def process_payment_simulation(payment_method, plan_type, user_id):
    """
    Simula un procesamiento de pago. En implementación real,
    se usarían las APIs de PayPal.
    
    Returns:
        tuple: (success, payment_id)
    """
    # Simular tiempo de procesamiento
    time.sleep(5)
    
    # Simulamos éxito (solo PayPal)
    payment_id = f"PP-{user_id}-{int(time.time())}"
    
    return True, payment_id

def handle_payment_callback(call: CallbackQuery, bot: TeleBot):
    """
    Maneja los callbacks relacionados con pagos.
    
    Args:
        call: Datos del callback
        bot: Instancia del bot
    """
    # Verificar si es un callback de pago
    if not call.data.startswith("pay_"):
        return
    
    # Parse del callback data
    parts = call.data.split("_")
    if len(parts) != 3:
        return
    
    _, payment_method, plan_type = parts
    
    # Verificar que sea PayPal
    if payment_method != "paypal":
        bot.answer_callback_query(call.id, "Solo pagos con PayPal están disponibles")
        return
    
    # Obtener detalles del plan
    plan = config.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan:
        bot.answer_callback_query(call.id, "Plan no válido")
        return
    
    # Mostrar mensaje de procesamiento con animación
    bot.answer_callback_query(call.id)
    payment_msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=payment_processing(),
        reply_markup=None
    )
    
    # Iniciar animación de procesamiento
    stop_event = threading.Event()
    animation_thread = start_payment_animation(
        bot, call.message.chat.id, payment_msg.message_id, stop_event
    )
    
    # Procesar el pago (simular en este caso)
    try:
        user_id = call.from_user.id
        success, payment_id = process_payment_simulation(payment_method, plan_type, user_id)
        
        # Detener la animación
        stop_event.set()
        animation_thread.join(timeout=1)
        
        # Manejar resultado del pago
        if success:
            # Crear/actualizar suscripción en la base de datos
            db = SessionLocal()
            try:
                # Obtener usuario
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    # Crear usuario si no existe
                    full_name = f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip()
                    user = UserRepository.create_user(db, user_id, full_name, call.from_user.username)
                
                # Calcular fecha de expiración
                expiry_date = datetime.utcnow() + timedelta(days=plan['duration_days'])
                
                # Crear nueva suscripción
                subscription = SubscriptionRepository.create_subscription(
                    db,
                    user_id=user_id,
                    plan_type=plan_type,
                    payment_method=payment_method,
                    payment_id=payment_id,
                    amount=plan['price'],
                    expiry_date=expiry_date
                )
                
                # Mostrar mensaje de éxito
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=payment_msg.message_id,
                    text=payment_success(subscription, payment_method),
                    reply_markup=back_markup(),
                    parse_mode='HTML'
                )
                
                # Notificar a los administradores
                for admin_id in config.ADMIN_IDS:
                    try:
                        bot.send_message(
                            chat_id=admin_id,
                            text=admin_new_subscription_notification(subscription, user, payment_method),
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        # Ignorar errores al enviar a admins
                        pass
                
            finally:
                db.close()
        else:
            # Mostrar error de pago
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=payment_msg.message_id,
                text="❌ Error en el procesamiento del pago. Por favor, intenta de nuevo.",
                reply_markup=back_markup("back_to_plans")
            )
    
    except Exception as e:
        # Detener animación en caso de error
        stop_event.set()
        if animation_thread.is_alive():
            animation_thread.join(timeout=1)
        
        # Mostrar mensaje de error
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=payment_msg.message_id,
            text=f"❌ Error inesperado: {str(e)}",
            reply_markup=back_markup("back_to_plans")
        )

def register_payment_handlers(bot: TeleBot):
    """
    Registra los handlers relacionados con pagos.
    
    Args:
        bot: Instancia del bot
    """
    bot.register_callback_query_handler(
        callback=handle_payment_callback,
        func=lambda call: call.data and call.data.startswith("pay_"),
        pass_bot=True
    )