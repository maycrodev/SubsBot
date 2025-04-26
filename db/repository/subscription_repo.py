from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta

from ..models.subscription import Subscription

class SubscriptionRepository:
    @staticmethod
    def create_subscription(db: Session, user_id: int, plan_type: str, payment_method: str, 
                           payment_id: str, amount: float, expiry_date: datetime,
                           auto_renew: bool = True):
        """
        Crea una nueva suscripción.
        
        Args:
            db: Sesión de base de datos
            user_id: ID de Telegram del usuario
            plan_type: Tipo de plan ("weekly", "monthly", "manual")
            payment_method: Método de pago ("paypal", "stripe", "admin_whitelist")
            payment_id: ID del pago
            amount: Monto del pago
            expiry_date: Fecha de expiración
            auto_renew: Si la suscripción se renueva automáticamente
            
        Returns:
            Subscription: La suscripción creada
        """
        # Desactivar suscripciones activas previas del usuario
        active_subs = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.is_active == True
        ).all()
        
        for sub in active_subs:
            sub.is_active = False
            
        # Crear nueva suscripción
        subscription = Subscription(
            user_id=user_id,
            plan_type=plan_type,
            payment_method=payment_method,
            payment_id=payment_id,
            amount=amount,
            start_date=datetime.utcnow(),
            expiry_date=expiry_date,
            is_active=True,
            auto_renew=auto_renew
        )
        
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return subscription
    
    @staticmethod
    def get_subscription_by_id(db: Session, subscription_id: int):
        """
        Obtiene una suscripción por su ID.
        
        Args:
            db: Sesión de base de datos
            subscription_id: ID de la suscripción
            
        Returns:
            Subscription: La suscripción encontrada o None
        """
        return db.query(Subscription).filter(Subscription.id == subscription_id).first()
    
    @staticmethod
    def get_subscription_by_payment_id(db: Session, payment_id: str):
        """
        Obtiene una suscripción por su ID de pago.
        
        Args:
            db: Sesión de base de datos
            payment_id: ID del pago
            
        Returns:
            Subscription: La suscripción encontrada o None
        """
        return db.query(Subscription).filter(Subscription.payment_id == payment_id).first()
    
    @staticmethod
    def get_active_subscription(db: Session, user_id: int):
        """
        Obtiene la suscripción activa de un usuario.
        
        Args:
            db: Sesión de base de datos
            user_id: ID de Telegram del usuario
            
        Returns:
            Subscription: La suscripción activa o None
        """
        now = datetime.utcnow()
        return db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.is_active == True,
            Subscription.expiry_date > now
        ).first()
    
    @staticmethod
    def get_subscriptions_by_user_id(db: Session, user_id: int, limit: int = 10, order_by_desc: bool = True):
        """
        Obtiene las suscripciones de un usuario.
        
        Args:
            db: Sesión de base de datos
            user_id: ID de Telegram del usuario
            limit: Número máximo de suscripciones a devolver
            order_by_desc: Si se ordenan por fecha de inicio descendente
            
        Returns:
            list: Lista de suscripciones
        """
        query = db.query(Subscription).filter(Subscription.user_id == user_id)
        
        if order_by_desc:
            query = query.order_by(desc(Subscription.start_date))
        else:
            query = query.order_by(Subscription.start_date)
            
        return query.limit(limit).all()
    
    @staticmethod
    def cancel_subscription(db: Session, subscription_id: int):
        """
        Cancela una suscripción.
        
        Args:
            db: Sesión de base de datos
            subscription_id: ID de la suscripción
            
        Returns:
            Subscription: La suscripción actualizada o None
        """
        subscription = SubscriptionRepository.get_subscription_by_id(db, subscription_id)
        if not subscription:
            return None
        
        subscription.is_active = False
        subscription.auto_renew = False
        
        db.commit()
        db.refresh(subscription)
        return subscription
    
    @staticmethod
    def renew_subscription(db: Session, subscription_id: int, new_expiry_date: datetime):
        """
        Renueva una suscripción.
        
        Args:
            db: Sesión de base de datos
            subscription_id: ID de la suscripción
            new_expiry_date: Nueva fecha de expiración
            
        Returns:
            Subscription: La suscripción actualizada o None
        """
        subscription = SubscriptionRepository.get_subscription_by_id(db, subscription_id)
        if not subscription:
            return None
        
        subscription.expiry_date = new_expiry_date
        subscription.is_active = True
        subscription.last_renewal_date = datetime.utcnow()
        
        db.commit()
        db.refresh(subscription)
        return subscription
    
    @staticmethod
    def get_expiring_subscriptions(db: Session, days: int = 3):
        """
        Obtiene suscripciones que expirarán en los próximos días.
        
        Args:
            db: Sesión de base de datos
            days: Número de días a considerar
            
        Returns:
            list: Lista de suscripciones por expirar
        """
        now = datetime.utcnow()
        expiry_limit = now + timedelta(days=days)
        
        return db.query(Subscription).filter(
            Subscription.is_active == True,
            Subscription.expiry_date > now,
            Subscription.expiry_date <= expiry_limit,
            Subscription.auto_renew == True
        ).all()
    
    @staticmethod
    def get_expired_subscriptions(db: Session):
        """
        Obtiene suscripciones que ya han expirado pero siguen marcadas como activas.
        
        Args:
            db: Sesión de base de datos
            
        Returns:
            list: Lista de suscripciones expiradas
        """
        now = datetime.utcnow()
        
        return db.query(Subscription).filter(
            Subscription.is_active == True,
            Subscription.expiry_date <= now
        ).all()