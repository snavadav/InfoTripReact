# Módulos 5 a 9: comunidad, perfiles e integración

## Funciones entregadas

| Módulo | Implementación |
|---|---|
| 5. Reseñas y calificaciones | Una reseña vigente por usuario y destino, calificación entera de 1 a 5, fecha de visita, edición y retirada por su autor. Promedio sobre reseñas publicadas de usuarios activos. |
| 6. Fotografías y gastos | Fotografías JPEG/PNG/WebP, máximo 5 MB y 20 megapíxeles; se recodifican a JPEG, se limitan a 2400 px y no se conservan metadatos EXIF. Gastos en MXN por entrada/persona, comida/persona, alojamiento/noche o transporte/persona. Promedios y rangos por concepto durante los últimos 365 días. |
| 7. Moderación | Aportes nuevos y editados pendientes; administrador publica u oculta; reportes sobre contenido público ajeno, uno por usuario/aporte; resolución y desestimación registradas con moderador, fecha y motivo. |
| 8. Perfil y recuperación | Perfil editable con fotografía, ciudad y biografía; listado paginado de aportes propios, edición y retirada; cambio de contraseña y recuperación mediante enlace de una hora y un uso. Cambiar la contraseña invalida access y refresh anteriores. |
| 9. Integración del MVP | Formularios en el detalle, fotos aprobadas en portada y listado, búsqueda por precio y calificación, enlaces de perfil y recuperación, renovación de tokens desde las nuevas pantallas, 57 pruebas y recorrido visual. |

También se completó la administración del catálogo (módulo 2), con modelos registrados en Django Admin y carga idempotente de cinco localidades. Las fuentes están en [catálogo inicial](catalogo-inicial.md).

## Cómo probarlo

1. Abre `/destinos/` y selecciona un destino del catálogo.
2. Registra una cuenta e inicia sesión confirmando el código. Con el backend de consola actual, el código aparece en la terminal; no se envía correo real.
3. En el detalle abre «Compartir mi experiencia» y selecciona reseña, fotografía o gasto.
4. El aporte aparece como pendiente en `/perfil/`. Los visitantes todavía no lo ven.
5. Con un administrador entra a `/admin/comunidad/aporte/`, selecciona el aporte y aplica «Publicar aportes seleccionados».
6. Recarga el detalle: aparecen el aporte y sus datos agregados. Una fotografía aprobada también puede utilizarse en portada y tarjetas.
7. Edita desde el perfil: vuelve a pendiente. «Retirar» lo oculta conservando su registro e historial.
8. Otro usuario puede reportar un aporte público. En `/admin/comunidad/reporte/` se puede resolver ocultando o desestimar. `/admin/comunidad/decision/` conserva las decisiones sin edición ni borrado desde el panel.

El correo confirmado identifica acceso a un buzón, no una visita. La revisión editorial tampoco constituye prueba de visita. No se cargaron reseñas o precios ficticios.

## Administrador

La base local no tenía administrador al terminar la implementación. Créalo eligiendo tu propio correo y contraseña:

```powershell
.\.venv314\Scripts\python.exe -B manage.py createsuperuser --settings=infotrip.settings_local
```

El comando se ejecuta desde `InfoTripReact`. Después abre `/admin/`. No se creó una contraseña de administrador compartida o predeterminada.

Un moderador delegado necesita `es_staff` y permisos de ver/cambiar aportes y reportes, y ver decisiones. No necesita permisos sobre usuarios. Las acciones respetan los permisos del panel; la resolución que oculta contenido también requiere cambiar aportes. El superusuario puede asignar esos permisos desde Usuarios.

## Base de datos y arranque

La migración nueva es `apps/comunidad/migrations/0001_initial.py`. Ya se aplicó en SQLite local. En otra instalación:

```powershell
.\.venv314\Scripts\python.exe -B manage.py migrate --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py cargar_destinos_iniciales --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py runserver --settings=infotrip.settings_local
```

Para PostgreSQL usa la configuración principal y sus variables `DB_*`, omitiendo `--settings=infotrip.settings_local`. No se usó `--fake`: las tablas se crean mediante las migraciones.

## API

| Ruta | Métodos | Acceso |
|---|---|---|
| `/api/v1/destinos/<slug>/aportes/` | GET / POST | Listado público paginado / creación con JWT y correo confirmado |
| `/api/v1/mis-aportes/` | GET | Autor autenticado; incluye pendientes y ocultos, excluye retirados |
| `/api/v1/aportes/<id>/` | GET / PATCH / DELETE | Solo el autor; DELETE retira sin borrar historial |
| `/api/v1/aportes/<id>/reportar/` | POST | Cuenta autenticada distinta del autor |
| `/api/v1/auth/perfil/` | GET / PATCH | Perfil propio |
| `/api/v1/auth/cambiar-password/` | POST | Contraseña actual y nueva confirmada |
| `/api/v1/auth/recuperar/` | POST | Correo; respuesta genérica sin confirmar si existe |
| `/api/v1/auth/restablecer/` | POST | UID, token de recuperación y contraseña nueva confirmada |

Los filtros HTML y API de destinos aceptan `calificacion_min`, `concepto` y `precio_max`. Precio máximo requiere concepto para no comparar, por ejemplo, una entrada con una noche de hotel. Al usar estos filtros se excluyen destinos sin datos publicados relevantes. Los valores vacíos no se propagan como `None` en paginación.

Hay límites de 30 aportes/reportes por hora y usuario, y 5 solicitudes de recuperación/restablecimiento por hora e IP. La recuperación conserva el paso de código por correo al volver a iniciar sesión.

## Verificación y límites operativos

57 pruebas aprobadas:

```powershell
.\.venv314\Scripts\python.exe -B manage.py test apps.destinos apps.usuarios apps.comunidad --settings=infotrip.settings_test
```

Cubren permisos entre usuarios, moderación y auditoría, duplicados, valores y archivos inválidos, visibilidad de imágenes, fechas, promedios por concepto, filtros, carga inicial idempotente, páginas de administración, recuperación caducada/reutilizada y revocación de tokens tras cambio de contraseña. La consulta del catálogo API conserva su presupuesto de cuatro consultas independientemente del número de destinos; la carga de fotos para HTML utiliza una consulta adicional compartida.

En navegador se comprobó: login con código de consola, envío de reseña, perfil, edición, publicación moderada y promedio visible, cierre de sesión, filtros móviles a 390 px sin desbordamiento horizontal. Las cuentas, destinos y aportes temporales se eliminaron; quedaron las cinco localidades iniciales y cero aportes ficticios.

La validación automatizada usa SQLite temporal. No se verificó una instancia PostgreSQL, carga de producción ni entrega real por Gmail. Google Places continúa pendiente. Las fotos de Tequila y Puerto Vallarta son los archivos que ya existían; el resto espera aportes fotográficos.

Para publicar: configurar un dominio HTTPS en `PUBLIC_BASE_URL`, correo SMTP real, `DEBUG=False`, clave secreta segura, `ALLOWED_HOSTS`, PostgreSQL, servidor WSGI/ASGI, estáticos y almacenamiento media con copias de seguridad. No publicar con `settings_local` ni `runserver`. Las cuotas actuales usan la caché de Django: para múltiples procesos se necesita una caché compartida. Los archivos media previamente compartidos pueden conservarse en cachés ajenas aunque su aporte sea ocultado; el panel controla su aparición en InfoTrip. El despliegue y la validación con usuarios reales son pasos posteriores, no realizados en esta entrega.
