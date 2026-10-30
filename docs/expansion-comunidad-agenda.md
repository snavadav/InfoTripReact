# Fichas prácticas, comunidad, favoritos y agenda

## Pantallas

- `/destinos/<slug>/`: información práctica, fuentes, fecha de consulta, versiones anteriores, correcciones, preguntas y respuestas. Los campos sin aportes publicados muestran «Sin confirmar».
- `/favoritos/`: favoritos privados; quitar un lugar, abrir su ficha, iniciar una nueva escapada o agregarlo a una ya guardada. La lista de viajes carga por páginas.
- `/mis-viajes/`: lugares vinculados, actividades por día y horario, notas y pendientes. Se guardan junto con el presupuesto. Las actividades usan días relativos: día 1 equivale a la fecha de salida. Cambiar las fechas no puede dejar actividades fuera del viaje.
- `/destinos/`: el filtro «Con información práctica consultada en los últimos 90 días» permite priorizar fichas con una corrección comunitaria reciente. Cada dato práctico indica si su consulta fue hace 30 días o menos, entre 31 y 90 días, o hace más de 90 días. Son señales orientativas, no garantías de vigencia; confirma directamente con la fuente.
- El menú y Mi perfil tienen accesos a favoritos. Desde la ficha se puede prellenar una nueva escapada con el nombre del destino; para vincular el registro de catálogo, agregarlo desde favoritos a un viaje guardado.

## Información y moderación

Horarios, acceso, estacionamiento, pago, restricciones, accesibilidad, contacto y precios adicionales son texto aportado por usuarios. No son cotizaciones ni certificaciones. Cada corrección exige fuente y fecha no futura.

Preguntas, respuestas y correcciones nuevas siempre quedan pendientes. En `/admin/comunidad/colaboracion/`, seleccionar registros y usar Publicar u Ocultar. Se necesita permiso de cambio sobre Colaboracion. El contenido original es de solo lectura y cada cambio de estado registra moderador, fecha y motivo en RevisionColaboracion, sin edición ni eliminación desde administración.

El valor mostrado es el aporte publicado con fecha de consulta más reciente; los anteriores permanecen en el historial público mientras estén publicados. Ocultar el dato actual vuelve a mostrar el anterior o «Sin confirmar». Se excluyen aportes de autores inactivos. Ocultar una pregunta oculta también sus respuestas de la ficha. Publicar una respuesta no publica su pregunta automáticamente.

## Privacidad y límites

Los favoritos y viajes solo son accesibles por su propietario. Guardar un favorito o vincular un lugar repetidamente no duplica registros. Los destinos inactivos no admiten nuevas vinculaciones, pero sus favoritos pueden quitarse y los viajes que ya los contienen pueden conservarlos.

Hasta 100 lugares por viaje, 150 actividades y 100 pendientes. La edición usa el último guardado; no hay sincronización en tiempo real entre pestañas. Los borradores no sobreviven al abandono de la página. Las nuevas contribuciones comparten el límite de 30 envíos por hora y usuario existente.

Estas funciones no usan una API de Google ni una API de IA. No se añadieron precios, horarios o testimonios ficticios.

## API

- `GET/POST /api/v1/destinos/<slug>/colaboraciones/`
- `GET /api/v1/favoritos/`
- `GET/PUT/DELETE /api/v1/favoritos/<slug>/`
- `POST /api/v1/mis-viajes/<id>/lugares/` con `slug` (vinculación privada sin reemplazar el resto del viaje).
- La API de viajes acepta actividades, pendientes, notas y lugares; devuelve lugares_detalle para su presentación.

## Instalación y pruebas

Migración `comunidad.0003_viaje_actividades_viaje_lugares_viaje_notas_and_more` aplicada a SQLite local. Aplicar `python -B manage.py migrate` con la configuración de cada entorno antes de desplegar. No se comprobó PostgreSQL de producción.

75 pruebas aprobadas con `python -B manage.py test apps.comunidad apps.destinos apps.usuarios --settings=infotrip.settings_test`, incluidas 11 nuevas pruebas de moderación, historial, validación, privacidad, vinculaciones y agenda. JavaScript verificado con `node --check`. Revisión visual en navegador de información desconocida, corrección, control de acceso a favoritos, destino prellenado, actividad y pendiente completado. Los flujos autenticados de persistencia se verificaron mediante API en pruebas aisladas.
