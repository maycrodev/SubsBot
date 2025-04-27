# Este archivo es solo un puntero a app.py para compatibilidad con Render.com
from app import app

# Si este archivo se ejecuta directamente
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)