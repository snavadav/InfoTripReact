"""Viaje en grupo: invitar amigos, "Yo pagué" en un establecimiento, pagos entre personas y "a mano"."""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.amigos.models import Amistad
from apps.destinos.models import Destino, Lugar, Municipio, Region
from apps.usuarios.models import Usuario
from .bote import calcular_cuentas, calcular_saldos
from .models import Notificacion, PagoEntreParticipantes, Participante, Viaje

CLAVE = 'Prueba-segura-493!'


class Grupo(APITestCase):
    def setUp(self):
        cache.clear()
        crear = Usuario.objects.create_user
        self.ana = crear('ana@example.com', 'Ana', 'P', CLAVE, es_verificado=True, username='ana')
        self.leo = crear('leo@example.com', 'Leo', 'P', CLAVE, es_verificado=True, username='leo')
        self.eva = crear('eva@example.com', 'Eva', 'P', CLAVE, es_verificado=True, username='eva')
        self.ivan = crear('ivan@example.com', 'Iván', 'P', CLAVE, es_verificado=True, username='ivan')
        for amigo in (self.leo, self.eva, self.ivan):
            Amistad.objects.create(de=self.ana, para=amigo, estado='aceptada')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.destino = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-',
                                              latitud='19.94', longitud='-103.76')
        self.fonda = Lugar.objects.create(nombre='Fonda Doña Lupe', tipo='comer', subtipo='restaurant',
                                          municipio=municipio, latitud='19.95', longitud='-103.75')
        self.lejos = Lugar.objects.create(nombre='Fonda del Puerto', tipo='comer', subtipo='restaurant',
                                          latitud='20.62', longitud='-105.23')
        # Una escapada cualquiera, como la que crea el planeador: sin bote abierto ni enlace.
        self.viaje = Viaje.objects.create(autor=self.ana, nombre='Tapalpa', destino='Tapalpa', personas=3,
                                          fecha_inicio='2026-01-01', fecha_fin='2026-01-03', presupuesto='0')
        self.viaje.lugares.add(self.destino)
        self.url = f'/api/v1/mis-viajes/{self.viaje.pk}/bote/'

    def como(self, usuario):
        self.client.force_authenticate(usuario)

    def invitar(self, *usernames):
        self.como(self.ana)
        return self.client.post(self.url + 'invitar/', {'usernames': list(usernames)}, format='json')

    def ids(self):
        return {p.usuario.username: p.pk for p in self.viaje.participantes.select_related('usuario')}

    def yo_pague(self, usuario, monto, entre=None, **extra):
        self.como(usuario)
        ids = self.ids()
        datos = {'monto': monto, 'concepto': 'comida', 'fecha': timezone.localdate().isoformat(),
                 'pagado_por': ids[usuario.username], 'entre': [ids[n] for n in (entre or ids)], **extra}
        return self.client.post(self.url + 'gastos/', datos, format='json')

    def pagar(self, de, para, monto):
        self.como(de)
        return self.client.post(self.url + 'pagos/', {'para': self.ids()[para.username], 'monto': monto},
                                format='json')

    def confirmar(self, quien, pago):
        self.como(quien)
        return self.client.post(f'{self.url}pagos/{pago}/confirmar/')


class InvitarTests(Grupo):
    def test_invita_solo_a_amigos_aceptados_y_avisa(self):
        extraño = Usuario.objects.create_user('x@example.com', 'X', 'P', CLAVE, es_verificado=True, username='x')
        Amistad.objects.create(de=self.ana, para=extraño, estado='pendiente')
        self.assertEqual(self.invitar('x').status_code, 400)
        self.assertEqual(self.invitar('leo', 'x').status_code, 400)
        self.assertFalse(self.viaje.participantes.exclude(usuario=self.ana).exists())
        estado = self.invitar('@Leo', 'eva').data
        self.assertEqual({p['username'] for p in estado['participantes']}, {'ana', 'leo', 'eva'})
        self.assertEqual([a['username'] for a in estado['amigos_invitables']], ['ivan'])
        aviso = Notificacion.objects.get(usuario=self.leo)
        self.assertIn('@ana te agregó al bote de Tapalpa', aviso.texto)
        self.assertEqual(aviso.enlace, f'/mis-viajes/{self.viaje.pk}/bote/')
        # Repetir no duplica a nadie.
        self.assertEqual(self.invitar('leo').status_code, 200)
        self.assertEqual(self.viaje.participantes.count(), 3)

    def test_solo_quien_organiza_invita(self):
        self.invitar('leo')
        self.como(self.leo)
        self.assertEqual(self.client.post(self.url + 'invitar/', {'usernames': ['eva']}, format='json').status_code,
                         404)

    def test_el_invitado_puede_salirse(self):
        self.invitar('leo')
        self.como(self.leo)
        yo = self.ids()['leo']
        self.assertTrue(next(p for p in self.client.get(self.url).data['participantes'] if p['id'] == yo)['puede_salir'])
        self.assertEqual(self.client.delete(f'{self.url}participantes/{yo}/').status_code, 204)

    def test_el_enlace_sigue_funcionando_para_quien_no_es_amigo(self):
        self.como(self.ana)
        enlace = self.client.post(self.url).data['enlace_invitacion']
        extraño = Usuario.objects.create_user('x@example.com', 'X', 'P', CLAVE, es_verificado=True)
        self.como(extraño)
        self.assertEqual(self.client.post(f'/api/v1/botes/{enlace}/unirse/').status_code, 200)


class PermisosTests(Grupo):
    def test_un_amigo_no_invitado_no_ve_la_escapada_ni_el_bote(self):
        self.invitar('leo')
        self.yo_pague(self.ana, '300.00')
        self.como(self.eva)
        for url in [f'/api/v1/mis-viajes/{self.viaje.pk}/', self.url, self.url + 'lugares/?q=fonda']:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.post(self.url + 'pagos/', {'para': self.ids()['ana'], 'monto': '1'},
                                          format='json').status_code, 404)
        self.assertEqual(self.client.post(self.url + 'gastos/', {}, format='json').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/mis-botes/').data, [])


class YoPagueTests(Grupo):
    def test_donde_es_un_establecimiento_y_da_la_descripcion(self):
        self.invitar('leo')
        respuesta = self.yo_pague(self.leo, '450.00', lugar=self.fonda.pk)
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual((respuesta.data['descripcion'], respuesta.data['lugar_nombre']),
                         ('Fonda Doña Lupe', 'Fonda Doña Lupe'))
        self.assertEqual(self.yo_pague(self.leo, '1.00', descripcion='').status_code, 400)
        self.fonda.es_activo = False
        self.fonda.save()
        self.assertEqual(self.yo_pague(self.leo, '1.00', lugar=self.fonda.pk).status_code, 400)

    def test_buscar_donde_cerca_de_la_escapada(self):
        self.invitar('leo')
        self.como(self.leo)
        self.assertEqual([lugar['nombre'] for lugar in self.client.get(self.url + 'lugares/?q=fonda').data],
                         ['Fonda Doña Lupe'])
        self.assertEqual(self.client.get(self.url + 'lugares/?q=f').data, [])


class PagosTests(Grupo):
    def preparar(self):
        self.invitar('leo', 'eva')
        self.yo_pague(self.ana, '300.00', lugar=self.fonda.pk)

    def test_crear_confirmar_y_cancelar(self):
        self.preparar()
        respuesta = self.pagar(self.leo, self.ana, '100.00')
        self.assertEqual(respuesta.status_code, 201)
        pago = respuesta.data['pagos'][0]
        self.assertEqual((pago['confirmado'], pago['puede_cancelar'], pago['puede_confirmar']), (False, True, False))
        de_leo = next(t for t in respuesta.data['transferencias'] if t['de_id'] == self.ids()['leo'])
        self.assertEqual(de_leo['pendiente'], pago['id'])
        self.assertIn('registró que te pagó $100.00', Notificacion.objects.filter(usuario=self.ana).first().texto)
        # Sin confirmar no cuenta.
        self.assertEqual({p['username']: p['saldo'] for p in respuesta.data['participantes']}['leo'], '-100.00')
        # Solo quien recibe confirma; solo quien pagó cancela.
        self.assertEqual(self.confirmar(self.leo, pago['id']).status_code, 404)
        self.assertEqual(self.confirmar(self.eva, pago['id']).status_code, 404)
        self.como(self.ana)
        self.assertEqual(self.client.delete(f"{self.url}pagos/{pago['id']}/").status_code, 404)
        estado = self.confirmar(self.ana, pago['id']).data
        leo = next(p for p in estado['participantes'] if p['username'] == 'leo')
        self.assertEqual((leo['pago'], leo['le_tocaba'], leo['enviados'], leo['saldo']),
                         ('0.00', '100.00', '100.00', '0.00'))
        self.assertIn('confirmó que recibió tu pago', Notificacion.objects.filter(usuario=self.leo).first().texto)
        self.como(self.leo)
        self.assertEqual(self.client.delete(f"{self.url}pagos/{pago['id']}/").status_code, 400)
        cancelable = self.pagar(self.leo, self.ana, '5.00').data['pagos'][0]['id']
        self.assertEqual(self.client.delete(f'{self.url}pagos/{cancelable}/').status_code, 200)
        self.assertEqual(PagoEntreParticipantes.objects.count(), 1)

    def test_valores_invalidos(self):
        self.preparar()
        ajeno = Participante.objects.create(
            viaje=Viaje.objects.create(autor=self.ivan, nombre='Otro', destino='X', personas=1,
                                       fecha_inicio='2026-01-01', fecha_fin='2026-01-01', presupuesto='0'),
            usuario=self.ivan)
        self.como(self.leo)
        ids = self.ids()
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        for datos in [{'para': ids['leo'], 'monto': '1'}, {'para': ajeno.pk, 'monto': '1'},
                      {'para': ids['ana'], 'monto': '0'}, {'para': ids['ana'], 'monto': '-5'},
                      {'para': ids['ana'], 'monto': '1', 'fecha': manana}]:
            self.assertEqual(self.client.post(self.url + 'pagos/', datos, format='json').status_code, 400, datos)
        self.assertFalse(PagoEntreParticipantes.objects.exists())

    def test_con_pagos_no_se_puede_salir(self):
        self.invitar('leo', 'ivan')
        self.pagar(self.ivan, self.leo, '10.00')
        self.como(self.ivan)
        ivan = self.ids()['ivan']
        self.assertEqual(self.client.delete(f'{self.url}participantes/{ivan}/').status_code, 400)

    def test_quedan_a_mano_en_centavos_exactos(self):
        self.invitar('leo', 'eva')
        self.yo_pague(self.ana, '100.00', lugar=self.fonda.pk)
        self.yo_pague(self.leo, '0.01')
        estado = self.client.get(self.url).data
        self.assertFalse(estado['a_mano'])
        for _ in range(4):
            if estado['a_mano']:
                break
            for sugerido in estado['transferencias']:
                de = Participante.objects.get(pk=sugerido['de_id']).usuario
                para = Participante.objects.get(pk=sugerido['a_id']).usuario
                pago = self.pagar(de, para, sugerido['monto']).data['pagos'][0]['id']
                estado = self.confirmar(para, pago).data
        self.assertTrue(estado['a_mano'])
        self.assertEqual(estado['transferencias'], [])
        self.assertEqual({p['saldo'] for p in estado['participantes']}, {'0.00'})
        # Un pago de más rompe el "a mano": no se redondea.
        pago = self.pagar(self.eva, self.ana, '0.01').data['pagos'][0]['id']
        self.assertFalse(self.confirmar(self.ana, pago).data['a_mano'])


class CalculoTests(Grupo):
    def test_cuentas_por_persona_con_pagos_confirmados(self):
        cuentas = calcular_cuentas([1, 2, 3], [(1, Decimal('300.00'), [1, 2, 3])], [(2, 1, Decimal('100.00'))])
        self.assertEqual(cuentas[1], {'pago': 30000, 'le_tocaba': 10000, 'enviados': 0, 'recibidos': 10000,
                                      'diferencia': 10000})
        self.assertEqual(cuentas[2]['diferencia'], 0)
        self.assertEqual(sum(c['diferencia'] for c in cuentas.values()), 0)
        self.assertEqual(calcular_saldos([1, 2], [(1, Decimal('10'), [1, 2])], [(2, 1, Decimal('5'))]), {1: 0, 2: 0})
