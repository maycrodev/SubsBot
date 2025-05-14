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
    
    # Tabla de usuarios (existente)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabla de suscripciones (existente, con modificación para is_recurring)
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
        is_recurring BOOLEAN DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Tabla de enlaces de invitación (existente)
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
    
    # Tabla de expulsiones (existente)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS expulsions (
        expel_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reason TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # NUEVAS TABLAS
    
    # Tabla de historial de renovaciones
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscription_renewals (
        renewal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        user_id INTEGER,
        plan TEXT,
        amount_usd REAL,
        previous_end_date TIMESTAMP,
        new_end_date TIMESTAMP,
        renewal_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        payment_id TEXT,
        status TEXT,
        FOREIGN KEY (sub_id) REFERENCES subscriptions (sub_id),
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Tabla de notificaciones de renovación
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS renewal_notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        user_id INTEGER,
        sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sub_id) REFERENCES subscriptions (sub_id),
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def record_subscription_renewal(sub_id, user_id, plan, amount_usd, previous_end_date, new_end_date, payment_id=None, status="COMPLETED"):
    """
    Registra una renovación de suscripción en el historial
    
    Args:
        sub_id (int): ID de la suscripción
        user_id (int): ID del usuario
        plan (str): ID del plan
        amount_usd (float): Monto cobrado en USD
        previous_end_date (datetime): Fecha de expiración anterior
        new_end_date (datetime): Nueva fecha de expiración
        payment_id (str, optional): ID del pago en PayPal
        status (str, optional): Estado de la renovación
        
    Returns:
        int: ID de la renovación creada
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO subscription_renewals (
        sub_id, user_id, plan, amount_usd, previous_end_date, new_end_date, payment_id, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (sub_id, user_id, plan, amount_usd, previous_end_date, new_end_date, payment_id, status))
    
    renewal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return renewal_id

def record_renewal_notification(sub_id, user_id):
    """
    Registra una notificación de renovación próxima
    
    Args:
        sub_id (int): ID de la suscripción
        user_id (int): ID del usuario
        
    Returns:
        int: ID de la notificación creada
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO renewal_notifications (sub_id, user_id)
    VALUES (?, ?)
    ''', (sub_id, user_id))
    
    notification_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return notification_id

def get_subscription_renewals(sub_id=None, user_id=None, limit=10):
    """
    Obtiene el historial de renovaciones de suscripción
    
    Args:
        sub_id (int, optional): Filtrar por ID de suscripción
        user_id (int, optional): Filtrar por ID de usuario
        limit (int, optional): Límite de resultados
        
    Returns:
        list: Lista de renovaciones
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
    SELECT * FROM subscription_renewals
    '''
    
    params = []
    where_clauses = []
    
    if sub_id:
        where_clauses.append("sub_id = ?")
        params.append(sub_id)
    
    if user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    query += " ORDER BY renewal_date DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    renewals = cursor.fetchall()
    
    conn.close()
    
    return [dict(renewal) for renewal in renewals]

def get_pending_renewal_subscriptions(minutes_before=10):
    """
    Obtiene suscripciones recurrentes que vencerán en los próximos minutos
    
    Args:
        minutes_before (int): Minutos antes del vencimiento
        
    Returns:
        list: Lista de suscripciones próximas a vencer
    """
    from datetime import datetime, timedelta
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Calcular fecha objetivo
    target_date = datetime.now() + timedelta(minutes=minutes_before)
    target_date_str = target_date.strftime('%Y-%m-%d %H:%M:%S')
    
    # Modificar la consulta para usar datetime en lugar de date
    cursor.execute('''
    SELECT s.*, u.username, u.first_name, u.last_name
    FROM subscriptions s
    JOIN users u ON s.user_id = u.user_id
    WHERE s.status = 'ACTIVE' 
      AND s.is_recurring = 1
      AND s.paypal_sub_id IS NOT NULL
      AND datetime(s.end_date) <= datetime(?)
      AND datetime(s.end_date) >= datetime('now')
    ''', (target_date_str,))
    
    subscriptions = cursor.fetchall()
    conn.close()
    
    return [dict(subscription) for subscription in subscriptions]

def get_recently_notified_subscriptions(hours=24):
    """
    Obtiene las suscripciones que ya han sido notificadas recientemente sobre renovación
    
    Args:
        hours (int): Horas previas a considerar
        
    Returns:
        list: Lista de IDs de suscripciones ya notificadas
    """
    from datetime import datetime, timedelta
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Calcular fecha límite
    limit_date = datetime.now() - timedelta(hours=hours)
    limit_date_str = limit_date.strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
    SELECT sub_id 
    FROM renewal_notifications
    WHERE sent_date >= ?
    ''', (limit_date_str,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [row[0] for row in results]

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

def add_renewals_table():
    """
    Crea una tabla para registrar el historial de renovaciones automáticas
    Esta función debe ejecutarse al inicializar la base de datos
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Crear tabla de historial de renovaciones
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscription_renewals (
        renewal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        user_id INTEGER,
        plan TEXT,
        amount_usd REAL,
        previous_end_date TIMESTAMP,
        new_end_date TIMESTAMP,
        renewal_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        payment_id TEXT,
        status TEXT,
        FOREIGN KEY (sub_id) REFERENCES subscriptions (sub_id),
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Crear tabla de notificaciones de renovación
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS renewal_notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_id INTEGER,
        user_id INTEGER,
        sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sub_id) REFERENCES subscriptions (sub_id),
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Funciones para manipular suscripciones
def create_subscription(
    user_id: int, 
    plan: str, 
    price_usd: float, 
    start_date: datetime.datetime, 
    end_date: datetime.datetime, 
    status: str = 'ACTIVE', 
    paypal_sub_id: str = None,
    is_recurring: bool = None  # Añadir este parámetro opcional
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar si la columna is_recurring existe, si no, crearla
    cursor.execute("PRAGMA table_info(subscriptions)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'is_recurring' not in columns:
        cursor.execute('ALTER TABLE subscriptions ADD COLUMN is_recurring BOOLEAN DEFAULT 1')
        conn.commit()
    
    cursor.execute('''
    INSERT INTO subscriptions (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id, is_recurring)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id, is_recurring))
    
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return sub_id

def get_subscription_by_payment_id(payment_id: str) -> Optional[Dict]:
    """Obtiene una suscripción por su ID de pago en PayPal (order_id para pagos únicos)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM subscriptions WHERE paypal_sub_id = ?', (payment_id,))
    subscription = cursor.fetchone()
    
    conn.close()
    
    if subscription:
        return dict(subscription)
    return None

def is_subscription_recurring(sub_id: int) -> bool:
    """Verifica si una suscripción es recurrente o de pago único"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # If the column doesn't exist yet, add it (for backward compatibility)
    cursor.execute("PRAGMA table_info(subscriptions)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'is_recurring' not in columns:
        cursor.execute('ALTER TABLE subscriptions ADD COLUMN is_recurring BOOLEAN DEFAULT 1')
        conn.commit()
        # When upgrading, we assume all existing subscriptions were recurring
        cursor.execute('UPDATE subscriptions SET is_recurring = 1')
        conn.commit()
    
    cursor.execute('SELECT is_recurring FROM subscriptions WHERE sub_id = ?', (sub_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if not result:
        return True  # Default to True if no result (shouldn't happen)
    
    return bool(result[0])

def get_active_subscription(user_id: int) -> Optional[Dict]:
    """Obtiene la suscripción activa de un usuario si existe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # CORREGIDO: Asegurarse que status='ACTIVE' y fecha no ha expirado
    cursor.execute('''
    SELECT * FROM subscriptions 
    WHERE user_id = ? 
    AND status = 'ACTIVE' 
    AND datetime(end_date) > datetime('now')
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
    """
    Extiende la fecha de expiración de una suscripción y asegura que mantenga estado ACTIVE
    
    Args:
        sub_id (int): ID de la suscripción
        new_end_date (datetime): Nueva fecha de expiración
        
    Returns:
        bool: True si la operación fue exitosa
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Registrar información para diagnóstico
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Extendiendo suscripción {sub_id} hasta {new_end_date}")
    
    # Obtener información actual de la suscripción
    cursor.execute('SELECT status, end_date FROM subscriptions WHERE sub_id = ?', (sub_id,))
    current = cursor.fetchone()
    
    if not current:
        logger.error(f"No se encontró la suscripción {sub_id} para extender")
        conn.close()
        return False
    
    current_status = current['status']
    current_end_date = current['end_date']
    
    # Actualizar la suscripción
    cursor.execute('''
    UPDATE subscriptions 
    SET end_date = ?, 
        status = 'ACTIVE' 
    WHERE sub_id = ?
    ''', (new_end_date, sub_id))
    
    affected = cursor.rowcount
    conn.commit()
    
    # Registrar cambio de estado si es necesario
    if current_status != 'ACTIVE':
        logger.info(f"Suscripción {sub_id} cambió de estado {current_status} a ACTIVE")
    
    # Registrar extensión
    logger.info(f"Suscripción {sub_id} extendida de {current_end_date} a {new_end_date}")
    
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

def close_expired_subscriptions(bot=None):
    """
    Procesa las suscripciones expiradas
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Marcar suscripciones expiradas
    cursor.execute("""
    UPDATE subscriptions 
    SET status = 'EXPIRED' 
    WHERE status = 'ACTIVE' AND end_date <= datetime('now')
    """)
    
    # Obtener los usuarios con suscripciones expiradas
    cursor.execute("""
    SELECT user_id, plan FROM subscriptions 
    WHERE status = 'EXPIRED'
    """)
    
    expired_users = cursor.fetchall()
    
    conn.commit()
    conn.close()
    
    logger.info(f"Suscripciones expiradas procesadas: {len(expired_users)}")
    
    return expired_users

def check_and_update_subscriptions(force=False) -> List[Tuple[int, int, str]]:
    """
    Verifica y actualiza el estado de las suscripciones expiradas
    Retorna lista de (user_id, sub_id, plan)
    
    Args:
        force (bool): Si es True, fuerza la verificación incluso de suscripciones ya marcadas como expiradas
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener la fecha actual para logging
    current_time = datetime.datetime.now()
    logger.info(f"Verificación iniciada a: {current_time}")
    
    try:
        # PASO 1: Marcar como EXPIRED solo las suscripciones ACTIVE que han expirado
        # Importante: No cambiar el estado de suscripciones que no sean ACTIVE
        query = """
        UPDATE subscriptions 
        SET status = 'EXPIRED'
        WHERE 
            status = 'ACTIVE' AND 
            datetime(end_date) <= datetime('now')
        """
        
        cursor.execute(query)
        
        # Registrar cuántas filas fueron afectadas
        affected_rows = cursor.rowcount
        logger.info(f"Suscripciones actualizadas a EXPIRED: {affected_rows}")
        
        # PASO 2: Obtener todas las suscripciones expiradas para procesamiento
        # Solo consideramos expiradas las que tengan estado EXPIRED
        # Si force=True, incluimos también las que han expirado en fecha pero no tienen estado EXPIRED
        if force:
            expired_query = """
            SELECT 
                user_id, 
                sub_id, 
                plan, 
                end_date, 
                start_date,
                status,
                CASE WHEN paypal_sub_id IS NULL THEN 'WHITELIST' ELSE 'PAID' END as subscription_type
            FROM subscriptions 
            WHERE 
                (status = 'EXPIRED' OR 
                (datetime(end_date) <= datetime('now') AND status != 'CANCELLED'))
            """
        else:
            expired_query = """
            SELECT 
                user_id, 
                sub_id, 
                plan, 
                end_date, 
                start_date,
                status,
                CASE WHEN paypal_sub_id IS NULL THEN 'WHITELIST' ELSE 'PAID' END as subscription_type
            FROM subscriptions 
            WHERE status = 'EXPIRED'
            """
        
        cursor.execute(expired_query)
        expired_subscriptions = cursor.fetchall()
        
        # Registro detallado de suscripciones expiradas
        whitelist_count = 0
        paid_count = 0
        
        for sub in expired_subscriptions:
            try:
                end_date = datetime.datetime.fromisoformat(sub[3]) if sub[3] else None
                start_date = datetime.datetime.fromisoformat(sub[4]) if sub[4] else None
                status = sub[5] if len(sub) > 5 else "DESCONOCIDO"
                sub_type = sub[6] if len(sub) > 6 else "DESCONOCIDO"
                
                # Contar por tipo
                if sub_type == 'WHITELIST':
                    whitelist_count += 1
                elif sub_type == 'PAID':
                    paid_count += 1
                    
                time_diff = "N/A"
                if end_date:
                    time_diff = current_time - end_date
                    
                logger.info(f"""
                Suscripción expirada:
                - User ID: {sub[0]}
                - Sub ID: {sub[1]}
                - Plan: {sub[2]}
                - Tipo: {sub_type}
                - Status: {status}
                - Fecha de inicio: {start_date}
                - Fecha de fin: {end_date}
                - Tiempo transcurrido desde expiración: {time_diff}
                """)
                
            except Exception as e:
                logger.error(f"Error al procesar datos de suscripción expirada: {e}")
        
        logger.info(f"Total expiradas: {len(expired_subscriptions)} (Whitelist: {whitelist_count}, Pagadas: {paid_count})")
        
        conn.commit()
        
        # Retornar solo los datos necesarios (user_id, sub_id, plan)
        return [(sub[0], sub[1], sub[2]) for sub in expired_subscriptions]
        
    except Exception as e:
        logger.error(f"Error en check_and_update_subscriptions: {e}")
        conn.rollback()
        return []
        
    finally:
        conn.close()

def get_users_to_expel() -> List[Tuple[int, str, str]]:
    """
    Obtiene una lista de todos los usuarios que deberían ser expulsados del grupo VIP.
    Incluye todos los usuarios con suscripciones expiradas o canceladas.
    
    Returns:
        List[Tuple[int, str, str]]: Lista de tuplas (user_id, motivo, tipo_suscripción)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Obtener usuarios con suscripciones expiradas o canceladas
        cursor.execute("""
        SELECT 
            u.user_id, 
            s.status, 
            s.end_date,
            CASE WHEN s.paypal_sub_id IS NULL THEN 'WHITELIST' ELSE 'PAID' END as subscription_type
        FROM users u
        JOIN subscriptions s ON u.user_id = s.user_id
        WHERE s.status IN ('EXPIRED', 'CANCELLED')
        OR datetime(s.end_date) <= datetime('now')
        GROUP BY u.user_id
        """)
        
        results = cursor.fetchall()
        
        # Formatear resultados
        users_to_expel = []
        for row in results:
            user_id = row[0]
            status = row[1]
            end_date = row[2]
            sub_type = row[3]
            
            # Determinar motivo de expulsión
            if status == 'EXPIRED' or (end_date and datetime.datetime.fromisoformat(end_date) <= datetime.datetime.now()):
                reason = "Suscripción expirada"
            elif status == 'CANCELLED':
                reason = "Suscripción cancelada"
            else:
                reason = "Suscripción no válida"
            
            users_to_expel.append((user_id, reason, sub_type))
        
        return users_to_expel
        
    except Exception as e:
        logger.error(f"Error en get_users_to_expel: {e}")
        return []
        
    finally:
        conn.close()

def record_failed_expulsion(user_id: int, reason: str, error_message: str) -> int:
    """
    Registra un intento fallido de expulsión para seguimiento y diagnóstico
    
    Args:
        user_id: ID del usuario que no pudo ser expulsado
        reason: Motivo por el que debía ser expulsado
        error_message: Mensaje de error que ocurrió al intentar expulsar
        
    Returns:
        int: ID del registro de fallo
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Primero verificar si la tabla existe
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_expulsions (
            fail_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            error_message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """)
        
        # Insertar el registro
        cursor.execute("""
        INSERT INTO failed_expulsions (user_id, reason, error_message)
        VALUES (?, ?, ?)
        """, (user_id, reason, error_message))
        
        fail_id = cursor.lastrowid
        conn.commit()
        
        return fail_id
        
    except Exception as e:
        logger.error(f"Error al registrar expulsión fallida: {e}")
        conn.rollback()
        return -1
        
    finally:
        conn.close()

def has_valid_subscription(user_id: int) -> bool:
    """Verifica si un usuario tiene alguna suscripción válida actualmente"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar suscripciones activas que no han expirado
        cursor.execute("""
        SELECT COUNT(*) FROM subscriptions 
        WHERE user_id = ? 
        AND status = 'ACTIVE' 
        AND datetime(end_date) > datetime('now')
        """, (user_id,))
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True
        
        # NUEVO: Verificar si hay suscripciones recurrentes recientemente expiradas
        # Esto da un "período de gracia" de hasta 3 horas para procesar renovaciones
        cursor.execute("""
        SELECT s.sub_id, s.plan, s.end_date, s.paypal_sub_id 
        FROM subscriptions s
        WHERE s.user_id = ? 
        AND s.status = 'ACTIVE'
        AND s.is_recurring = 1
        AND s.paypal_sub_id IS NOT NULL
        AND datetime(s.end_date) BETWEEN datetime('now', '-3 hour') AND datetime('now')
        ORDER BY s.end_date DESC
        LIMIT 1
        """, (user_id,))
        
        recent_expired = cursor.fetchone()
        
        if recent_expired:
            sub_id = recent_expired[0]
            plan = recent_expired[1]
            end_date = recent_expired[2]
            paypal_id = recent_expired[3]
            
            # Registrar para diagnóstico
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"PERÍODO DE GRACIA: Usuario {user_id} tiene suscripción recurrente {sub_id} (plan {plan}) "
                        f"recientemente expirada ({end_date}), considerando válida para renovación")
            
            # Verificar en la tabla de renovaciones si ya hubo algún intento reciente
            cursor.execute("""
            SELECT COUNT(*) FROM subscription_renewals
            WHERE sub_id = ? AND renewal_date > datetime('now', '-1 day')
            """, (sub_id,))
            
            recent_renewals = cursor.fetchone()[0]
            
            if recent_renewals > 0:
                logger.info(f"Encontradas {recent_renewals} renovaciones recientes para suscripción {sub_id}")
                # Ya se procesó una renovación, pero la suscripción sigue expirada, algo está mal
                # Extender automáticamente por precaución
                try:
                    from config import PLANS
                    import datetime
                    
                    plan_details = PLANS.get(plan)
                    if plan_details:
                        # Calcular nueva fecha de expiración
                        now = datetime.datetime.now()
                        new_end_date = now + datetime.timedelta(days=plan_details['duration_days'])
                        
                        # Actualizar suscripción
                        cursor.execute("""
                        UPDATE subscriptions 
                        SET end_date = ?, status = 'ACTIVE' 
                        WHERE sub_id = ?
                        """, (new_end_date.isoformat(), sub_id))
                        
                        conn.commit()
                        
                        logger.warning(f"RECUPERACIÓN AUTOMÁTICA: Extendida suscripción {sub_id} hasta {new_end_date}")
                        
                        # Notificar a administradores
                        try:
                            from config import ADMIN_IDS
                            for admin_id in ADMIN_IDS:
                                try:
                                    import telebot
                                    from config import BOT_TOKEN
                                    bot = telebot.TeleBot(BOT_TOKEN)
                                    bot.send_message(
                                        chat_id=admin_id,
                                        text=f"🔄 Suscripción {sub_id} recuperada automáticamente para usuario {user_id}\n\n"
                                             f"Estaba expirada pero tenía un pago reciente. Extendida hasta {new_end_date}."
                                    )
                                except:
                                    pass
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Error en recuperación automática: {e}")
            
            # En cualquier caso, consideramos la suscripción válida durante este período de gracia
            return True
        
        # Si llegamos aquí, no hay suscripción válida ni en período de gracia
        return False
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error al verificar suscripción válida: {e}")
        return False
        
    finally:
        conn.close()

def is_whitelist_subscription(sub_id: int) -> bool:
    """Verifica si una suscripción es de tipo whitelist (manual, sin pago)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT paypal_sub_id FROM subscriptions WHERE sub_id = ?', (sub_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    # Es whitelist si paypal_sub_id es NULL
    return result is not None and result[0] is None

# Inicializar la base de datos al importar el módulo
init_db()