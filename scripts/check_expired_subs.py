import sys
import os
import logging
from datetime import datetime, timedelta

# Añadir directorio raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telebot
import config
from db.database import SessionLocal
from db.repository.subscription_repo import SubscriptionRepository
from db.repository.user_repo import UserRepository
from services.telegram.group_manager import GroupManager

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_expired_subscriptions():
    """
    Verifica suscripciones expiradas y ejecuta acciones necesarias:
    1. Desactiva suscripciones expiradas
    2. Notifica a los usuarios afectados
    3. Notifica a los administradores
    """
    logger.info("Verificando suscripciones expiradas...")
    
    # Crear instancia del bot para enviar notificaciones
    bot = telebot.TeleBot(config.BOT_TOKEN)
    group_manager = GroupManager(bot)
    
    # Crear sesión de base de datos
    db = SessionLocal()
    
    try:
        # Obtener suscripciones expiradas que siguen activas
        expired_subs = SubscriptionRepository.get_expired_subscriptions(db)
        
        if not expired_subs:
            logger.info("No hay suscripciones expiradas pendientes de procesar")
            return
        
        logger.info(f"Se encontraron {len(expired_subs)} suscripciones expiradas")
        
        # Procesar cada suscripción expirada
        for sub in expired_subs:
            user_id = sub.user_id
            
            # Marcar como inactiva
            sub.is_active = False
            db.commit()
            
            logger.info(f"Suscripción {sub.id} para el usuario {user_id} desactivada")
            
            # Obtener información del usuario
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            
            if not user:
                logger.warning(f"No se encontró usuario con ID {user_id}")
                continue
            
            # Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Tu suscripción VIP ha expirado\n\n"
                         f"📦 Plan: {sub.plan_type.upper()}\n"
                         f"📅 Expiró el: {sub.expiry_date.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                         f"Para renovar tu suscripción, utiliza el comando /start"
                )
                logger.info(f"Notificación enviada al usuario {user_id}")
            except Exception as e:
                logger.error(f"Error al notificar al usuario {user_id}: {str(e)}")
            
            # Notificar a los administradores
            for admin_id in config.ADMIN_IDS:
                try:
                    bot.send_message(
                        chat_id=admin_id,
                        text=f"🕒 Suscripción expirada:\n\n"
                             f"👤 Usuario: {user.full_name} (id{user.telegram_id})\n"
                             f"📦 Plan: {sub.plan_type.upper()}\n"
                             f"💰 Monto: ${sub.amount:.2f}\n"
                             f"📅 Expiró el: {sub.expiry_date.strftime('%d/%m/%Y %H:%M:%S')}\n"
                             f"🔄 Auto-renovación: {'Activada' if sub.auto_renew else 'Desactivada'}"
                    )
                except Exception:
                    # Ignorar errores al notificar admins
                    pass
    
    except Exception as e:
        logger.error(f"Error al procesar suscripciones expiradas: {str(e)}")
    
    finally:
        db.close()
        logger.info("Verificación de suscripciones expiradas completada")

def check_expiring_soon_subscriptions(days=3):
    """
    Notifica a los usuarios cuyas suscripciones están por expirar pronto.
    
    Args:
        days: Días antes de la expiración para notificar
    """
    logger.info(f"Verificando suscripciones por expirar en {days} días...")
    
    # Crear instancia del bot para enviar notificaciones
    bot = telebot.TeleBot(config.BOT_TOKEN)
    
    # Crear sesión de base de datos
    db = SessionLocal()
    
    try:
        # Obtener suscripciones por expirar
        expiring_soon = SubscriptionRepository.get_expiring_subscriptions(db, days)
        
        if not expiring_soon:
            logger.info(f"No hay suscripciones por expirar en {days} días")
            return
        
        logger.info(f"Se encontraron {len(expiring_soon)} suscripciones por expirar")
        
        # Procesar cada suscripción
        for sub in expiring_soon:
            user_id = sub.user_id
            
            # Marcar como notificada para no enviar múltiples avisos
            # Esto se podría implementar con un campo adicional en la BD
            
            # Obtener información del usuario
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            
            if not user:
                logger.warning(f"No se encontró usuario con ID {user_id}")
                continue
            
            # Calcular días restantes
            days_left = (sub.expiry_date - datetime.utcnow()).days
            
            # Notificar al usuario
            try:
                bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ Tu suscripción VIP expirará pronto\n\n"
                         f"📦 Plan: {sub.plan_type.upper()}\n"
                         f"🗓️ Expira en: {days_left} días\n"
                         f"📅 Fecha exacta: {sub.expiry_date.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                         f"{'✅ Tu suscripción se renovará automáticamente.' if sub.auto_renew else '⚠️ Tu suscripción NO se renovará automáticamente. Para continuar disfrutando de los beneficios, renueva antes de la fecha de expiración.'}"
                )
                logger.info(f"Notificación de expiración enviada al usuario {user_id}")
            except Exception as e:
                logger.error(f"Error al notificar expiración al usuario {user_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error al procesar suscripciones por expirar: {str(e)}")
    
    finally:
        db.close()
        logger.info("Verificación de suscripciones por expirar completada")

if __name__ == "__main__":
    # Verificar suscripciones expiradas
    check_expired_subscriptions()
    
    # Verificar suscripciones por expirar en 3 días
    check_expiring_soon_subscriptions(days=3)