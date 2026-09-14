# Módulo 4: exploración y mapa

Disponible en `/destinos/`, desde el buscador de inicio o «Ver todos».

- Búsqueda por nombre, descripción o municipio; filtros combinables de categoría, municipio, región y servicio.
- Validación de filtros, errores visibles, limpieza y paginación de ocho resultados conservando la selección.
- Mapa con Leaflet 1.9.4 y teselas de OpenStreetMap, cargado al pulsar «Ver mapa». Marcadores de los resultados de la página, ventanas con enlace al detalle, controles de zoom, encuadre y botones «Ubicar».
- Ubicación opcional, solicitada únicamente con el botón correspondiente, con indicador de precisión y manejo de rechazo, indisponibilidad y tiempo de espera. No se persiste ni se envía a Django. Al centrar el mapa, el proveedor de teselas recibe las solicitudes del área visible. La ubicación no modifica los filtros.
- Alternativa manual: buscar por municipio o usar filtros. No se consulta un geocodificador ni Google Places.
- Búsqueda y fichas disponibles sin JavaScript. Ante fallo del proveedor del mapa se conservan los enlaces de detalle.

La base local está vacía de destinos. Las dos fichas editoriales permanecen como inspiración y no tienen marcadores: no se inventaron coordenadas. Los destinos activos con coordenadas de la base se representan automáticamente. Los filtros de precio y calificación esperan a sus respectivos módulos.

No necesita claves, tarjeta ni migraciones. El mapa requiere conexión externa para Leaflet y OpenStreetMap. Se conserva la atribución, sin precarga ni descarga masiva de teselas. Antes de un despliegue con tráfico significativo revisar el proveedor y su política de uso:
https://operations.osmfoundation.org/policies/tiles/
https://leafletjs.com/examples/quick-start/

## Comprobación

36 pruebas aprobadas con:

```powershell
.\.venv314\Scripts\python.exe -B manage.py test apps.destinos apps.usuarios --settings=infotrip.settings_test
```

Incluyen filtros combinados, paginación, parámetros inválidos, exclusión de destinos inactivos, escape del JSON y fichas editoriales sin coordenadas inventadas. Se verificó visualmente la carga del mapa, el encuadre de un marcador y su ventana con enlace al detalle usando un destino temporal, eliminado después. No se solicitó ubicación real al usuario durante la verificación.

El servidor local utiliza:

```powershell
.\.venv314\Scripts\python.exe -B manage.py runserver --settings=infotrip.settings_local
```
