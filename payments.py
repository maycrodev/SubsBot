import requests
import json
import base64
import datetime
from typing import Dict, Optional, Tuple
import logging

from config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, PLANS, WEBHOOK_URL

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# URLs base según el modo (sandbox o producción)
BASE_URL = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == 'sandbox' else "https://api-m.paypal.com"

def get_access_token() -> Optional[str]:
    """Obtiene un token de acceso para la API de PayPal"""
    try:
        auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = "grant_type=client_credentials"
        
        response = requests.post(f"{BASE_URL}/v1/oauth2/token", headers=headers, data=data)
        response.raise_for_status()
        
        return response.json().get("access_token")
    except Exception as e:
        logger.error(f"Error al obtener token de PayPal: {e}")
        return None

def create_product_if_not_exists() -> Optional[str]:
    """Crea un producto en PayPal si no existe aún y devuelve su ID"""
    try:
        token = get_access_token()
        if not token:
            return None
        
        # Verificar si ya tenemos el producto guardado (en una implementación real, deberías guardar esto)
        # Para simplificar, crearemos uno nuevo cada vez, pero lo ideal sería guardarlo
        product_name = "Grupo VIP"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "name": product_name,
            "description": "Acceso exclusivo a contenido premium",
            "type": "SERVICE",
            "category": "DIGITAL_GOODS"
        }
        
        response = requests.post(f"{BASE_URL}/v1/catalogs/products", headers=headers, json=data)
        response.raise_for_status()
        
        return response.json().get("id")
    except Exception as e:
        logger.error(f"Error al crear producto en PayPal: {e}")
        return None

def create_plan(plan_id: str, product_id: str) -> Optional[str]:
    """Crea un plan de suscripción en PayPal para el producto dado"""
    try:
        token = get_access_token()
        if not token:
            return None
        
        plan_details = PLANS.get(plan_id)
        if not plan_details:
            logger.error(f"Plan no reconocido: {plan_id}")
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"plan-{plan_id}-{datetime.datetime.now().timestamp()}"
        }
        
        # Determinar la unidad de tiempo y frecuencia según la duración
        interval_unit = "DAY"
        interval_count = plan_details['duration_days']
        if plan_id == "monthly":
            interval_unit = "MONTH"
            interval_count = 1
        elif plan_id == "weekly":
            interval_unit = "WEEK"
            interval_count = 1
        
        data = {
            "product_id": product_id,
            "name": plan_details['name'],
            "description": plan_details['description'],
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": interval_unit,
                        "interval_count": interval_count
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,  # 0 significa sin límite
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": str(plan_details['price_usd']),
                            "currency_code": "USD"
                        }
                    }
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "setup_fee": {
                    "value": "0",
                    "currency_code": "USD"
                },
                "setup_fee_failure_action": "CONTINUE",
                "payment_failure_threshold": 3
            }
        }
        
        response = requests.post(f"{BASE_URL}/v1/billing/plans", headers=headers, json=data)
        response.raise_for_status()
        
        return response.json().get("id")
    except Exception as e:
        logger.error(f"Error al crear plan en PayPal: {e}")
        return None

def create_subscription_link(plan_id: str, user_id: int) -> Optional[str]:
    """Crea un enlace de suscripción para que el usuario se suscriba a través de PayPal"""
    try:
        # Obtener un producto o crear uno nuevo
        product_id = create_product_if_not_exists()
        if not product_id:
            return None
        
        # Crear el plan basado en el producto
        paypal_plan_id = create_plan(plan_id, product_id)
        if not paypal_plan_id:
            return None
        
        token = get_access_token()
        if not token:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Configurar la URL de retorno con el ID del usuario y el plan
        return_url = f"{WEBHOOK_URL}/paypal/return?user_id={user_id}&plan_id={plan_id}"
        cancel_url = f"{WEBHOOK_URL}/paypal/cancel?user_id={user_id}&plan_id={plan_id}"
        
        data = {
            "plan_id": paypal_plan_id,
            "application_context": {
                "brand_name": "Bot Suscripciones VIP",
                "locale": "es-ES",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "payment_method": {
                    "payer_selected": "PAYPAL",
                    "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED"
                },
                "return_url": return_url,
                "cancel_url": cancel_url
            }
        }
        
        response = requests.post(f"{BASE_URL}/v1/billing/subscriptions", headers=headers, json=data)
        response.raise_for_status()
        
        response_data = response.json()
        
        # Extraer y devolver el enlace de aprobación (approve URL)
        for link in response_data.get("links", []):
            if link.get("rel") == "approve":
                return link.get("href")
        
        return None
    except Exception as e:
        logger.error(f"Error al crear enlace de suscripción: {e}")
        return None

def verify_subscription(subscription_id: str) -> Optional[Dict]:
    """Verifica y obtiene los detalles de una suscripción"""
    try:
        token = get_access_token()
        if not token:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(f"{BASE_URL}/v1/billing/subscriptions/{subscription_id}", headers=headers)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        logger.error(f"Error al verificar suscripción: {e}")
        return None

def get_subscription_details(subscription_id: str) -> Optional[Dict]:
    """Obtiene los detalles completos de una suscripción"""
    return verify_subscription(subscription_id)

def cancel_subscription(subscription_id: str, reason: str = "Cancelado por el bot") -> bool:
    """Cancela una suscripción de PayPal"""
    try:
        token = get_access_token()
        if not token:
            return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "reason": reason
        }
        
        response = requests.post(f"{BASE_URL}/v1/billing/subscriptions/{subscription_id}/cancel", 
                                 headers=headers, json=data)
        response.raise_for_status()
        
        return True
    except Exception as e:
        logger.error(f"Error al cancelar suscripción: {e}")
        return False

def process_webhook_event(event_data: Dict) -> Tuple[bool, str]:
    """Procesa eventos de webhook de PayPal"""
    try:
        event_type = event_data.get("event_type")
        
        # Registro del evento para debugging
        logger.info(f"Evento PayPal recibido: {event_type}")
        
        # Manejar diferentes tipos de eventos
        if event_type == "BILLING.SUBSCRIPTION.CREATED":
            # Una suscripción ha sido creada, pero aún no está activa
            return True, "Suscripción creada"
            
        elif event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            # La suscripción está activa
            return True, "Suscripción activada"
            
        elif event_type == "BILLING.SUBSCRIPTION.UPDATED":
            # La suscripción ha sido actualizada
            return True, "Suscripción actualizada"
            
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            # La suscripción ha sido cancelada
            return True, "Suscripción cancelada"
            
        elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
            # La suscripción ha sido suspendida
            return True, "Suscripción suspendida"
            
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            # Un pago de la suscripción ha fallado
            return True, "Pago fallido"
            
        elif event_type == "PAYMENT.SALE.COMPLETED":
            # Se ha completado un pago
            return True, "Pago completado"
            
        else:
            # Evento no manejado
            logger.warning(f"Evento no manejado: {event_type}")
            return False, f"Evento no manejado: {event_type}"
            
    except Exception as e:
        logger.error(f"Error al procesar evento de webhook: {e}")
        return False, f"Error: {str(e)}"