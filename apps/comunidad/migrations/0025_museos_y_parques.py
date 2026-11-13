# Solo agrega museo, parque y área natural a los subtipos de las propuestas (los mismos de Lugar). No toca la base.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunidad', '0024_avisos_tipos_y_preferencias'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propuestalugar',
            name='subtipo',
            field=models.CharField(choices=[('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'), ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'), ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'), ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'), ('convenience', 'Tienda de conveniencia'), ('supermarket', 'Supermercado'), ('variety_store', 'Tienda variada'), ('department_store', 'Tienda departamental'), ('mall', 'Centro comercial'), ('bakery', 'Panadería'), ('pastry', 'Pastelería'), ('confectionery', 'Dulcería'), ('alcohol', 'Licorería'), ('wine', 'Vinos'), ('beverages', 'Bebidas'), ('gift', 'Regalos y recuerdos'), ('craft', 'Artesanías y manualidades'), ('art', 'Arte y galería'), ('marketplace', 'Mercado'), ('museum', 'Museo'), ('park', 'Parque'), ('nature_reserve', 'Área natural')], max_length=20),
        ),
    ]
