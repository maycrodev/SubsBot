import time
import telebot
from threading import Thread

# Marcos de animación para el proceso de pago
PAYMENT_FRAMES = [
    "🔄 Confirmando Pago\n      /\nAguarde por favor...",
    "🔄 Confirmando Pago\n      -\nAguarde por favor...",
    "🔄 Confirmando Pago\n      \\\nAguarde por favor...",
    "🔄 Confirmando Pago\n      |\nAguarde por favor...",
    "🔄 Confirmando Pago\n      -\nAguarde por favor..."
]

def animate_payment_processing(bot, chat_id, message_id, stop_event, interval=0.5):
    """
    Anima el mensaje de procesamiento de pago.
    
    Args:
        bot: Instancia del bot de Telegram
        chat_id: ID del chat donde mostrar la animación
        message_id: ID del mensaje a animar
        stop_event: Evento para detener la animación
        interval: Intervalo entre frames en segundos
    """
    frame_index = 0
    
    while not stop_event.is_set():
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=PAYMENT_FRAMES[frame_index % len(PAYMENT_FRAMES)]
            )
            frame_index += 1
            time.sleep(interval)
        except telebot.apihelper.ApiTelegramException as e:
            # Si hay un error de edición, detenemos la animación
            break

def start_payment_animation(bot, chat_id, message_id, stop_event):
    """
    Inicia la animación del proceso de pago en un hilo separado.
    
    Args:
        bot: Instancia del bot de Telegram
        chat_id: ID del chat donde mostrar la animación
        message_id: ID del mensaje a animar
        stop_event: Evento para detener la animación
        
    Returns:
        Thread: El hilo de la animación
    """
    animation_thread = Thread(
        target=animate_payment_processing,
        args=(bot, chat_id, message_id, stop_event)
    )
    animation_thread.daemon = True
    animation_thread.start()
    
    return animation_thread