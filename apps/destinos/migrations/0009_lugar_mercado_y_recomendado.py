# Solo agrega: el campo recomendado_equipo (falso para todos) y el subtipo «Mercado» en las opciones.
# Cambiar las opciones de subtipo no toca la base de datos ni los datos existentes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('destinos', '0008_datos_al_dia'),
    ]

    operations = [
        migrations.AddField(
            model_name='lugar',
            name='recomendado_equipo',
            field=models.BooleanField(default=False, help_text='Solo el equipo lo marca, después de conocer el lugar. Se muestra como «Recomendado por el equipo».', verbose_name='recomendado por el equipo'),
        ),
        migrations.AlterField(
            model_name='lugar',
            name='subtipo',
            field=models.CharField(choices=[('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'), ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'), ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'), ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'), ('convenience', 'Tienda de conveniencia'), ('supermarket', 'Supermercado'), ('variety_store', 'Tienda variada'), ('department_store', 'Tienda departamental'), ('mall', 'Centro comercial'), ('bakery', 'Panadería'), ('pastry', 'Pastelería'), ('confectionery', 'Dulcería'), ('alcohol', 'Licorería'), ('wine', 'Vinos'), ('beverages', 'Bebidas'), ('gift', 'Regalos y recuerdos'), ('craft', 'Artesanías y manualidades'), ('art', 'Arte y galería'), ('marketplace', 'Mercado')], max_length=20),
        ),
    ]
