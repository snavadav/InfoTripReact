# Inicio de sesión con código por correo

## Flujo

1. Registro crea una cuenta sin JWT y dirige a `/login/?registro=1`.
2. `POST /api/v1/auth/login/` recibe `email` y `password`. Si son correctos envía un código de seis dígitos y devuelve `desafio`, `expira_en: 600` y `reenviar_en: 60`. No entrega tokens.
3. `POST /api/v1/auth/verificar-codigo/` recibe `desafio` y `codigo` como cadenas. Solo al acertar entrega `access`, `refresh` y `usuario`, marca `es_verificado` y actualiza `ultimo_acceso`.
4. Reenviar usa nuevamente login con las credenciales. Hay que esperar 60 segundos; el nuevo desafío sustituye al anterior. El navegador conserva las credenciales solo en memoria mientras está abierto ese paso.

Se requiere un código en cada inicio de sesión, incluso en cuentas verificadas, salvo que la persona marque "Recordar este dispositivo": entonces basta la contraseña durante 30 días en ese navegador. Cambiar la contraseña o el correo anula el recuerdo. Confirma el control del buzón en ese momento, no la identidad legal ni la autenticidad de las reseñas. Django Admin conserva su inicio de sesión de personal independiente.

## Probar ahora, sin correo real

Se preparó `.env` local con el backend `django.core.mail.backends.console.EmailBackend`. El remitente `infotrip.pruebas@gmail.com` es un ejemplo, no una cuenta creada ni verificada.

```powershell
.\.venv314\Scripts\python.exe -B manage.py migrate --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py runserver --settings=infotrip.settings_local
```

Registrarse o usar una cuenta local, iniciar sesión y leer el código en la terminal. La interfaz indica claramente el modo de prueba. No se entrega correo y esto no comprueba la existencia de un buzón real. No usar este backend en producción.

## Activar Gmail real

1. Usa una cuenta Gmail propia y activa la verificación en dos pasos de Google.
2. Genera una contraseña de aplicación si la cuenta permite esa opción. No uses la contraseña habitual ni compartas la contraseña en el chat.
3. Edita `.env` local:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=tu-cuenta-real@gmail.com
EMAIL_HOST_PASSWORD=tu-contraseña-de-aplicación
DEFAULT_FROM_EMAIL=InfoTrip <tu-cuenta-real@gmail.com>
```

4. Reinicia el servidor y prueba con un destinatario que controles. Mantén `.env` fuera de Git; `.env.example` contiene solo ejemplos.

Ayuda oficial: https://support.google.com/mail/answer/185833?hl=es

## Controles y despliegue

- Código aleatorio criptográfico; en base de datos se almacena un HMAC, nunca el código en claro.
- Caduca en diez minutos, cinco intentos válidamente formados, un solo uso. Un reenvío invalida el anterior.
- Cambiar contraseña/correo o desactivar la cuenta invalida un desafío pendiente.
- Bloqueo transaccional del usuario en PostgreSQL para serializar envíos y verificación. Las pruebas locales usan SQLite; no equivalen a una prueba de concurrencia PostgreSQL.
- Límite por IP de 10 solicitudes/minuto para login y 30/minuto para códigos. Para varios procesos, configurar una caché compartida de Django (por ejemplo Redis) y controles de tráfico en el proxy; la caché local por defecto no comparte estos límites.
- El código no se devuelve en la API. Fallos SMTP devuelven 503 sin emitir tokens y revierten el nuevo desafío.
- Se rechazan JWT antiguos sin la marca `correo_confirmado`, incluido su refresh: las sesiones anteriores deben iniciar sesión de nuevo. Se mantiene el refresh para sesiones que ya completaron el código.
- La migración `usuarios/0002_codigoacceso.py` debe aplicarse también en PostgreSQL antes de desplegar.
- No se ha probado la entrega real por Gmail; faltan la cuenta remitente y su contraseña de aplicación.

## Pruebas

```powershell
.\.venv314\Scripts\python.exe -B manage.py test apps.usuarios apps.destinos --settings=infotrip.settings_test
```

Las pruebas de correo usan el backend en memoria; no envían mensajes externos.
