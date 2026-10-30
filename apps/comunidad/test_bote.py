"""Bote de la escapada: cuentas exactas, privacidad del grupo y publicación sin nombres."""
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .bote import calcular_saldos, calcular_transferencias, repartir
from .cuenta import anonimizar_cuenta
from .models import Aporte, GastoReal, Notificacion, Participante, Viaje


class CuentasTests(SimpleTestCase):
    def test_repartir_suma_exacto(self):
        self.assertEqual(repartir(100, 3), [34, 33, 33])
        self.assertEqual(sum(repartir(1001, 7)), 1001)

    def test_saldos_suman_cero_aunque_no_sea_divisible(self):
        saldos = calcular_saldos([1, 2, 3], [(1, Decimal('100.00'), [1, 2, 3]), (2, Decimal('10.01'), [1, 3])])
        self.assertEqual(sum(saldos.values()), 0)
        self.assertEqual(saldos, {1: 10000 - 3334 - 501, 2: 1001 - 3333, 3: -3333 - 500})

    def test_quien_no_participa_del_gasto_no_lo_paga(self):
        self.assertEqual(calcular_saldos([1, 2, 3], [(1, Decimal('50'), [1, 2])]), {1: 2500, 2: -2500, 3: 0})

    def test_transferencias_saldan_todo(self):
        saldos = {1: 7000, 2: -5000, 3: -1500, 4: -500, 5: 0}
        pagos = calcular_transferencias(saldos)
        self.assertEqual(pagos, [(2, 1, 5000), (3, 1, 1500), (4, 1, 500)])
        for de, a, monto in pagos:
            saldos[de] += monto
            saldos[a] -= monto
        self.assertEqual(set(saldos.values()), {0})

    def test_sin_gastos_no_hay_transferencias(self):
        self.assertEqual(calcular_transferencias({1: 0, 2: 0}), [])


class BoteBase(APITestCase):
    def setUp(self):
        crear = Usuario.objects.create_user
        self.ana = crear('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = crear('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.eva = crear('eva@example.com', 'Eva', 'P', 'Prueba-segura-493!', es_verificado=True)
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.lugar = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-',
                                            latitud='19.9', longitud='-103.7')
        self.viaje = Viaje.objects.create(autor=self.ana, nombre='Con amigos', destino='Tapalpa', personas=3,
                                          fecha_inicio='2026-01-01', fecha_fin='2026-01-03', presupuesto='100')
        self.viaje.lugares.add(self.lugar)
        self.url = f'/api/v1/mis-viajes/{self.viaje.pk}/bote/'

    def como(self, usuario):
        self.client.force_authenticate(usuario)

    def abrir(self):
        self.como(self.ana)
        return self.client.post(self.url).data

    def unir(self, usuario, enlace):
        self.como(usuario)
        return self.client.post(f'/api/v1/botes/{enlace}/unirse/')

    def grupo(self):
        enlace = self.abrir()['enlace_invitacion']
        self.unir(self.leo, enlace)
        self.como(self.ana)
        return {p['nombre']: p['id'] for p in self.client.get(self.url).data['participantes']}

    def gasto(self, ids, **cambios):
        datos = {'descripcion': 'Cena', 'concepto': 'comida', 'monto': '300.00',
                 'fecha': timezone.localdate().isoformat(), 'pagado_por': ids['Ana'], 'entre': list(ids.values()),
                 'destino': self.lugar.pk, **cambios}
        return self.client.post(self.url + 'gastos/', datos, format='json')


class InvitacionTests(BoteBase):
    def test_abrir_es_idempotente_y_quien_organiza_participa(self):
        enlace = self.abrir()['enlace_invitacion']
        self.assertEqual(self.client.post(self.url).data['enlace_invitacion'], enlace)
        self.assertEqual(self.viaje.participantes.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='bote_creado').count(), 1)

    def test_solo_quien_organiza_abre_o_revoca(self):
        self.como(self.leo)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.client.delete(self.url)
        self.assertFalse(self.viaje.participantes.exists())

    def test_unirse_avisa_y_no_duplica(self):
        enlace = self.abrir()['enlace_invitacion']
        self.assertEqual(self.unir(self.leo, enlace).data, {'viaje': self.viaje.pk})
        self.assertEqual(self.unir(self.leo, enlace).status_code, 200)
        self.assertEqual(self.viaje.participantes.count(), 2)
        self.assertEqual(Notificacion.objects.get(usuario=self.ana).enlace, f'/mis-viajes/{self.viaje.pk}/bote/')

    def test_revocar_impide_nuevas_uniones_y_conserva_al_grupo(self):
        enlace = self.abrir()['enlace_invitacion']
        self.unir(self.leo, enlace)
        self.como(self.ana)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertEqual(self.unir(self.eva, enlace).status_code, 404)
        self.assertEqual(self.client.get(f'/botes/{enlace}/').status_code, 404)
        self.como(self.leo)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_sin_sesion_no_se_une_y_la_invitacion_no_muestra_importes(self):
        ids = self.grupo()
        self.gasto(ids, monto='987.65')
        enlace = self.viaje.__class__.objects.get(pk=self.viaje.pk).enlace_bote
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f'/api/v1/botes/{enlace}/unirse/').status_code, 401)
        pagina = self.client.get(f'/botes/{enlace}/')
        self.assertContains(pagina, 'Con amigos')
        self.assertContains(pagina, 'noindex')
        self.assertNotContains(pagina, '987')
        self.assertNotContains(pagina, 'ana@example.com')

    def test_limite_de_personas(self):
        enlace = self.abrir()['enlace_invitacion']
        Participante.objects.bulk_create([
            Participante(viaje=self.viaje, usuario=Usuario.objects.create_user(f'u{i}@example.com', 'U', 'P', 'x'))
            for i in range(49)])
        self.assertEqual(self.unir(self.leo, enlace).status_code, 400)

    def test_mis_botes_incluye_donde_participo(self):
        enlace = self.abrir()['enlace_invitacion']
        self.unir(self.leo, enlace)
        datos = self.client.get('/api/v1/mis-botes/').data
        self.assertEqual([(b['nombre'], b['personas'], b['es_organizador']) for b in datos], [('Con amigos', 2, False)])
        self.como(self.eva)
        self.assertEqual(self.client.get('/api/v1/mis-botes/').data, [])


class GastosTests(BoteBase):
    def test_cuentas_del_grupo(self):
        ids = self.grupo()
        self.assertEqual(self.gasto(ids, monto='300.00').status_code, 201)
        self.como(self.leo)
        self.assertEqual(self.gasto(ids, monto='100.00', pagado_por=ids['Leo']).status_code, 201)
        estado = self.client.get(self.url).data
        self.assertEqual(estado['total'], '400.00')
        self.assertEqual(estado['transferencias'], [{'de': 'Leo', 'a': 'Ana', 'monto': '100.00'}])
        self.assertEqual({p['nombre']: p['saldo'] for p in estado['participantes']}, {'Ana': '100.00', 'Leo': '-100.00'})
        self.assertIsNone(estado['enlace_invitacion'])

    def test_ajeno_no_ve_ni_modifica(self):
        ids = self.grupo()
        pk = self.gasto(ids).data['id']
        self.como(self.eva)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.gasto(ids).status_code, 404)
        self.assertEqual(self.client.patch(f'{self.url}gastos/{pk}/', {'monto': '1'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(f'{self.url}gastos/{pk}/').status_code, 404)
        self.assertEqual(self.client.post(self.url + 'publicar/').status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_solo_quien_anoto_o_quien_organiza_edita(self):
        ids = self.grupo()
        pk = self.gasto(ids).data['id']
        self.como(self.leo)
        self.assertEqual(self.client.patch(f'{self.url}gastos/{pk}/', {'monto': '1'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'{self.url}gastos/{pk}/').status_code, 403)
        propio = self.gasto(ids).data['id']
        self.assertEqual(self.client.patch(f'{self.url}gastos/{propio}/', {'monto': '5'}, format='json').status_code, 200)
        self.como(self.ana)
        self.assertEqual(self.client.delete(f'{self.url}gastos/{propio}/').status_code, 204)

    def test_valores_invalidos(self):
        ids = self.grupo()
        otro = Viaje.objects.create(autor=self.eva, nombre='Otro', destino='X', personas=1, fecha_inicio='2026-01-01',
                                    fecha_fin='2026-01-01', presupuesto='1')
        ajeno = Participante.objects.create(viaje=otro, usuario=self.eva)
        lejos = Destino.objects.create(nombre='Otro', slug='otro', municipio=self.lugar.municipio, descripcion='-',
                                       latitud='19', longitud='-103')
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        for cambio in [{'monto': '0'}, {'monto': '-1'}, {'entre': []}, {'entre': [ajeno.pk]}, {'pagado_por': ajeno.pk},
                       {'fecha': manana}, {'destino': lejos.pk}, {'concepto': 'inventado'}, {'noches': 2},
                       {'descripcion': ''}]:
            self.assertEqual(self.gasto(ids, **cambio).status_code, 400, cambio)
        self.assertFalse(GastoReal.objects.exists())

    def test_salir_o_quitar_solo_sin_gastos(self):
        ids = self.grupo()
        pk = self.gasto(ids).data['id']
        persona = f"{self.url}participantes/{ids['Leo']}/"
        self.assertEqual(self.client.delete(persona).status_code, 400)
        self.assertEqual(self.client.delete(f"{self.url}participantes/{ids['Ana']}/").status_code, 400)
        self.client.delete(f'{self.url}gastos/{pk}/')
        self.como(self.leo)
        self.assertEqual(self.client.delete(f"{self.url}participantes/{ids['Ana']}/").status_code, 403)
        self.assertEqual(self.client.delete(persona).status_code, 204)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_eliminar_el_viaje_borra_el_bote(self):
        ids = self.grupo()
        self.gasto(ids)
        self.assertEqual(self.client.delete(f'/api/v1/mis-viajes/{self.viaje.pk}/').status_code, 204)
        self.assertFalse(Participante.objects.exists())
        self.assertFalse(GastoReal.objects.exists())


class PublicarTests(BoteBase):
    def publicar(self):
        return self.client.post(self.url + 'publicar/')

    def test_publica_por_persona_sin_nombre_y_pendiente(self):
        ids = self.grupo()
        self.gasto(ids, monto='100.00', descripcion='Cena con Leo Pérez')
        self.assertEqual(self.publicar().data, {'publicados': 1, 'omitidos': 0})
        aporte = Aporte.objects.get()
        self.assertEqual((aporte.estado, aporte.anonimo, aporte.monto, aporte.concepto, aporte.tipo),
                         ('pendiente', True, Decimal('50.00'), 'comida', 'gasto'))
        self.assertNotIn('Leo', aporte.texto)
        self.assertEqual(Evento.objects.filter(nombre='gasto_real_publicado', destino='tapalpa').count(), 1)

    def test_alojamiento_se_publica_por_noche(self):
        ids = self.grupo()
        self.gasto(ids, concepto='alojamiento', monto='3000.00', noches=2)
        self.publicar()
        self.assertEqual(Aporte.objects.get().monto, Decimal('1500.00'))

    def test_repetir_no_duplica_y_omite_lo_no_comparable(self):
        ids = self.grupo()
        self.gasto(ids)
        self.gasto(ids, concepto='otros')
        self.gasto(ids, destino=None)
        self.assertEqual(self.publicar().data, {'publicados': 1, 'omitidos': 2})
        self.assertEqual(self.publicar().data, {'publicados': 0, 'omitidos': 2})
        self.assertEqual(Aporte.objects.count(), 1)

    def test_solo_quien_organiza_publica(self):
        ids = self.grupo()
        self.gasto(ids)
        self.como(self.leo)
        self.assertEqual(self.publicar().status_code, 404)
        self.assertFalse(Aporte.objects.exists())

    def test_en_la_ficha_y_la_api_no_aparece_el_nombre(self):
        ids = self.grupo()
        self.gasto(ids)
        self.publicar()
        Aporte.objects.update(estado='publicado')
        self.client.force_authenticate(None)
        ficha = self.client.get('/destinos/tapalpa/')
        self.assertContains(ficha, 'Viajero anónimo')
        self.assertNotContains(ficha, '· Ana')
        api = self.client.get('/api/v1/destinos/tapalpa/aportes/').data['results'][0]
        self.assertEqual(api['autor_nombre'], 'Viajero anónimo')

    def test_alimenta_el_costo_del_destino(self):
        ids = self.grupo()
        for _ in range(3):
            self.gasto(ids, monto='200.00')
        self.publicar()
        Aporte.objects.update(estado='publicado')
        self.assertContains(self.client.get('/destinos/tapalpa/costos/'), '$100')


class BajaDeCuentaTests(BoteBase):
    def test_quien_se_va_de_un_bote_ajeno_queda_sin_datos_y_las_cuentas_cuadran(self):
        ids = self.grupo()
        self.como(self.leo)
        self.gasto(ids, pagado_por=ids['Leo'], descripcion='Gasolina de Leo', monto='100.00')
        anonimizar_cuenta(self.leo)
        self.como(self.ana)
        estado = self.client.get(self.url).data
        self.assertEqual({p['nombre'] for p in estado['participantes']}, {'Ana', 'Cuenta eliminada'})
        self.assertNotIn('Leo', estado['gastos'][0]['descripcion'])
        self.assertEqual(estado['transferencias'], [{'de': 'Ana', 'a': 'Cuenta eliminada', 'monto': '50.00'}])

    def test_quien_organiza_se_lleva_su_bote(self):
        self.grupo()
        anonimizar_cuenta(self.ana)
        self.assertFalse(Viaje.objects.exists())
        self.assertFalse(Participante.objects.exists())


class PaginasTests(BoteBase):
    def test_pagina_del_bote(self):
        pagina = self.client.get(self.url.removeprefix('/api/v1'))
        self.assertContains(pagina, 'js/bote.js')
        self.assertContains(pagina, f'data-viaje="{self.viaje.pk}"')
        self.assertContains(pagina, 'noindex')
