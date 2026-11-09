# Servicio `respaldos`: pg_dump de PostgreSQL 16 más el cliente de AWS para subir las copias a S3 (opcional).
# trixie fijo: es la versión de Debian que trae el paquete awscli (2.23).
FROM postgres:16-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends awscli ca-certificates \
    && rm -rf /var/lib/apt/lists/*
