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
- **PostgreSQL** — vía [DBngin](https://dbngin.com/) (Mac) o [postgresql.org](https://www.postgresql.org/download/) (Windows)
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
python -m pip install django djangorestframework djangorestframework-simplejwt pillow psycopg2-binary python-decouple
```

### 3. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto con este contenido:

```
SECRET_KEY=django-insecure-cambia-esta-clave
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=infotrip
DB_USER=postgres
DB_PASSWORD=tu_password_aqui
DB_HOST=localhost
DB_PORT=5432
```

> ⚠️ Nunca subas el `.env` a GitHub — ya está en el `.gitignore`

### 4. Crear la base de datos

Abre **DBeaver**, conéctate a PostgreSQL y ejecuta:

```sql
CREATE DATABASE infotrip;
```

### 5. Aplicar migraciones

```bash
python manage.py migrate --fake-initial
```

### 6. Crear superusuario

```bash
python manage.py createsuperuser
```

Te pedirá:
- Email
- Nombre
- Apellido
- Contraseña

### 7. Correr el servidor

```bash
python manage.py runserver
```

---

## 🌐 URLs disponibles

| URL | Descripción |
|---|---|
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
