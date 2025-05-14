import requests
import json
import base64
import datetime
import os
from typing import Dict, Optional, Tuple
import logging

from config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, PLANS, WEBHOOK_URL, DB_PATH, RECURRING_PAYMENTS_ENABLED

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

def create_order(plan_id: str, user_id: int) -> Optional[str]:
    """Crea una orden de pago único en PayPal"""
    try:
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token para crear orden")
            return None
        
        plan_details = PLANS.get(plan_id)
        if not plan_details:
            logger.error(f"Plan no reconocido: {plan_id}")
            return None
        
        # Generate a unique request ID
        request_id = f"order-{plan_id}-{user_id}-{datetime.datetime.now().timestamp()}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
            "Prefer": "return=representation"
        }
        
        # Configure return URLs with user_id and plan_id
        return_url = f"{WEBHOOK_URL}/paypal/return?user_id={user_id}&plan_id={plan_id}&payment_type=order"
        cancel_url = f"{WEBHOOK_URL}/paypal/cancel?user_id={user_id}&plan_id={plan_id}&payment_type=order"
        
        data = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": "USD",
                        "value": str(plan_details['price_usd'])
                    },
                    "description": plan_details['description'],
                    "custom_id": f"{user_id}:{plan_id}"  # Store user_id and plan_id for webhook processing
                }
            ],
            "application_context": {
                "brand_name": "Bot Suscripciones VIP",
                "locale": "es-ES",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url
            }
        }
        
        logger.info(f"Creando orden de pago único en PayPal para usuario {user_id}, plan {plan_id}")
        response = requests.post(f"{BASE_URL}/v2/checkout/orders", headers=headers, json=data)
        
        # Log response for debugging
        if response.status_code not in [200, 201, 202]:
            logger.error(f"Error al crear orden: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        
        order_data = response.json()
        order_id = order_data.get("id")
        
        if order_id:
            logger.info(f"Orden creada con ID: {order_id}")
        
        # Extract and return the approval URL
        for link in order_data.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                logger.info(f"Enlace de aprobación generado para orden: {approve_url}")
                return approve_url
        
        logger.error("No se encontró enlace de aprobación en la respuesta")
        return None
    except Exception as e:
        logger.error(f"Error al crear orden de pago único: {str(e)}")
        return None


def process_subscription_renewals(bot):
    """
    Procesa las renovaciones pendientes de suscripciones
    
    Args:
        bot: Instancia del bot de Telegram
        
    Returns:
        tuple: (número de notificaciones enviadas, número de errores)
    """
    try:
        import database as db
        import datetime
        
        logger.info("Procesando renovaciones pendientes de suscripciones...")
        
        # Obtener suscripciones a punto de vencer (en los próximos 60 minutos)
        pending_renewals = db.get_pending_renewal_subscriptions(minutes_before=60)
        logger.info(f"Encontradas {len(pending_renewals)} suscripciones pendientes de renovación")
        
        # Verificar si ya se han enviado notificaciones recientes para estas suscripciones
        recently_notified = db.get_recently_notified_subscriptions(hours=24)
        
        notifications_sent = 0
        errors = 0
        
        for subscription in pending_renewals:
            sub_id = subscription['sub_id']
            user_id = subscription['user_id']
            
            # Evitar duplicar notificaciones
            if sub_id in recently_notified:
                logger.info(f"Suscripción {sub_id} ya fue notificada recientemente, omitiendo")
                continue
            
            try:
                # Verificar el estado de la suscripción en PayPal
                paypal_sub_id = subscription.get('paypal_sub_id')
                
                if not paypal_sub_id:
                    logger.warning(f"Suscripción {sub_id} no tiene un ID de PayPal asociado")
                    continue
                
                subscription_details = verify_subscription(paypal_sub_id)
                
                if not subscription_details:
                    logger.error(f"No se pudo verificar la suscripción {paypal_sub_id} en PayPal")
                    errors += 1
                    continue
                
                status = subscription_details.get('status')
                
                if status not in ['ACTIVE', 'APPROVED']:
                    logger.warning(f"La suscripción {paypal_sub_id} no está activa en PayPal. Estado: {status}")
                    continue
                
                # Enviar notificación al usuario
                notify_successful_renewal(bot, user_id, subscription, None, is_upcoming=True)
                
                # Registrar la notificación
                db.record_renewal_notification(sub_id, user_id)
                
                notifications_sent += 1
                
            except Exception as e:
                logger.error(f"Error al procesar renovación {sub_id}: {str(e)}")
                errors += 1
        
        logger.info(f"Proceso de renovaciones completado: {notifications_sent} notificaciones enviadas, {errors} errores")
        return notifications_sent, errors
        
    except Exception as e:
        logger.error(f"Error general en process_subscription_renewals: {str(e)}")
        return -1, 1

def notify_successful_renewal(bot, user_id, subscription, new_end_date=None, is_upcoming=False):
    """
    Notifica a un usuario sobre una renovación exitosa o próxima
    
    Args:
        bot: Instancia del bot de Telegram
        user_id (int): ID del usuario
        subscription (dict): Datos de la suscripción
        new_end_date (datetime, optional): Nueva fecha de vencimiento
        is_upcoming (bool): Si es una renovación próxima o ya completada
    
    Returns:
        bool: True si se envió la notificación, False en caso contrario
    """
    try:
        from config import PLANS
        import datetime
        
        plan_id = subscription.get('plan')
        plan = PLANS.get(plan_id, {})
        plan_name = plan.get('display_name', plan_id)
        
        if is_upcoming:
            # Formatear fecha de vencimiento actual
            end_date = datetime.datetime.fromisoformat(subscription.get('end_date'))
            end_date_str = end_date.strftime('%d/%m/%Y')
            
            # Mensaje para renovación próxima
            message = (
                "📅 *Recordatorio de renovación automática*\n\n"
                f"Tu suscripción al plan {plan_name} se renovará automáticamente "
                f"el {end_date_str}.\n\n"
                "💳 El pago se procesará a través de PayPal usando tu método de pago registrado.\n\n"
                "ℹ️ Si deseas cancelar la renovación automática, puedes hacerlo desde tu cuenta de PayPal antes de esa fecha."
            )
        else:
            # Mensaje para renovación completada
            if not new_end_date:
                end_date = datetime.datetime.fromisoformat(subscription.get('end_date'))
            else:
                end_date = new_end_date
                
            end_date_str = end_date.strftime('%d/%m/%Y')
            
            message = (
                "🌸 *¡Renovación exitosa!* 🌸\n\n"
                f"˖° ୨୧ Tu suscripción al plan *{plan_name}* ha sido renovada con éxito (๑˃ᴗ˂)ﻭ\n\n"
                f"📅 *Nuevo vencimiento:* {end_date_str} 🎀\n\n"
                "Si quieres que prepare una nueva entradita para ti, usa el comando /recover ✧\(>o<)/✧\n\n"
                "｡･ﾟﾟ･ Gracias por seguir con nosotrxs ✨ ¡Disfruta de todos los beneficios exclusivos ~! 💕\n"
            )
        
        # Enviar mensaje
        bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error al notificar renovación a usuario {user_id}: {str(e)}")
        return False

def verify_and_capture_order(order_id: str) -> Optional[Dict]:
    """Verifica y captura un pago único"""
    try:
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token para verificar orden")
            return None
        
        # First, get order details
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Verificando orden con ID: {order_id}")
        response = requests.get(f"{BASE_URL}/v2/checkout/orders/{order_id}", headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Error al verificar orden: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        
        order_data = response.json()
        order_status = order_data.get("status")
        
        # If the order is approved, capture it
        if order_status == "APPROVED":
            logger.info(f"Orden {order_id} aprobada, procediendo a capturar el pago")
            
            # Capture the payment
            capture_response = requests.post(
                f"{BASE_URL}/v2/checkout/orders/{order_id}/capture",
                headers=headers
            )
            
            if capture_response.status_code not in [200, 201, 202]:
                logger.error(f"Error al capturar pago: Status code {capture_response.status_code}")
                logger.error(f"Respuesta: {capture_response.text}")
                return None
                
            capture_response.raise_for_status()
            
            capture_data = capture_response.json()
            capture_status = capture_data.get("status")
            
            if capture_status == "COMPLETED":
                logger.info(f"Pago capturado exitosamente para orden {order_id}")
                return capture_data
            else:
                logger.error(f"Captura de pago no completada: {capture_status}")
                return None
        else:
            logger.info(f"Orden {order_id} no está aprobada. Estado actual: {order_status}")
            return order_data
    except Exception as e:
        logger.error(f"Error al verificar y capturar orden: {str(e)}")
        return None
    
def create_payment_link(plan_id: str, user_id: int) -> Optional[str]:
    """
    Crea un enlace de pago para que el usuario pague a través de PayPal.
    Maneja tanto pagos únicos como recurrentes según la configuración.
    """
    try:
        # Determine if this should be a recurring payment
        plan_details = PLANS.get(plan_id)
        if not plan_details:
            logger.error(f"Plan no reconocido: {plan_id}")
            return None
        
        # Check plan-specific setting first, then fall back to global setting
        is_recurring = plan_details.get('recurring')
        if is_recurring is None:  # If not set at plan level
            is_recurring = RECURRING_PAYMENTS_ENABLED
        
        # Create the appropriate payment link
        if is_recurring:
            logger.info(f"Creando enlace de pago RECURRENTE para usuario {user_id}, plan {plan_id}")
            return create_subscription_link(plan_id, user_id)
        else:
            logger.info(f"Creando enlace de pago ÚNICO para usuario {user_id}, plan {plan_id}")
            return create_order(plan_id, user_id)
            
    except Exception as e:
        logger.error(f"Error al crear enlace de pago: {str(e)}")
        return None
    


# Modificación para la función create_plan en payments.py

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
        
        # MODIFICACIÓN: Verificar si es un plan de prueba (duración menor a 1 día)
        is_test_plan = plan_details['duration_days'] < 1
        
        # Determinar la unidad de tiempo y frecuencia según la duración
        interval_unit = "DAY"
        interval_count = plan_details['duration_days']
        
        # Para planes normales, usar las reglas estándar
        if not is_test_plan:
            if plan_id == "monthly" or interval_count >= 30:
                interval_unit = "MONTH"
                interval_count = max(1, int(interval_count / 30))
            elif plan_id == "weekly" or (interval_count >= 7 and interval_count < 30):
                interval_unit = "WEEK"
                interval_count = max(1, int(interval_count / 7))
        else:
            # PARA PLANES DE PRUEBA: Usar 1 día como mínimo para PayPal
            # pero mantendremos el valor real para nuestro sistema
            logger.info(f"Plan de prueba detectado: {plan_id} con duración de {plan_details['duration_days']} días")
            interval_unit = "DAY"
            interval_count = 1  # Usar 1 día como mínimo para PayPal
        
        # Asegurar que interval_count sea al menos 1
        interval_count = max(1, int(interval_count))
        
        # Log para depuración
        logger.info(f"Creando plan con interval_unit: {interval_unit}, interval_count: {interval_count}")
        
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
    """Crea un enlace de suscripción recurrente a través de PayPal"""
    try:
        # 1. First verify that the credentials are valid by getting a token
        token = get_access_token()
        if not token:
            logger.error("No se pudo obtener token de acceso para crear suscripción")
            return None
            
        # 2. Get a product or create a new one
        product_id = create_product_if_not_exists()
        if not product_id:
            logger.error("No se pudo obtener/crear el producto para la suscripción")
            return None
        
        # 3. Create the plan based on the product
        paypal_plan_id = create_plan(plan_id, product_id)
        if not paypal_plan_id:
            logger.error(f"No se pudo crear el plan de suscripción para {plan_id}")
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": f"subscription-{user_id}-{datetime.datetime.now().timestamp()}"
        }
        
        # Configure return URLs with user_id, plan_id and payment type
        return_url = f"{WEBHOOK_URL}/paypal/return?user_id={user_id}&plan_id={plan_id}&payment_type=subscription"
        cancel_url = f"{WEBHOOK_URL}/paypal/cancel?user_id={user_id}&plan_id={plan_id}&payment_type=subscription"
        
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
        
        # Log response for debugging
        if response.status_code not in [200, 201, 202]:
            logger.error(f"Error al crear suscripción: Status code {response.status_code}")
            logger.error(f"Respuesta: {response.text}")
            return None
            
        response.raise_for_status()
        
        response_data = response.json()
        
        # Extract and return the approval URL
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

# En payments.py
def process_webhook_event(event_data: Dict) -> Tuple[bool, str]:
    try:
        event_type = event_data.get("event_type")
        
        # Log the event for debugging
        logger.info(f"PayPal webhook recibido: {event_type}")
        
        # Extract the resource (can be subscription or order)
        resource = event_data.get("resource", {})
        
        # CRITICAL: Manejo del evento PAYMENT.SALE.COMPLETED para renovaciones
        if event_type == "PAYMENT.SALE.COMPLETED":
            # Obtener la suscripción relacionada con el pago
            billing_agreement_id = resource.get("billing_agreement_id")
            
            if billing_agreement_id:
                # Obtener la suscripción de la base de datos
                import database as db
                subscription = db.get_subscription_by_paypal_id(billing_agreement_id)
                
                if subscription:
                    # Calcular nueva fecha de expiración
                    import datetime
                    from config import PLANS
                    
                    user_id = subscription['user_id']
                    plan_id = subscription['plan']
                    plan = PLANS.get(plan_id)
                    
                    if plan:
                        # Verificar si la fecha ya expiró
                        current_end_date = datetime.datetime.fromisoformat(subscription['end_date'])
                        now = datetime.datetime.now()
                        
                        if current_end_date < now:
                            # Ya expiró, calcular desde ahora
                            new_end_date = now + datetime.timedelta(days=plan['duration_days'])
                        else:
                            # Aún activa, extender desde la fecha actual
                            new_end_date = current_end_date + datetime.timedelta(days=plan['duration_days'])
                        
                        # Extender la suscripción en la base de datos
                        db.extend_subscription(subscription['sub_id'], new_end_date)
                        
                        # No intentamos notificar aquí, lo dejamos para bot_handlers
                        
                        logger.info(f"Renovación exitosa: Suscripción {subscription['sub_id']} extendida hasta {new_end_date}")
                        return True, "Renovación procesada correctamente"
                    
            logger.warning(f"No se pudo procesar renovación para PAYMENT.SALE.COMPLETED - ID: {billing_agreement_id}")
        
        # Resto del código para otros eventos...
        return True, "Evento procesado"
        
    except Exception as e:
        logger.error(f"Error al procesar webhook: {e}")
        return False, f"Error: {e}"
        
        # Resto del código para otros eventos...
        
    except Exception as e:
        logger.error(f"Error al procesar webhook: {e}")
        return False, f"Error: {e}"