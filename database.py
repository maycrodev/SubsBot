import sqlite3
import datetime
from typing import Dict, List, Optional, Tuple, Any
from config import DB_PATH
from config import SUBSCRIPTION_GRACE_PERIOD_HOURS
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
    
    create_processed_payments_table()

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

# Añadir estas nuevas funciones en database.py

def create_processed_payments_table():
    """Crea la tabla para registrar eventos de pago ya procesados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS processed_payments (
        payment_id TEXT,
        event_type TEXT,
        subscription_id INTEGER,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (payment_id, event_type)
    )
    ''')
    
    conn.commit()
    conn.close()

def is_payment_processed(payment_id, event_type):
    """Verifica si un evento de pago ya ha sido procesado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT COUNT(*) FROM processed_payments 
    WHERE payment_id = ? AND event_type = ?
    ''', (payment_id, event_type))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count > 0

def mark_payment_processed(payment_id, event_type, subscription_id=None):
    """Registra que un evento de pago ha sido procesado"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO processed_payments (payment_id, event_type, subscription_id)
    VALUES (?, ?, ?)
    ''', (payment_id, event_type, subscription_id))
    
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
    is_recurring: bool = None  # Opcional
) -> int:
    """
    Crea una nueva suscripción con duración exacta calculada en horas
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si la columna is_recurring existe, si no, crearla
        cursor.execute("PRAGMA table_info(subscriptions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_recurring' not in columns:
            cursor.execute('ALTER TABLE subscriptions ADD COLUMN is_recurring BOOLEAN DEFAULT 1')
            conn.commit()
        
        # MEJORA: Calcular duración exacta en horas
        from config import PLANS
        plan_config = PLANS.get(plan, {})
        plan_days = plan_config.get('duration_days', 30)
        plan_hours = int(plan_days * 24)
        
        # Calcular la fecha de fin exacta basada en la hora
        corrected_end_date = start_date + datetime.timedelta(hours=plan_hours)
        
        # Usar la fecha calculada en lugar de la proporcionada
        end_date = corrected_end_date
        
        logger.info(f"Creando suscripción: Plan {plan}, Duración {plan_days} días ({plan_hours} horas)")
        logger.info(f"Fecha inicio: {start_date}, Fecha fin calculada: {end_date}")
        
        cursor.execute('''
        INSERT INTO subscriptions (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id, is_recurring)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, plan, price_usd, start_date, end_date, status, paypal_sub_id, is_recurring))
        
        sub_id = cursor.lastrowid
        conn.commit()
        
        return sub_id
    
    except Exception as e:
        logger.error(f"Error en create_subscription: {str(e)}")
        conn.rollback()
        return -1
        
    finally:
        conn.close()

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
    (pero solo si no está cancelada)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Registrar información para diagnóstico
        logger.info(f"Extendiendo suscripción {sub_id} hasta {new_end_date}")
        
        # Obtener información actual de la suscripción
        cursor.execute('SELECT status, end_date, start_date, plan FROM subscriptions WHERE sub_id = ?', (sub_id,))
        current = cursor.fetchone()
        
        if not current:
            logger.error(f"No se encontró la suscripción {sub_id} para extender")
            conn.close()
            return False
        
        current_status = current[0]
        current_end_date = current[1]
        current_start_date = current[2]
        plan_id = current[3]
        
        # MEJORA: No extender suscripciones canceladas
        if current_status == 'CANCELLED':
            logger.info(f"No se extiende suscripción {sub_id} porque está CANCELADA")
            conn.close()
            return False
        
        # Verificar que la nueva fecha sea posterior a la fecha actual
        now = datetime.datetime.now(datetime.timezone.utc)
        if new_end_date <= now:
            logger.error(f"La nueva fecha de fin ({new_end_date}) es anterior o igual a la fecha actual ({now})")
            new_end_date = now + datetime.timedelta(hours=1)  # Mínimo 1 hora de extensión como salvaguarda
            logger.warning(f"Ajustando fecha de fin a {new_end_date} para evitar expiración inmediata")
        
        # MEJORA: Calcular con precisión de horas en lugar de días para evitar duplicación
        try:
            original_end = datetime.datetime.fromisoformat(current_end_date)
            original_start = datetime.datetime.fromisoformat(current_start_date)
            
            # Importar configuración de planes
            from config import PLANS
            plan_config = PLANS.get(plan_id, {})
            
            # MEJORA: Obtener duración en horas para mayor precisión
            plan_duration_days = plan_config.get('duration_days', 30)
            plan_duration_hours = int(plan_duration_days * 24)
            
            # Calcular extensión desde la fecha de fin actual o desde ahora, la que sea mayor
            if original_end > now:
                # Si la suscripción aún no ha expirado, extender desde la fecha fin actual
                extension_base = original_end
            else:
                # Si ya expiró, extender desde ahora
                extension_base = now
            
            # Calcular la nueva fecha fin con la duración exacta en horas
            corrected_end_date = extension_base + datetime.timedelta(hours=plan_duration_hours)
            
            logger.info(f"Fecha start original: {original_start}")
            logger.info(f"Fecha end original: {original_end}")
            logger.info(f"Base de extensión: {extension_base}")
            logger.info(f"Duración del plan en horas: {plan_duration_hours}")
            logger.info(f"Nueva fecha calculada: {corrected_end_date}")
            logger.info(f"Fecha proporcionada: {new_end_date}")
            
            # MEJORA: Usar siempre la fecha calculada para evitar duplicaciones
            new_end_date = corrected_end_date
            
        except Exception as e:
            logger.error(f"Error al calcular nueva fecha: {e}")
            # En caso de error, mantener la fecha proporcionada
        
        # Actualizar la suscripción
        cursor.execute('''
        UPDATE subscriptions 
        SET end_date = ?, 
            status = 'ACTIVE' 
        WHERE sub_id = ? AND status != 'CANCELLED'
        ''', (new_end_date, sub_id))
        
        affected = cursor.rowcount
        conn.commit()
        
        # Registrar cambio específico de fecha solo si se actualizó
        if affected > 0:
            logger.info(f"Suscripción {sub_id}: Cambiando fecha de fin de {current_end_date} a {new_end_date}")
            if current_status != 'ACTIVE':
                logger.info(f"Suscripción {sub_id} cambió de estado {current_status} a ACTIVE")
        else:
            logger.warning(f"No se actualizó la suscripción {sub_id}")
        
        return affected > 0
        
    except Exception as e:
        logger.error(f"Error en extend_subscription: {str(e)}")
        return False
        
    finally:
        conn.close()

def mark_failed_expulsion_processed(fail_id: int) -> bool:
    """
    Marca un intento fallido de expulsión como procesado
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Actualizar el registro
        cursor.execute("""
        UPDATE failed_expulsions
        SET processed = 1
        WHERE fail_id = ?
        """, (fail_id,))
        
        affected = cursor.rowcount
        conn.commit()
        
        return affected > 0
        
    except Exception as e:
        logger.error(f"Error al marcar fallo de expulsión como procesado: {e}")
        return False
        
    finally:
        conn.close()

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
    """Obtiene el número de suscripciones activas incluyendo las del periodo de gracia"""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT COUNT(*) FROM subscriptions 
    WHERE 
        -- Suscripciones ACTIVE normales
        (status = 'ACTIVE' AND end_date > datetime('now'))
        OR
        -- Suscripciones en periodo de gracia con renovaciones recientes
        (status = 'ACTIVE' AND is_recurring = 1 AND paypal_sub_id IS NOT NULL 
         AND datetime(end_date) BETWEEN datetime('now', '-{SUBSCRIPTION_GRACE_PERIOD_HOURS} hour') AND datetime('now'))
        OR
        -- Suscripciones con renovaciones recientes (detectadas por la tabla de renovaciones)
        (sub_id IN (SELECT sub_id FROM subscription_renewals 
                   WHERE renewal_date >= datetime('now', '-36 hour')))
    """)
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
    Verifica y actualiza el estado de las suscripciones expiradas y canceladas
    Retorna lista de (user_id, sub_id, plan)
    
    Args:
        force (bool): Si es True, fuerza la verificación incluso de suscripciones ya marcadas como expiradas
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Obtener la fecha actual para logging
    current_time = datetime.datetime.now(datetime.timezone.utc)  # Make timezone-aware
    logger.info(f"Verificación iniciada a: {current_time}")
    
    try:
        # PASO 1: Marcar como EXPIRED solo las suscripciones ACTIVE que han expirado
        # MEJORA: Usar 24 horas como período de gracia estándar
        query = """
        UPDATE subscriptions 
        SET status = 'EXPIRED'
        WHERE 
            status = 'ACTIVE' AND 
            datetime(end_date) <= datetime('now', '-24 hour')
        """
        
        cursor.execute(query)
        
        # Registrar cuántas filas fueron afectadas
        affected_rows = cursor.rowcount
        logger.info(f"Suscripciones actualizadas a EXPIRED: {affected_rows}")
        
        # PASO 2: Obtener todas las suscripciones expiradas o canceladas para procesamiento
        # MEJORA: Siempre incluir suscripciones CANCELLED en la verificación
        if force:
            expired_query = """
            SELECT 
                user_id, 
                sub_id, 
                plan, 
                end_date, 
                start_date,
                status,
                CASE WHEN paypal_sub_id IS NULL THEN 'WHITELIST' ELSE 'PAID' END as subscription_type,
                is_recurring,
                paypal_sub_id
            FROM subscriptions 
            WHERE 
                status = 'EXPIRED' OR status = 'CANCELLED'
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
                CASE WHEN paypal_sub_id IS NULL THEN 'WHITELIST' ELSE 'PAID' END as subscription_type,
                is_recurring,
                paypal_sub_id
            FROM subscriptions 
            WHERE status = 'EXPIRED' OR status = 'CANCELLED'
            """
        
        cursor.execute(expired_query)
        expired_subscriptions = cursor.fetchall()
        
        # Registro detallado de suscripciones expiradas
        whitelist_count = 0
        paid_count = 0
        cancelled_count = 0
        expired_count = 0
        
        for sub in expired_subscriptions:
            try:
                user_id = sub[0]
                sub_id = sub[1]
                plan = sub[2]
                
                # Fix: Handle timezone consistently when parsing dates
                end_date_str = sub[3] if sub[3] else None
                start_date_str = sub[4] if sub[4] else None
                
                # Create timezone-aware datetime objects
                end_date = None
                if end_date_str:
                    try:
                        # Parse the date and make it timezone-aware if it isn't already
                        end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                        if not end_date.tzinfo:
                            end_date = end_date.replace(tzinfo=datetime.timezone.utc)
                    except Exception as date_err:
                        logger.error(f"Error parsing end_date: {date_err}")
                
                start_date = None
                if start_date_str:
                    try:
                        # Parse the date and make it timezone-aware if it isn't already
                        start_date = datetime.datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                        if not start_date.tzinfo:
                            start_date = start_date.replace(tzinfo=datetime.timezone.utc)
                    except Exception as date_err:
                        logger.error(f"Error parsing start_date: {date_err}")
                
                status = sub[5] 
                sub_type = sub[6]
                is_recurring = sub[7]
                paypal_sub_id = sub[8]
                
                # Contar por tipo
                if sub_type == 'WHITELIST':
                    whitelist_count += 1
                elif sub_type == 'PAID':
                    paid_count += 1
                
                if status == 'CANCELLED':
                    cancelled_count += 1
                elif status == 'EXPIRED':
                    expired_count += 1
                    
                time_diff = "N/A"
                if end_date:
                    try:
                        # Asegúrese de que ambas fechas tienen información de zona horaria
                        if not end_date.tzinfo:
                            # Si end_date no tiene zona horaria, asignar UTC
                            end_date = end_date.replace(tzinfo=datetime.timezone.utc)
                            
                        if not current_time.tzinfo:
                            # Si current_time no tiene zona horaria, asignar UTC
                            current_time = current_time.replace(tzinfo=datetime.timezone.utc)
                            
                        # Ahora ambas fechas tienen información de zona horaria y pueden restarse
                        time_diff = current_time - end_date
                    except Exception as e:
                        logger.error(f"Error al calcular diferencia de tiempo: {e}")
                        time_diff = "N/A"
                    
                logger.info(f"""
                Suscripción {status}:
                - User ID: {user_id}
                - Sub ID: {sub_id}
                - Plan: {plan}
                - Tipo: {sub_type}
                - Recurrente: {is_recurring}
                - PayPal ID: {paypal_sub_id}
                - Fecha de inicio: {start_date}
                - Fecha de fin: {end_date}
                - Tiempo transcurrido desde expiración: {time_diff}
                """)
                
            except Exception as e:
                logger.error(f"Error al procesar datos de suscripción: {e}")
        
        logger.info(f"Total: {len(expired_subscriptions)} (Whitelist: {whitelist_count}, Pagadas: {paid_count}, Canceladas: {cancelled_count}, Expiradas: {expired_count})")
        
        # PASO 3: Verificar si cada usuario tiene alguna otra suscripción válida antes de expulsarlo
        filtered_subscriptions = []
        for sub in expired_subscriptions:
            user_id = sub[0]
            sub_id = sub[1]
            plan = sub[2]
            status = sub[5]
            
            # MEJORA: Si la suscripción está cancelada, siempre incluirla
            if status == 'CANCELLED':
                logger.info(f"Incluyendo usuario {user_id} con suscripción CANCELADA (sub_id: {sub_id})")
                filtered_subscriptions.append((user_id, sub_id, plan))
                continue
            
            # Verificar que el usuario no tenga ninguna suscripción válida
            if not db.has_valid_subscription(user_id):
                logger.info(f"Usuario {user_id} no tiene suscripciones válidas, incluyendo para expulsión")
                filtered_subscriptions.append((user_id, sub_id, plan))
            else:
                logger.info(f"Omitiendo usuario {user_id} (sub_id: {sub_id}) porque tiene otra suscripción válida")
        
        logger.info(f"Total de suscripciones a procesar después de filtrado: {len(filtered_subscriptions)} de {len(expired_subscriptions)}")
        
        conn.commit()
        
        # Retornar solo los datos necesarios (user_id, sub_id, plan)
        return filtered_subscriptions
        
    except Exception as e:
        logger.error(f"Error en check_and_update_subscriptions: {e}")
        conn.rollback()
        return []
        
    finally:
        conn.close()

def record_failed_expulsion(user_id: int, reason: str, error_message: str) -> int:
    """
    Registra un intento fallido de expulsión para seguimiento y diagnóstico
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Crear tabla si no existe
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS failed_expulsions (
            fail_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            error_message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed BOOLEAN DEFAULT 0,
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
        
        logger.info(f"Registrado fallo de expulsión ID {fail_id} para usuario {user_id}: {reason}")
        return fail_id
        
    except Exception as e:
        logger.error(f"Error al registrar expulsión fallida: {e}")
        conn.rollback()
        return -1
        
    finally:
        conn.close()

def get_subscription_by_id(sub_id: int) -> Optional[Dict]:
    """Obtiene una suscripción por su ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM subscriptions WHERE sub_id = ?', (sub_id,))
    subscription = cursor.fetchone()
    
    conn.close()
    
    if subscription:
        return dict(subscription)
    return None

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
        # PASO 1: Verificar si hay alguna suscripción CANCELLED reciente
        # MEJORA: Primero verificamos si hay suscripciones canceladas para evitar problemas
        cursor.execute("""
        SELECT COUNT(*) FROM subscriptions 
        WHERE user_id = ? 
        AND status = 'CANCELLED'
        AND datetime(end_date) > datetime('now', '-1 day')
        """, (user_id,))
        
        cancelled_count = cursor.fetchone()[0]
        
        if cancelled_count > 0:
            logger.info(f"Usuario {user_id} tiene suscripciones canceladas recientes")
            return False  # Si hay suscripciones canceladas recientes, no se considera válido
        
        # PASO 2: Verificar suscripciones activas que no han expirado
        cursor.execute("""
        SELECT COUNT(*) FROM subscriptions 
        WHERE user_id = ? 
        AND status = 'ACTIVE' 
        AND datetime(end_date) > datetime('now')
        """, (user_id,))
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Usuario {user_id} tiene {count} suscripciones activas vigentes")
            return True
        
        # PASO 3: PERÍODO DE GRACIA: Verificar suscripciones recurrentes en período de gracia
        # MEJORA: Aumentar el período de gracia a 24 horas para manejar los adelantos de PayPal
        cursor.execute(f"""
        SELECT s.sub_id, s.plan, s.end_date, s.paypal_sub_id 
        FROM subscriptions s
        WHERE s.user_id = ? 
        AND s.status = 'ACTIVE'
        AND s.is_recurring = 1
        AND s.paypal_sub_id IS NOT NULL
        AND datetime(s.end_date) BETWEEN datetime('now', '-24 hour') AND datetime('now', '+24 hour')
        ORDER BY s.end_date DESC
        LIMIT 1
        """, (user_id,))
        
        grace_period_sub = cursor.fetchone()
        
        if grace_period_sub:
            sub_id = grace_period_sub[0]
            plan = grace_period_sub[1]
            end_date = grace_period_sub[2]
            
            logger.info(f"PERÍODO DE GRACIA: Usuario {user_id} tiene suscripción recurrente {sub_id} "
                        f"(plan {plan}) en período de gracia ({end_date}), considerando válida")
            return True
            
        # PASO 4: También verificar si hay renovaciones recientes en las últimas 36 horas
        cursor.execute("""
        SELECT COUNT(*) FROM subscription_renewals
        WHERE user_id = ? AND renewal_date >= datetime('now', '-36 hour')
        """, (user_id,))
        
        recent_renewals = cursor.fetchone()[0]
        
        if recent_renewals > 0:
            logger.info(f"Usuario {user_id} tiene {recent_renewals} renovaciones recientes, considerado válido")
            return True
        
        # Si llegamos aquí, no hay ninguna suscripción válida
        return False
        
    except Exception as e:
        logger.error(f"Error al verificar suscripción válida: {e}")
        # En caso de error, damos el beneficio de la duda
        return True
        
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