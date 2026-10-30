#!/bin/sh
# Copia diaria de la base de datos y de las fotos, en el volumen `respaldos`. Conserva 14 días.
# Restauración paso a paso: docs/operacion.md
set -u
export PGPASSWORD="$POSTGRES_PASSWORD"

while true; do
  fecha=$(date +%Y-%m-%d-%H%M)
  if pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "/respaldos/.db-$fecha.tmp" \
      && mv "/respaldos/.db-$fecha.tmp" "/respaldos/db-$fecha.dump" \
      && tar -czf "/respaldos/.media-$fecha.tmp" -C /media . \
      && mv "/respaldos/.media-$fecha.tmp" "/respaldos/media-$fecha.tar.gz"; then
    echo "Respaldo completo: $fecha"
    find /respaldos -type f \( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) -mtime +14 -delete
  else
    echo "ERROR: el respaldo de $fecha falló" >&2
    rm -f "/respaldos/.db-$fecha.tmp" "/respaldos/.media-$fecha.tmp"
  fi
  sleep 86400
done
