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

## Destinos cerca de ti (Explorar sin búsqueda)

Al entrar a `/destinos/` sin búsqueda ni filtros, arriba de la lista aparece «Destinos cerca de ti» con los 8 destinos más cercanos y su distancia («Tapalpa · 42 km»).

- **Permiso.** Si `navigator.permissions` dice `granted`, se ordena sola al cargar. Si dice `prompt` o el navegador no tiene esa API, no se pide nada al cargar: se ofrece la tarjeta «Ver qué hay cerca de ti». Si dice `denied` o la ubicación falla, se muestra un aviso amable y la lista de siempre. Si la persona da permiso desde otro botón («Mi ubicación», «Cerca de mí»), la sección se ordena sola.
- **Privacidad.** La distancia se calcula en el navegador (`static/js/destinos-cerca.js`, fórmula de haversine, en línea recta) con los puntos que ya recibe el mapa. La ubicación no va al servidor, a la URL, a `localStorage` ni a ningún registro; solo vive en memoria mientras se ordena. La prueba e2e lo comprueba revisando las peticiones y el almacenamiento.
- **Paginación (decisión).** La lista sigue paginada en el servidor de 8 en 8, sin cambios. Ordenar toda la lista por distancia exigiría mandar la ubicación al servidor o cargar todas las tarjetas en el navegador. En cambio, el mapa ya recibe todos los resultados con coordenadas, así que el navegador elige los 8 más cercanos de todo el catálogo y los muestra en una sección propia arriba de la primera página. La lista normal y sus páginas quedan debajo, tal como estaban. El servidor solo decide si ofrecer la sección (`cerca_de_ti`): página 1, formulario válido y sin búsqueda, filtros ni orden.
- **Lo demás.** Al ordenar, el mapa se centra en la persona y en los 5 destinos más cercanos (sin animación con `prefers-reduced-motion`). Las tarjetas nuevas abren el destino en el mapa igual que las de la lista. Si la persona busca o filtra, la página nueva ya no muestra la sección. Los cambios se anuncian con `role="status"` y, al responder la ubicación, el foco pasa al título de la sección.
