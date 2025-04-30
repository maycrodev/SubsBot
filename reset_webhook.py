#!/usr/bin/env python
"""
Script para reiniciar el webhook de Telegram.
Este script debe ejecutarse cuando haya problemas con la recepción de comandos.
"""
import os
import requests
import logging
import time
from config import BOT_TOKEN, WEBHOOK_URL

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_bot():
    """Verifica que el bot esté activo y responda correctamente"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url)
        
        if response.status_code != 200:
            logger.error(f"Error al verificar el bot: {response.status_code}, {response.text}")
            return False
            
        bot_info = response.json()
        
        if not bot_info.get("ok"):
            logger.error(f"Error en la respuesta del bot: {bot_info.get('description')}")
            return False
            
        result = bot_info.get("result", {})
        bot_name = result.get("username")
        
        logger.info(f"Bot verificado: @{bot_name} (ID: {result.get('id')})")
        return True
    except Exception as e:
        logger.error(f"Error al verificar el bot: {str(e)}")
        return False

def get_webhook_info():
    """Obtiene la información actual del webhook"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        response = requests.get(url)
        
        if response.status_code != 200:
            logger.error(f"Error al obtener información del webhook: {response.status_code}, {response.text}")
            return None
            
        webhook_info = response.json()
        
        if not webhook_info.get("ok"):
            logger.error(f"Error en la respuesta: {webhook_info.get('description')}")
            return None
            
        return webhook_info.get("result", {})
    except Exception as e:
        logger.error(f"Error al obtener información del webhook: {str(e)}")
        return None

def delete_webhook():
    """Elimina el webhook actual"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        response = requests.get(url)
        
        if response.status_code != 200:
            logger.error(f"Error al eliminar webhook: {response.status_code}, {response.text}")
            return False
            
        result = response.json()
        
        if not result.get("ok"):
            logger.error(f"Error al eliminar webhook: {result.get('description')}")
            return False
            
        logger.info("Webhook eliminado correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al eliminar webhook: {str(e)}")
        return False

def set_new_webhook():
    """Configura un nuevo webhook"""
    try:
        # Crear la URL completa del webhook
        webhook_url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        data = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query", "chat_member"]
        }
        
        logger.info(f"Configurando webhook en: {webhook_url}")
        
        response = requests.post(url, json=data)
        
        if response.status_code != 200:
            logger.error(f"Error al configurar webhook: {response.status_code}, {response.text}")
            return False
            
        result = response.json()
        
        if not result.get("ok"):
            logger.error(f"Error al configurar webhook: {result.get('description')}")
            return False
            
        logger.info("Webhook configurado correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al configurar webhook: {str(e)}")
        return False

def main():
    """Función principal"""
    logger.info("==== REINICIO DE WEBHOOK ====")
    
    # 1. Verificar que el bot esté activo
    if not verify_bot():
        logger.error("No se pudo verificar el bot. Abortando operación.")
        return False
    
    # 2. Obtener información del webhook actual
    webhook_info = get_webhook_info()
    
    if webhook_info:
        current_url = webhook_info.get("url", "")
        logger.info(f"Webhook actual: {current_url}")
        
        if "pending_update_count" in webhook_info:
            pending = webhook_info.get("pending_update_count", 0)
            logger.info(f"Actualizaciones pendientes: {pending}")
        
        if "last_error_date" in webhook_info:
            last_error = webhook_info.get("last_error_date", 0)
            last_error_message = webhook_info.get("last_error_message", "")
            
            if last_error:
                logger.warning(f"Último error: {last_error_message}")
    
    # 3. Eliminar el webhook existente
    if not delete_webhook():
        logger.error("Error al eliminar el webhook. Abortando operación.")
        return False
    
    # 4. Esperar un momento
    logger.info("Esperando 2 segundos...")
    time.sleep(2)
    
    # 5. Configurar el nuevo webhook
    if not set_new_webhook():
        logger.error("Error al configurar el nuevo webhook. Abortando operación.")
        return False
    
    # 6. Verificar que el webhook se haya configurado correctamente
    webhook_info = get_webhook_info()
    
    if webhook_info:
        new_url = webhook_info.get("url", "")
        
        if new_url:
            logger.info(f"¡Webhook reiniciado correctamente! Nueva URL: {new_url}")
            return True
        else:
            logger.error("El webhook no se configuró correctamente.")
            return False
    else:
        logger.error("No se pudo obtener información del webhook después de configurarlo.")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        logger.info("Reinicio del webhook completado exitosamente.")
        
        # Mostrar instrucciones para verificar el funcionamiento
        print("\n=== INSTRUCCIONES PARA VERIFICAR ===")
        print("1. Abre tu bot en Telegram")
        print("2. Ejecuta el comando /stats (si eres administrador)")
        print("3. Verifica que el bot responda correctamente")
        print("=================================\n")
    else:
        logger.error("El reinicio del webhook falló.")