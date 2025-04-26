import paypalrestsdk
import logging
from datetime import datetime, timedelta

import config

# Configurar logger
logger = logging.getLogger(__name__)

# Configurar SDK de PayPal
paypalrestsdk.configure({
    "mode": config.PAYPAL_MODE,  # sandbox o live
    "client_id": config.PAYPAL_CLIENT_ID,
    "client_secret": config.PAYPAL_CLIENT_SECRET
})

def create_subscription_plan(plan_type):
    """
    Crea un plan de suscripción en PayPal.
    
    Args:
        plan_type: Tipo de plan ("weekly" o "monthly")
        
    Returns:
        tuple: (success, plan_id, error_message)
    """
    plan_info = config.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan_info:
        return False, None, "Tipo de plan no válido"
    
    # Definir el plan
    billing_cycles = []
    
    # Ciclo de facturación regular
    if plan_type == "weekly":
        frequency = "WEEK"
        frequency_interval = "1"
    elif plan_type == "monthly":
        frequency = "MONTH"
        frequency_interval = "1"
    else:
        return False, None, f"Tipo de plan {plan_type} no soportado"
    
    billing_cycles.append({
        "frequency": {
            "interval_unit": frequency,
            "interval_count": frequency_interval
        },
        "tenure_type": "REGULAR",
        "sequence": 1,
        "total_cycles": 0,  # 0 significa infinito
        "pricing_scheme": {
            "fixed_price": {
                "value": str(plan_info['price']),
                "currency_code": "USD"
            }
        }
    })
    
    # Crear el plan
    plan = {
        "name": f"VIP Bot {plan_info['name']}",
        "description": f"Acceso VIP por {plan_info['duration']}",
        "type": "INFINITE",
        "payment_definitions": [
            {
                "name": "Regular Payment",
                "type": "REGULAR",
                "frequency": frequency,
                "frequency_interval": frequency_interval,
                "amount": {
                    "value": str(plan_info['price']),
                    "currency": "USD"
                },
                "cycles": "0"  # Infinito
            }
        ],
        "merchant_preferences": {
            "setup_fee": {
                "value": "0",
                "currency": "USD"
            },
            "auto_bill_amount": "YES",
            "max_fail_attempts": "3"
        }
    }
    
    try:
        billing_plan = paypalrestsdk.BillingPlan(plan)
        if billing_plan.create():
            # Activar el plan
            billing_plan.replace([
                {
                    "op": "replace",
                    "path": "/",
                    "value": {
                        "state": "ACTIVE"
                    }
                }
            ])
            return True, billing_plan.id, None
        else:
            return False, None, billing_plan.error
    except Exception as e:
        logger.error(f"Error al crear plan PayPal: {str(e)}")
        return False, None, str(e)

def create_subscription_agreement(plan_id, user_id, return_url, cancel_url):
    """
    Crea un acuerdo de suscripción para que el usuario lo acepte.
    
    Args:
        plan_id: ID del plan de PayPal
        user_id: ID de Telegram del usuario
        return_url: URL de retorno después del pago
        cancel_url: URL si se cancela el pago
        
    Returns:
        tuple: (success, agreement_url, agreement_id, error_message)
    """
    # Calcular fechas
    start_date = datetime.utcnow() + timedelta(minutes=5)
    
    # Crear acuerdo
    agreement = {
        "name": "Suscripción VIP Bot",
        "description": "Suscripción para acceso al grupo VIP",
        "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": {
            "id": plan_id
        },
        "payer": {
            "payment_method": "paypal"
        },
        "override_merchant_preferences": {
            "return_url": return_url,
            "cancel_url": cancel_url
        }
    }
    
    try:
        billing_agreement = paypalrestsdk.BillingAgreement(agreement)
        if billing_agreement.create():
            for link in billing_agreement.links:
                if link.rel == "approval_url":
                    return True, link.href, billing_agreement.id, None
            
            return False, None, None, "No se encontró la URL de aprobación"
        else:
            return False, None, None, billing_agreement.error
    except Exception as e:
        logger.error(f"Error al crear acuerdo PayPal: {str(e)}")
        return False, None, None, str(e)

def execute_subscription_agreement(token):
    """
    Ejecuta un acuerdo de suscripción después de que el usuario lo acepte.
    
    Args:
        token: Token de PayPal
        
    Returns:
        tuple: (success, agreement_data, error_message)
    """
    try:
        billing_agreement = paypalrestsdk.BillingAgreement.execute(token)
        return True, {
            "id": billing_agreement.id,
            "state": billing_agreement.state,
            "payer_email": billing_agreement.payer.payer_info.email
        }, None
    except Exception as e:
        logger.error(f"Error al ejecutar acuerdo PayPal: {str(e)}")
        return False, None, str(e)

def cancel_subscription(subscription_id, reason="Cancelación solicitada por el usuario"):
    """
    Cancela una suscripción de PayPal.
    
    Args:
        subscription_id: ID de la suscripción de PayPal
        reason: Motivo de la cancelación
        
    Returns:
        tuple: (success, error_message)
    """
    try:
        agreement = paypalrestsdk.BillingAgreement.find(subscription_id)
        cancel_note = {"note": reason}
        if agreement.cancel(cancel_note):
            return True, None
        else:
            return False, agreement.error
    except Exception as e:
        logger.error(f"Error al cancelar suscripción PayPal: {str(e)}")
        return False, str(e)

def verify_webhook_signature(transmission_id, timestamp, webhook_id, event_body, cert_url, actual_signature):
    """
    Verifica la firma de un webhook de PayPal.
    
    Args:
        transmission_id: ID de transmisión
        timestamp: Timestamp
        webhook_id: ID del webhook
        event_body: Cuerpo del evento
        cert_url: URL del certificado
        actual_signature: Firma actual
        
    Returns:
        bool: True si la firma es válida
    """
    try:
        return paypalrestsdk.notifications.WebhookEvent.verify(
            transmission_id=transmission_id,
            timestamp=timestamp,
            webhook_id=webhook_id,
            event_body=event_body,
            cert_url=cert_url,
            actual_signature=actual_signature
        )
    except Exception as e:
        logger.error(f"Error al verificar firma webhook PayPal: {str(e)}")
        return False

def process_webhook_event(event_type, event_data):
    """
    Procesa un evento de webhook de PayPal.
    
    Args:
        event_type: Tipo de evento
        event_data: Datos del evento
        
    Returns:
        tuple: (success, action, subscription_id, error_message)
    """
    try:
        if event_type == "BILLING.SUBSCRIPTION.CREATED":
            # Nueva suscripción creada
            return True, "created", event_data["resource"]["id"], None
        
        elif event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            # Suscripción activada
            return True, "activated", event_data["resource"]["id"], None
        
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            # Suscripción cancelada
            return True, "cancelled", event_data["resource"]["id"], None
        
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
            # Suscripción suspendida
            return True, "suspended", event_data["resource"]["id"], None
        
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            # Pago de suscripción fallido
            return True, "payment_failed", event_data["resource"]["id"], None
        
        elif event_type == "PAYMENT.SALE.COMPLETED":
            # Pago completado
            return True, "payment_completed", event_data["resource"]["billing_agreement_id"], None
        
        else:
            # Evento no manejado
            return False, None, None, f"Tipo de evento no manejado: {event_type}"
    
    except Exception as e:
        logger.error(f"Error al procesar evento webhook PayPal: {str(e)}")
        return False, None, None, str(e)