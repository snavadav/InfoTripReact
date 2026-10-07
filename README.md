# InfoTrip

Plataforma web colaborativa para la gestión de información turística y validación de experiencias de viaje en Jalisco, México.

![Django](https://img.shields.io/badge/Django-6.0.4-092E20?style=flat&logo=django)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat&logo=postgresql)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat&logo=python)

---

## ¿Qué es InfoTrip?

InfoTrip centraliza información turística verificada por la comunidad. Los viajeros pueden consultar destinos, precios reales, reseñas verificadas y rutas de acceso — todo sin publicidad ni contenido patrocinado.

---

## Tecnologías

|Capa|Tecnología|
| Backend | Django 6.0.4 + Django REST Framework |
| Base de datos | PostgreSQL |
| Autenticación | Simple JWT |
| Frontend | HTML, CSS, JavaScript |
| Gestor de DB | DBeaver + DBngin |

---

## Requisitos previos

Antes de instalar el proyecto necesitas tener:

- **Python 3.14+** — [python.org](https://www.python.org/downloads/)
- **PostgreSQL 16** — servidor y pgAdmin, desde [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
- **DBeaver** — [dbeaver.io](https://dbeaver.io/download/)
- **Git** — [git-scm.com](https://git-scm.com/)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/snavadav/InfoTripReact.git
cd InfoTripReact
```

### 2. Instalar dependencias

```bash
python -m pip install -r requirements.txt
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

## 🌐 URLs disponibles

| URL | Descripción |
| `http://127.0.0.1:8000/` | Página principal |
| `http://127.0.0.1:8000/admin/` | Panel de administración |
| `http://127.0.0.1:8000/api/v1/auth/registro/` | Registro de usuarios |
| `http://127.0.0.1:8000/api/v1/auth/login/` | Login |
| `http://127.0.0.1:8000/api/v1/auth/logout/` | Logout |
| `http://127.0.0.1:8000/api/v1/auth/perfil/` | Perfil del usuario |

---

## 📁 Estructura del proyecto

```text
INFOTRIP/
  apps/
    usuarios/          ← Autenticación y usuarios
  infotrip/            ← Configuración Django
  static/
    css/               ← Estilos
    js/                ← Scripts
    images/            ← Imágenes estáticas
  media/
    perfiles/          ← Fotos de perfil subidas por usuarios
    destinos/          ← Fotos de destinos
  templates/
    base/
      index.html       ← Página principal
    partials/          ← Secciones del frontend
  manage.py
  .env                 ← Variables de entorno (NO subir a Git)
  .gitignore
  requirements.txt
```

---

## 🔄 Flujo de commits

Cada vez que hagas cambios:

```bash
git add .
git commit -m "descripción de los cambios"
git push origin master
```

---

## 👥 Equipo

| Nombre |
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

El comando de carga agrega cinco localidades sin sobrescribir registros existentes. Fuentes y alcance de sus coordenadas en [catálogo inicial](docs/catalogo-inicial.md). Las credenciales del administrador las eliges al ejecutar `createsuperuser`.

Pruebas:

```powershell
.\.venv314\Scripts\python.exe -B manage.py test apps.destinos apps.usuarios apps.comunidad --settings=infotrip.settings_test
```

La configuración local actual imprime correos en consola; no entrega mensajes a Gmail. No publicar con `settings_local`. El despliegue y la validación con PostgreSQL real siguen siendo pasos operativos independientes.


## Fichas, favoritos y agenda

Las fichas admiten información práctica con fuentes y fechas, correcciones moderadas y preguntas/respuestas. `/favoritos/` permite guardar destinos y vincularlos a viajes. Mis viajes incorpora actividades por día, notas y pendientes. Instalación, moderación y pruebas en [la guía de expansión](docs/expansion-comunidad-agenda.md).
