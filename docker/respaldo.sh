#!/bin/sh
# Copia diaria de la base de datos y de las fotos en el volumen `respaldos`, donde se conservan 14 días.
# Si RESPALDO_S3_BUCKET tiene valor, también sube cada copia a S3 fuera del servidor:
#   diarias/AAAA-MM-DD-HHMM/    todos los días    (una regla del bucket las borra a los 7 días)
#   semanales/AAAA-MM-DD-HHMM/  solo los domingos (una regla del bucket las borra a los 28 días)
# Las credenciales vienen del rol de IAM de la instancia: aquí no se guarda ninguna llave.
# Uso: sh respaldo.sh            un respaldo al día, sin fin (así corre el servicio)
#      sh respaldo.sh --una-vez  un solo respaldo; termina con error si falla (pruebas y respaldos a mano)
# Configuración de S3 y restauración paso a paso: docs/operacion.md
set -u
export PGPASSWORD="$POSTGRES_PASSWORD"
BUCKET="${RESPALDO_S3_BUCKET:-}"
PREFIJO="${RESPALDO_S3_PREFIJO:-infotrip}"
REGION="${RESPALDO_S3_REGION:-}"

subir() {  # subir <archivo> <destino en el bucket>
  if [ -n "$REGION" ]; then
    aws s3 cp --only-show-errors --region "$REGION" "$1" "s3://$BUCKET/$PREFIJO/$2"
  else
    aws s3 cp --only-show-errors "$1" "s3://$BUCKET/$PREFIJO/$2"
  fi
}

subir_a_s3() {  # subir_a_s3 <fecha>
  [ -n "$BUCKET" ] || return 0
  carpetas="diarias"
  [ "$(date +%u)" = 7 ] && carpetas="diarias semanales"
  for carpeta in $carpetas; do
    for archivo in "db-$1.dump" "media-$1.tar.gz"; do
      subir "/respaldos/$archivo" "$carpeta/$1/$archivo" || return 1
    done
  done
  echo "Respaldo subido a S3 ($carpetas): $1"
}

respaldar() {
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
    return 1
  fi
  # La copia local ya quedó: si S3 falla, se avisa en el registro y se reintenta mañana.
  if ! subir_a_s3 "$fecha"; then
    echo "ERROR: no se pudo subir a S3 el respaldo de $fecha (la copia local sí quedó)" >&2
    return 1
  fi
}

if [ "${1:-}" = "--una-vez" ]; then
  respaldar
  exit
fi

while true; do
  respaldar
  sleep 86400
done
