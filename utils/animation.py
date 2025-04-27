import time
import threading
import logging

# Obtener la instancia del bot
from app import bot

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LoadingAnimation:
    """Clase para manejar animaciones de carga en mensajes de Telegram"""
    
    def __init__(self, chat_id, message_id, prefix_text="Cargando", suffix_text="Por favor, espere..."):
        self.chat_id = chat_id
        self.message_id = message_id
        self.prefix_text = prefix_text
        self.suffix_text = suffix_text
        self.is_active = False
        self.animation_thread = None
        self.animation_markers = ['/', '-', '|', '\\']
        self.current_marker_index = 0
    
    def start(self):
        """Inicia la animación en un hilo separado"""
        if self.is_active:
            return False
        
        self.is_active = True
        self.animation_thread = threading.Thread(target=self._run_animation)
        self.animation_thread.daemon = True
        self.animation_thread.start()
        return True
    
    def stop(self):
        """Detiene la animación"""
        self.is_active = False
        if self.animation_thread:
            self.animation_thread.join(timeout=1.0)
    
    def _run_animation(self):
        """Ejecuta la animación mientras esté activa"""
        try:
            while self.is_active:
                marker = self.animation_markers[self.current_marker_index]
                
                message_text = (
                    f"{self.prefix_text}\n"
                    f"      {marker}      \n"
                    f"{self.suffix_text}"
                )
                
                try:
                    bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.message_id,
                        text=message_text
                    )
                except Exception as e:
                    logger.error(f"Error al actualizar animación: {str(e)}")
                    self.is_active = False
                    break
                
                # Avanzar al siguiente marcador
                self.current_marker_index = (self.current_marker_index + 1) % len(self.animation_markers)
                
                # Esperar antes de la siguiente actualización
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error en animación: {str(e)}")
            self.is_active = False

def create_processing_animation(chat_id, message_id, prefix="🔄 Confirmando Pago", suffix="Aguarde por favor..."):
    """Crea una nueva instancia de animación de procesamiento"""
    animation = LoadingAnimation(chat_id, message_id, prefix, suffix)
    animation.start()
    return animation