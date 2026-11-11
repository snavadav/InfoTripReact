# Importar lugares desde OpenStreetMap

Trae lugares turísticos de Jalisco sin registrarlos a mano. Es gratis y no necesita cuenta ni clave.

## Cómo usarlo

Mira primero qué haría, sin guardar nada:

```bash
python manage.py importar_osm --simular
```

Importa de verdad. Tarda un par de minutos:

```bash
python manage.py importar_osm
```

Después entra a `/admin/destinos/destino/`, filtra por **Origen: OpenStreetMap, sin publicar**, marca los lugares que valgan la pena y usa la acción **Publicar destinos seleccionados**.

Los lugares **quedan ocultos** hasta ese paso, porque los datos de OpenStreetMap son irregulares: hay nombres genéricos y lugares mal etiquetados. Conviene publicar pocos y buenos.

## Qué trae y qué no

- **Trae:** nombre, ubicación, municipio y tipo (museos, miradores, cascadas, playas, aguas termales, sitios arqueológicos y atracciones).
- **Casi nunca trae:** descripción, horarios, precios ni fotos. Sin descripción, la ficha usa un texto neutro que invita a aportar. Conviene mejorar el texto antes de publicar.

## Repetirlo

Se puede correr las veces que quieras. Lo ya importado no se modifica, así que tus ediciones se conservan; un lugar que ya ocultaste no vuelve a publicarse solo. Tampoco crea el lugar si ya existe uno con el mismo nombre a menos de 2 km.

Si el servidor está saturado, el comando avisa y no importa nada: reintenta más tarde. El sitio no depende de ese servidor, porque los lugares quedan guardados en tu base.

Para no repetir la descarga mientras pruebas:

```bash
python manage.py importar_osm --guardar osm.json --simular
```

```bash
python manage.py importar_osm --archivo osm.json
```

## Municipios y regiones

Los municipios nuevos se crean en la región "Otras zonas de Jalisco". Puedes asignarles su región real en el admin. Los filtros de `/destinos/` solo muestran categorías, municipios y regiones con destinos publicados.

## Licencia

Los datos de OpenStreetMap tienen licencia [ODbL](https://www.openstreetmap.org/copyright):

- Hay que dar crédito. La ficha de cada lugar importado, `/creditos/` y la API (`atribucion`) ya lo hacen.
- Si se distribuye una base de datos derivada, debe ir bajo la misma licencia. Por eso `Destino.osm_id` identifica lo que viene de OpenStreetMap, y conviene no mezclarlo con lo que aporta la comunidad.

Reglas del servicio: identifica la aplicación (el comando lo hace) y úsalo con moderación. Una importación de vez en cuando está dentro de lo normal. No lo programes en cada visita ni lo ejecutes en paralelo.

## Dónde comer, dormir y servicios

Restaurantes, cafés, bares, hoteles, moteles, hostales, tiendas útiles para viajar, gasolineras, farmacias, cajeros y bancos van en otra tabla, `Lugar`, y **se publican de inmediato**, porque son miles:

```bash
python manage.py importar_lugares --simular
```

```bash
python manage.py importar_lugares
```

- Aparecen en `/destinos/`, con los botones sobre el mapa y **Cerca de mí**, y en la ficha de cada destino, en "Cerca de aquí". No aparecen en la lista de destinos, las misiones ni el pasaporte.
- Repetirlo trae los cambios de OpenStreetMap. Lo que edites en `/admin/destinos/lugar/` queda protegido y no se pisa. Para retirar un lugar, ocúltalo.
- `--retirar-ausentes` oculta lo que ya no aparece en OpenStreetMap. No lo uses si la descarga parece incompleta.
- Pocos lugares traen horario o teléfono: la página los muestra como registrados y pide confirmar antes de ir.

## Lugares propuestos por la comunidad

Las personas proponen lugares en `/lugares/proponer/`. Se revisan en `/admin/moderacion/`, donde se ven los parecidos a menos de 150 m y se puede corregir lo escrito antes de aprobar. Al aprobar se crea el lugar con `osm_id` vacío: así queda separado de lo que viene de OpenStreetMap y la importación nunca lo toca. El municipio se toma de lo publicado más cercano y se puede corregir en el admin.

## Qué tiendas se importan

De las 7,719 tiendas con nombre que había en Jalisco el 30 de octubre de 2026, solo se traen las útiles para quien viaja: conveniencia, supermercados, tiendas variadas y departamentales, centros comerciales, panaderías, pastelerías, dulcerías, licorerías, vinos, bebidas, regalos, artesanías y arte. Se omiten las demás (por ejemplo 1,658 papelerías, ópticas, purificadoras y talleres) y las registradas sin un nombre real, como "Papeleria sin nombre". Para agregar un tipo, súmalo a `TIPO_DE_SUBTIPO` y `Lugar.SUBTIPOS` y a la consulta de `apps/destinos/osm.py`.

## Negocios del DENUE (INEGI)

El [DENUE](https://www.inegi.org.mx/servicios/api_denue.html) agrega muchos negocios y más datos de contacto que OpenStreetMap, sobre todo fuera de las ciudades. Necesita una clave gratuita, en `.env` como `DENUE_TOKEN`:

```bash
python manage.py importar_denue --simular --guardar denue.json
```

```bash
python manage.py importar_denue --archivo denue.json
```

- **Qué trae:** hospedaje, comida, gasolineras, farmacias, bancos, supermercados, departamentales, artesanías y licorerías.
- **Qué omite:** los miles de negocios de otros giros, los nombres genéricos ("Restaurante"), los puestos semifijos y, en la zona metropolitana de Guadalajara, la comida con hasta 5 empleados. Sin ese filtro serían más de 50 mil puntos de comida.
- **Privacidad:** no se importan correos ni razones sociales, que pueden ser datos de una persona.
- **Duplicados:** lo que ya existe de OpenStreetMap o de la comunidad, con nombre parecido a menos de 100 m, no se vuelve a crear.
- **Clave:** va en la dirección de cada consulta, así que el comando nunca la muestra en errores y el sitio no consulta el DENUE durante una visita. El archivo de `--guardar` no la contiene.
- **Licencia:** los [términos de INEGI](https://www.inegi.org.mx/inegi/terminos.html) permiten reutilizar los datos, también con fines comerciales, si se cita la fuente, se avisa de las transformaciones y no se presenta como postura del INEGI. La ficha, la API y `/creditos/` ya lo hacen.

## Mercados públicos (Planeador 2.0)

El planeador propone primero la comida local y clásica: mercados y fondas. Los mercados son el subtipo `marketplace` («Mercado», en el tipo comer) y llegan de dos fuentes. **No se inventa ninguno:** si ninguna fuente lo registra, no aparece.

- **OpenStreetMap:** lo etiquetado `amenity=marketplace` con nombre. Ya va en la consulta normal de `importar_lugares`.
- **DENUE:** el INEGI no registra el mercado como negocio, pero cada puesto dice si está dentro de un «MERCADO PUBLICO» (`tipo_corredor_industrial`) y cómo se llama (`nom_corredor_industrial`). Con los puestos de comida (actividad 722) se arma un lugar por mercado y localidad:
  - el punto es la mediana de sus puestos; los que están a más de 1 km se descartan;
  - la clave es la del primer puesto con una «M» delante (por ejemplo, `M6345678`);
  - al nombre se le antepone «Mercado» si no lo trae («IV Centenario» → «Mercado IV Centenario»). Es una transformación más del nombre, como pasar de mayúsculas a minúsculas, y `/creditos/` ya avisa que los nombres se transforman.

  La importación normal de `importar_denue` también los trae.

Para traer **solo los mercados**, sin repetir toda la descarga ni tocar los demás lugares, en el servidor:

```bash
dc exec web python manage.py importar_lugares --solo-mercados --simular
```

```bash
dc exec web python manage.py importar_lugares --solo-mercados
```

```bash
dc exec web python manage.py importar_denue --solo-mercados --simular --guardar /tmp/denue-comida.json
```

```bash
dc exec web python manage.py importar_denue --solo-mercados --archivo /tmp/denue-comida.json
```

(`dc` es el alias de `docker compose` de [despliegue-aws.md](despliegue-aws.md).) Con `--solo-mercados`, `--retirar-ausentes` solo oculta mercados que ya no aparecen; los demás lugares no se tocan. Lo que ya existe de OpenStreetMap con un nombre parecido a menos de 100 m no se duplica.

### «Recomendado por el equipo»

`Lugar.recomendado_equipo` (falso por omisión) solo lo cambia el equipo o el grupo Moderación en `/admin/destinos/lugar/`, después de conocer el lugar. El planeador lo sube un poco en las opciones de comida y muestra el distintivo «Recomendado por el equipo». Marcarlo protege el lugar de la siguiente importación, como cualquier edición en el admin.
