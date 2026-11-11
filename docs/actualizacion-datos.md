# Datos siempre al día (Módulo D)

Costos, horarios y lugares se actualizan solos, pero **siempre con fuente y nunca sin aprobación humana**. El lema
del proyecto se mantiene: cada dato dice de dónde viene.

| Parte | Qué hace | Dónde |
|---|---|---|
| D1 · Fuentes abiertas | Repite cada mes la importación del DENUE y cada semana la de OpenStreetMap. Agrega lo nuevo, actualiza nombre, dirección y horario, y marca lo que desapareció como *posiblemente cerrado*. | `apps/datos/tareas.py`, `importar_denue`, `importar_lugares` |
| D2 · Sitios oficiales con IA | Revisa cada semana las páginas oficiales de una lista cerrada. Si una cambió, un modelo pequeño de Claude extrae el precio o el horario con su cita textual y deja una **propuesta**. | `apps/datos/lector.py`, `revisar_fuentes_oficiales` |
| Bitácora | Cada corrida queda en **Ejecuciones de tareas** (qué, cuándo, resultado y conteos). | `/admin/datos/ejecuciontarea/` |
| Decisión humana | La cola `/admin/moderacion/` muestra *dato anterior → dato nuevo · ver fuente* y los lugares que ya no aparecen en su fuente. | `apps/comunidad/cola.py` |

## Calendario

El servicio `tareas` de `docker-compose.yml` usa la misma imagen que `web` y `avisos`. Cada hora ejecuta
`python manage.py ejecutar_tareas`, que decide qué toca según la última `EjecucionTarea`:

| Tarea | Frecuencia | Necesita | Sin lo que necesita |
|---|---|---|---|
| `denue` | cada 30 días | `DENUE_TOKEN` | Se salta con un aviso y lo vuelve a intentar al día siguiente |
| `osm` | cada 7 días | nada (Overpass es público) | — |
| `fuentes_oficiales` | cada 7 días; cada fuente, además, según su `frecuencia_dias` (mínimo 7) | `ANTHROPIC_API_KEY` | Se salta con un aviso, sin descargar nada |

Si una tarea falla (Overpass saturado, por ejemplo), se registra como *Error* y se reintenta al día siguiente. Como
el calendario sale de la base de datos, reiniciar el contenedor no repite corridas ni se salta alguna.

Para correr una tarea a mano, aunque no le toque:

```bash
docker compose --env-file .env.docker exec tareas python manage.py ejecutar_tareas --tarea osm
```

## Lugares que desaparecen de su fuente

Un lugar importado que ya no aparece en OpenStreetMap o en el DENUE **no se borra ni se oculta**: puede faltar por
un error de la fuente. Se marca con `posiblemente_cerrado` y `ausente_desde`, y aparece en la cola, en
*Lugares que ya no aparecen en su fuente*. Ahí, quien modera elige una de dos acciones:

- **Ocultar lugares seleccionados**: deja de mostrarse.
- **Sigue abierto**: quita la marca y protege el lugar para que la siguiente importación no lo vuelva a marcar.

Si el lugar reaparece en la fuente, la marca se quita sola. Lo que editó el equipo (`protegido`) nunca se marca ni
se pisa. Un horario que se aprobó desde una fuente oficial tampoco lo pisa el `opening_hours` de OpenStreetMap.

Las opciones `--marcar-ausentes` de `importar_lugares` e `importar_denue` hacen lo mismo cuando se corren a mano.
La opción anterior, `--retirar-ausentes`, todavía oculta sin preguntar; las tareas programadas no la usan.

## Lector de sitios oficiales

Por cada `FuenteOficial` activa que toca revisar:

1. **robots.txt**: se lee con `urllib.robotparser`. Si no permite al agente `InfoTrip`, la fuente queda en
   *robots.txt no lo permite* y no se descarga. Si el sitio bloquea o no responde su robots.txt, tampoco se
   descarga; si no lo tiene (404), sí.
2. **Descarga**: con `User-Agent: InfoTrip/1.0 (+https://infotrip.online)`, 20 s de tiempo máximo, 3 MB como
   máximo y 3 s de pausa entre páginas. Solo HTML o texto: los PDF quedan como *Formato no compatible*. Si una
   redirección lleva a un dominio prohibido, se descarta.
3. **Huella**: SHA-256 del texto visible normalizado, sin scripts ni estilos. Si no cambió, termina **sin llamar a
   la IA**.
4. **IA**: solo se envía el fragmento relevante (±350 caracteres alrededor de cada mención de precio u horario,
   6 000 como máximo). El modelo devuelve JSON con un esquema fijo (`encontrado`, `valor`, `cita`) mediante salida
   estructurada del SDK oficial de Anthropic (`output_config.format`), con esfuerzo `low`. El texto de la página
   se trata como dato, no como instrucciones.
5. **Validación**:
   - La cita debe aparecer **literal** en el texto descargado.
   - Un precio debe ser un monto en pesos entre 0 y 100 000 que aparezca en la cita. El 0 solo se acepta si la
     cita dice "libre", "gratuito" o "sin costo".
   - Un horario debe tener al menos una hora que aparezca en la cita.

   Lo que no pasa queda como *Extracción descartada*.
6. **Propuesta**: se crea una `PropuestaActualizacion` pendiente con el dato actual, el nuevo, la cita, la URL y la
   fecha de consulta. No se repite una propuesta pendiente o rechazada con el mismo dato.

**Aprobar** (acción del admin o desde la cola):

- Un precio actualiza el `monto` y la `fecha_consulta` de la `ReferenciaCosto`.
- Un horario actualiza el `horario` del destino o lugar, con `horario_fuente_url` y `horario_fecha_consulta`.

`cargar_referencias_costo` no deshace un precio aprobado después de la fecha del CSV. Aun así, conviene pasarlo
también al CSV.

**Rechazar** descarta la propuesta sin tocar el dato publicado.

Pueden aprobar los superusuarios y el grupo *Moderación*: `python manage.py crear_moderacion` les da ver y cambiar
propuestas, y solo ver las fuentes y la bitácora.

## Cómo agregar una fuente oficial

1. Confirma que el sitio sea **oficial**: museo, INAH, ayuntamiento, Secretaría de Turismo, Sistema de Información
   Cultural, SCT, SITEUR o similar. La página debe publicar el dato en HTML y su robots.txt debe permitir leerla.
2. En el admin, entra a **Datos siempre al día › Fuentes oficiales › Agregar**:
   - **Nombre**: quién publica, tal como se cita.
   - **URL**: con `https://`.
   - **Tipo de dato**: *Precio* o *Horario*.
   - **Destino o lugar**: uno de los dos.
   - **Referencia**: la `ReferenciaCosto` que se actualizará. Obligatoria en los precios.
   - **Frecuencia**: en días, como mínimo 7.
3. Para las fuentes que ya cita `apps/destinos/datos/referencias_costo.csv` no hace falta capturar nada: basta con
   ejecutar este comando, que se puede repetir sin duplicar.

   ```bash
   python manage.py sembrar_fuentes_oficiales
   ```

   Los PDF (como las tarifas de CAPUFE) quedan inactivos porque se revisan a mano.

La acción **Revisar en la próxima corrida** olvida la huella para forzar una lectura completa.

## Cómo apagarlo

| Para | Haz esto |
|---|---|
| Apagar todo | `TAREAS_PROGRAMADAS=` (vacío) en `.env.docker` y `docker compose up -d tareas`, o `docker compose stop tareas` |
| Apagar una tarea | Deja solo las demás: `TAREAS_PROGRAMADAS=osm,fuentes_oficiales` |
| Apagar la IA | Deja vacía `ANTHROPIC_API_KEY` (la tarea se salta) o desactiva las fuentes en el admin |
| Dejar de revisar una página | Desmarca **Activo** en esa fuente |

## Variables

Van vacías y comentadas en `.env.docker.example`, `.env.docker.aws.example` y `.env.example`.

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `TAREAS_PROGRAMADAS` | `denue,osm,fuentes_oficiales` | Tareas que corre el servicio. Vacía: ninguna |
| `DENUE_TOKEN` | vacío | Clave gratuita del INEGI. Va en la URL de cada consulta, así que nunca se registra |
| `ANTHROPIC_API_KEY` | vacío | Clave de la API de Claude. Se pasa al cliente del SDK; nunca está en el código ni en los registros |
| `IA_MODELO` | `claude-haiku-5-5` | Modelo de Claude para la extracción |

Los mensajes de error de las tareas registran solo el tipo de error, sin URLs del DENUE ni cabeceras. La página de
errores de Django oculta las variables que contienen `KEY` o `TOKEN`.

## Costo estimado

Precios vigentes de Claude Haiku 5.5 según la guía de la API de Claude (consultada el 10/11/2026): **US$0.10 por
millón de tokens de entrada y US$0.50 por millón de salida**, para solicitudes de hasta 100 000 tokens.

| Concepto | Por llamada |
|---|---|
| Entrada: fragmento de hasta 6 000 caracteres más las instrucciones | ≈ 2 000 tokens → US$0.0002 |
| Salida: JSON más el razonamiento breve del esfuerzo `low`, con un tope de 2 048 | ≤ 2 048 tokens → ≤ US$0.001 |
| **Total** | **≤ US$0.0012** (≈ 2 centavos de peso) |

Con 36 fuentes activas, si **todas** cambiaran **cada semana**, serían unas 157 llamadas al mes: **menos de
US$0.20 al mes**. En la práctica las páginas oficiales cambian pocas veces al año. Como sin cambio de huella no hay
llamada, el costo real es de centavos. La descarga, robots.txt y la huella no tienen costo.

## Por qué no Google, TripAdvisor, Facebook ni Booking

- **Términos de uso**: Google Maps, TripAdvisor, Facebook, Instagram, Booking y Airbnb prohíben la extracción
  automatizada. Usarlos expondría al proyecto a bloqueos y reclamaciones, y no se podría defender ante el comité.
- **No son la fuente**: un precio en TripAdvisor o en Google lo copió alguien más y no dice de dónde sale. El
  precio oficial lo publica el museo, el INAH o el ayuntamiento.
- **Reseñas y datos personales**: esos sitios están hechos de opiniones y perfiles de personas. InfoTrip nunca
  copia reseñas, comentarios ni datos personales de otros sitios. Las reseñas de InfoTrip las escriben sus
  usuarios, con moderación.

Por eso esos dominios se rechazan en código (`apps/datos/models.py`, `DOMINIOS_PROHIBIDOS`): al guardar una fuente,
al sembrarla, antes de descargarla y después de cada redirección. Las fuentes abiertas (DENUE del INEGI y
OpenStreetMap) sí permiten reutilizar sus datos si se cita la fuente, y `/creditos/` lo hace.
