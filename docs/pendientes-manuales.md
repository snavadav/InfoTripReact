# Pendientes manuales (refactorización de robustez)

Tareas que no se pueden automatizar desde el código. Marca cada una al completarla.

## Fase 1

- [ ] **Rotar la contraseña de PostgreSQL.** El `.env` del commit `de86d6d` (luego borrado en `04a1f87`) incluía `DB_PASSWORD`; sigue en el historial de git. Cambia la contraseña del usuario de base de datos y actualiza tu `.env`.
  - Comprobado el 22/10/2026: la contraseña filtrada (usuario `postgres`, puerto 5433) es distinta a la actual del servidor local en el puerto 5432. Solo hay riesgo si esa contraseña sigue usándose en otro servidor o equipo del equipo de trabajo.
- [ ] **Cambiar la contraseña del superusuario `postgres`.** Se compartió en texto plano en la conversación con el asistente. No está en el `.env` ni en git: la aplicación usa el rol `infotrip_user`, así que cambiarla no afecta a InfoTrip.
- [x] **Decidir si limpiar el historial de git.** Si el repositorio `snavadav/InfoTripReact` es público, el `.env` antiguo es visible para cualquiera. Limpiarlo (`git filter-repo`) reescribe el historial y obliga al equipo a volver a clonar; acordarlo antes.
  - Hecho el 29/10/2026: `.env` eliminado de los 39 commits y la `SECRET_KEY` filtrada reemplazada; push forzado de `master` y `refactor/robustez` (`main` no lo contenía). La `DB_PASSWORD` filtrada era la palabra `postgres`.
- [ ] **Pedir a GitHub Support que purgue los commits antiguos.** GitHub sigue sirviendo el commit `de86d6d` por su identificador. Formulario "Remove sensitive data" en support.github.com; indicar el repositorio y ese commit.
- [ ] **Avisar al equipo que vuelva a clonar** el repositorio y borre sus copias antiguas. Un push desde una copia vieja volvería a subir el `.env`.
- [ ] **Borrar el respaldo** `C:\Users\Sergi\infotrip-respaldo-git\` cuando todo esté comprobado: contiene el historial original con los secretos.
- [x] **Completar el `.env` local con las variables de PostgreSQL** (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`). Sin ellas, `manage.py` (configuración `dev`) no conecta: el servidor de PostgreSQL de tu equipo exige contraseña. Alternativa sin PostgreSQL: `--settings=infotrip.settings_local`.
  - Hecho el 22/10/2026: rol `infotrip_user` (contraseña aleatoria, permiso `CREATEDB`) dueño de la base `infotrip` en el puerto 5432; variables `DB_*` añadidas al `.env`. Todas las migraciones aplicadas.
- [x] **Aplicar la migración `usuarios.0003`** con `python manage.py migrate` (y con `--settings=infotrip.settings_local` si usas SQLite). Solo añade la restricción de correo único sin mayúsculas; no modifica datos. Si se detiene por correos duplicados, resolverlos a mano antes de reintentar.
- [ ] **Al desplegar, definir las variables de producción** (`infotrip.settings.prod`):
  - `SECRET_KEY` de 50+ caracteres aleatorios (distinta a la de desarrollo).
  - `ALLOWED_HOSTS` con el dominio público.
  - `NUM_PROXIES=1` y `DETRAS_DE_PROXY_HTTPS=True` si va detrás de nginx o un balanceador.
  - `SECURE_HSTS_SECONDS=3600` al principio; subir a `31536000` cuando todo funcione por HTTPS.
  - `PUBLIC_BASE_URL` con `https://` y el dominio real.
  - Configuración SMTP real (`EMAIL_BACKEND` smtp, `EMAIL_HOST`, credenciales).
  - `REDIS_URL`: producción no arranca sin ella.
  - Sin Docker, programar `python manage.py enviar_avisos` cada pocos minutos. Con Docker lo hace el servicio `avisos`.
  - HTTPS: terminar TLS en nginx o en el balanceador; `docker/nginx.conf` solo escucha HTTP. Con `.env.docker` real, quitar `SECURE_SSL_REDIRECT=False` y `SECURE_HSTS_SECONDS=0`, y definir `DETRAS_DE_PROXY_HTTPS=True`. Si el TLS termina en un balanceador delante de nginx, seguir el comentario de `docker/nginx.conf`; de lo contrario, el refresco de sesión y el logout responderán 403.
  - `/media/`: el volumen `media` guarda las fotos de los usuarios; incluirlo en las copias de seguridad junto con la base de datos.

## Fase 2

- [x] **Actualizar tu entorno virtual** con las versiones nuevas: `uv pip install --python .venv314/Scripts/python.exe -r requirements-dev.txt` (Django 6.0.9, DRF 3.18.3, simplejwt 5.5.1, redis y herramientas de desarrollo).
- [x] **Aplicar `token_blacklist.0013`** (de simplejwt 5.5.1) con `python manage.py migrate`. Solo cambia opciones `Meta`; no modifica datos.
- [x] **Decidir sobre Pillow 13.0.0.** Corrige 35 vulnerabilidades de Pillow 12.3.0, pero salió el 16/10/2026 y es versión mayor. Hasta actualizar, el paso `pip-audit` de la CI fallará.
  - Hecho el 29/10/2026: actualizado a 13.0.0. Las 93 pruebas pasan en PostgreSQL; `pip-audit` y ruff sin hallazgos.
- [ ] **Al hacer push, revisar la primera ejecución de la CI**: es la primera vez que las pruebas corren con Redis (no hay Redis local para comprobarlo).
- [x] **Decidir si quitar del repositorio los 10 `.pyc` versionados** en `apps/usuarios/__pycache__/` (se subieron antes de que `.gitignore` los excluyera). Sería `git rm --cached`; los archivos locales no se borran.
  - Hecho el 29/10/2026 con `git rm --cached`.
- [x] Opcional: para correr las pruebas de concurrencia en local, `python manage.py test --settings=infotrip.settings.test_postgres` con `DB_*` de un usuario con permiso `CREATEDB`.

## Mejoras de producto

- [ ] **Revisar con alguien de derecho el aviso de privacidad y los términos** (`templates/legal/`). Son un borrador, marcado así en la página.
- [ ] **Definir `CONTACTO_PRIVACIDAD`** con un correo real. Sin él, el aviso no muestra cómo contactar al equipo.

## Generales

- [ ] **Mover el proyecto fuera de OneDrive** (por ejemplo a `C:\dev\InfoTrip`). La sincronización de `.venv314`, `.venv`, `db.sqlite3` y las cachés de `uv` puede corromper archivos y ralentizar el equipo. Hacerlo con el editor y los servidores cerrados.
- [ ] **Decidir qué hacer con los entornos virtuales duplicados** (`.venv` y `.venv314`) y las carpetas `.uv-cache` y `.runtime-python` de la carpeta superior. No se borró nada.
