from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.test import APITestCase

from .models import Categoria, Destino, Municipio, Region, Servicio


class CatalogoTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(nombre='Región de prueba', slug='region-prueba')
        cls.municipio = Municipio.objects.create(nombre='Municipio de prueba', slug='municipio-prueba', region=cls.region)
        cls.categoria = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')
        cls.servicio = Servicio.objects.create(nombre='Estacionamiento', slug='estacionamiento')
        cls.destino = Destino.objects.create(
            nombre='Bosque de prueba', slug='bosque-prueba', descripcion='Senderos para caminar',
            municipio=cls.municipio, latitud=Decimal('20.123456'), longitud=Decimal('-103.123456'),
        )
        cls.destino.categorias.add(cls.categoria)
        cls.destino.servicios.add(cls.servicio)
        cls.oculto = Destino.objects.create(
            nombre='Destino oculto', slug='oculto', descripcion='No publicado',
            municipio=cls.municipio, latitud=20, longitud=-103, es_activo=False,
        )

    def test_listado_publico_paginado_con_relaciones(self):
        response = self.client.get('/api/v1/destinos/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        item = response.data['results'][0]
        self.assertEqual(item['municipio']['region']['slug'], self.region.slug)
        self.assertEqual(item['categorias'][0]['slug'], 'naturaleza')
        self.assertEqual(item['servicios'][0]['slug'], 'estacionamiento')

    def test_detalle_y_destinos_no_publicos(self):
        self.assertEqual(self.client.get('/api/v1/destinos/bosque-prueba/').status_code, 200)
        for slug in ['oculto', 'no-existe']:
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(f'/api/v1/destinos/{slug}/').status_code, 404)

    def test_filtros_combinados_y_busqueda(self):
        filtros = {'q': 'senderos', 'categoria': 'naturaleza', 'municipio': self.municipio.slug,
                   'region': self.region.slug, 'servicio': self.servicio.slug}
        response = self.client.get('/api/v1/destinos/', filtros)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        for campo in filtros:
            with self.subTest(campo=campo):
                response = self.client.get('/api/v1/destinos/', {campo: 'inexistente'})
                self.assertEqual(response.data['count'], 0)

    def test_filtros_invalidos(self):
        for datos in [{'categoria': 'no es un slug'}, {'q': 'x' * 201}]:
            self.assertEqual(self.client.get('/api/v1/destinos/', datos).status_code, 400)

    def test_catalogos_publicos(self):
        for ruta in ['regiones', 'municipios', 'categorias', 'servicios']:
            with self.subTest(ruta=ruta):
                response = self.client.get(f'/api/v1/{ruta}/')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['count'], 1)
                self.assertEqual(self.client.post(f'/api/v1/{ruta}/', {}).status_code, 405)

    def test_api_solo_consulta(self):
        self.assertEqual(self.client.post('/api/v1/destinos/', {}).status_code, 405)
        self.assertEqual(self.client.patch('/api/v1/destinos/bosque-prueba/', {}).status_code, 405)
        self.assertEqual(self.client.delete('/api/v1/destinos/bosque-prueba/').status_code, 405)

    def test_coordenadas_validacion_y_restriccion_bd(self):
        for campo, valor in [('latitud', 91), ('latitud', -91), ('longitud', 181), ('longitud', -181)]:
            with self.subTest(campo=campo, valor=valor):
                destino = Destino.objects.get(pk=self.destino.pk)
                setattr(destino, campo, valor)
                with self.assertRaises(ValidationError):
                    destino.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Destino.objects.filter(pk=destino.pk).update(**{campo: valor})

    def test_slug_unico(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Destino.objects.filter(pk=self.oculto.pk).update(slug=self.destino.slug)

    def test_geografia_protegida(self):
        with self.assertRaises(ProtectedError):
            self.municipio.delete()
        with self.assertRaises(ProtectedError):
            self.region.delete()

    def test_consultas_no_crecen_por_destino(self):
        for numero in range(5):
            Destino.objects.create(nombre=f'Destino {numero}', slug=f'destino-{numero}',
                                   descripcion='Prueba', municipio=self.municipio, latitud=20, longitud=-103)
        with self.assertNumQueries(4):
            response = self.client.get('/api/v1/destinos/')
            self.assertEqual(len(response.data['results']), 6)
