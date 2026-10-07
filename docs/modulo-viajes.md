# Mis viajes: planificación y presupuesto

Disponible en `/mis-viajes/`, desde el menú, Mi perfil y el chatbot.

## Alcance

- Crear, consultar, editar, duplicar como nuevo borrador y eliminar escapadas privadas.
- Nombre, destino libre, fechas, 1–100 viajeros y presupuesto total del grupo en MXN.
- Hasta 100 gastos de transporte, comida, entradas, alojamiento u otros.
- Importe unitario, cantidad y reparto individual o compartido.
- Total, reparto igual por persona y diferencia respecto al presupuesto.
- Estimaciones introducidas por el usuario; no importa precios comunitarios ni simula cotizaciones.
- Presupuesto usable sin sesión; guardado y consulta requieren la autenticación existente.
- Aviso antes de descartar cambios. Los borradores no se conservan después de abandonar la página.

El redondeo individual es a centavos; puede quedar una diferencia de centavos al multiplicarlo por todos los viajeros. No se gestionan cobros, reservas ni saldos individuales. La agenda, notas, pendientes y lugares vinculados están documentados en [expansión de comunidad y agenda](expansion-comunidad-agenda.md).

## API

`GET/POST /api/v1/mis-viajes/` y `GET/PATCH/DELETE /api/v1/mis-viajes/<id>/`.

El servidor asigna la autoría a partir de la cuenta autenticada, limita cada consulta al propietario y recalcula los importes usando Decimal. Las escrituras reemplazan la lista completa de gastos. La edición simultánea entre pestañas usa el último guardado.

## Instalación y verificación

Aplicar `python -B manage.py migrate` con la configuración del entorno antes de desplegar. Migración: `comunidad.0002_viaje`. Ya aplicada a SQLite local; PostgreSQL de producción no se verificó.

Pruebas: `python -B manage.py test apps.comunidad apps.destinos apps.usuarios --settings=infotrip.settings_test`.

64 pruebas aprobadas, incluidas siete del módulo: persistencia, aislamiento entre propietarios, rechazo anónimo, importes y fechas inválidos, actualización/eliminación, redondeo y pantalla integrada. Sintaxis JavaScript comprobada con Node. Revisión en navegador en vista estrecha del formulario y de cambios entre gasto compartido y por persona; el guardado autenticado se verificó mediante API en pruebas aisladas.
