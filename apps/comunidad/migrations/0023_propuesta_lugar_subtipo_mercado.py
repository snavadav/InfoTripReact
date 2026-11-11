# Solo agrega «Mercado» a las opciones de subtipo de las propuestas (las mismas de Lugar). No toca la base de datos.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunidad', '0022_pagos_entre_participantes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propuestalugar',
            name='subtipo',
            field=models.CharField(choices=[('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'), ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'), ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'), ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'), ('convenience', 'Tienda de conveniencia'), ('supermarket', 'Supermercado'), ('variety_store', 'Tienda variada'), ('department_store', 'Tienda departamental'), ('mall', 'Centro comercial'), ('bakery', 'Panadería'), ('pastry', 'Pastelería'), ('confectionery', 'Dulcería'), ('alcohol', 'Licorería'), ('wine', 'Vinos'), ('beverages', 'Bebidas'), ('gift', 'Regalos y recuerdos'), ('craft', 'Artesanías y manualidades'), ('art', 'Arte y galería'), ('marketplace', 'Mercado')], max_length=20),
        ),
    ]
