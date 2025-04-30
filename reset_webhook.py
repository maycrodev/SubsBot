#!/usr/bin/env python
"""
Script para corregir problemas con los comandos de administrador en el bot de Telegram.
Este script debe ejecutarse en el directorio raíz del proyecto.
"""
import os
import re

def fix_app_py():
    """Corrige problemas en app.py"""
    print("Corrigiendo app.py...")
    
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Fix: Importar verify_bot_permissions correctamente
    updated_content = content.replace(
        "verify_bot_permissions() and bot.reply_to(update.message, \"✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles.\")",
        "bot_handlers.verify_bot_permissions(bot) and bot.reply_to(update.message, \"✅ Verificación de permisos del bot completada. Revisa los mensajes privados para detalles.\")"
    )
    
    # Guardar cambios
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print("✅ app.py corregido")

def fix_bot_handlers():
    """Corrige problemas en bot_handlers.py"""
    print("Corrigiendo bot_handlers.py...")
    
    with open('bot_handlers.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Fix: Mover verify_bot_permissions() a bot_handlers.py
    # Buscamos la función en app.py
    with open('app.py', 'r', encoding='utf-8') as f:
        app_content = f.read()
    
    verify_bot_func_pattern = re.compile(r'def verify_bot_permissions\(\):(.*?)(?=\ndef|\Z)', re.DOTALL)
    match = verify_bot_func_pattern.search(app_content)
    
    if match:
        verify_bot_func = match.group(0)
        # Modificar para que acepte un parámetro bot
        verify_bot_func = verify_bot_func.replace(
            "def verify_bot_permissions():",
            "def verify_bot_permissions(bot):"
        )
        
        # Agregar la función al final de bot_handlers.py
        if "def verify_bot_permissions(bot):" not in content:
            content += "\n\n" + verify_bot_func
    
    # 2. Fix: Corregir manejo de comando /whitelist
    whitelist_handler_pattern = re.compile(r'def handle_whitelist\(message, bot\):(.*?)(?=\ndef|\Z)', re.DOTALL)
    match = whitelist_handler_pattern.search(content)
    
    if match:
        whitelist_handler = match.group(0)
        # Modificar para manejar correctamente cuando no se proporciona un ID de usuario
        updated_handler = whitelist_handler.replace(
            "if len(command_parts) < 2:",
            "if len(command_parts) < 2:\n"
            "        # Mostrar instrucciones de uso\n"
            "        bot.send_message(\n"
            "            chat_id=chat_id,\n"
            "            text=\"❌ Uso incorrecto. Por favor, usa /whitelist USER_ID\\n\\nEjemplo: /whitelist 1234567890\"\n"
            "        )\n"
            "        return"
        )
        
        content = content.replace(whitelist_handler, updated_handler)
    
    # 3. Fix: Corregir manejo de comando /subinfo
    subinfo_handler_pattern = re.compile(r'def handle_subinfo\(message, bot\):(.*?)(?=\ndef|\Z)', re.DOTALL)
    match = subinfo_handler_pattern.search(content)
    
    if match:
        subinfo_handler = match.group(0)
        # Modificar para manejar correctamente cuando no se proporciona un ID de usuario
        updated_handler = subinfo_handler.replace(
            "if len(command_parts) < 2:",
            "if len(command_parts) < 2:\n"
            "        # Mostrar instrucciones de uso\n"
            "        bot.send_message(\n"
            "            chat_id=chat_id,\n"
            "            text=\"❌ Uso incorrecto. Por favor, usa /subinfo USER_ID\\n\\nEjemplo: /subinfo 1234567890\"\n"
            "        )\n"
            "        return"
        )
        
        content = content.replace(subinfo_handler, updated_handler)
    
    # 4. Fix: Asegurar que register_admin_commands se llame
    if "register_admin_commands" in content and "register_admin_commands(bot)" not in content:
        # Encuentra la función register_handlers
        register_handlers_pattern = re.compile(r'def register_handlers\(bot\):(.*?)(?=\ndef|\Z)', re.DOTALL)
        match = register_handlers_pattern.search(content)
        
        if match:
            register_handlers_func = match.group(0)
            updated_func = register_handlers_func.replace(
                "def register_handlers(bot):",
                "def register_handlers(bot):\n"
                "    # Registrar comandos de administrador\n"
                "    register_admin_commands(bot)"
            )
            
            content = content.replace(register_handlers_func, updated_func)
    
    # 5. Fix: Corregir registro de comandos /check_permissions y /stats
    check_permissions_pattern = re.compile(r'bot\.register_message_handler\(\s*lambda message: verify_bot_permissions\(\) and bot\.reply_to.*?check_permissions.*?\)', re.DOTALL)
    
    if check_permissions_pattern.search(content):
        old_handler = check_permissions_pattern.search(content).group(0)
        new_handler = old_handler.replace(
            "verify_bot_permissions()",
            "verify_bot_permissions(bot)"
        )
        content = content.replace(old_handler, new_handler)
    
    # 6. Fix: Asegurar que handle_stats_command se maneje correctamente
    stats_handler_pattern = re.compile(r'bot\.register_message_handler\(\s*lambda message: handle_stats_command.*?\)', re.DOTALL)
    
    if stats_handler_pattern.search(content):
        # El patrón ya existe, no hacemos cambios
        pass
    else:
        # Asegurarnos de que existe la función handle_stats_command
        if "def handle_stats_command(message, bot):" in content:
            # Añadir el handler en register_handlers
            register_handlers_func = register_handlers_pattern.search(content).group(0)
            updated_func = register_handlers_func.replace(
                "schedule_security_verification(bot)",
                "schedule_security_verification(bot)\n\n"
                "    # Handler para estadísticas\n"
                "    bot.register_message_handler(\n"
                "        lambda message: handle_stats_command(message, bot),\n"
                "        func=lambda message: message.from_user.id in ADMIN_IDS and message.text in ['/stats', '/estadisticas']\n"
                "    )"
            )
            content = content.replace(register_handlers_func, updated_func)
    
    # Guardar cambios
    with open('bot_handlers.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ bot_handlers.py corregido")

def create_verify_bot_command():
    """Crea un nuevo script para verificar la configuración del bot"""
    print("Creando script de verificación...")
    
    script_content = """#!/usr/bin/env python
'''
Script para verificar y diagnosticar la configuración del bot.
Ejecutar este script para identificar problemas con los comandos de administrador.
'''
import sys
import os
import logging
import telebot
from config import BOT_TOKEN, ADMIN_IDS

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_admin_commands():
    '''Verifica la configuración de comandos administrativos'''
    try:
        # Verificar que existe el token
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN no está configurado")
            return False
        
        # Verificar administradores
        if not ADMIN_IDS:
            logger.error("❌ No hay administradores configurados en ADMIN_IDS")
            return False
        
        logger.info(f"ℹ️ Administradores configurados: {ADMIN_IDS}")
        
        # Importar bot_handlers para verificar funciones
        try:
            import bot_handlers
            logger.info("✅ Módulo bot_handlers importado correctamente")
            
            # Verificar funciones de administrador
            admin_functions = [
                'handle_stats_command',
                'handle_test_invite',
                'handle_whitelist',
                'handle_subinfo',
                'handle_verify_all_members',
                'verify_bot_permissions'
            ]
            
            for func_name in admin_functions:
                if hasattr(bot_handlers, func_name):
                    logger.info(f"✅ Función {func_name} encontrada")
                else:
                    logger.error(f"❌ Función {func_name} NO encontrada")
            
        except ImportError as e:
            logger.error(f"❌ Error al importar bot_handlers: {str(e)}")
            return False
        
        # Crear un bot de prueba
        try:
            bot = telebot.TeleBot(BOT_TOKEN)
            me = bot.get_me()
            logger.info(f"✅ Bot conectado: @{me.username} (ID: {me.id})")
        except Exception as e:
            logger.error(f"❌ Error al conectar con el bot: {str(e)}")
            return False
        
        logger.info("✅ Verificación completada. Todo parece estar correcto.")
        
        # Instrucciones para el usuario
        print("\\n" + "-"*50)
        print("INSTRUCCIONES PARA COMANDOS DE ADMINISTRADOR:")
        print("-"*50)
        print("1. Usa los comandos con el formato correcto:")
        print("   /whitelist USER_ID - Añade un usuario a la whitelist")
        print("   /subinfo USER_ID - Muestra información de suscripción de un usuario")
        print("   /stats - Muestra estadísticas del bot")
        print("   /check_permissions - Verifica permisos del bot en el grupo")
        print("   /test_invite - Prueba la generación de enlaces de invitación")
        print("   /verify_all - Verifica todos los miembros del grupo")
        print("\\n2. Asegúrate de ejecutar estos comandos desde un chat privado con el bot")
        print("   o desde el grupo si estás usando comandos específicos del grupo.")
        print("-"*50)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error durante la verificación: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔍 Iniciando verificación de comandos de administrador...")
    verify_admin_commands()
"""
    
    with open('verify_commands.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Hacer ejecutable
    os.chmod('verify_commands.py', 0o755)
    
    print("✅ Script de verificación creado: verify_commands.py")

def main():
    """Función principal"""
    print("🔧 Iniciando arreglo de comandos de administrador...\n")
    
    # Corregir archivos
    fix_app_py()
    fix_bot_handlers()
    create_verify_bot_command()
    
    print("\n✅ Correcciones completadas.")
    print("Para verificar la configuración, ejecuta: python verify_commands.py")
    print("Para reiniciar el bot, ejecuta: python main.py")

if __name__ == "__main__":
    main()