"""Detalle de las paradas del planeador: solo lo publicado, con su fuente, y nada inventado."""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.comunidad.models import Aporte, Colaboracion, VisitaComprobada
from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario

URL = '/api/v1/rutas/paradas/'


class ParadasTests(APITestCase):
    def setUp(self):
        cache.clear()
        region = Region.objects.create(nombre='Centro', slug='centro')
        municipio = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=region)
        self.museo = Destino.objects.create(nombre='Museo', slug='museo', municipio=municipio, latitud=20.67,
                                            longitud=-103.34, descripcion='Pintura y murales de Orozco.')
        self.plaza = Destino.objects.create(nombre='Plaza', slug='plaza', municipio=municipio, latitud=20.68,
                                            longitud=-103.35, descripcion='Kiosco y portales.')
        self.equipo = Usuario.objects.create_user('equipo@example.com', 'Equipo', 'I', 'x')
        self.hoy = timezone.localdate()

    def persona(self, numero, activa=True):
        return Usuario.objects.create_user(f'p{numero}@example.com', f'Persona{numero}', 'P', 'x', es_activo=activa)

    def dato(self, campo, texto, estado='publicado', dias=0, destino=None):
        return Colaboracion.objects.create(destino=destino or self.museo, autor=self.equipo, tipo='correccion',
                                           campo=campo, texto=texto, fuente='https://sic.cultura.gob.mx/',
                                           estado=estado, fecha_dato=self.hoy - timedelta(days=dias))

    def resena(self, autor, calificacion=5, estado='publicado', destino=None, texto='Muy bonito'):
        return Aporte.objects.create(destino=destino or self.museo, autor=autor, tipo='resena', texto=texto,
                                     calificacion=calificacion, fecha_visita=self.hoy, estado=estado)

    def pedir(self, destinos):
        return self.client.get(URL, {'destinos': destinos})

    def test_descripcion_y_datos_practicos_vigentes_con_su_fuente(self):
        self.dato('horarios', 'Martes a domingo de 10 a 17 h', dias=40)
        self.dato('horarios', 'Martes a domingo de 10 a 18 h', dias=2)
        self.dato('precios', 'Entrada $80', estado='pendiente')
        self.dato('acceso', 'Por la calle Hidalgo')
        respuesta = self.pedir(f'{self.plaza.pk},{self.museo.pk}')
        self.assertEqual(respuesta.status_code, 200)
        plaza, museo = respuesta.json()['destinos']
        # En el orden pedido.
        self.assertEqual((plaza['id'], museo['id']), (self.plaza.pk, self.museo.pk))
        self.assertEqual(museo['descripcion'], 'Pintura y murales de Orozco.')
        # Solo el horario vigente; el precio pendiente de moderación y el acceso no se muestran aquí.
        self.assertEqual(museo['practicos'], [{
            'campo': 'horarios', 'nombre': 'Horarios', 'texto': 'Martes a domingo de 10 a 18 h',
            'fuente': 'https://sic.cultura.gob.mx/', 'fecha_dato': (self.hoy - timedelta(days=2)).isoformat()}])
        self.assertEqual(plaza['practicos'], [])

    def test_sin_resenas_no_se_inventa_ninguna(self):
        museo = self.pedir(str(self.museo.pk)).json()['destinos'][0]
        self.assertEqual((museo['resenas'], museo['total_resenas'], museo['promedio']), ([], 0, None))

    def test_solo_resenas_publicadas_y_las_mas_recientes(self):
        for numero, calificacion in enumerate([3, 4, 5, 4], start=1):
            self.resena(self.persona(numero), calificacion, texto=f'Reseña {numero}')
        self.resena(self.persona(5), 1, estado='pendiente', texto='Pendiente')
        self.resena(self.persona(6), 1, estado='oculto', texto='Oculta')
        self.resena(self.persona(7, activa=False), 1, texto='Cuenta de baja')
        self.resena(self.persona(8), 2, destino=self.plaza, texto='De la plaza')
        Aporte.objects.create(destino=self.museo, autor=self.persona(9), tipo='gasto', texto='Entrada',
                              monto=80, concepto='entrada', fecha_visita=self.hoy, estado='publicado')
        VisitaComprobada.objects.create(autor=Usuario.objects.get(email='p4@example.com'), destino=self.museo,
                                        fecha=self.hoy)
        museo, plaza = self.pedir(f'{self.museo.pk},{self.plaza.pk}').json()['destinos']
        self.assertEqual([r['texto'] for r in museo['resenas']], ['Reseña 4', 'Reseña 3', 'Reseña 2'])
        self.assertEqual(museo['total_resenas'], 4)
        self.assertEqual(museo['promedio'], 4.0)
        self.assertTrue(museo['resenas'][0]['visita_comprobada'])
        self.assertFalse(museo['resenas'][1]['visita_comprobada'])
        self.assertEqual(museo['resenas'][0]['autor_nombre'], 'Persona4')
        self.assertEqual([r['texto'] for r in plaza['resenas']], ['De la plaza'])

    def test_destinos_inactivos_o_inexistentes_no_aparecen(self):
        self.plaza.es_activo = False
        self.plaza.save()
        destinos = self.pedir(f'{self.museo.pk},{self.plaza.pk},999999').json()['destinos']
        self.assertEqual([d['id'] for d in destinos], [self.museo.pk])

    def test_peticiones_invalidas(self):
        for valor in ['', 'abc', '1,,2', '1;2', ','.join(str(n) for n in range(1, 32))]:
            self.assertEqual(self.pedir(valor).status_code, 400, valor)
        self.assertEqual(self.client.get(URL).status_code, 400)
        self.assertEqual(self.client.post(URL, {'destinos': '1'}).status_code, 405)
