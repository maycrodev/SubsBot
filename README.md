# Bot de Suscripciones VIP para Telegram

Bot para gestionar suscripciones de pago a un grupo VIP en Telegram, con soporte para diferentes planes, pagos a través de PayPal, y gestión automática de acceso.

## Características

- Sistema de suscripciones con planes personalizables
- Integración con PayPal para pagos recurrentes
- Gestión automática de enlaces de invitación únicos
- Sistema de seguridad para expulsar usuarios con suscripciones expiradas
- Panel de administración web
- Soporte para subscripciones gratuitas mediante whitelist
- Notificaciones automáticas

## Configuración de Planes de Pago

Los planes de pago se configuran en el archivo `config.py`. El sistema utiliza la estructura de `PLANS` para definir los diferentes niveles de suscripción disponibles.

### Estructura de un plan

```python
'plan_id': {
    'name': 'Nombre del Plan',
    'price_usd': 9.99,
    'duration_days': 30,
    'display_name': '𝙉𝙊𝙈𝘽𝙍𝙀 𝘿𝙀𝙇 𝙋𝙇𝘼𝙉',
    'description': 'Descripción del plan'
}
```

### Parámetros requeridos

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | String | Nombre interno del plan |
| `price_usd` | Float | Precio en dólares (USD) |
| `duration_days` | Integer | Duración del plan en días |
| `display_name` | String | Nombre que se muestra al usuario |
| `description` | String | Descripción breve del plan |

### Ejemplo de configuración

Para añadir un nuevo plan (por ejemplo, un plan trimestral), añade lo siguiente al diccionario `PLANS` en `config.py`:

```python
PLANS = {
    'weekly': {
        'name': 'Plan Semanal',
        'price_usd': 3.50,
        'duration_days': 7,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙎𝙀𝙈𝘼𝙉𝘼𝙇',
        'description': 'Acceso: 1 semana al grupo VIP'
    },
    'monthly': {
        'name': 'Plan Mensual',
        'price_usd': 5.00,
        'duration_days': 30,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙈𝙀𝙉𝙎𝙐𝘼𝙇',
        'description': 'Acceso: 1 mes al grupo VIP'
    },
    # Nuevo plan trimestral
    'quarterly': {
        'name': 'Plan Trimestral',
        'price_usd': 12.00,
        'duration_days': 90,
        'display_name': '𝙎𝙐𝙎𝘾𝙍𝙄𝙋𝘾𝙄Ó𝙉 𝙏𝙍𝙄𝙈𝙀𝙎𝙏𝙍𝘼𝙇',
        'description': 'Acceso: 3 meses al grupo VIP con descuento'
    }
}
```

### Notas importantes sobre los planes

1. **ID del plan**: Debe ser único y simple (letras minúsculas, sin espacios).
2. **Duración**: Se especifica en días exactos.
3. **Formato de precio**: Utiliza punto decimal, no coma (ej: `9.99`).
4. **Después de añadir un plan**: Debes actualizar la interfaz de usuario para incluirlo en las opciones mostradas a los usuarios.

## Comandos de Administrador

Los siguientes comandos están disponibles solo para usuarios configurados como administradores (`ADMIN_IDS` en `config.py`).

### Estadísticas y Monitoreo

#### `/stats` o `/estadisticas`

Muestra estadísticas generales sobre el bot.

**Uso**: Envía `/stats` al bot

**Información mostrada**:
- Total de usuarios registrados
- Total de suscripciones y activas
- Número de suscripciones nuevas en las últimas 24 horas
- Enlaces de invitación generados
- Estadísticas de seguridad
- Enlaces al panel de administración

---

#### `/subinfo [USER_ID]`

Muestra información detallada sobre la suscripción de un usuario específico.

**Uso**: `/subinfo 1234567890`

**Ejemplo de respuesta**:
```
👤 ID: 1234567890
🧑 Nombre: Juan Pérez (@juanperez)
📊 Estado: 🟢 ACTIVE

📥 Plan: Plan Mensual
🗓️ Inicio: 01 May 2025
⏳ Expira: 31 May 2025

💳 Pagos: PayPal
Subscription ID: I-XXXXXXXXXX
```

---

### Gestión de Permisos y Seguridad

#### `/check_permissions`

Verifica que el bot tenga los permisos necesarios en el grupo VIP.

**Uso**: Envía `/check_permissions` al bot

**Permisos verificados**:
- Estado de administrador en el grupo
- Permiso para expulsar usuarios
- Permiso para invitar usuarios

---

#### `/force_security_check`

Fuerza una verificación inmediata de todas las suscripciones y expulsa a los usuarios con suscripciones expiradas.

**Uso**: Envía `/force_security_check` al bot

**Proceso**:
1. Verifica todas las suscripciones en la base de datos
2. Identifica las expiradas
3. Expulsa automáticamente a los usuarios correspondientes
4. Envía notificación sobre el resultado

---

### Gestión de Usuarios

#### `/whitelist [USER_ID]`

Añade un usuario a la whitelist, otorgándole acceso gratuito al grupo VIP por un tiempo determinado.

**Uso**: `/whitelist 1234567890`

**Proceso**:
1. Introduce el ID del usuario
2. El bot te pedirá especificar la duración del acceso
3. Responde con un formato como: `1 week`, `30 days`, `2 months`
4. Se generará un enlace de invitación para el usuario
5. El usuario será notificado automáticamente

---

#### `/whitelist list`

Muestra la lista de todos los usuarios en whitelist.

**Uso**: Envía `/whitelist list` al bot

**Información mostrada**:
- Nombre y username de cada usuario
- ID de usuario
- Tiempo restante de acceso

---

### Pruebas y Diagnóstico

#### `/test_invite`

Genera un enlace de invitación de prueba para verificar que el sistema funciona correctamente.

**Uso**: Envía `/test_invite` al bot

**Notas**:
- El enlace generado es temporal (expira en 1 hora)
- Es de un solo uso
- No se registra en la base de datos
- Solo sirve para verificación

---

## Panel de Administración Web

Además de los comandos de Telegram, hay un panel de administración web disponible en:

```
https://[WEBHOOK_URL]/admin/panel?admin_id=[TU_ID_DE_ADMIN]
```

### Funciones disponibles en el panel web:

1. **Panel principal**: Estadísticas en tiempo real
2. **Verificación de seguridad**: `/admin/force-security-check` - Fuerza verificación inmediata
3. **Estado del sistema**: `/admin/check-security-thread` - Verifica el funcionamiento del hilo de seguridad
4. **Suscripciones expiradas**: `/admin/expired-subscriptions` - Listado de suscripciones expiradas
5. **Diagnóstico PayPal**: `/admin/paypal-diagnostic` - Verifica conexión con PayPal
6. **Base de datos**: `/admin/database` - Ejecuta consultas personalizadas
7. **Respaldo**: `/admin/download-database` - Descarga copia de la base de datos

## Notas importantes

- Los enlaces de invitación generados son únicos, tienen un límite de tiempo y solo pueden usarse una vez.
- El sistema de seguridad verificará periódicamente las suscripciones expiradas y expulsará automáticamente a los usuarios.
- Para cambiar a producción en PayPal, modifica `PAYPAL_MODE` a `'live'` en el archivo `.env`.
- Siempre asegúrate de que el bot sea administrador del grupo con permisos para expulsar usuarios.
- Puedes monitorear la actividad del sistema consultando los logs.