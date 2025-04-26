from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def welcome_markup():
    """Crea el markup de bienvenida con botones"""
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
    """Crea el markup con los planes de suscripción"""
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
    """Crea el markup con los métodos de pago para un plan específico"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🅿️ Pagar con PayPal", callback_data=f"pay_paypal_{plan_type}")
    )
    markup.row(
        InlineKeyboardButton("🔙 Atrás", callback_data="back_to_plans")
    )
    return markup

def back_markup(callback_data="back_to_start"):
    """Crea un markup con solo un botón de regreso"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔙 Atrás", callback_data=callback_data)
    )
    return markup

def admin_whitelist_time_markup(user_id):
    """Crea un markup para que el admin seleccione tiempo de whitelist"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⏳ Tiempo de Whitelist", callback_data=f"whitelist_time_{user_id}")
    )
    return markup

def admin_confirm_whitelist_markup(user_id):
    """Crea un markup para confirmar la adición a la whitelist"""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_whitelist_{user_id}"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel_admin_action")
    )
    return markup