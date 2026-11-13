# Operación

Tareas para mantener InfoTrip en marcha cuando corre con `docker-compose.yml`.

## Copias de seguridad

El servicio `respaldos` guarda cada día en el volumen `respaldos`:

- `db-AAAA-MM-DD-HHMM.dump`: la base de datos.
- `media-AAAA-MM-DD-HHMM.tar.gz`: las fotos subidas.

Conserva 14 días. **Ese volumen está en el mismo servidor que los datos:** si se pierde el servidor, se pierden también las copias. Por eso conviene activar la copia en S3 (abajo). Nunca uses `docker compose down --volumes` en producción, porque borra la base, las fotos y las copias.

Listar las copias:

```bash
docker compose --env-file .env.docker exec respaldos ls -lh /respaldos
```

Hacer un respaldo ahora mismo, por ejemplo antes de una actualización delicada. Termina con error si algo falla:

```bash
docker compose --env-file .env.docker exec respaldos sh /respaldo.sh --una-vez
```

### Copia fuera del servidor (S3)

Si `RESPALDO_S3_BUCKET` tiene valor en `.env.docker`, cada respaldo diario se sube también a ese bucket:

| Carpeta en el bucket | Cuándo se sube | Se borra a los | Copias que quedan |
|---|---|---|---|
| `infotrip/diarias/AAAA-MM-DD-HHMM/` | todos los días | 7 días | 7 |
| `infotrip/semanales/AAAA-MM-DD-HHMM/` | los domingos (hora UTC) | 28 días | 4 |

- **Borrado automático:** lo hacen las reglas de ciclo de vida del bucket, no el servidor. El rol del servidor
  puede subir y leer, pero no borrar: si alguien toma el servidor, no puede borrar las copias que ya están en S3.
- **Credenciales:** el cliente de AWS las toma del rol de IAM asignado a la instancia, así que en el servidor no
  se guarda ninguna llave.
- **Si la subida falla:** la copia local queda igual. El registro de `respaldos` dice
  `ERROR: no se pudo subir a S3`, y al día siguiente se vuelve a intentar.
- **Si la variable está vacía:** todo funciona como antes, solo con la copia local.

La configuración en la consola de AWS (bucket, reglas, rol y su asignación a la instancia) está en el
[paso 10 de despliegue-aws.md](despliegue-aws.md#paso-10-respaldos-en-s3).

Comprobar que el servidor llega al bucket. Cambia `NOMBRE-DEL-BUCKET` por el tuyo:

```bash
docker compose --env-file .env.docker exec respaldos aws sts get-caller-identity
```

```bash
docker compose --env-file .env.docker exec respaldos aws s3 ls --recursive --human-readable s3://NOMBRE-DEL-BUCKET/infotrip/
```

El primer comando debe mostrar el rol `infotrip-ec2-respaldos`. Si dice `Unable to locate credentials`, revisa que
el rol esté asignado y que el límite de saltos de los metadatos sea 2 (paso 10.5 de la guía).

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

El nombre `infotripreact_respaldos` depende de la carpeta del proyecto; compruébalo con `docker volume ls`. En el
servidor de AWS es `infotrip_respaldos`.

### Restaurar desde S3

Sirve si se perdió el servidor, o si la copia que buscas ya no está en el volumen local.

1. **Prepara el servidor nuevo.** Sigue [despliegue-aws.md](despliegue-aws.md) del paso 2 al 5. Asígnale el mismo
   rol y el límite de saltos 2, como en los pasos 10.4 y 10.5.
2. **Deja la subida apagada mientras restauras.** En `.env.docker`, deja `RESPALDO_S3_BUCKET=` vacío por ahora.
   El servicio respalda en cuanto arranca, y así no sube a S3 una copia de la base vacía.
3. **Arranca:**

   ```bash
   dc up -d --build
   ```

4. **Elige la copia.** Lista las disponibles; cambia `NOMBRE-DEL-BUCKET`:

   ```bash
   dc exec respaldos aws s3 ls --region us-east-2 s3://NOMBRE-DEL-BUCKET/infotrip/diarias/
   ```

   Usa `semanales/` en lugar de `diarias/` si necesitas algo de hace más de una semana.
5. **Baja la copia al volumen de respaldos.** Cambia el nombre del bucket y la fecha:

   ```bash
   dc exec respaldos aws s3 cp --recursive --region us-east-2 s3://NOMBRE-DEL-BUCKET/infotrip/diarias/AAAA-MM-DD-HHMM/ /respaldos/
   ```

6. **Restaura** con los pasos de [Restaurar](#restaurar). Cambia `docker compose --env-file .env.docker` por `dc`,
   y el volumen por `infotrip_respaldos`.
7. **Vuelve a encender la subida.** Pon el nombre del bucket en `RESPALDO_S3_BUCKET` y aplica el cambio:

   ```bash
   dc up -d respaldos
   ```

`dc` es el atajo del [paso 7 de despliegue-aws.md](despliegue-aws.md#paso-7-arrancar-y-restaurar).

## Monitoreo de errores

Define `SENTRY_DSN` en `.env.docker` para enviar los errores del servidor a Sentry; sin esa variable no se envía nada. Crear la cuenta gratuita y poner el DSN: [paso 11 de despliegue-aws.md](despliegue-aws.md#paso-11-avisos-de-errores-con-sentry). [GlitchTip](https://glitchtip.com/) es compatible, por si prefieren alojarlo ustedes.

**No se envían datos personales.** `infotrip/monitoreo.py` configura Sentry así, y `infotrip/test_monitoreo.py` lo comprueba con una petición real que falla:

| Dato | Qué se hace |
|---|---|
| IP, cookies, cabeceras de sesión, usuario y valores de las consultas SQL | No se envían (`send_default_pii=False`). |
| Cuerpo de la petición: ubicaciones, reseñas o contraseñas | No se envía. |
| Variables locales de cada línea del error | No se envían. |
| Consulta de la URL, como el `?t=` del enlace de baja de avisos | Se quita; queda solo la ruta. |
| Correos dentro del mensaje de error, de los registros o de las migas de pan | Se cambian por `[oculto]`. |
| Rendimiento (trazas) | Apagado: solo se envían errores. |

Lo que sí llega: el tipo de error, el mensaje (sin correos), la ruta, las líneas de código, la versión y el navegador
(`User-Agent`). Si agregas código que guarda datos personales en un mensaje de error, tápalos también en
`limpiar_evento`.

## Disponibilidad

`/health/` responde 200 con `{"estado": "ok", …}` si la base de datos y la caché funcionan, y 503 con el componente que falla si no.

En el servidor de AWS hay dos vigilantes que avisan por correo. Cómo crearlos:
[paso 12 de despliegue-aws.md](despliegue-aws.md#paso-12-avisos-si-el-sitio-se-cae).

- **UptimeRobot** revisa `https://infotrip.online/health/` cada 5 minutos desde fuera de AWS.
- **CloudWatch** tiene tres alarmas:
  - `infotrip-hardware`: falla el equipo físico de AWS; recupera la instancia sola.
  - `infotrip-sistema`: falla el sistema de la instancia; la reinicia.
  - `infotrip-cpu`: CPU arriba de 80 % durante 15 minutos; solo avisa.

Si llega un aviso de caída:

1. Abre `https://infotrip.online/health/` y mira qué componente dice `error`.
2. Entra al servidor y revisa `dc ps`: todos los servicios deben decir `running` o `healthy`.
3. Busca la causa con `dc logs --tail 100 web nginx caddy`.
4. Si el servidor no responde por SSH, reinícialo desde *EC2 → Instances → Reboot instance*.

## Registros

Todo va a la salida estándar:

```bash
docker compose --env-file .env.docker logs -f web avisos respaldos
```

Conviene vigilar `infotrip.correo` (correos fallidos), `infotrip.seguridad` (cuentas bloqueadas) e `infotrip.salud` (base de datos, caché y Redis).

### Tiempos de respuesta

Cada línea de acceso de `web` termina con la duración de la petición en microsegundos (`gunicorn.conf.py`). Para ver las 20 peticiones más lentas del último día, con su ruta:

```bash
docker compose --env-file .env.docker logs --since 24h --no-log-prefix web | awk '$NF ~ /^[0-9]+$/ {print $NF/1000 " ms", $6, $7}' | sort -rn | head -20
```

Cada proceso de gunicorn se renueva tras unas 1000 peticiones y reutiliza su conexión a PostgreSQL durante `CONN_MAX_AGE` segundos (60 por defecto; `CONN_MAX_AGE=0` en `.env.docker` vuelve a una conexión por petición).

## Miniaturas

Las fotos nuevas crean su miniatura al subirse. Para las anteriores, ejecuta una vez `python manage.py generar_miniaturas`.

## Métricas

`/admin/metricas/` (personal) muestra los eventos de los últimos 7 y 30 días, los embudos de activación, contribución y referencia, la retención a 30 días, el porcentaje de fichas con al menos 3 datos prácticos, las 10 fichas más vistas y cada evento comparado con los 30 días anteriores. El inicio del admin (`/admin/`) abre con «Estado del sitio»: cuánto hay en la cola y desde cuándo espera lo más antiguo, los avisos por correo fallidos de la semana y la última corrida de cada tarea programada. Desde `/admin/moderacion/` se publica u oculta en un clic; al ocultar se elige un motivo de una lista cerrada, que es lo que recibe quien lo envió. Para el tráfico desde buscadores usa [Google Search Console](https://search.google.com/search-console), que es gratis: registra el dominio y envía `/sitemap.xml`.

## Tareas periódicas

El servicio `avisos` envía los avisos por correo cada 5 minutos y borra una vez al día los tokens caducados (`flushexpiredtokens`) y los eventos de más de 13 meses (`purgar_eventos`). Sin Docker, programa esos mismos comandos.

El mismo servicio intenta cada hora `resumen_moderacion`: un correo al día, a partir de las 8:00, con los totales de la cola de moderación y los fallos de tareas o correos de las últimas 24 horas. Lo reciben las cuentas activas del grupo Moderación y los superusuarios; si no hay nada pendiente, no se envía. Para probarlo: `docker compose --env-file .env.docker exec web python manage.py resumen_moderacion --forzar`.
