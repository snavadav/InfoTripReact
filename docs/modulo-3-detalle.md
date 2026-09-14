# Módulo 3: detalle del destino y portada compacta

- `/`: buscador y hasta tres tarjetas; se retiran de la portada las secciones extensas de categorías, reseñas, promociones y el pie anterior.
- `/destinos/?q=...`: búsqueda por nombre, descripción o municipio, filtro opcional `categoria` por slug y páginas de ocho destinos.
- `/destinos/<slug>/`: descripción, ubicación, categorías, servicios y enlace Cómo llegar a Google Maps. Solo muestra destinos activos.

Las vistas públicas están en `apps/destinos/frontend.py`. No hay cambios de esquema ni migraciones adicionales.

En una base completamente vacía, las páginas utilizan dos fichas de inspiración: Tequila y Puerto Vallarta, con las fotografías locales existentes. Están marcadas como inspiración y no aparecen como registros de la API. En cuanto existe cualquier destino en la base, las páginas utilizan exclusivamente el catálogo; un destino desactivado nunca reaparece como inspiración.

Las fotos locales se asocian por slug a esos dos lugares. Otros destinos muestran un estado sin fotografía. La subida y galería comunitaria corresponden al módulo de fotografías. Los precios, reseñas y calificaciones siguen pendientes de sus módulos; no se presentan cifras inventadas. Google Maps recibe coordenadas del catálogo; para las fichas de inspiración recibe el nombre del lugar.

La selección de inicio toma hasta tres destinos al azar entre los primeros doce activos por nombre. El listado completo permite consultar el resto.

## Verificación

```powershell
.\.venv314\Scripts\python.exe -B manage.py test apps.destinos apps.usuarios --settings=infotrip.settings_test
```

30 pruebas aprobadas. Se verificó manualmente el recorrido inicio → búsqueda → detalle y el enlace generado de Google Maps. La portada con las dos fichas actuales cabe sin scroll en 1280×720 y 390×844; pantallas más pequeñas, mayor tamaño de texto o más contenido pueden requerir desplazamiento natural.

Servidor local:

```powershell
.\.venv314\Scripts\python.exe -B manage.py runserver --settings=infotrip.settings_local
```

## Actualización: inicio interactivo

La portada ahora utiliza una selección interactiva de hasta doce destinos activos, con filtros por categorías, tarjetas seleccionables, flechas, selección aleatoria y panel de fotografía/mapa. La búsqueda superior sigue consultando el catálogo completo en su página de resultados. Si la base está vacía se mantienen las dos fichas editoriales.

El mapa integrado de Google se carga únicamente al elegir Mapa y se sincroniza con el destino seleccionado. Permite desplazamiento y zoom sin configurar una clave en el proyecto; requiere conexión al servicio externo. Cómo llegar permanece disponible para abrir Google Maps en otra pestaña. No se solicita ubicación GPS al visitante.

En móvil las tarjetas se recorren horizontalmente; el panel y la descripción quedan debajo. La altura se adapta al contenido y puede requerir desplazamiento vertical, sin recuperar las secciones extensas de la portada original. Con JavaScript desactivado se muestran enlaces de tarjetas como alternativa.

Verificación actual: 32 pruebas aprobadas; mapa cargado, filtros y selección sincronizados comprobados en navegador, revisión móvil sin desbordamiento horizontal. No requiere migraciones.
