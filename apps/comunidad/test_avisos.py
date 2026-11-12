"""Módulo de avisos: tipos, preferencias, privacidad, recordatorios programados y envío por correo."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.amigos.models import Bloqueo
from apps.usuarios.models import Usuario
from .avisos_programados import (agenda_de_hoy, cuentas_por_saldar, generar, pagos_sin_confirmar,
                                 viajes_pronto)
from .models import GastoReal, Notificacion, PagoEntreParticipantes, Participante, Viaje
from .notificar import avisar, con_aviso, visibles

HOY = date(2026, 11, 11)  # miércoles
CLAVE = 'Prueba-segura-493!'


def usuario(nombre, **extra):
    return Usuario.objects.create_user(f'{nombre.lower()}@example.com', nombre, 'P', CLAVE, es_verificado=True,
                                       username=nombre.lower(), **extra)


def a_las(hora, dia=HOY):
    return timezone.make_aware(datetime.combine(dia, datetime.min.time()).replace(hour=hora))


class EnlaceTests(SimpleTestCase):
    def test_agrega_el_aviso_antes_del_ancla(self):
        self.assertEqual(con_aviso('/mis-viajes/3/bote/#cuentas', 7), '/mis-viajes/3/bote/?aviso=7#cuentas')
        self.assertEqual(con_aviso('/mis-viajes/?abrir=3', 7, ref=True), '/mis-viajes/?abrir=3&ref=aviso&aviso=7')


class AvisarTests(TestCase):
    def setUp(self):
        self.ana, self.leo = usuario('Ana'), usuario('Leo')

    def test_crea_con_tipo_actor_y_correo_pendiente(self):
        aviso = avisar(self.ana, 'pago', 'Te pagaron', '/x/', actor=self.leo)
        self.assertEqual((aviso.tipo, aviso.actor, aviso.correo_pendiente), ('pago', self.leo, True))

    def test_tipo_silenciado_no_se_crea(self):
        self.ana.avisos_silenciados = ['pago']
        self.ana.save()
        self.assertIsNone(avisar(self.ana, 'pago', 'Te pagaron'))
        self.assertFalse(Notificacion.objects.exists())

    def test_sin_correo_por_tipo_o_en_general(self):
        self.ana.avisos_sin_correo = ['pago']
        self.ana.save()
        self.assertFalse(avisar(self.ana, 'pago', 'a').correo_pendiente)
        self.assertTrue(avisar(self.ana, 'bote', 'b').correo_pendiente)
        self.assertFalse(avisar(self.ana, 'pasaporte', 'c').correo_pendiente)  # Solo dentro de InfoTrip.
        self.ana.avisos_correo = False
        self.ana.save()
        self.assertFalse(avisar(self.ana, 'bote', 'd').correo_pendiente)

    def test_la_clave_evita_duplicados(self):
        self.assertIsNotNone(avisar(self.ana, 'viaje_pronto', 'a', clave='viaje_pronto:1:x'))
        self.assertIsNone(avisar(self.ana, 'viaje_pronto', 'a', clave='viaje_pronto:1:x'))
        self.assertIsNotNone(avisar(self.leo, 'viaje_pronto', 'a', clave='viaje_pronto:1:x'))
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_no_avisa_si_hay_bloqueo_en_cualquier_direccion(self):
        Bloqueo.objects.create(de=self.leo, para=self.ana)
        self.assertIsNone(avisar(self.ana, 'amistad', 'x', actor=self.leo))
        self.assertIsNone(avisar(self.leo, 'amistad', 'x', actor=self.ana))

    def test_un_bloqueo_posterior_oculta_el_aviso_y_su_correo(self):
        avisar(self.ana, 'pago', '@leo te pagó', actor=self.leo)
        avisar(self.ana, 'viaje_pronto', 'Tu escapada')
        Bloqueo.objects.create(de=self.leo, para=self.ana)
        self.assertEqual([a.texto for a in visibles(self.ana)], ['Tu escapada'])
        call_command('enviar_avisos', stdout=StringIO())
        self.assertEqual([m.subject for m in mail.outbox], ['Tu escapada se acerca'])

    def test_actor_dado_de_baja_oculta_el_aviso(self):
        avisar(self.ana, 'pago', '@leo te pagó', actor=self.leo)
        self.leo.es_activo = False
        self.leo.save()
        self.assertFalse(visibles(self.ana).exists())


class ApiAvisosTests(APITestCase):
    def setUp(self):
        self.ana, self.leo = usuario('Ana'), usuario('Leo')
        self.client.force_authenticate(self.ana)

    def test_lista_con_accion_y_oculta_bloqueados(self):
        avisar(self.ana, 'pago', '@leo te pagó', '/mis-viajes/1/bote/#cuentas', actor=self.leo)
        avisar(self.ana, 'viaje_pronto', 'Tu escapada', '/mis-viajes/?abrir=1')
        datos = self.client.get('/api/v1/notificaciones/').data
        self.assertEqual(datos['no_leidas'], 2)
        self.assertEqual({a['tipo']: a['accion'] for a in datos['results']},
                         {'pago': 'Confirmar pago', 'viaje_pronto': 'Ver escapada'})
        Bloqueo.objects.create(de=self.ana, para=self.leo)
        datos = self.client.get('/api/v1/notificaciones/').data
        self.assertEqual((datos['no_leidas'], len(datos['results'])), (1, 1))

    def test_marca_uno_como_leido(self):
        uno = avisar(self.ana, 'bote', 'a')
        avisar(self.ana, 'bote', 'b')
        respuesta = self.client.post(f'/api/v1/notificaciones/{uno.pk}/leida/')
        self.assertEqual(respuesta.data, {'no_leidas': 1})
        uno.refresh_from_db()
        self.assertTrue(uno.leida)

    def test_no_marca_avisos_de_otra_persona(self):
        ajeno = avisar(self.leo, 'bote', 'a')
        self.assertEqual(self.client.post(f'/api/v1/notificaciones/{ajeno.pk}/leida/').status_code, 404)
        ajeno.refresh_from_db()
        self.assertFalse(ajeno.leida)

    def test_preferencias(self):
        datos = self.client.get('/api/v1/notificaciones/preferencias/').data
        self.assertTrue(datos['correo'])
        self.assertIn('viaje_pronto', [t['tipo'] for t in datos['tipos']])
        pendiente = avisar(self.ana, 'lugares', 'Novedad')
        respuesta = self.client.put('/api/v1/notificaciones/preferencias/', {
            'correo': True, 'silenciados': ['viaje_hoy'], 'sin_correo': ['lugares'],
        }, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.ana.refresh_from_db()
        self.assertEqual((self.ana.avisos_silenciados, self.ana.avisos_sin_correo), (['viaje_hoy'], ['lugares']))
        pendiente.refresh_from_db()
        self.assertFalse(pendiente.correo_pendiente)

    def test_preferencias_rechazan_tipos_desconocidos(self):
        respuesta = self.client.put('/api/v1/notificaciones/preferencias/', {
            'correo': True, 'silenciados': ['inventado'], 'sin_correo': [],
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)


class EscapadaBase(TestCase):
    def setUp(self):
        self.ana, self.leo, self.eva = usuario('Ana'), usuario('Leo'), usuario('Eva')
        self.viaje = Viaje.objects.create(
            autor=self.ana, nombre='Tapalpa', destino='Tapalpa', personas=3, presupuesto='3000',
            fecha_inicio=HOY + timedelta(days=3), fecha_fin=HOY + timedelta(days=5),
            pendientes=[{'texto': 'Reservar cabaña', 'hecho': False}, {'texto': 'Gasolina', 'hecho': True}],
            actividades=[{'dia': 1, 'hora': '09:00', 'titulo': 'Salir de Guadalajara', 'notas': ''},
                         {'dia': 1, 'hora': '12:30', 'titulo': 'Las Piedrotas', 'notas': 'privado'},
                         {'dia': 2, 'hora': '', 'titulo': 'Presa del Nogal', 'notas': ''}])
        self.p_ana = Participante.objects.create(viaje=self.viaje, usuario=self.ana)
        self.p_leo = Participante.objects.create(viaje=self.viaje, usuario=self.leo)

    def avisos(self, tipo):
        return Notificacion.objects.filter(tipo=tipo).order_by('usuario__nombre')


class EscapadaProntoTests(EscapadaBase):
    def test_avisa_a_quien_organiza_y_al_bote_una_sola_vez(self):
        self.assertEqual(viajes_pronto(HOY), 2)
        self.assertEqual(viajes_pronto(HOY), 0)
        ana, leo = self.avisos('viaje_pronto').get(usuario=self.ana), self.avisos('viaje_pronto').get(usuario=self.leo)
        self.assertIn('empieza en 3 días, el sábado 14 de noviembre', ana.texto)
        self.assertIn('Reservar cabaña', ana.texto)
        self.assertNotIn('Gasolina', ana.texto)
        self.assertEqual(ana.enlace, f'/mis-viajes/?abrir={self.viaje.pk}')
        # Los pendientes son de quien organiza; al bote solo le llega la fecha.
        self.assertNotIn('cabaña', leo.texto)
        self.assertEqual(leo.enlace, f'/mis-viajes/{self.viaje.pk}/bote/')

    def test_manana_y_fuera_de_la_ventana(self):
        self.assertEqual(viajes_pronto(HOY - timedelta(days=1)), 0)  # Faltan 4 días.
        viajes_pronto(HOY + timedelta(days=2))
        self.assertIn('empieza mañana', self.avisos('viaje_pronto').first().texto)

    def test_si_cambia_la_fecha_vuelve_a_avisar(self):
        viajes_pronto(HOY)
        Viaje.objects.filter(pk=self.viaje.pk).update(fecha_inicio=HOY + timedelta(days=2),
                                                     fecha_fin=HOY + timedelta(days=4))
        self.assertEqual(viajes_pronto(HOY), 2)

    def test_no_avisa_al_bote_si_quien_organiza_lo_bloqueo(self):
        Bloqueo.objects.create(de=self.ana, para=self.leo)
        viajes_pronto(HOY)
        self.assertEqual(list(self.avisos('viaje_pronto').values_list('usuario', flat=True)), [self.ana.pk])

    def test_respeta_el_silencio_del_tipo(self):
        self.leo.avisos_silenciados = ['viaje_pronto']
        self.leo.save()
        self.assertEqual(viajes_pronto(HOY), 1)


class AgendaDeHoyTests(EscapadaBase):
    def test_primer_dia_con_horas_sin_notas(self):
        self.assertEqual(agenda_de_hoy(HOY + timedelta(days=3)), 1)
        aviso = self.avisos('viaje_hoy').get()
        self.assertEqual(aviso.usuario, self.ana)
        self.assertIn('(día 1 de 3)', aviso.texto)
        self.assertIn('09:00 Salir de Guadalajara, 12:30 Las Piedrotas', aviso.texto)
        self.assertNotIn('privado', aviso.texto)
        self.assertEqual(agenda_de_hoy(HOY + timedelta(days=3)), 0)

    def test_cada_dia_el_suyo_y_nada_sin_actividades(self):
        self.assertEqual(agenda_de_hoy(HOY + timedelta(days=4)), 1)
        self.assertEqual(agenda_de_hoy(HOY + timedelta(days=5)), 0)  # El día 3 no tiene actividades.
        self.assertEqual(agenda_de_hoy(HOY), 0)  # Todavía no empieza.


class CuentasYPagosTests(EscapadaBase):
    def setUp(self):
        super().setUp()
        self.p_eva = Participante.objects.create(viaje=self.viaje, usuario=self.eva)
        gasto = GastoReal.objects.create(viaje=self.viaje, pagado_por=self.p_ana, registrado_por=self.ana,
                                         descripcion='Cabaña', concepto='alojamiento', monto=Decimal('900'),
                                         fecha=HOY)
        gasto.entre.set([self.p_ana, self.p_leo, self.p_eva])
        self.fin = self.viaje.fecha_fin + timedelta(days=1)

    def test_avisa_a_quien_debe_sin_nombrar_a_nadie(self):
        self.assertEqual(cuentas_por_saldar(self.fin), 2)
        self.assertEqual(cuentas_por_saldar(self.fin), 0)
        avisos = self.avisos('cuentas')
        self.assertEqual({a.usuario for a in avisos}, {self.leo, self.eva})
        self.assertIn('te quedan $300.00 por pagar', avisos[0].texto)
        self.assertNotIn('Ana', avisos[0].texto)
        self.assertTrue(avisos[0].enlace.endswith('/bote/#cuentas'))

    def test_quien_ya_registro_su_pago_no_recibe_recordatorio(self):
        PagoEntreParticipantes.objects.create(viaje=self.viaje, de=self.p_leo, para=self.p_ana,
                                              monto=Decimal('300'), fecha=HOY)
        cuentas_por_saldar(self.fin)
        self.assertEqual([a.usuario for a in self.avisos('cuentas')], [self.eva])

    def test_ni_antes_de_terminar_ni_mucho_despues(self):
        self.assertEqual(cuentas_por_saldar(self.viaje.fecha_fin), 0)
        self.assertEqual(cuentas_por_saldar(self.fin + timedelta(days=8)), 0)

    def test_pago_sin_confirmar_se_recuerda_una_vez(self):
        pago = PagoEntreParticipantes.objects.create(viaje=self.viaje, de=self.p_leo, para=self.p_ana,
                                                     monto=Decimal('300'), fecha=HOY)
        ahora = timezone.now()
        self.assertEqual(pagos_sin_confirmar(ahora), 0)  # Recién registrado.
        tarde = ahora + timedelta(days=3, minutes=1)
        self.assertEqual(pagos_sin_confirmar(tarde), 1)
        self.assertEqual(pagos_sin_confirmar(tarde), 0)
        aviso = self.avisos('pago').get()
        self.assertEqual((aviso.usuario, aviso.actor), (self.ana, self.leo))
        self.assertIn('$300', aviso.texto)
        pago.confirmado = True
        pago.save()

    def test_pago_confirmado_no_se_recuerda(self):
        PagoEntreParticipantes.objects.create(viaje=self.viaje, de=self.p_leo, para=self.p_ana,
                                              monto=Decimal('300'), fecha=HOY, confirmado=True)
        self.assertEqual(pagos_sin_confirmar(timezone.now() + timedelta(days=4)), 0)


class HorarioYComandoTests(EscapadaBase):
    def test_de_madrugada_no_crea_recordatorios_de_escapada(self):
        creados = generar(a_las(3))
        self.assertNotIn('viaje_pronto', creados)
        self.assertFalse(self.avisos('viaje_pronto').exists())
        self.assertEqual(generar(a_las(3), forzar=True)['viaje_pronto'], 2)

    def test_la_agenda_solo_por_la_manana(self):
        dia = HOY + timedelta(days=3)
        self.assertNotIn('viaje_hoy', generar(a_las(15, dia)))
        self.assertEqual(generar(a_las(7, dia))['viaje_hoy'], 1)

    @override_settings(PUBLIC_BASE_URL='https://infotrip.test')
    def test_comando_con_fecha_y_forzar_crea_y_envia_sin_duplicar(self):
        salida = StringIO()
        call_command('enviar_avisos', '--forzar', '--fecha', HOY.isoformat(), stdout=salida)
        self.assertIn('viaje_pronto 2', salida.getvalue())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['ana@example.com', 'leo@example.com'])
        correo = next(m for m in mail.outbox if m.to == ['ana@example.com'])
        self.assertEqual(correo.subject, 'Tu escapada se acerca')
        aviso = Notificacion.objects.get(usuario=self.ana)
        self.assertIn(f'Ver escapada: https://infotrip.test/mis-viajes/?abrir={self.viaje.pk}&ref=aviso&aviso={aviso.pk}',
                      correo.body)
        self.assertIn('/perfil/#avisos-preferencias', correo.body)
        call_command('enviar_avisos', '--forzar', '--fecha', HOY.isoformat(), stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_sin_correo_por_tipo_no_envia(self):
        self.ana.avisos_sin_correo = ['viaje_pronto']
        self.ana.save()
        call_command('enviar_avisos', '--forzar', '--fecha', HOY.isoformat(), stdout=StringIO())
        self.assertEqual([m.to for m in mail.outbox], [['leo@example.com']])
        self.assertTrue(Notificacion.objects.filter(usuario=self.ana).exists())


class AvisosDeAmigosYBoteTests(APITestCase):
    def setUp(self):
        self.ana, self.leo = usuario('Ana'), usuario('Leo')

    def test_solicitud_y_aceptacion(self):
        self.client.force_authenticate(self.ana)
        self.client.post('/api/v1/amigos/solicitudes/', {'username': 'leo'}, format='json')
        aviso = Notificacion.objects.get(usuario=self.leo)
        self.assertEqual((aviso.tipo, aviso.actor, aviso.enlace), ('amistad', self.ana, '/amigos/#recibidas-titulo'))
        self.assertTrue(aviso.correo_pendiente)
        self.client.force_authenticate(self.leo)
        solicitud = self.client.get('/api/v1/amigos/').data['recibidas'][0]['solicitud']
        self.client.post(f'/api/v1/amigos/solicitudes/{solicitud}/aceptar/')
        self.assertEqual(Notificacion.objects.get(usuario=self.ana).tipo, 'amistad')

    def test_pago_registrado_pide_confirmar(self):
        viaje = Viaje.objects.create(autor=self.ana, nombre='Mazamitla', destino='Mazamitla', personas=2,
                                     presupuesto='0', fecha_inicio=HOY, fecha_fin=HOY)
        Participante.objects.create(viaje=viaje, usuario=self.ana)
        para = Participante.objects.create(viaje=viaje, usuario=self.leo)
        self.client.force_authenticate(self.ana)
        self.client.post(f'/api/v1/mis-viajes/{viaje.pk}/bote/pagos/', {'para': para.pk, 'monto': '150'},
                         format='json')
        aviso = Notificacion.objects.get(usuario=self.leo)
        self.assertEqual((aviso.tipo, aviso.actor, aviso.correo_pendiente), ('pago', self.ana, True))
        self.assertIn('Confírmalo', aviso.texto)


class EliminarCuentaTests(TestCase):
    def test_borra_los_avisos_que_provoco(self):
        from .cuenta import anonimizar_cuenta
        ana, leo = usuario('Ana'), usuario('Leo')
        avisar(ana, 'pago', '@leo te pagó', actor=leo)
        avisar(ana, 'viaje_pronto', 'Tu escapada')
        anonimizar_cuenta(leo)
        self.assertEqual(list(Notificacion.objects.values_list('texto', flat=True)), ['Tu escapada'])
