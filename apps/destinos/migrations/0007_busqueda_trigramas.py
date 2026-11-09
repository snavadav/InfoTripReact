"""Búsqueda tolerante en PostgreSQL: extensiones unaccent y pg_trgm, e índice de trigramas para los lugares.

Solo agrega extensiones e índices; no altera ni borra datos. Desde PostgreSQL 13 ambas extensiones son
«trusted»: las puede crear el dueño de la base sin ser superusuario. En SQLite no hace nada.
"""
from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations

INDICE = 'lugar_nombre_trgm_idx'


def crear_indice(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        # ILIKE y `<%` (similitud por palabra) sobre 40 mil nombres usan este índice en lugar de leer la tabla.
        schema_editor.execute(f'CREATE INDEX IF NOT EXISTS {INDICE} ON destinos_lugar USING gin (nombre gin_trgm_ops)')


def borrar_indice(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(f'DROP INDEX IF EXISTS {INDICE}')


class Migration(migrations.Migration):

    dependencies = [
        ('destinos', '0006_referencia_costo'),
    ]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
        migrations.RunPython(crear_indice, borrar_indice),
    ]
