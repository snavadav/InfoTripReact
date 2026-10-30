# InfoTrip

Plataforma web colaborativa para la gestión de información turística y validación de experiencias de viaje en Jalisco, México.

![Django](https://img.shields.io/badge/Django-6.0.9-092E20?style=flat&logo=django)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat&logo=postgresql)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat&logo=python)

---

## ¿Qué es InfoTrip?

InfoTrip reúne información turística aportada por viajeros y revisada antes de publicarse. Se pueden consultar destinos, gastos reportados, reseñas y cómo llegar, sin publicidad ni contenido patrocinado. La revisión no acredita una visita: conviene confirmar con el lugar antes de viajar.

---

## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Django 6.0 + Django REST Framework |
| Base de datos | PostgreSQL 16 |
| Caché y límites de intentos | Redis (en producción) |
| Autenticación | Simple JWT con código de verificación por correo |
| Frontend | Plantillas de Django, CSS y JavaScript sin frameworks |
| Despliegue | Docker: gunicorn, WhiteNoise y nginx |
| Documentación de la API | OpenAPI con drf-spectacular |
| Calidad | ruff, coverage, pip-audit y GitHub Actions |

---

## Requisitos previos

Antes de instalar el proyecto necesitas tener:

- **Python 3.14+** — [python.org](https://www.python.org/downloads/)
- **PostgreSQL 16** — servidor y pgAdmin, desde [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
- **DBeaver** — [dbeaver.io](https://dbeaver.io/download/)
- **Git** — [git-scm.com](https://git-scm.com/)

---

## Instalación

Hay dos caminos: [con Docker](#docker), que levanta todo con un comando, o la instalación manual de esta sección, más cómoda para desarrollar.

### 1. Clonar el repositorio

```bash
git clone https://github.com/snavadav/InfoTripReact.git
cd InfoTripReact
```

### 2. Instalar dependencias

```bash
python -m pip install -r requirements-dev.txt
```

### 3. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto con este contenido:

```-
SECRET_KEY=django-insecure-cambia-esta-clave
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=infotrip
DB_USER=infotrip_user
DB_PASSWORD=la_contraseña_que_elegiste_para_infotrip_user
DB_HOST=127.0.0.1
DB_PORT=5432
```

> ⚠️ Nunca subas el `.env` a GitHub — ya está en el `.gitignore`

### 4. Instalar e iniciar PostgreSQL (Windows)

1. Descarga el instalador oficial de PostgreSQL para Windows desde el enlace de requisitos. Durante la instalación conserva el puerto `5432`, instala pgAdmin y define una contraseña para el usuario administrador `postgres`. Guarda esa contraseña: Django la necesita.
2. Al terminar, abre **Servicios** de Windows y confirma que el servicio `postgresql-x64-16` esté en estado **En ejecución**. El nombre puede variar si instalaste otra versión. También puedes abrir **SQL Shell (psql)** desde Inicio; con servidor `localhost`, puerto `5432`, base `postgres` y usuario `postgres`, debe conectarse.
3. Abre **SQL Shell (psql)** o pgAdmin y conéctate como `postgres`. En psql ejecuta:

```sql
CREATE USER infotrip_user WITH PASSWORD 'elige_una_contraseña_local';
CREATE DATABASE infotrip OWNER infotrip_user;
```

En pgAdmin puedes abrir **Query Tool** sobre la base `postgres` y ejecutar las mismas sentencias. Usa una contraseña propia y evita reutilizar la del usuario `postgres`.

### 5. Configurar Django

En el `.env` de la raíz, establece los datos de la base recién creada:

```dotenv
DB_NAME=infotrip
DB_USER=infotrip_user
DB_PASSWORD=la_misma_contraseña_que_elegiste_arriba
DB_HOST=127.0.0.1
DB_PORT=5432
```

No subas `.env` a Git. El `.env.example` incluye la plantilla sin credenciales.

### 6. Crear las tablas y datos iniciales

Desde PowerShell en la raíz del repositorio, ejecuta:

```powershell
.\.venv314\Scripts\python.exe -B manage.py migrate
.\.venv314\Scripts\python.exe -B manage.py cargar_destinos_iniciales
```

Si usas otro entorno virtual, reemplaza la ruta al ejecutable de Python. La carga de destinos es opcional e idempotente.

### 7. Crear superusuario

```powershell
.\.venv314\Scripts\python.exe -B manage.py createsuperuser
```

Te pedirá:
-Email
-Nombre
-Apellido
-Contraseña

### 8. Correr el servidor

```powershell
.\.venv314\Scripts\python.exe -B manage.py runserver
```

---

## Docker

Levanta la aplicación completa: nginx, gunicorn con Django, PostgreSQL 16, Redis y el envío de avisos por correo. Solo necesitas [Docker Desktop](https://www.docker.com/products/docker-desktop/) abierto.

```bash
cp .env.docker.example .env.docker
```

Edita `.env.docker` y cambia los valores marcados con `CAMBIAR`. Después:

```bash
docker compose --env-file .env.docker up --build
```

La aplicación queda en http://localhost:8080. Si ese puerto está ocupado, cambia `INFOTRIP_PUERTO` en `.env.docker`. Las migraciones se aplican solas al arrancar.

Para crear un administrador, con la pila levantada:

```bash
docker compose --env-file .env.docker exec web python manage.py createsuperuser
```

Para apagarla (agrega `--volumes` si también quieres borrar la base de datos y las fotos):

```bash
docker compose --env-file .env.docker down
```

**Cómo se reparten el trabajo:** nginx sirve las fotos subidas (`/media/`) desde un volumen compartido y reenvía el resto a gunicorn. WhiteNoise sirve los archivos estáticos desde la aplicación. El servicio `avisos` ejecuta `enviar_avisos` cada 5 minutos.

`.env.docker.example` está pensado para probar en tu equipo, sin HTTPS. Antes de publicar, revisa la lista de producción en [pendientes manuales](docs/pendientes-manuales.md).

---

## 🌐 URLs disponibles

### Páginas

| Ruta | Descripción |
|---|---|
| `/` | Página principal |
| `/destinos/` | Exploración con filtros y mapa |
| `/destinos/<slug>/` | Ficha del destino: datos prácticos, aportes y preguntas |
| `/login/`, `/registro/`, `/recuperar/` | Acceso a la cuenta |
| `/perfil/` | Datos personales, avisos de moderación y aportes propios |
| `/favoritos/`, `/mis-viajes/` | Lugares guardados y planes de viaje |
| `/admin/` | Administración del catálogo, usuarios y moderación |
| `/admin/moderacion/` | Cola de moderación con contadores (personal) |
| `/admin/metricas/` | Embudos, retención y fichas útiles (personal) |
| `/escapadas/<id>/` | Escapada compartida, de solo lectura y sin cuenta |
| `/costos/`, `/destinos/<slug>/costos/` | ¿Cuánto cuesta ir?: gastos reales, con un mínimo de 3 reportes por concepto |
| `/privacidad/`, `/terminos/`, `/creditos/` | Avisos legales y créditos de fotografías |
| `/baja-avisos/` | Dejar de recibir correos de novedades, desde el enlace de cada correo |

### API

La referencia completa e interactiva está en `/api/v1/docs/` (Swagger) y el esquema OpenAPI en `/api/v1/esquema/`. Para probar rutas protegidas desde Swagger, usa **Authorize** con el token `access`.

| Módulo | Ruta | Métodos |
|---|---|---|
| Cuenta | `/api/v1/auth/registro/` | POST |
| Cuenta | `/api/v1/auth/login/`, `/api/v1/auth/verificar-codigo/` | POST |
| Cuenta | `/api/v1/auth/token/refresh/`, `/api/v1/auth/logout/` | POST |
| Cuenta | `/api/v1/auth/perfil/` | GET, PUT, PATCH |
| Cuenta | `/api/v1/auth/cambiar-password/` | POST |
| Cuenta | `/api/v1/auth/recuperar/`, `/api/v1/auth/restablecer/` | POST |
| Catálogo | `/api/v1/destinos/` | GET |
| Catálogo | `/api/v1/destinos/<slug>/` | GET |
| Catálogo | `/api/v1/regiones/`, `/municipios/`, `/categorias/`, `/servicios/` | GET |
| Aportes | `/api/v1/destinos/<slug>/aportes/` | GET, POST |
| Aportes | `/api/v1/mis-aportes/` | GET |
| Aportes | `/api/v1/aportes/<id>/` | GET, PATCH, DELETE |
| Aportes | `/api/v1/aportes/<id>/reportar/` | POST |
| Información práctica | `/api/v1/destinos/<slug>/colaboraciones/` | GET, POST |
| Información práctica | `/api/v1/colaboraciones/<id>/confirmar/`, `/reportar/` | POST |
| Favoritos | `/api/v1/favoritos/` | GET |
| Favoritos | `/api/v1/favoritos/<slug>/` | GET, PUT, DELETE |
| Viajes | `/api/v1/mis-viajes/` | GET, POST |
| Viajes | `/api/v1/mis-viajes/<id>/` | GET, PATCH, DELETE |
| Viajes | `/api/v1/mis-viajes/<id>/lugares/` | POST |
| Viajes | `/api/v1/mis-viajes/<id>/compartir/` | POST, DELETE |
| Cuenta | `/api/v1/mi-cuenta/eliminar/` | POST |
| Métricas | `/api/v1/eventos/` | POST |
| Avisos | `/api/v1/notificaciones/` | GET |
| Avisos | `/api/v1/notificaciones/leidas/` | POST |

`/api/v1/destinos/` admite los filtros `q`, `categoria`, `municipio`, `region`, `servicio`, `calificacion_min`, `concepto`, `precio_max`, `datos_recientes` y `orden=recientes`.

### Sesión

Registrarse o iniciar sesión envía un código al correo, y `verificar-codigo` lo valida. Con `recordar: true`, ese navegador solo necesitará la contraseña durante 30 días. `verificar-codigo` responde con el token `access` y guarda el refresh token en una cookie `HttpOnly`, que JavaScript no puede leer. `token/refresh` y `logout` usan esa cookie, no reciben el token en el cuerpo y exigen la cabecera `X-CSRFToken` con el valor de la cookie `csrftoken`. El navegador conserva el `access` solo en memoria y pide uno nuevo al cargar cada página privada. En `localStorage` solo queda `usuario`, que sirve para mostrar el nombre en la interfaz.

### Operación

| Ruta o comando | Descripción |
|---|---|
| `/health/` | Estado de la base de datos y la caché: 200 si responden, 503 si no |
| `python manage.py enviar_avisos` | Crea las invitaciones tras un viaje y envía los avisos pendientes; programarlo cada pocos minutos |
| `python manage.py generar_miniaturas` | Crea las miniaturas de fotos anteriores a este campo; basta una vez |
| `python manage.py purgar_eventos` | Borra los eventos de uso de más de 13 meses |
| `python manage.py cargar_destinos_iniciales` | Carga opcional del catálogo inicial |
| `python manage.py importar_osm` | Importa lugares de OpenStreetMap, ocultos hasta publicarlos; gratis y sin cuenta ([guía](docs/importar-osm.md)) |

Los registros van a la salida estándar. `LOG_LEVEL` ajusta el detalle, y nunca incluyen correos ni contraseñas. Copias de seguridad, restauración y monitoreo en [la guía de operación](docs/operacion.md).

---

## 📁 Estructura del proyecto

```text
InfoTripReact/
  apps/
    core/              ← Utilidades sin dependencias: imágenes y /health/
    usuarios/          ← Cuentas, login con código por correo y recuperación
    destinos/          ← Catálogo, filtros compartidos y páginas públicas
    comunidad/         ← Aportes, moderación, avisos, información práctica,
                         favoritos y viajes (selectors.py: consultas para otros módulos)
  infotrip/
    settings/          ← base, dev, local, test, test_postgres y prod
  static/              ← CSS, JavaScript e imágenes
  templates/
    admin/             ← Encabezado del admin y cola de moderación
    comunidad/, destinos/, partials/
  docs/                ← Guías por módulo, plan y pendientes manuales
  docker/nginx.conf
  .github/workflows/   ← CI
  Dockerfile
  docker-compose.yml
  manage.py
  .env                 ← Variables de entorno (NO subir a Git)
  .env.example, .env.docker.example
  pyproject.toml       ← Configuración de ruff y coverage
  requirements.txt, requirements-dev.txt
```

La dependencia entre módulos va en un solo sentido: `destinos` usa `comunidad` solo mediante `selectors` y `models`, y `comunidad` solo importa `destinos.models`. Lo comprueba `apps/comunidad/test_dependencias.py`.

---

## 🔄 Flujo de commits

Trabaja en una rama y abre un pull request contra `master`. La CI revisa cada PR: ruff, `pip-audit`, pruebas en PostgreSQL con Redis y en SQLite, flujos en un navegador real, `check --deploy` y la imagen de Docker.

Para correr los flujos de navegador en tu equipo: `playwright install chromium`, y después `E2E=1 python manage.py test e2e --settings=infotrip.settings.test`.

```bash
git switch -c mi-cambio
git add .
git commit -m "descripción de los cambios"
git push -u origin mi-cambio
```

---

## 👥 Equipo

| Nombre |
|---|
| Isaac Arturo Camarillo Vega |
| Sergio David Nava Hernández |
| Roberto Carlos Ramirez Cordova |
| Jorge Gabriel Mariscal Aguayo |
| Jose de Jesus Ramirez Castro |

---

## 📄 Licencia

Proyecto académico — Universidad de Guadalajara 🎓

## Catálogo de destinos

El módulo de catálogo incluye modelos, migraciones y API pública de consulta. Consulta [la guía del módulo](docs/modulo-1-catalogo.md) para instalarlo, consultar endpoints y ejecutar las pruebas.


## MVP integrado

Módulos disponibles: catálogo y administración, exploración y mapa, detalle, reseñas, fotos y gastos, moderación con historial, perfil y recuperación de contraseña. Consulta [la guía de los módulos restantes](docs/modulos-5-a-9.md).

- `/destinos/`: filtros y mapa, con comparación de precios por concepto y calificación.
- `/destinos/<slug>/`: aportes públicos y formulario de contribución.
- `/perfil/`: datos personales, foto, contraseña y gestión de aportes propios.
- `/recuperar/`: solicitud y confirmación de recuperación por correo.
- `/admin/`: catálogo, usuarios y moderación; necesita una cuenta de administrador.

Para desarrollo con SQLite (sin PostgreSQL), selecciona explícitamente `settings_local` desde la carpeta de este README:

```powershell
.\.venv314\Scripts\python.exe -B manage.py migrate --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py cargar_destinos_iniciales --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py createsuperuser --settings=infotrip.settings_local
.\.venv314\Scripts\python.exe -B manage.py runserver --settings=infotrip.settings_local
```

El comando de carga agrega 15 localidades sin sobrescribir registros existentes. Fuentes y alcance de sus coordenadas en [catálogo inicial](docs/catalogo-inicial.md). Las credenciales del administrador las eliges al ejecutar `createsuperuser`.

Pruebas:

```powershell
.\.venv314\Scripts\python.exe -B manage.py test --settings=infotrip.settings.test
```

La configuración local actual imprime correos en consola; no entrega mensajes a Gmail. No publicar con `settings_local`. Para un entorno parecido a producción usa [Docker](#docker).


## Fichas, favoritos y agenda

Las fichas admiten información práctica con fuentes y fechas, correcciones moderadas y preguntas/respuestas. `/favoritos/` permite guardar destinos y vincularlos a viajes. Mis viajes incorpora actividades por día, notas y pendientes. Instalación, moderación y pruebas en [la guía de expansión](docs/expansion-comunidad-agenda.md).
