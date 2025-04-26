import logging
import telebot
from telebot.apihelper import ApiTelegramException

import config
from db.repository.user_repo import UserRepository
from db.database import SessionLocal

# Configurar logger
logger = logging.getLogger(__name__)

class GroupManager:
    def __init__(self, bot):
        """
        Inicializa el gestor de grupos.
        
        Args:
            bot: Instancia del bot de Telegram
        """
        self.bot = bot
    
    def add_user_to_group(self, user_id):
        """
        Envía un enlace de invitación al usuario para el grupo VIP.
        
        Args:
            user_id: ID de Telegram del usuario
            
        Returns:
            bool: True si se envió el enlace correctamente
        """
        try:
            # Enviar enlace de invitación
            self.bot.send_message(
                chat_id=user_id,
                text=f"🚪 Aquí tienes tu enlace de acceso al grupo VIP:\n{config.GROUP_INVITE_LINK}"
            )
            return True
        except ApiTelegramException as e:
            logger.error(f"Error al enviar enlace al usuario {user_id}: {str(e)}")
            return False
    
    def kick_user_from_group(self, chat_id, user_id):
        """
        Expulsa a un usuario del grupo.
        
        Args:
            chat_id: ID del chat del grupo
            user_id: ID de Telegram del usuario
            
        Returns:
            bool: True si se expulsó al usuario correctamente
        """
        try:
            self.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            return True
        except ApiTelegramException as e:
            logger.error(f"Error al expulsar al usuario {user_id} del grupo {chat_id}: {str(e)}")
            return False
    
    def unban_user_from_group(self, chat_id, user_id):
        """
        Desbloquea a un usuario del grupo.
        
        Args:
            chat_id: ID del chat del grupo
            user_id: ID de Telegram del usuario
            
        Returns:
            bool: True si se desbloqueó al usuario correctamente
        """
        try:
            self.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            return True
        except ApiTelegramException as e:
            logger.error(f"Error al desbloquear al usuario {user_id} del grupo {chat_id}: {str(e)}")
            return False
    
    def check_user_in_whitelist(self, user_id):
        """
        Verifica si un usuario está en la whitelist.
        
        Args:
            user_id: ID de Telegram del usuario
            
        Returns:
            bool: True si el usuario está en la whitelist
        """
        db = SessionLocal()
        try:
            return UserRepository.is_in_whitelist(db, user_id)
        finally:
            db.close()
    
    def handle_new_chat_member(self, message):
        """
        Maneja la entrada de nuevos miembros al grupo.
        Verifica si están en la whitelist y expulsa a los que no lo están.
        
        Args:
            message: Mensaje de entrada al grupo
        """
        # Solo procesar si es un mensaje de grupo
        if message.chat.type not in ['group', 'supergroup']:
            return
        
        # Solo procesar si hay nuevos miembros
        if not message.new_chat_members:
            return
        
        # Obtener ID del grupo
        group_id = message.chat.id
        
        # Procesar cada nuevo miembro
        for user in message.new_chat_members:
            user_id = user.id
            
            # Ignorar al propio bot
            if user_id == self.bot.get_me().id:
                continue
                
            # Verificar whitelist
            if not self.check_user_in_whitelist(user_id):
                # Usuario no en whitelist, expulsarlo
                self.kick_user_from_group(group_id, user_id)
                
                # Registrar el usuario expulsado
                db = SessionLocal()
                try:
                    user_obj = UserRepository.get_user_by_telegram_id(db, user_id)
                    if not user_obj:
                        # Crear usuario si no existe
                        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                        user_obj = UserRepository.create_user(db, user_id, full_name, user.username)
                    
                    # Marcar como bloqueado
                    UserRepository.block_user(db, user_id)
                finally:
                    db.close()
                
                # Enviar mensaje al usuario
                try:
                    self.bot.send_message(
                        chat_id=user_id,
                        text="⛔ No tienes acceso al grupo VIP. Para obtener acceso, debes suscribirte primero. Usa /start para ver los planes disponibles."
                    )
                except ApiTelegramException:
                    # Ignorar errores al enviar mensaje
                    pass
                
                # Notificar a los admins
                for admin_id in config.ADMIN_IDS:
                    try:
                        self.bot.send_message(
                            chat_id=admin_id,
                            text=f"🛑 Usuario expulsado del grupo VIP:\n"
                                 f"👤 {user.first_name or ''} {user.last_name or ''}\n"
                                 f"🆔 {user_id}\n"
                                 f"👤 @{user.username or 'sin_username'}\n"
                                 f"❌ Motivo: No está en la whitelist"
                        )
                    except ApiTelegramException:
                        # Ignorar errores al enviar mensaje
                        pass