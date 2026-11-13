# Solo agrega los tipos «Museo» y «Parque» y sus subtipos a las opciones. No toca la base de datos ni los datos.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('destinos', '0009_lugar_mercado_y_recomendado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lugar',
            name='subtipo',
            field=models.CharField(choices=[('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'), ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'), ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'), ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'), ('convenience', 'Tienda de conveniencia'), ('supermarket', 'Supermercado'), ('variety_store', 'Tienda variada'), ('department_store', 'Tienda departamental'), ('mall', 'Centro comercial'), ('bakery', 'Panadería'), ('pastry', 'Pastelería'), ('confectionery', 'Dulcería'), ('alcohol', 'Licorería'), ('wine', 'Vinos'), ('beverages', 'Bebidas'), ('gift', 'Regalos y recuerdos'), ('craft', 'Artesanías y manualidades'), ('art', 'Arte y galería'), ('marketplace', 'Mercado'), ('museum', 'Museo'), ('park', 'Parque'), ('nature_reserve', 'Área natural')], max_length=20),
        ),
        migrations.AlterField(
            model_name='lugar',
            name='tipo',
            field=models.CharField(choices=[('comer', 'Comer'), ('dormir', 'Dormir'), ('gasolina', 'Gasolina'), ('farmacia', 'Farmacia'), ('cajero', 'Cajero o banco'), ('comprar', 'Comprar'), ('museo', 'Museo'), ('parque', 'Parque')], max_length=10),
        ),
    ]
