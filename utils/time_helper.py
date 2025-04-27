import re
import datetime
import logging
from typing import Optional, Tuple

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_duration(duration_text: str) -> Optional[int]:
    """
    Parsea una duración en texto y la convierte a días.
    Ejemplos: '7 days', '1 week', '1 month', '3 months'
    Retorna None si no se puede parsear.
    """
    try:
        # Patrones para diferentes formatos
        day_pattern = re.compile(r'(\d+)\s*(?:day|days|día|dias|d)', re.IGNORECASE)
        week_pattern = re.compile(r'(\d+)\s*(?:week|weeks|semana|semanas|w)', re.IGNORECASE)
        month_pattern = re.compile(r'(\d+)\s*(?:month|months|mes|meses|m)', re.IGNORECASE)
        year_pattern = re.compile(r'(\d+)\s*(?:year|years|año|años|y)', re.IGNORECASE)
        
        # Verificar cada patrón
        day_match = day_pattern.search(duration_text)
        if day_match:
            return int(day_match.group(1))
        
        week_match = week_pattern.search(duration_text)
        if week_match:
            return int(week_match.group(1)) * 7
        
        month_match = month_pattern.search(duration_text)
        if month_match:
            return int(month_match.group(1)) * 30
        
        year_match = year_pattern.search(duration_text)
        if year_match:
            return int(year_match.group(1)) * 365
        
        # Si es solo un número, asumir días
        if duration_text.isdigit():
            return int(duration_text)
        
        # No se pudo parsear
        return None
        
    except Exception as e:
        logger.error(f"Error al parsear duración '{duration_text}': {str(e)}")
        return None

def calculate_expiry_date(days: int) -> datetime.datetime:
    """Calcula la fecha de expiración a partir de la cantidad de días."""
    return datetime.datetime.now() + datetime.timedelta(days=days)

def format_datetime(dt: datetime.datetime, format_str: str = "%d %b %Y %I:%M %p") -> str:
    """Formatea una fecha y hora en un formato legible."""
    return dt.strftime(format_str)

def format_date(dt: datetime.datetime, format_str: str = "%d %b %Y") -> str:
    """Formatea una fecha en un formato legible."""
    return dt.strftime(format_str)

def get_time_remaining(end_date: datetime.datetime) -> Tuple[int, int, int]:
    """
    Calcula el tiempo restante hasta una fecha de expiración.
    Retorna una tupla de (días, horas, minutos).
    """
    now = datetime.datetime.now()
    if end_date < now:
        return (0, 0, 0)
    
    delta = end_date - now
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    return (days, hours, minutes)

def time_remaining_text(end_date: datetime.datetime) -> str:
    """
    Obtiene un texto legible con el tiempo restante.
    Ejemplo: "2 días, 5 horas y 30 minutos"
    """
    days, hours, minutes = get_time_remaining(end_date)
    
    if days == 0 and hours == 0 and minutes == 0:
        return "Expirado"
    
    parts = []
    if days > 0:
        parts.append(f"{days} día{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
    
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} y {parts[1]}"
    else:
        return f"{parts[0]}, {parts[1]} y {parts[2]}"