"""Referencias oficiales de costo: precios publicados por una fuente, siempre citados y aparte de los viajeros."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Destino, Municipio, ReferenciaCosto, Region

SIC = 'Sistema de Información Cultural, Secretaría de Cultura'


class ReferenciasBase(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Teuchitlán', slug='teuchitlan',
                                             region=Region.objects.create(nombre='Valles', slug='valles'))
        self.destino = Destino.objects.create(nombre='Guachimontones', slug='guachimontones', municipio=municipio,
                                              descripcion='-', latitud=20.69, longitud=-103.83)

    def referencia(self, **cambios):
        datos = dict(destino=self.destino, concepto='entrada', monto=Decimal(30), descripcion='Entrada general',
                     fuente_nombre=SIC, fuente_url='https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=1841',
                     fecha_consulta=date(2026, 11, 9), fecha_fuente=date(2026, 9, 29))
        return ReferenciaCosto.objects.create(**{**datos, **cambios})


class ModeloTests(ReferenciasBase):
    def test_se_describe_con_destino_concepto_y_monto(self):
        self.assertEqual(str(self.referencia()), 'Guachimontones · Entrada · $30')

    def test_no_admite_montos_negativos(self):
        with self.assertRaises(ValidationError):
            ReferenciaCosto(destino=self.destino, concepto='entrada', monto=Decimal(-1), descripcion='x',
                            fuente_nombre=SIC, fuente_url='https://example.org', fecha_consulta=date(2026, 11, 9)
                            ).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.referencia(monto=Decimal(-1))

    def test_la_misma_cita_no_se_duplica(self):
        self.referencia()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.referencia(monto=Decimal(40))

    def test_entrada_libre_es_monto_cero(self):
        self.referencia(monto=Decimal(0), descripcion='Entrada libre')
        self.assertEqual(self.destino.referencias_costo.get(descripcion='Entrada libre').monto, Decimal(0))
