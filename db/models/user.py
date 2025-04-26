from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from ..database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String)
    join_date = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    
    # Relación con suscripciones
    subscriptions = relationship("Subscription", back_populates="user", foreign_keys="Subscription.user_id")