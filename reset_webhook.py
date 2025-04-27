"""
Script para reiniciar y verificar el webhook del bot de Telegram.
Este script debe ejecutarse por separado para diagnosticar problemas.
"""
import requests
import time
import logging
import os
from config import BOT_TOKEN, WEBHOOK_URL

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def delete_webhook():
    """Elimina cualquier webhook establecido anteriormente"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        response = requests.get(url)
        response_data = response.json()
        
        if response_data.get("ok"):
            logger.info("✅ Webhook eliminado correctamente")
        else:
            logger.error(f"❌ Error al eliminar webhook: {response_data}")
        
        return response_data.get("ok", False)
    except Exception as e:
        logger.error(f"❌ Excepción al eliminar webhook: {e}")
        return False

def get_webhook_info():
    """Obtiene información sobre el webhook actual"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        info = response.json()
        
        logger.info("ℹ️ Información del webhook:")
        logger.info(f"  URL: {info.get('result', {}).get('url', 'No establecida')}")
        logger.info(f"  Actualizaciones pendientes: {info.get('result', {}).get('pending_update_count', 0)}")
        logger.info(f"  Último error: {info.get('result', {}).get('last_error_message', 'Ninguno')}")
        logger.info(f"  Último código de error: {info.get('result', {}).get('last_error_date', 'Ninguno')}")
        
        return info.get("result", {})
    except Exception as e:
        logger.error(f"❌ Error al obtener información del webhook: {e}")
        return {}

def set_new_webhook():
    """Establece un nuevo webhook"""
    try:
        # Asegurar que WEBHOOK_URL no tenga barra al final
        base_url = WEBHOOK_URL.rstrip('/')
        webhook_path = f"/webhook/{BOT_TOKEN}"
        full_webhook_url = f"{base_url}{webhook_path}"
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        params = {
            "url": full_webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True
        }
        
        logger.info(f"🔄 Intentando configurar webhook en: {full_webhook_url}")
        
        response = requests.post(url, json=params)
        result = response.json()
        
        if result.get("ok"):
            logger.info("✅ Webhook configurado correctamente")
        else:
            logger.error(f"❌ Error al configurar webhook: {result}")
        
        return result.get("ok", False)
    except Exception as e:
        logger.error(f"❌ Error al configurar webhook: {e}")
        return False

def verify_bot():
    """Verifica que el bot esté activo y funcionando"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url)
        me = response.json()
        
        if me.get("ok"):
            bot_info = me.get("result", {})
            logger.info(f"✅ Bot verificado: @{bot_info.get('username')} (ID: {bot_info.get('id')})")
            return True
        else:
            logger.error(f"❌ Error al verificar bot: {me}")
            return False
    except Exception as e:
        logger.error(f"❌ Error al verificar bot: {e}")
        return False

def send_test_message():
    """Envía un mensaje de prueba a todos los administradores"""
    from config import ADMIN_IDS
    
    for admin_id in ADMIN_IDS:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            params = {
                "chat_id": admin_id,
                "text": "🧪 Prueba de webhook reiniciado. Por favor, envía el comando /start para verificar que el bot responde."
            }
            
            response = requests.post(url, json=params)
            result = response.json()
            
            if result.get("ok"):
                logger.info(f"✅ Mensaje de prueba enviado a {admin_id}")
            else:
                logger.error(f"❌ Error al enviar mensaje de prueba a {admin_id}: {result}")
        except Exception as e:
            logger.error(f"❌ Error al enviar mensaje de prueba a {admin_id}: {e}")

if __name__ == "__main__":
    logger.info("🚀 Iniciando diagnóstico y reinicio de webhook")
    
    # 1. Verificar que el bot esté activo
    if not verify_bot():
        logger.error("❌ El bot no está activo o el token es inválido. Abortando.")
        exit(1)
    
    # 2. Obtener información del webhook actual
    logger.info("📊 Obteniendo información del webhook actual...")
    current_webhook = get_webhook_info()
    
    # 3. Eliminar webhook actual
    logger.info("🗑️ Eliminando webhook actual...")
    if delete_webhook():
        logger.info("✅ Webhook eliminado correctamente")
        # Esperar un momento para que Telegram procese la eliminación
        time.sleep(1)
    else:
        logger.warning("⚠️ No se pudo eliminar el webhook actual")
    
    # 4. Configurar nuevo webhook
    logger.info("🔄 Configurando nuevo webhook...")
    if set_new_webhook():
        logger.info("✅ Nuevo webhook configurado correctamente")
    else:
        logger.error("❌ Error al configurar nuevo webhook")
    
    # 5. Verificar la configuración final
    logger.info("📊 Verificando configuración final...")
    final_webhook = get_webhook_info()
    
    # 6. Enviar mensaje de prueba a los administradores
    logger.info("📤 Enviando mensaje de prueba a los administradores...")
    send_test_message()
    
    logger.info("🏁 Proceso de reinicio de webhook completado")
    logger.info(f"📌 WEBHOOK_URL configurada: {WEBHOOK_URL}")
    logger.info(f"📌 Webhook actual: {final_webhook.get('url', 'No establecido')}")
    logger.info("⏱️ Espera unos momentos y luego envía el comando /start al bot para verificar")