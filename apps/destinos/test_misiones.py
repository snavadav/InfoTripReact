"""Misiones de la comunidad: qué falta saber de cada lugar y quién lo ha contado."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.comunidad.models import Colaboracion, Confirmacion
from apps.comunidad.selectors import cronistas, misiones_por_destino
from apps.usuarios.models import Usuario
from .models import Destino, Municipio, Region


class MisionesBase(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        self.mazamitla = Municipio.objects.create(nombre='Mazamitla', slug='mazamitla', region=region)
        self.lugar = self.crear_destino('Lugar', self.tapalpa)
        self.otro = self.crear_destino('Otro', self.mazamitla)

    def crear_destino(self, nombre, municipio, **campos):
        return Destino.objects.create(nombre=nombre, slug=nombre.lower(), municipio=municipio, descripcion='-',
                                      latitud='19.9', longitud='-103.7', **campos)

    def dato(self, campo='horarios', dias=0, destino=None, autor=None, estado='publicado'):
        return Colaboracion.objects.create(
            destino=destino or self.lugar, autor=autor or self.ana, tipo='correccion', campo=campo, texto='Dato',
            fuente='Visita', fecha_dato=self.hoy - timedelta(days=dias), estado=estado)


class MisionesPorDestinoTests(MisionesBase):
    def mision(self):
        return misiones_por_destino([self.lugar.pk])[self.lugar.pk]

    def test_sin_datos_falta_todo(self):
        mision = self.mision()
        self.assertEqual(len(mision['faltan']), len(Colaboracion.CAMPOS))
        self.assertEqual(mision['confirmar'], [])

    def test_un_dato_reciente_no_es_mision(self):
        self.dato(dias=5)
        mision = self.mision()
        self.assertNotIn('horarios', [campo['clave'] for campo in mision['faltan']])
        self.assertEqual(mision['confirmar'], [])

    def test_un_dato_de_mas_de_30_dias_pide_confirmacion(self):
        self.dato(dias=45)
        self.assertEqual([(c['clave'], c['edad_dias']) for c in self.mision()['confirmar']], [('horarios', 45)])

    def test_confirmar_lo_saca_de_la_lista(self):
        dato = self.dato(dias=120)
        Confirmacion.objects.create(dato=dato, autor=self.leo, fecha=self.hoy)
        self.assertEqual(self.mision()['confirmar'], [])

    def test_cuenta_la_version_vigente_no_la_anterior(self):
        self.dato(dias=200)
        self.dato(dias=2)
        self.assertEqual(self.mision()['confirmar'], [])

    def test_lo_no_publicado_no_cuenta(self):
        self.dato(estado='pendiente')
        self.dato(campo='acceso', estado='oculto')
        self.assertEqual(len(self.mision()['faltan']), len(Colaboracion.CAMPOS))

    def test_consulta_acotada_sin_importar_cuantos_destinos(self):
        for campo, _ in Colaboracion.CAMPOS:
            self.dato(campo=campo, dias=40)
        with self.assertNumQueries(2):
            misiones_por_destino([self.lugar.pk, self.otro.pk])


class CronistasTests(MisionesBase):
    def test_hace_falta_un_minimo(self):
        self.dato(campo='horarios')
        self.dato(campo='acceso')
        self.assertEqual(cronistas(), [])

    def test_gana_quien_mas_publico_por_municipio(self):
        for campo in ('horarios', 'acceso', 'pago'):
            self.dato(campo=campo)
        for campo in ('horarios', 'acceso', 'pago', 'contacto'):
            self.dato(campo=campo, autor=self.leo)
        for campo in ('horarios', 'acceso', 'pago'):
            self.dato(campo=campo, destino=self.otro)
        self.assertEqual(cronistas(), [
            {'municipio': 'Mazamitla', 'nombre': 'Ana', 'datos': 3},
            {'municipio': 'Tapalpa', 'nombre': 'Leo', 'datos': 4},
        ])

    def test_no_cuenta_lo_no_publicado_lo_antiguo_ni_cuentas_inactivas(self):
        for campo in ('horarios', 'acceso', 'pago'):
            self.dato(campo=campo, estado='pendiente')
        viejos = [self.dato(campo=campo) for campo in ('horarios', 'acceso', 'pago')]
        Colaboracion.objects.filter(pk__in=[d.pk for d in viejos]).update(creado=timezone.now() - timedelta(days=400))
        for campo in ('horarios', 'acceso', 'pago'):
            self.dato(campo=campo, autor=self.leo)
        Usuario.objects.filter(pk=self.leo.pk).update(es_activo=False)
        self.assertEqual(cronistas(), [])


class PaginaTests(MisionesBase):
    def test_muestra_lugares_con_enlace_al_formulario(self):
        pagina = self.client.get('/misiones/')
        self.assertContains(pagina, '/destinos/lugar/?dato=horarios#sugerir-dato')
        self.assertContains(pagina, f'{len(Colaboracion.CAMPOS) * 2} misiones')
        self.assertContains(pagina, 'data-misiones')
        self.assertContains(pagina, 'js/medicion.js', count=1)

    def test_no_muestra_ocultos(self):
        self.crear_destino('Importado', self.tapalpa, es_activo=False)
        self.assertNotContains(self.client.get('/misiones/'), 'Importado')

    def test_filtra_por_municipio(self):
        pagina = self.client.get('/misiones/', {'municipio': 'mazamitla'})
        self.assertContains(pagina, '/destinos/otro/')
        self.assertNotContains(pagina, '/destinos/lugar/')

    def test_lugar_completo_desaparece(self):
        for campo, _ in Colaboracion.CAMPOS:
            self.dato(campo=campo)
        self.assertNotContains(self.client.get('/misiones/'), '/destinos/lugar/')

    def test_reconoce_a_cronistas(self):
        for campo in ('horarios', 'acceso', 'pago'):
            self.dato(campo=campo)
        self.assertContains(self.client.get('/misiones/'), 'Cronista de Tapalpa:')

    def test_sin_destinos_no_falla(self):
        Destino.objects.all().delete()
        self.assertContains(self.client.get('/misiones/'), 'No hay misiones pendientes')

    def test_pagina_invalida_y_sitemap(self):
        self.assertEqual(self.client.get('/misiones/', {'pagina': 'x'}).status_code, 200)
        self.assertContains(self.client.get('/sitemap.xml'), '/misiones/')

    def test_la_ficha_abre_el_formulario_del_dato(self):
        self.assertContains(self.client.get('/destinos/lugar/'), 'id="sugerir-dato"')
