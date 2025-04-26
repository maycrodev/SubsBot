from sqlalchemy import Boolean, Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from ..database import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), index=True)
    plan_type = Column(String)  # "weekly", "monthly", "manual"
    payment_method = Column(String)  # "paypal", "stripe", "admin_whitelist"
    payment_id = Column(String, unique=True)  # ID de pago externo
    amount = Column(Float)
    start_date = Column(DateTime, default=datetime.utcnow)
    expiry_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    auto_renew = Column(Boolean, default=True)
    last_renewal_date = Column(DateTime, nullable=True)
    
    # Relación con el usuario
    user = relationship("User", back_populates="subscriptions", foreign_keys=[user_id])