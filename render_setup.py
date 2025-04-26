import os
import logging
import sys
import telebot
import requests
import time

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger("render_setup")

def check_environment():
    """Verifica las variables de entorno necesarias"""
    logger.info("Verificando variables de entorno...")
    
    # Variables críticas
    required_vars = [
        "BOT_TOKEN", 
        "WEBHOOK_URL", 
        "ADMIN_IDS", 
        "GROUP_INVITE_LINK"
    ]
    
    # Verificar cada variable
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
            logger.error(f"❌ Falta variable de entorno: {var}")
        else:
            # Mostrar parcialmente para variables sensibles
            if var == "BOT_TOKEN":
                logger.info(f"✅ {var}: {value[:5]}...{value[-5:]}")
            else:
                logger.info(f"✅ {var}: {value}")
    
    if missing:
        logger.error(f"❌ Faltan {len(missing)} variables de entorno necesarias")
        return False
    
    logger.info("✅ Todas las variables de entorno necesarias están configuradas")
    return True

def check_telegram_api():
    """Verifica que se pueda conectar con la API de Telegram"""
    logger.info("Verificando conexión con la API de Telegram...")
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("❌ No se puede verificar la API de Telegram: token no disponible")
        return False
    
    try:
        bot = telebot.TeleBot(bot_token)
        me = bot.get_me()
        logger.info(f"✅ Conexión con API de Telegram exitosa - Bot: @{me.username} (ID: {me.id})")
        return True
    except Exception as e:
        logger.error(f"❌ Error al conectar con la API de Telegram: {str(e)}")
        return False

def check_webhook_url():
    """Verifica que la URL del webhook sea accesible"""
    logger.info("Verificando accesibilidad de la URL del webhook...")
    
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.error("❌ No se puede verificar la URL del webhook: URL no disponible")
        return False
    
    # Verificar si la URL es accesible
    try:
        response = requests.get(webhook_url, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ URL del webhook accesible: {webhook_url}")
            return True
        else:
            logger.warning(f"⚠️ URL del webhook respondió con código {response.status_code}: {webhook_url}")
            return True  # Aún podría funcionar si el código es distinto de 200
    except Exception as e:
        logger.error(f"❌ Error al verificar la URL del webhook: {str(e)}")
        return False

def configure_webhook():
    """Configura el webhook del bot"""
    logger.info("Configurando webhook del bot...")
    
    bot_token = os.getenv("BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    
    if not bot_token or not webhook_url:
        logger.error("❌ No se puede configurar el webhook: faltan datos necesarios")
        return False
    
    # Construir la URL completa del webhook
    webhook_path = f"/webhook/{bot_token}"
    full_webhook_url = f"{webhook_url.rstrip('/')}{webhook_path}"
    
    try:
        bot = telebot.TeleBot(bot_token)
        
        # Eliminar webhook existente
        bot.remove_webhook()
        time.sleep(1)  # Breve pausa
        
        # Configurar nuevo webhook
        bot.set_webhook(url=full_webhook_url)
        time.sleep(1)  # Breve pausa
        
        # Verificar configuración
        webhook_info = bot.get_webhook_info()
        if webhook_info.url == full_webhook_url:
            logger.info(f"✅ Webhook configurado correctamente: {full_webhook_url}")
            logger.info(f"ℹ️ Pendientes: {webhook_info.pending_update_count}, Errores: {webhook_info.last_error_message or 'Ninguno'}")
            return True
        else:
            logger.error(f"❌ El webhook no se configuró correctamente. URL actual: {webhook_info.url}")
            return False
    except Exception as e:
        logger.error(f"❌ Error al configurar el webhook: {str(e)}")
        return False

def main():
    """Función principal"""
    logger.info("🔧 Iniciando configuración para Render.com...")
    
    success = True
    
    # Ejecutar verificaciones
    if not check_environment():
        success = False
    
    if not check_telegram_api():
        success = False
    
    if not check_webhook_url():
        success = False
    
    if not configure_webhook():
        success = False
    
    # Resultado final
    if success:
        logger.info("✅ Configuración completada correctamente")
    else:
        logger.error("❌ La configuración no se completó correctamente")
    
    return success

if __name__ == "__main__":
    main()