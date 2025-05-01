# Este archivo es solo un puntero a app.py para compatibilidad con Render.com
from app import app, bot, verify_all_memberships_on_startup
import bot_handlers
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Asegurar que los handlers y sistemas de seguridad estén inicializados
# Esto garantiza la inicialización incluso si la app se arranca desde main.py
bot_handlers.register_handlers(bot)
verify_all_memberships_on_startup()
logger.info("Bot inicializado y listo para funcionar desde main.py")

# Si este archivo se ejecuta directamente
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)