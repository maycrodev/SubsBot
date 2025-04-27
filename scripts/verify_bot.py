import sys
import os
import logging

# Añadir directorio raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telebot
import config
from bot.bot_instance import bot

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("verify_bot")

def verify_bot_token():
    """Verifica que el token del bot sea válido"""
    try:
        me = bot.get_me()
        logger.info(f"✅ Bot conectado correctamente: @{me.username} (ID: {me.id})")
        return True
    except Exception as e:
        logger.error(f"❌ Error al conectar con el bot: {str(e)}")
        return False

def verify_webhook_status():
    """Verifica la configuración del webhook"""
    try:
        webhook_info = bot.get_webhook_info()
        if webhook_info.url:
            logger.info(f"✅ Webhook configurado en: {webhook_info.url}")
            logger.info(f"   - Pendientes: {webhook_info.pending_update_count}")
            logger.info(f"   - Último error: {webhook_info.last_error_message or 'Ninguno'}")
            
            if webhook_info.last_error_message:
                logger.warning("⚠️ El webhook tiene errores recientes")
                return False
                
            # Verificar formato correcto del webhook URL
            expected_path = config.WEBHOOK_PATH
            if expected_path not in webhook_info.url:
                logger.warning(f"⚠️ La URL del webhook no contiene la ruta esperada: {expected_path}")
                return False
        else:
            logger.warning("⚠️ No hay webhook configurado, el bot debe estar usando polling")
            
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar webhook: {str(e)}")
        return False

def test_start_command():
    """Intenta enviar un comando /start al bot (prueba local)"""
    try:
        # Solo para modo de desarrollo con polling
        logger.info("Esta prueba solo funciona en modo desarrollo con polling activo")
        logger.info("Para probar el comando /start en producción, usa el bot directamente")
        
        if os.environ.get('ENVIRONMENT') == 'development':
            # En desarrollo podríamos simular un mensaje, pero no es recomendado
            pass
        
        return True
    except Exception as e:
        logger.error(f"❌ Error al probar comando start: {str(e)}")
        return False

def verify_admin_config():
    """Verifica la configuración de administradores"""
    try:
        if not config.ADMIN_IDS:
            logger.warning("⚠️ No hay administradores configurados")
            return False
            
        logger.info(f"✅ Administradores configurados: {config.ADMIN_IDS}")
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar configuración de administradores: {str(e)}")
        return False

def verify_group_invite():
    """Verifica la configuración del enlace de invitación al grupo"""
    try:
        if not config.GROUP_INVITE_LINK:
            logger.warning("⚠️ No hay enlace de invitación al grupo configurado")
            return False
            
        if not config.GROUP_INVITE_LINK.startswith("https://t.me/"):
            logger.warning(f"⚠️ Formato de enlace de invitación no válido: {config.GROUP_INVITE_LINK}")
            return False
            
        logger.info(f"✅ Enlace de invitación configurado correctamente")
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar enlace de invitación: {str(e)}")
        return False

def verify_port_config():
    """Verifica la configuración del puerto"""
    try:
        port = config.PORT
        logger.info(f"✅ Puerto configurado: {port}")
        
        if port != 10000 and os.environ.get('PORT') is None:
            logger.warning(f"⚠️ Puerto configurado ({port}) diferente al valor por defecto de Render (10000)")
            return False
            
        return True
    except Exception as e:
        logger.error(f"❌ Error al verificar configuración de puerto: {str(e)}")
        return False

def send_test_message():
    """Intenta enviar un mensaje de prueba a cada administrador"""
    try:
        admin_ids = config.ADMIN_IDS
        if not admin_ids:
            logger.warning("⚠️ No hay administradores a quienes enviar mensaje de prueba")
            return False
            
        logger.info(f"Enviando mensaje de prueba a {len(admin_ids)} administradores...")
        
        success = 0
        for admin_id in admin_ids:
            try:
                msg = bot.send_message(
                    chat_id=admin_id,
                    text="🧪 Este es un mensaje de prueba de verificación del bot.\n\n"
                         "Si estás recibiendo este mensaje, significa que el bot está funcionando correctamente.\n\n"
                         "✅ Bot online y funcionando"
                )
                success += 1
                logger.info(f"✅ Mensaje enviado a administrador {admin_id}")
            except Exception as e:
                logger.error(f"❌ Error al enviar mensaje a administrador {admin_id}: {str(e)}")
                
        if success > 0:
            logger.info(f"✅ Se enviaron {success} de {len(admin_ids)} mensajes de prueba correctamente")
            return True
        else:
            logger.error("❌ No se pudo enviar ningún mensaje de prueba")
            return False
    except Exception as e:
        logger.error(f"❌ Error al enviar mensajes de prueba: {str(e)}")
        return False

def run_verification():
    """Ejecuta todas las verificaciones"""
    logger.info("🔍 Iniciando verificación del bot...")
    
    success = True
    
    # Verificaciones básicas
    if not verify_bot_token():
        logger.error("❌ Verificación de token fallida - ¡Verificación abortada!")
        return False
    
    # Verificar configuración del webhook
    if not verify_webhook_status():
        success = False
    
    # Verificar configuración de administradores
    if not verify_admin_config():
        success = False
    
    # Verificar enlace de invitación
    if not verify_group_invite():
        success = False
    
    # Verificar configuración de puerto
    if not verify_port_config():
        success = False
    
    # Enviar mensaje de prueba
    if not send_test_message():
        success = False
    
    # Resultado final
    if success:
        logger.info("🎉 ¡Verificación completa! El bot parece estar correctamente configurado.")
    else:
        logger.warning("⚠️ Verificación completada con advertencias o errores. Revisa los mensajes anteriores.")
    
    return success

if __name__ == "__main__":
    run_verification()