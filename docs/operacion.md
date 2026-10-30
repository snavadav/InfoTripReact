# Operación

Tareas para mantener InfoTrip en marcha cuando corre con `docker-compose.yml`.

## Copias de seguridad

El servicio `respaldos` guarda cada día en el volumen `respaldos`:

- `db-AAAA-MM-DD-HHMM.dump`: la base de datos.
- `media-AAAA-MM-DD-HHMM.tar.gz`: las fotos subidas.

Conserva 14 días. **Ese volumen está en el mismo servidor que los datos:** si se pierde el servidor, se pierden también las copias. Cópialas a otro lugar con regularidad, y nunca uses `docker compose down --volumes` en producción, porque borra la base, las fotos y las copias.

Listar las copias:

```bash
docker compose --env-file .env.docker exec respaldos ls -lh /respaldos
```

### Restaurar

Detén la aplicación para que nadie escriba mientras restauras:

```bash
docker compose --env-file .env.docker stop web avisos nginx
```

Restaura la base. Sustituye la fecha por la de la copia que quieras:

```bash
docker compose --env-file .env.docker exec respaldos sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /respaldos/db-AAAA-MM-DD-HHMM.dump'
```

Restaura las fotos:

```bash
docker compose --env-file .env.docker run --rm --no-deps --user root --entrypoint sh -v infotripreact_respaldos:/respaldos web -c 'tar -xzf /respaldos/media-AAAA-MM-DD-HHMM.tar.gz -C /app/media'
```

Vuelve a arrancar:

```bash
docker compose --env-file .env.docker start web avisos nginx
```

El nombre `infotripreact_respaldos` depende de la carpeta del proyecto; compruébalo con `docker volume ls`.

## Monitoreo de errores

Define `SENTRY_DSN` para enviar los errores del servidor a un servicio compatible con Sentry. Sin esa variable, no se envía nada. [GlitchTip](https://glitchtip.com/) es una opción gratuita si lo alojas tú; Sentry tiene un plan gratuito limitado. No se envían datos personales (`send_default_pii=False`).

Para saber si el sitio está en pie, apunta un monitor a `/health/`: responde 200 si la base de datos y la caché funcionan, y 503 si no.

## Registros

Todo va a la salida estándar:

```bash
docker compose --env-file .env.docker logs -f web avisos respaldos
```

Conviene vigilar `infotrip.correo` (correos fallidos), `infotrip.seguridad` (cuentas bloqueadas) e `infotrip.salud` (base de datos, caché y Redis).

## Miniaturas

Las fotos nuevas crean su miniatura al subirse. Para las anteriores, ejecuta una vez `python manage.py generar_miniaturas`.

## Métricas

`/admin/metricas/` (personal) muestra los eventos de los últimos 7 y 30 días, los embudos de activación, contribución y referencia, la retención a 30 días y el porcentaje de fichas con al menos 3 datos prácticos. Para el tráfico desde buscadores usa [Google Search Console](https://search.google.com/search-console), que es gratis: registra el dominio y envía `/sitemap.xml`.

## Tareas periódicas

El servicio `avisos` envía los avisos por correo cada 5 minutos y borra una vez al día los tokens caducados (`flushexpiredtokens`) y los eventos de más de 13 meses (`purgar_eventos`). Sin Docker, programa esos mismos comandos.
