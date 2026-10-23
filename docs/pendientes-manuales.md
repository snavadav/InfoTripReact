# Pendientes manuales (refactorización de robustez)

Tareas que no se pueden automatizar desde el código. Marca cada una al completarla.

## Fase 1

- [ ] **Rotar la contraseña de PostgreSQL.** El `.env` del commit `de86d6d` (luego borrado en `04a1f87`) incluía `DB_PASSWORD`; sigue en el historial de git. Cambia la contraseña del usuario de base de datos y actualiza tu `.env`.
- [ ] **Decidir si limpiar el historial de git.** Si el repositorio `snavadav/InfoTripReact` es público, el `.env` antiguo es visible para cualquiera. Limpiarlo (`git filter-repo`) reescribe el historial y obliga al equipo a volver a clonar; acordarlo antes.
- [ ] **Completar el `.env` local con las variables de PostgreSQL** (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`). Sin ellas, `manage.py` (configuración `dev`) no conecta: el servidor de PostgreSQL de tu equipo exige contraseña. Alternativa sin PostgreSQL: `--settings=infotrip.settings_local`.
- [ ] **Aplicar la migración `usuarios.0003`** con `python manage.py migrate` (y con `--settings=infotrip.settings_local` si usas SQLite). Solo añade la restricción de correo único sin mayúsculas; no modifica datos. Si se detiene por correos duplicados, resolverlos a mano antes de reintentar.
- [ ] **Al desplegar, definir las variables de producción** (`infotrip.settings.prod`):
  - `SECRET_KEY` de 50+ caracteres aleatorios (distinta a la de desarrollo).
  - `ALLOWED_HOSTS` con el dominio público.
  - `NUM_PROXIES=1` y `DETRAS_DE_PROXY_HTTPS=True` si va detrás de nginx o un balanceador.
  - `SECURE_HSTS_SECONDS=3600` al principio; subir a `31536000` cuando todo funcione por HTTPS.
  - `PUBLIC_BASE_URL` con `https://` y el dominio real.
  - Configuración SMTP real (`EMAIL_BACKEND` smtp, `EMAIL_HOST`, credenciales).

## Generales

- [ ] **Mover el proyecto fuera de OneDrive** (por ejemplo a `C:\dev\InfoTrip`). La sincronización de `.venv314`, `.venv`, `db.sqlite3` y las cachés de `uv` puede corromper archivos y ralentizar el equipo. Hacerlo con el editor y los servidores cerrados.
- [ ] **Decidir qué hacer con los entornos virtuales duplicados** (`.venv` y `.venv314`) y las carpetas `.uv-cache` y `.runtime-python` de la carpeta superior. No se borró nada.
