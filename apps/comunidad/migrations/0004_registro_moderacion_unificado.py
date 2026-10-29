"""Unifica los campos del historial de moderación (RegistroModeracion) sin copiar ni borrar datos.

- RevisionColaboracion: `anterior` y `nuevo` se renombran (la columna conserva sus filas) y
  `motivo` se amplía de 500 caracteres a texto de hasta 1000, como en Decision.
- Decision solo cambia su orden por defecto, que no genera SQL.

Reversible. Al revertir, `motivo` vuelve a 500 caracteres: fallaría si algún motivo guardado
después de aplicar esta migración es más largo.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunidad', '0003_viaje_actividades_viaje_lugares_viaje_notas_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(name='decision', options={'ordering': ['-creado', '-pk']}),
        migrations.RenameField(model_name='revisioncolaboracion', old_name='anterior', new_name='estado_anterior'),
        migrations.RenameField(model_name='revisioncolaboracion', old_name='nuevo', new_name='estado_nuevo'),
        migrations.AlterField(
            model_name='revisioncolaboracion', name='motivo', field=models.TextField(max_length=1000),
        ),
    ]
