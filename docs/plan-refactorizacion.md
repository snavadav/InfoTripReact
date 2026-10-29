# Plan de la refactorización de robustez

Plan acordado el 22/10/2026 a partir de la revisión de arquitectura. Rama: `refactor/robustez` (el PR va contra `master`). Al terminar cada fase se espera confirmación antes de pasar a la siguiente. Las tareas manuales están en [pendientes-manuales.md](pendientes-manuales.md).

## Fase 1: correcciones críticas (recomendaciones 1, 2 y 3). Terminada

- [x] S1: `NUM_PROXIES` configurable y límite por cuenta en el login.
- [x] S2 y S3: correos en minúsculas, `UniqueConstraint(Lower('email'))` y registro con respuesta genérica y límite de solicitudes.
- [x] S4: settings separados (`base`, `dev`, `local`, `test`, `prod`), `DEBUG=False` por defecto, `SECRET_KEY` obligatoria en producción, HSTS y cookies seguras, `asgi.py` completo.
- [x] S7: envío del correo fuera de `transaction.atomic()`.
- [ ] S5 (secretos en el historial) y S6 (tokens en `localStorage` y sin CSP): S5 es manual; S6 no entró en ninguna fase.

## Fase 2: red de seguridad (recomendación 9). Terminada

- [x] `pyproject.toml` con ruff y coverage; `requirements-dev.txt`.
- [x] GitHub Actions con PostgreSQL 16 y Redis: pruebas, `makemigrations --check`, `check --deploy` y `pip-audit`.
- [x] Settings de prueba con PostgreSQL y prueba de concurrencia del login.
- [x] `CACHES` con Redis configurable y LocMem de respaldo.
- [ ] Revisar la primera ejecución de la CI en el PR.

## Fase 3: arquitectura (recomendaciones 4, 5 y 6)

- [ ] 4: crear `apps/comunidad/selectors.py` y `apps/core/` (mover `imagenes.py`); eliminar las importaciones dentro de funciones entre `destinos` y `comunidad`.
- [ ] 5: una sola fuente de verdad para los filtros de destinos (django-filter) compartida por la API y la vista HTML, con una prueba de que ambas devuelven lo mismo.
- [ ] 6: modelo abstracto `Moderable` y función única `moderar()`. La migración de datos conserva todo el historial de `Decision` y `RevisionColaboracion`; mostrar el plan de migración antes de aplicarla.
- [ ] Limpieza: importaciones a mitad de archivo (quitar sus excepciones de ruff), consultas repetidas en `frontend.py`, el `except Exception` de `LogoutView`, líneas de más de 120 caracteres y el JS minificado de `favoritos.js`.

## Fase 4: funcionalidades (recomendaciones 7 y 8)

- [ ] 7: notificar al autor cuando cambie el estado de su aporte o colaboración, y cola de moderación con contadores para staff.
- [ ] 8: botón "¿Sigue vigente?" y orden o filtro por frescura del dato.

## Fase 5: despliegue, observabilidad y documentación (recomendación 10)

- [ ] `Dockerfile` (gunicorn y WhiteNoise) y `docker-compose.yml` (app, PostgreSQL y Redis); plan para servir `media/`.
- [ ] `LOGGING` y loggers en fallos de SMTP, decisiones de moderación e intentos de login bloqueados; endpoint `/health/`.
- [ ] OpenAPI con drf-spectacular y README actualizado.

## Cierre

Lista de commits por fase, resultado final de pruebas, cobertura y `check --deploy`, y tareas manuales pendientes.

## Reglas de trabajo

- Un commit por recomendación (o por sub-paso), en español.
- Tras cada cambio: `manage.py test`, `makemigrations --check` y `check`. No avanzar con pruebas en rojo.
- No cambiar comportamiento visible (URLs, respuestas de la API, plantillas) sin avisar antes.
- Preguntar antes de: reescribir el historial o hacer push, migraciones que modifiquen o borren datos, borrar archivos o entornos virtuales, y cualquier cambio que no se revierta con `git revert`.
