import requests
import json
import base64
import datetime
import os
from typing import Dict, Optional, Tuple
import logging

from config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, PLANS, WEBHOOK_URL, DB_PATH

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
        
        # Añadir logs para depuración
        logger.info(f"Obteniendo token de acceso de PayPal desde: {BASE_URL}/v1/oauth2/token")
        
        response = requests.post(f"{BASE_URL}/v1/oauth2/token", headers=headers, data=data)
        
        # Registrar respuesta para depuración (sin exponer información sensible)
        if response.status_code != 200:
            logger.error(f"Error al obtener token: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        token_data = response.json()
        
        logger.info("Token de acceso obtenido correctamente")
        return token_data.get("access_token")
    except Exception as e:
        logger.error(f"Error al obtener token de PayPal: {str(e)}")
        return None

def create_product_if_not_exists() -> Optional[str]:
    """Crea un producto en PayPal si no existe aún y devuelve su ID"""
    try:
        # Para fines de desarrollo, podemos usar un ID de producto estático
        # Esta es una solución temporal hasta implementar una gestión de productos adecuada
        # En un entorno de producción real, deberías almacenar y reutilizar el ID del producto
        
        # Verificamos si existe un archivo con el ID del producto
        product_id_file = os.path.join(os.path.dirname(DB_PATH), 'paypal_product_id.txt')
        
        # Si el archivo existe, leemos el ID del producto
        if os.path.exists(product_id_file):
            with open(product_id_file, 'r') as f:
                product_id = f.read().strip()
                if product_id:
                    logger.info(f"Usando producto existente con ID: {product_id}")
                    return product_id
        
        # Si no tenemos un ID guardado, creamos un nuevo producto
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener el token de acceso")
            return None
        
        product_name = "Grupo VIP"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"create-product-{datetime.datetime.now().timestamp()}"  # ID único para evitar duplicados
        }
        
        # CAMBIO: Eliminamos el campo "category" y usamos solo el tipo
        # La API de PayPal Sandbox no acepta DIGITAL_GOODS como valor válido para category
        data = {
            "name": product_name,
            "description": "Acceso exclusivo a contenido premium",
            "type": "SERVICE"
        }
        
        logger.info(f"Creando producto en PayPal: {product_name}")
        response = requests.post(f"{BASE_URL}/v1/catalogs/products", headers=headers, json=data)
        
        # Registrar respuesta para depuración
        if response.status_code != 201:
            logger.error(f"Error al crear producto: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            
            # Si el error es 401, podría ser un problema con el token
            if response.status_code == 401:
                logger.error("Error de autenticación. Verificar credenciales de PayPal.")
                
            return None
            
        response.raise_for_status()
        product_data = response.json()
        product_id = product_data.get("id")
        
        # Guardar el ID del producto para futuras referencias
        if product_id:
            os.makedirs(os.path.dirname(product_id_file), exist_ok=True)
            with open(product_id_file, 'w') as f:
                f.write(product_id)
            logger.info(f"Producto creado correctamente con ID: {product_id}")
        
        return product_id
    except Exception as e:
        logger.error(f"Error al crear producto en PayPal: {str(e)}")
        return None

def create_plan(plan_id: str, product_id: str) -> Optional[str]:
    """Crea un plan de suscripción en PayPal para el producto dado"""
    try:
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token para crear plan")
            return None
        
        plan_details = PLANS.get(plan_id)
        if not plan_details:
            logger.error(f"Plan no reconocido: {plan_id}")
            return None
        
        # Generar un ID de solicitud único
        request_id = f"plan-{plan_id}-{datetime.datetime.now().timestamp()}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
            "Prefer": "return=representation"  # Solicitar la representación completa en la respuesta
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
        
        logger.info(f"Creando plan en PayPal: {plan_details['name']}")
        response = requests.post(f"{BASE_URL}/v1/billing/plans", headers=headers, json=data)
        
        # Registrar respuesta para depuración
        if response.status_code not in [200, 201]:
            logger.error(f"Error al crear plan: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        plan_data = response.json()
        
        plan_id_paypal = plan_data.get("id")
        if plan_id_paypal:
            logger.info(f"Plan creado correctamente con ID: {plan_id_paypal}")
        
        return plan_id_paypal
    except Exception as e:
        logger.error(f"Error al crear plan en PayPal: {str(e)}")
        return None

def create_subscription_link(plan_id: str, user_id: int) -> Optional[str]:
    """Crea un enlace de suscripción para que el usuario se suscriba a través de PayPal"""
    try:
        # 1. Primero verificamos que las credenciales sean válidas obteniendo un token
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token de acceso para crear suscripción")
            return None
            
        # 2. Obtener un producto o crear uno nuevo
        product_id = create_product_if_not_exists()
        if not product_id:
            logger.error("No se pudo obtener/crear el producto para la suscripción")
            return None
        
        # 3. Crear el plan basado en el producto
        paypal_plan_id = create_plan(plan_id, product_id)
        if not paypal_plan_id:
            logger.error(f"No se pudo crear el plan de suscripción para {plan_id}")
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"subscription-{user_id}-{datetime.datetime.now().timestamp()}"
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
        
        logger.info(f"Creando enlace de suscripción para usuario {user_id}, plan {plan_id}")
        response = requests.post(f"{BASE_URL}/v1/billing/subscriptions", headers=headers, json=data)
        
        # Registrar respuesta para depuración
        if response.status_code not in [200, 201, 202]:
            logger.error(f"Error al crear suscripción: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        
        response_data = response.json()
        
        # Extraer y devolver el enlace de aprobación (approve URL)
        for link in response_data.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                logger.info(f"Enlace de aprobación generado: {approve_url}")
                return approve_url
        
        logger.error("No se encontró enlace de aprobación en la respuesta")
        return None
    except Exception as e:
        logger.error(f"Error al crear enlace de suscripción: {str(e)}")
        return None

def verify_subscription(subscription_id: str) -> Optional[Dict]:
    """Verifica y obtiene los detalles de una suscripción"""
    try:
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token para verificar suscripción")
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Verificando suscripción con ID: {subscription_id}")
        response = requests.get(f"{BASE_URL}/v1/billing/subscriptions/{subscription_id}", headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Error al verificar suscripción: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        
        subscription_data = response.json()
        logger.info(f"Suscripción verificada correctamente. Estado: {subscription_data.get('status')}")
        
        return subscription_data
    except Exception as e:
        logger.error(f"Error al verificar suscripción: {str(e)}")
        return None

def get_subscription_details(subscription_id: str) -> Optional[Dict]:
    """Obtiene los detalles completos de una suscripción"""
    return verify_subscription(subscription_id)

def cancel_subscription(subscription_id: str, reason: str = "Cancelado por el bot") -> bool:
    """Cancela una suscripción de PayPal"""
    try:
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token para cancelar suscripción")
            return False
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "reason": reason
        }
        
        logger.info(f"Cancelando suscripción con ID: {subscription_id}")
        response = requests.post(f"{BASE_URL}/v1/billing/subscriptions/{subscription_id}/cancel", 
                                 headers=headers, json=data)
        
        if response.status_code not in [200, 201, 204]:
            logger.error(f"Error al cancelar suscripción: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return False
            
        response.raise_for_status()
        
        logger.info(f"Suscripción {subscription_id} cancelada correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al cancelar suscripción: {str(e)}")
        return False

def process_webhook_event(event_data: Dict) -> Tuple[bool, str]:
    """Procesa eventos de webhook de PayPal"""
    try:
        event_type = event_data.get("event_type")
        
        # Registro del evento para debugging
        logger.info(f"Evento PayPal recibido: {event_type}")
        logger.info(f"Datos del evento: {json.dumps(event_data)[:500]}...")  # Mostrar primeros 500 caracteres
        
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
        logger.error(f"Error al procesar evento de webhook: {str(e)}")
        return False, f"Error: {str(e)}"