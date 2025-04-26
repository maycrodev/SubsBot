import stripe
import logging
from datetime import datetime, timedelta

import config

# Configurar logger
logger = logging.getLogger(__name__)

# Configurar Stripe
stripe.api_key = config.STRIPE_SECRET_KEY

def create_customer(email, name, telegram_id):
    """
    Crea un nuevo cliente en Stripe.
    
    Args:
        email: Email del cliente
        name: Nombre del cliente
        telegram_id: ID de Telegram
        
    Returns:
        tuple: (success, customer_id, error_message)
    """
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={
                'telegram_id': str(telegram_id)
            }
        )
        return True, customer.id, None
    except stripe.error.StripeError as e:
        logger.error(f"Error al crear cliente Stripe: {str(e)}")
        return False, None, str(e)

def create_payment_intent(amount, currency, customer_id, payment_method_id, description, metadata=None):
    """
    Crea un intent de pago en Stripe.
    
    Args:
        amount: Cantidad en centavos (ej: 500 para $5.00)
        currency: Moneda (ej: "usd")
        customer_id: ID del cliente
        payment_method_id: ID del método de pago
        description: Descripción del pago
        metadata: Metadatos adicionales
        
    Returns:
        tuple: (success, payment_intent, error_message)
    """
    if metadata is None:
        metadata = {}
        
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convertir a centavos
            currency=currency.lower(),
            customer=customer_id,
            payment_method=payment_method_id,
            off_session=False,
            confirm=True,
            description=description,
            metadata=metadata
        )
        return True, payment_intent, None
    except stripe.error.StripeError as e:
        logger.error(f"Error al crear PaymentIntent Stripe: {str(e)}")
        return False, None, str(e)

def create_subscription(customer_id, price_id, metadata=None):
    """
    Crea una suscripción en Stripe.
    
    Args:
        customer_id: ID del cliente
        price_id: ID del precio
        metadata: Metadatos adicionales
        
    Returns:
        tuple: (success, subscription, error_message)
    """
    if metadata is None:
        metadata = {}
        
    try:
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': price_id}],
            expand=['latest_invoice.payment_intent'],
            metadata=metadata
        )
        return True, subscription, None
    except stripe.error.StripeError as e:
        logger.error(f"Error al crear Suscripción Stripe: {str(e)}")
        return False, None, str(e)

def create_checkout_session(plan_type, success_url, cancel_url, customer_email=None, customer_id=None, metadata=None):
    """
    Crea una sesión de checkout para suscripción.
    
    Args:
        plan_type: Tipo de plan ("weekly" o "monthly")
        success_url: URL de éxito
        cancel_url: URL de cancelación
        customer_email: Email del cliente (opcional)
        customer_id: ID del cliente (opcional)
        metadata: Metadatos adicionales
        
    Returns:
        tuple: (success, session_id, session_url, error_message)
    """
    if metadata is None:
        metadata = {}
        
    # Obtener información del plan
    plan_info = config.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan_info:
        return False, None, None, "Tipo de plan no válido"
    
    # Configurar precios según el plan
    price_data = {
        'currency': 'usd',
        'unit_amount_decimal': str(int(plan_info['price'] * 100)),
        'recurring': {
            'interval': 'week' if plan_type == 'weekly' else 'month',
            'interval_count': 1
        },
        'product_data': {
            'name': f"Suscripción VIP {plan_info['name']}",
            'description': f"Acceso VIP por {plan_info['duration']}"
        }
    }
    
    try:
        # Crear sesión de checkout
        session_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'quantity': 1,
                'price_data': price_data
            }],
            'mode': 'subscription',
            'success_url': success_url,
            'cancel_url': cancel_url,
            'metadata': metadata
        }
        
        # Añadir cliente si está disponible
        if customer_id:
            session_params['customer'] = customer_id
        elif customer_email:
            session_params['customer_email'] = customer_email
        
        checkout_session = stripe.checkout.Session.create(**session_params)
        
        return True, checkout_session.id, checkout_session.url, None
    except stripe.error.StripeError as e:
        logger.error(f"Error al crear sesión de checkout Stripe: {str(e)}")
        return False, None, None, str(e)

def cancel_subscription(subscription_id):
    """
    Cancela una suscripción de Stripe.
    
    Args:
        subscription_id: ID de la suscripción
        
    Returns:
        tuple: (success, error_message)
    """
    try:
        subscription = stripe.Subscription.delete(subscription_id)
        return True, None
    except stripe.error.StripeError as e:
        logger.error(f"Error al cancelar suscripción Stripe: {str(e)}")
        return False, str(e)

def verify_webhook_signature(payload, sig_header, webhook_secret):
    """
    Verifica la firma de un webhook de Stripe.
    
    Args:
        payload: Cuerpo del webhook
        sig_header: Encabezado de firma
        webhook_secret: Secreto del webhook
        
    Returns:
        tuple: (success, event, error_message)
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return True, event, None
    except ValueError as e:
        # Invalid payload
        return False, None, f"Payload inválido: {str(e)}"
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return False, None, f"Firma inválida: {str(e)}"
    except Exception as e:
        # Other errors
        return False, None, f"Error inesperado: {str(e)}"

def process_webhook_event(event):
    """
    Procesa un evento de webhook de Stripe.
    
    Args:
        event: Evento de Stripe
        
    Returns:
        tuple: (success, action, subscription_id, customer_id, metadata, error_message)
    """
    try:
        event_type = event['type']
        
        if event_type == 'checkout.session.completed':
            # Sesión de checkout completada
            session = event['data']['object']
            
            # Solo procesar si es una suscripción
            if session.get('mode') == 'subscription':
                subscription_id = session.get('subscription')
                customer_id = session.get('customer')
                metadata = session.get('metadata', {})
                
                return True, "created", subscription_id, customer_id, metadata, None
        
        elif event_type == 'customer.subscription.created':
            # Suscripción creada
            subscription = event['data']['object']
            subscription_id = subscription.get('id')
            customer_id = subscription.get('customer')
            metadata = subscription.get('metadata', {})
            
            return True, "created", subscription_id, customer_id, metadata, None
        
        elif event_type == 'customer.subscription.updated':
            # Suscripción actualizada
            subscription = event['data']['object']
            subscription_id = subscription.get('id')
            customer_id = subscription.get('customer')
            metadata = subscription.get('metadata', {})
            status = subscription.get('status')
            
            if status == 'active':
                return True, "activated", subscription_id, customer_id, metadata, None
            elif status == 'past_due':
                return True, "past_due", subscription_id, customer_id, metadata, None
            elif status == 'canceled':
                return True, "cancelled", subscription_id, customer_id, metadata, None
            elif status == 'unpaid':
                return True, "unpaid", subscription_id, customer_id, metadata, None
            else:
                return True, "updated", subscription_id, customer_id, metadata, None
        
        elif event_type == 'customer.subscription.deleted':
            # Suscripción eliminada
            subscription = event['data']['object']
            subscription_id = subscription.get('id')
            customer_id = subscription.get('customer')
            metadata = subscription.get('metadata', {})
            
            return True, "deleted", subscription_id, customer_id, metadata, None
        
        elif event_type == 'invoice.payment_succeeded':
            # Pago de factura exitoso
            invoice = event['data']['object']
            subscription_id = invoice.get('subscription')
            customer_id = invoice.get('customer')
            
            if subscription_id:
                # Obtener metadatos de la suscripción
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    metadata = subscription.get('metadata', {})
                except Exception:
                    metadata = {}
                
                return True, "payment_succeeded", subscription_id, customer_id, metadata, None
        
        elif event_type == 'invoice.payment_failed':
            # Pago de factura fallido
            invoice = event['data']['object']
            subscription_id = invoice.get('subscription')
            customer_id = invoice.get('customer')
            
            if subscription_id:
                # Obtener metadatos de la suscripción
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    metadata = subscription.get('metadata', {})
                except Exception:
                    metadata = {}
                
                return True, "payment_failed", subscription_id, customer_id, metadata, None
        
        # Evento no manejado
        return False, None, None, None, {}, f"Tipo de evento no manejado: {event_type}"
    
    except Exception as e:
        logger.error(f"Error al procesar evento webhook Stripe: {str(e)}")
        return False, None, None, None, {}, str(e)