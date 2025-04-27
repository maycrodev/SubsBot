#!/usr/bin/env python
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_render():
    """
    Realiza la configuración inicial para el despliegue en Render.com
    """
    try:
        logger.info("Iniciando configuración de Render...")
        
        # Crear directorios necesarios
        for directory in ['data', 'static', 'templates']:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"Directorio '{directory}' creado")
        
        # Crear archivo terms.txt si no existe
        terms_path = os.path.join('static', 'terms.txt')
        if not os.path.exists(terms_path):
            with open(terms_path, 'w', encoding='utf-8') as f:
                f.write("""📜 *TÉRMINOS DE USO - GRUPO VIP*

Al suscribirte a nuestro servicio, aceptas los siguientes términos y condiciones:

1. *SUSCRIPCIÓN*
   - El acceso al grupo VIP está condicionado al pago de la suscripción.
   - La suscripción se renovará automáticamente hasta que la canceles.
   - Los precios están sujetos a cambios con previo aviso.

2. *ACCESO*
   - Los enlaces de invitación son personales y no transferibles.
   - Cada enlace es válido para un solo uso y expira en 24 horas.
   - Está prohibido compartir o revender los enlaces de acceso.

3. *CONTENIDO*
   - Todo el material disponible en el grupo VIP es exclusivo.
   - Está prohibida la redistribución, copia o descarga masiva de contenido.
   - No nos hacemos responsables por el uso indebido del contenido.

4. *CANCELACIÓN*
   - Puedes cancelar tu suscripción en cualquier momento desde PayPal.
   - No se realizan reembolsos por períodos parciales no utilizados.
   - Al cancelar, perderás acceso inmediato al grupo VIP.

5. *COMPORTAMIENTO*
   - Se espera un comportamiento respetuoso hacia otros miembros.
   - Está prohibido el spam, la publicidad no autorizada y el acoso.
   - El incumplimiento de estas normas puede resultar en expulsión sin reembolso.

6. *LIMITACIÓN DE RESPONSABILIDAD*
   - El servicio se proporciona "tal cual" sin garantías de ningún tipo.
   - No nos hacemos responsables por la disponibilidad continua del servicio.
   - Nos reservamos el derecho de modificar o discontinuar el servicio.

7. *PRIVACIDAD*
   - Tus datos personales serán tratados según nuestra política de privacidad.
   - Solo recopilamos información necesaria para la gestión de suscripciones.

8. *MODIFICACIONES*
   - Estos términos pueden ser actualizados en cualquier momento.
   - Los cambios entrarán en vigor inmediatamente después de su publicación.
   - Es tu responsabilidad revisar periódicamente los términos.

Para cualquier consulta o reclamación, contacta a @admin_support.

Última actualización: Abril 2025""")
            logger.info("Archivo 'terms.txt' creado")
        
        # Asegurar que existe la plantilla HTML
        template_path = os.path.join('templates', 'webhook_success.html')
        if not os.path.exists(template_path):
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write("""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suscripción VIP</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            text-align: center;
        }
        .container {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            padding: 30px;
            max-width: 500px;
            width: 90%;
        }
        h1 {
            color: #2e86de;
            margin-bottom: 20px;
        }
        .message {
            color: #333;
            line-height: 1.6;
            margin-bottom: 25px;
        }
        .success {
            color: #27ae60;
            font-weight: bold;
        }
        .error {
            color: #e74c3c;
            font-weight: bold;
        }
        .button {
            display: inline-block;
            background-color: #2e86de;
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-weight: bold;
            transition: background-color 0.3s;
        }
        .button:hover {
            background-color: #1c71c7;
        }
        .logo {
            margin-bottom: 20px;
            font-size: 48px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🎟️</div>
        <h1>Suscripción VIP</h1>
        <div class="message {% if 'error' in message.lower() %}error{% else %}success{% endif %}">
            {{ message }}
        </div>
        <a href="https://t.me/VIPSubscriptionBot" class="button">Volver a Telegram</a>
    </div>
</body>
</html>""")
            logger.info("Archivo 'webhook_success.html' creado")
        
        logger.info("Configuración de Render completada con éxito")
        return True
    
    except Exception as e:
        logger.error(f"Error en la configuración de Render: {str(e)}")
        return False

if __name__ == "__main__":
    setup_render()