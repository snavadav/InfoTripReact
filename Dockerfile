# Imagen de producción de InfoTrip: gunicorn + WhiteNoise. Uso: ver README (sección Docker).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=infotrip.settings.prod

WORKDIR /app

# Las dependencias primero: la capa se reutiliza mientras requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic no se conecta a nada; estos valores solo satisfacen las comprobaciones de prod.py.
RUN SECRET_KEY=solo-para-construir-la-imagen-no-se-usa-en-ejecucion-0123456789 \
    ALLOWED_HOSTS=build REDIS_URL=redis://build:6379/0 \
    python manage.py collectstatic --noinput

# Sin privilegios de root. media/ existe en la imagen para que el volumen herede este dueño.
RUN useradd --create-home --uid 1000 infotrip && mkdir -p /app/media && chown -R infotrip /app/media
USER infotrip

EXPOSE 8000
CMD ["gunicorn", "infotrip.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
