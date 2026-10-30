# Plan de la refactorización de robustez

Plan acordado el 22/10/2026 a partir de la revisión de arquitectura. Rama: `refactor/robustez` (el PR va contra `master`). Al terminar cada fase se espera confirmación antes de pasar a la siguiente. Las tareas manuales están en [pendientes-manuales.md](pendientes-manuales.md).

## Fase 1: correcciones críticas (recomendaciones 1, 2 y 3). Terminada

- [x] S1: `NUM_PROXIES` configurable y límite por cuenta en el login.
- [x] S2 y S3: correos en minúsculas, `UniqueConstraint(Lower('email'))` y registro con respuesta genérica y límite de solicitudes.
- [x] S4: settings separados (`base`, `dev`, `local`, `test`, `prod`), `DEBUG=False` por defecto, `SECRET_KEY` obligatoria en producción, HSTS y cookies seguras, `asgi.py` completo.
- [x] S7: envío del correo fuera de `transaction.atomic()`.
- [ ] S5 (secretos en el historial): tarea manual, en [pendientes-manuales.md](pendientes-manuales.md).
- [x] S6, primera parte: Content Security Policy con la integración de Django 6 (`SECURE_CSP`). Los scripts en línea pasaron a `static/js/` (`navbar.js`, `registro.js`, `categorias.js`). La migración de los tokens a cookies quedó en la Fase 5.

## Fase 2: red de seguridad (recomendación 9). Terminada

- [x] `pyproject.toml` con ruff y coverage; `requirements-dev.txt`.
- [x] GitHub Actions con PostgreSQL 16 y Redis: pruebas, `makemigrations --check`, `check --deploy` y `pip-audit`.
- [x] Settings de prueba con PostgreSQL y prueba de concurrencia del login.
- [x] `CACHES` con Redis configurable y LocMem de respaldo.
- [ ] Revisar la primera ejecución de la CI en el PR.

## Fase 3: arquitectura (recomendaciones 4, 5 y 6). Terminada

- [x] 4: `apps/comunidad/selectors.py` y `apps/core/` (con `imagenes.py`); sin importaciones dentro de funciones. `destinos` usa `comunidad` solo mediante `selectors` y `models` (lo comprueba `test_dependencias.py`).
- [x] 5: `FiltroDestinos` (django-filter) en `apps/destinos/filtros.py`, compartido por la API y `/destinos/`, con una prueba de que ambas devuelven lo mismo. La validación sigue en cada interfaz para no cambiar los mensajes de error.
- [x] 6: modelos abstractos `Moderable` y `RegistroModeracion`, y `moderacion.moderar()`. Plan aprobado: se mantienen las dos tablas de historial; la migración `comunidad.0004` solo renombra columnas y amplía `motivo`, sin copiar ni borrar datos (lo comprueba `test_moderacion.py`).
- [x] Limpieza: importaciones a mitad de archivo, consultas repetidas en `frontend.py`, el `except Exception` de `LogoutView`, líneas de más de 120 caracteres (E501 en el código de la aplicación) y el JS minificado de `favoritos.js`.

## Fase 4: funcionalidades (recomendaciones 7 y 8). Terminada

- [x] 7: avisos internos al autor al publicar u ocultar su contenido (modelo `Notificacion`, se ven en Mi perfil) y cola de moderación en `/admin/moderacion/` con contadores y enlace en el encabezado del admin. El aviso por correo queda para la Fase 5.
- [x] 8: botón "¿Sigue vigente?" (modelo `Confirmacion`, una por persona y dato; renueva la vigencia sin moderación) y orden `orden=recientes` en la API y en `/destinos/`. El filtro de información reciente cuenta las confirmaciones.

## Fase 5: despliegue, observabilidad y documentación (recomendación 10)

- [x] `Dockerfile` (gunicorn y WhiteNoise) y `docker-compose.yml` (app, PostgreSQL, Redis, nginx y envío de avisos). nginx sirve `media/` desde un volumen compartido. La CI construye la imagen y la prueba de punta a punta.
- [x] `LOGGING` y loggers en fallos de SMTP, decisiones de moderación e intentos de login bloqueados; endpoint `/health/`.
- [x] Aviso por correo al autor cuando se modera su contenido, enviado por el comando `enviar_avisos` fuera de la petición del admin y con registro de fallos.
- [x] OpenAPI con drf-spectacular (`/api/v1/docs/` y `/api/v1/esquema/`) y README actualizado.
- [x] S6, segunda parte: refresh token en una cookie `HttpOnly`, `Secure` en producción y `SameSite=Strict`, con protección CSRF en el refresco y el logout, y access token solo en memoria. El refresh token rota como mucho una vez al día (`apps/usuarios/sesion.py`).

## Cierre

Lista de commits por fase, resultado final de pruebas, cobertura y `check --deploy`, y tareas manuales pendientes.

## Reglas de trabajo

- Un commit por recomendación (o por sub-paso), en español.
- Tras cada cambio: `manage.py test`, `makemigrations --check` y `check`. No avanzar con pruebas en rojo.
- No cambiar comportamiento visible (URLs, respuestas de la API, plantillas) sin avisar antes.
- Preguntar antes de: reescribir el historial o hacer push, migraciones que modifiquen o borren datos, borrar archivos o entornos virtuales, y cualquier cambio que no se revierta con `git revert`.

## Mejoras de producto (revisión de arquitectura, UX y crecimiento)

Rama `mejoras/crecimiento`, salvo 1, 3 y 13, que van en `refactor/robustez`.

- [x] 1: mapa de la portada bloqueado por la CSP.
- [x] 2: aviso de privacidad, términos y baja de cuenta. Falta la revisión legal.
- [x] 3: páginas 404 y 500 en español, y errores legibles.
- [x] 4: reportar datos prácticos, preguntas y respuestas.
- [x] 5: volver a la página tras iniciar sesión y conservar el borrador del viaje.
- [x] 6: SEO base. Falta dar de alta el dominio en Search Console.
- [x] 7: móvil y accesibilidad.
- [x] 8: miniaturas e imágenes más ligeras.
- [ ] 9: contenido. Hecho: 15 destinos con fotos y créditos. Falta: **datos prácticos, que debe aportar el equipo** ([guía](sembrar-contenido.md)).
- [x] 10: registro en un paso y dispositivo recordado.
- [x] 11: compartir fichas y escapadas.
- [x] 12: invitación tras el viaje, novedades en favoritos y baja de correos.
- [x] 13: pruebas de navegador con Playwright en la CI.
- [x] 14: copias de seguridad, monitoreo, límite global y limpieza.
- [x] 15: eventos propios y panel de métricas.
