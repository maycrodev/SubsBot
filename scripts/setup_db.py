import sys
import os
import logging

# Añadir directorio raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Base, engine
from db.models.user import User
from db.models.subscription import Subscription
import config

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    """
    Inicializa la base de datos creando todas las tablas necesarias.
    También añade a los administradores si están configurados.
    """
    logger.info("Inicializando base de datos...")
    
    # Crear todas las tablas
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Tablas creadas correctamente")
    
    # Añadir administradores
    from db.repository.user_repo import UserRepository
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError
    
    # Crear sesión
    session = Session(engine)
    
    try:
        # Añadir cada admin configurado
        for admin_id in config.ADMIN_IDS:
            try:
                # Verificar si ya existe
                user = session.query(User).filter(User.telegram_id == admin_id).first()
                
                if not user:
                    # Crear usuario admin
                    admin_user = User(
                        telegram_id=admin_id,
                        full_name=f"Admin {admin_id}",
                        username=None,
                        is_admin=True
                    )
                    session.add(admin_user)
                    session.commit()
                    logger.info(f"✅ Administrador con ID {admin_id} añadido correctamente")
                elif not user.is_admin:
                    # Actualizar usuario existente a admin
                    user.is_admin = True
                    session.commit()
                    logger.info(f"✅ Usuario con ID {admin_id} actualizado a administrador")
                else:
                    logger.info(f"ℹ️ Administrador con ID {admin_id} ya existe")
            
            except IntegrityError:
                session.rollback()
                logger.error(f"❌ Error al añadir administrador con ID {admin_id}")
            
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Error inesperado al añadir administrador con ID {admin_id}: {str(e)}")
    
    finally:
        session.close()
    
    logger.info("🎉 Inicialización de base de datos completada")

if __name__ == "__main__":
    init_db()