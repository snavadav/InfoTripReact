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
