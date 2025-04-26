from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from ..models.user import User
from ..models.subscription import Subscription

class UserRepository:
    @staticmethod
    def create_user(db: Session, telegram_id: int, full_name: str, username: str = None):
        """
        Crea un nuevo usuario en la base de datos.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            full_name: Nombre completo del usuario
            username: Nombre de usuario (opcional)
            
        Returns:
            User: El usuario creado
        """
        db_user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    
    @staticmethod
    def get_user_by_telegram_id(db: Session, telegram_id: int):
        """
        Obtiene un usuario por su ID de Telegram.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            
        Returns:
            User: El usuario encontrado o None
        """
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    
    @staticmethod
    def update_user(db: Session, telegram_id: int, **kwargs):
        """
        Actualiza los datos de un usuario.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            **kwargs: Campos a actualizar
            
        Returns:
            User: El usuario actualizado o None
        """
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        db.commit()
        db.refresh(user)
        return user
    
    @staticmethod
    def get_all_users(db: Session, skip: int = 0, limit: int = 100):
        """
        Obtiene todos los usuarios paginados.
        
        Args:
            db: Sesión de base de datos
            skip: Número de registros a saltar
            limit: Número máximo de registros a devolver
            
        Returns:
            list: Lista de usuarios
        """
        return db.query(User).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_active_subscribers(db: Session):
        """
        Obtiene todos los usuarios con suscripciones activas.
        
        Args:
            db: Sesión de base de datos
            
        Returns:
            list: Lista de usuarios con suscripciones activas
        """
        now = datetime.utcnow()
        return db.query(User).join(User.subscriptions).filter(
            Subscription.is_active == True,
            Subscription.expiry_date > now
        ).distinct().all()
    
    @staticmethod
    def add_to_whitelist(db: Session, telegram_id: int, expiry_date: datetime):
        """
        Añade un usuario a la whitelist creando una suscripción manual.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            expiry_date: Fecha de expiración de la whitelist
            
        Returns:
            Subscription: La suscripción creada o None
        """
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if not user:
            return None
        
        # Crear suscripción manual
        subscription = Subscription(
            user_id=telegram_id,
            plan_type="manual",
            payment_method="admin_whitelist",
            payment_id=f"admin_wl_{telegram_id}_{datetime.utcnow().timestamp()}",
            amount=0.0,  # Gratis por ser manual
            start_date=datetime.utcnow(),
            expiry_date=expiry_date,
            is_active=True,
            auto_renew=False  # Manual no se renueva automáticamente
        )
        
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return subscription
    
    @staticmethod
    def is_in_whitelist(db: Session, telegram_id: int):
        """
        Verifica si un usuario está en la whitelist (tiene suscripción activa).
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            
        Returns:
            bool: True si está en whitelist, False en caso contrario
        """
        now = datetime.utcnow()
        subscription = db.query(Subscription).filter(
            Subscription.user_id == telegram_id,
            Subscription.is_active == True,
            Subscription.expiry_date > now
        ).first()
        
        return subscription is not None
    
    @staticmethod
    def block_user(db: Session, telegram_id: int):
        """
        Bloquea a un usuario.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            
        Returns:
            User: El usuario bloqueado o None
        """
        return UserRepository.update_user(db, telegram_id, is_blocked=True)
    
    @staticmethod
    def unblock_user(db: Session, telegram_id: int):
        """
        Desbloquea a un usuario.
        
        Args:
            db: Sesión de base de datos
            telegram_id: ID de Telegram del usuario
            
        Returns:
            User: El usuario desbloqueado o None
        """
        return UserRepository.update_user(db, telegram_id, is_blocked=False)