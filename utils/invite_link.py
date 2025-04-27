import logging
import datetime
import database as db
from config import GROUP_INVITE_LINK, INVITE_LINK_EXPIRY_HOURS, INVITE_LINK_MEMBER_LIMIT

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_invite_link(user_id, sub_id):
    """
    Crea un enlace de invitación para el grupo VIP.
    Utiliza la API de Telegram para crear un enlace temporal y único.
    """
    try:
        # Para un bot real, esto debería usar createChatInviteLink
        # En este ejemplo, usaremos un enlace estático o simulado
        if not GROUP_INVITE_LINK:
            logger.error("GROUP_INVITE_LINK no está configurado")
            return None
            
        # En un bot real, aquí llamaríamos a:
        # invite = bot.create_chat_invite_link(
        #     chat_id=-GROUP_CHAT_ID,  # ID del grupo VIP
        #     expire_date=int((datetime.datetime.now() + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)).timestamp()),
        #     member_limit=INVITE_LINK_MEMBER_LIMIT,
        #     name=f"Invite for user {user_id}",
        #     creates_join_request=False
        # )
        # invite_link = invite.invite_link
        
        # Para este ejemplo, simulamos el enlace
        invite_link = f"{GROUP_INVITE_LINK}?ref={user_id}_{sub_id}"
        
        # Calcular la fecha de expiración
        created_at = datetime.datetime.now()
        expires_at = created_at + datetime.timedelta(hours=INVITE_LINK_EXPIRY_HOURS)
        
        # Guardar el enlace en la base de datos
        db.save_invite_link(
            sub_id=sub_id,
            invite_link=invite_link,
            created_at=created_at,
            expires_at=expires_at
        )
        
        logger.info(f"Enlace de invitación creado para usuario {user_id}, expira en {INVITE_LINK_EXPIRY_HOURS} horas")
        
        return invite_link
        
    except Exception as e:
        logger.error(f"Error al crear enlace de invitación: {str(e)}")
        return None

def mark_invite_link_used(link_id):
    """Marca un enlace de invitación como usado"""
    try:
        result = db.mark_invite_link_used(link_id)
        return result
    except Exception as e:
        logger.error(f"Error al marcar enlace usado: {str(e)}")
        return False

def remove_user_from_group(user_id, reason="Suscripción expirada"):
    """
    Expulsa a un usuario del grupo VIP.
    En una implementación real, esto usaría la API de Telegram.
    """
    try:
        # En un bot real, aquí llamaríamos a:
        # bot.kick_chat_member(
        #     chat_id=-GROUP_CHAT_ID,  # ID del grupo VIP
        #     user_id=user_id
        # )
        
        # Registrar la expulsión en la base de datos
        db.record_expulsion(user_id, reason)
        
        logger.info(f"Usuario {user_id} expulsado del grupo. Razón: {reason}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error al expulsar usuario {user_id}: {str(e)}")
        return False