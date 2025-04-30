import sqlite3
import datetime
from typing import Dict, List, Optional, Tuple, Any
from config import DB_PATH
import logging  # Añade esta línea

# Configurar logging si no está configurado
logger = logging.getLogger(__name__)

def get_db_connection():
    """Establece una conexión a la base de datos SQLite"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Para acceder a las columnas por nombre
    return conn

def init_db():
    """Inicializa la base de datos creando las tablas si no existen"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla de usuarios
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabla de suscripciones
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        sub_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        price_usd REAL,
        start_date TIMESTAMP,
        end_date TIMESTAMP,
        status TEXT,
        paypal_sub_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Tabla de enlaces de invitación
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS invite_links (
        link_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        invite_link TEXT,
        created_at TIMESTAMP,
        expires_at TIMESTAMP,
        used BOOLEAN DEFAULT 0,
        FOREIGN KEY (sub_id) REFERENCES subscriptions (sub_id)
    )
    ''')
    
    # Tabla de expulsiones
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS expulsions (
        expel_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reason TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Funciones para manipular usuarios
def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> int:
    """Guarda o actualiza un usuario en la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar si el usuario ya existe
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        # Actualizar usuario existente
        cursor.execute('''
        UPDATE users SET username = ?, first_name = ?, last_name = ? WHERE user_id = ?
        ''', (username, first_name, last_name, user_id))
    else:
        # Insertar nuevo usuario
        cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()
    return user_id

def get_user(user_id: int) -> Optional[Dict]:
    """Obtiene información de un usuario por su ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    conn.close()
    
    if user:
        return dict(user)
    return None

# Funciones para manipular suscripciones
def create_subscription(user_id: int, plan: str, price_usd: float, 
                        start_date: datetime.datetime, end_date: datetime.datetime, 
                        status: str = 'ACTIVE', paypal_sub_id: str = None) -> int:
    """Crea una nueva suscripción"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO subscriptions (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id))
    
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return sub_id

def get_active_subscription(user_id: int) -> Optional[Dict]:
    """Obtiene la suscripción activa de un usuario si existe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM subscriptions 
    WHERE user_id = ? AND status = 'ACTIVE' AND end_date > datetime('now')
    ORDER BY end_date DESC LIMIT 1
    ''', (user_id,))
    
    subscription = cursor.fetchone()
    conn.close()
    
    if subscription:
        return dict(subscription)
    return None

def update_subscription_status(sub_id: int, status: str) -> bool:
    """Actualiza el estado de una suscripción"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE subscriptions SET status = ? WHERE sub_id = ?
    ''', (status, sub_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def extend_subscription(sub_id: int, new_end_date: datetime.datetime) -> bool:
    """Extiende la fecha de expiración de una suscripción"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE subscriptions 
    SET end_date = ?, 
        status = 'ACTIVE' 
    WHERE sub_id = ?
    ''', (new_end_date, sub_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def get_subscription_by_paypal_id(paypal_sub_id: str) -> Optional[Dict]:
    """Obtiene una suscripción por su ID de PayPal"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM subscriptions WHERE paypal_sub_id = ?', (paypal_sub_id,))
    subscription = cursor.fetchone()
    
    conn.close()
    
    if subscription:
        return dict(subscription)
    return None

def get_subscription_info(sub_id: int) -> Optional[Dict]:
    """Obtiene información detallada de una suscripción incluyendo datos del usuario"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT s.*, u.username, u.first_name, u.last_name
    FROM subscriptions s
    JOIN users u ON s.user_id = u.user_id
    WHERE s.sub_id = ?
    ''', (sub_id,))
    
    subscription_info = cursor.fetchone()
    conn.close()
    
    if subscription_info:
        return dict(subscription_info)
    return None

def get_subscription_by_user_id(user_id: int) -> Optional[Dict]:
    """Obtiene la suscripción más reciente de un usuario"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM subscriptions 
    WHERE user_id = ? 
    ORDER BY start_date DESC LIMIT 1
    ''', (user_id,))
    
    subscription = cursor.fetchone()
    conn.close()
    
    if subscription:
        return dict(subscription)
    return None

# Funciones para enlaces de invitación
def save_invite_link(sub_id: int, invite_link: str, 
                     created_at: datetime.datetime, 
                     expires_at: datetime.datetime) -> int:
    """Guarda un nuevo enlace de invitación"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO invite_links (sub_id, invite_link, created_at, expires_at, used)
    VALUES (?, ?, ?, ?, 0)
    ''', (sub_id, invite_link, created_at, expires_at))
    
    link_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return link_id

def get_active_invite_link(sub_id: int) -> Optional[Dict]:
    """Obtiene un enlace de invitación activo para una suscripción"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT * FROM invite_links 
    WHERE sub_id = ? AND used = 0 AND expires_at > datetime('now')
    ORDER BY created_at DESC LIMIT 1
    ''', (sub_id,))
    
    link = cursor.fetchone()
    conn.close()
    
    if link:
        return dict(link)
    return None

def mark_invite_link_used(link_id: int) -> bool:
    """Marca un enlace de invitación como usado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE invite_links SET used = 1 WHERE link_id = ?
    ''', (link_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

# Funciones para expulsiones
def record_expulsion(user_id: int, reason: str) -> int:
    """Registra una expulsión del grupo VIP"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO expulsions (user_id, reason)
    VALUES (?, ?)
    ''', (user_id, reason))
    
    expel_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return expel_id

def get_user_expulsions(user_id: int) -> List[Dict]:
    """Obtiene todas las expulsiones de un usuario"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM expulsions WHERE user_id = ? ORDER BY date DESC', (user_id,))
    expulsions = cursor.fetchall()
    
    conn.close()
    
    return [dict(expulsion) for expulsion in expulsions]

# Modifica o añade estas funciones en database.py

def get_table_count(conn, table_name):
    """Obtiene el número de registros en una tabla"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]

def get_total_users_count(conn=None):
    """
    Obtiene el número total de usuarios registrados en el bot.
    Esta función se usa para el panel de administración.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if close_conn:
        conn.close()
    
    return count

def get_active_subscriptions_count(conn=None):
    """Obtiene el número de suscripciones activas"""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'ACTIVE' AND end_date > datetime('now')")
    count = cursor.fetchone()[0]
    
    if close_conn:
        conn.close()
    
    return count

def remove_expired_subscriptions():
    """
    Elimina suscripciones expiradas, incluyendo whitelist temporales
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Marcar suscripciones expiradas
    cursor.execute("""
    UPDATE subscriptions 
    SET status = 'EXPIRED' 
    WHERE (end_date <= datetime('now') OR status = 'EXPIRED') 
    AND status != 'EXPIRED'
    """)
    
    # Obtener los IDs de usuarios con suscripciones expiradas
    cursor.execute("""
    SELECT DISTINCT user_id 
    FROM subscriptions 
    WHERE status = 'EXPIRED'
    """)
    
    expired_users = [row[0] for row in cursor.fetchall()]
    
    conn.commit()
    conn.close()
    
    return expired_users

def close_expired_subscriptions():
    """
    Procesa las suscripciones expiradas
    """
    from bot_handlers import perform_group_security_check
    from config import GROUP_CHAT_ID
    
    # Obtener usuarios con suscripciones expiradas
    expired_users = remove_expired_subscriptions()
    
    if expired_users:
        logger.info(f"Usuarios con suscripciones expiradas: {len(expired_users)}")
        
        # Opcional: Llamar a la verificación de seguridad general
        perform_group_security_check()

# Inicializar la base de datos al importar el módulo
init_db()