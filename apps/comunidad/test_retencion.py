"""Razones para volver: recordatorio tras el viaje, novedades en favoritos y control de los correos."""
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario
from apps.usuarios.sesion import token_baja_avisos
from .models import Aporte, Colaboracion, Favorito, Notificacion, Viaje
from .moderacion import moderar

CLAVE = 'Prueba-segura-493!'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PUBLIC_BASE_URL='https://infotrip.example')
class RetencionBase(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.viajera = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', CLAVE, es_verificado=True)
        self.moderador = Usuario.objects.create_superuser('mod@example.com', 'Mod', 'P', CLAVE)
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-',
                                              latitud=20, longitud=-103)

    def enviar(self):
        call_command('enviar_avisos', stdout=StringIO())

    def viaje(self, dias_desde_el_fin, lugares=()):
        fin = self.hoy - timedelta(days=dias_desde_el_fin)
        viaje = Viaje.objects.create(autor=self.viajera, nombre='Fin de semana', destino='Tapalpa', fecha_inicio=fin,
                                     fecha_fin=fin, personas=1, presupuesto=1)
        viaje.lugares.set(lugares)
        return viaje


class RecordatorioTrasElViajeTests(RetencionBase):
    def test_invita_una_sola_vez_con_enlace_al_lugar(self):
        viaje = self.viaje(2, [self.destino])
        self.enviar()
        self.enviar()
        self.assertEqual(len(mail.outbox), 1)
        cuerpo = mail.outbox[0].body
        self.assertIn('¿Cómo te fue en «Fin de semana»?', cuerpo)
        self.assertIn('https://infotrip.example/destinos/tapalpa/?ref=aviso', cuerpo)
        viaje.refresh_from_db()
        self.assertIsNotNone(viaje.recordatorio_enviado)
        self.assertEqual(Notificacion.objects.get().enlace, '/destinos/tapalpa/')

    def test_solo_viajes_recien_terminados(self):
        self.viaje(0)
        self.viaje(-5)
        self.viaje(30)
        self.enviar()
        self.assertFalse(Notificacion.objects.exists())

    def test_sin_lugares_enlaza_a_mis_viajes(self):
        self.viaje(1)
        self.enviar()
        self.assertEqual(Notificacion.objects.get().enlace, '/mis-viajes/')


class NovedadesEnFavoritosTests(RetencionBase):
    def setUp(self):
        super().setUp()
        self.autora = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', CLAVE)
        Favorito.objects.create(autor=self.viajera, destino=self.destino)
        Favorito.objects.create(autor=self.autora, destino=self.destino)

    def dato(self, campo='acceso'):
        return Colaboracion.objects.create(destino=self.destino, autor=self.autora, tipo='correccion', campo=campo,
                                           texto='T', fuente='F', fecha_dato=self.hoy)

    def test_avisa_a_quien_lo_guardo_pero_no_a_quien_lo_aporto(self):
        moderar(self.dato(), self.moderador, 'publicado', 'Revisado')
        avisos = Notificacion.objects.filter(usuario=self.viajera)
        self.assertEqual(avisos.get().texto, 'Hay información nueva sobre Tapalpa, uno de tus lugares guardados.')
        self.assertFalse(Notificacion.objects.filter(usuario=self.autora, texto__startswith='Hay información').exists())

    def test_como_mucho_un_aviso_por_semana(self):
        moderar(self.dato('acceso'), self.moderador, 'publicado', 'Revisado')
        moderar(self.dato('pago'), self.moderador, 'publicado', 'Revisado')
        self.assertEqual(Notificacion.objects.filter(usuario=self.viajera).count(), 1)
        Notificacion.objects.update(creado=timezone.now() - timedelta(days=8))
        moderar(self.dato('contacto'), self.moderador, 'publicado', 'Revisado')
        self.assertEqual(Notificacion.objects.filter(usuario=self.viajera).count(), 2)

    def test_ocultar_o_una_pregunta_no_avisa(self):
        moderar(self.dato(), self.moderador, 'oculto', 'No')
        pregunta = Colaboracion.objects.create(destino=self.destino, autor=self.autora, tipo='pregunta', texto='¿?')
        moderar(pregunta, self.moderador, 'publicado', 'Revisado')
        self.assertFalse(Notificacion.objects.filter(usuario=self.viajera).exists())

    def test_una_resena_si_avisa(self):
        resena = Aporte.objects.create(destino=self.destino, autor=self.autora, tipo='resena', texto='Bien',
                                       calificacion=5, fecha_visita=self.hoy)
        moderar(resena, self.moderador, 'publicado', 'Revisado')
        self.assertTrue(Notificacion.objects.filter(usuario=self.viajera).exists())


class BajaDeCorreosTests(RetencionBase):
    def test_sin_correos_no_se_envian_pero_el_aviso_sigue_en_el_perfil(self):
        Usuario.objects.filter(pk=self.viajera.pk).update(avisos_correo=False)
        Notificacion.objects.create(usuario=self.viajera, texto='Aviso', correo_pendiente=True)
        self.enviar()
        self.assertEqual(mail.outbox, [])
        aviso = Notificacion.objects.get()
        self.assertFalse(aviso.correo_pendiente)

    def test_el_correo_trae_un_enlace_que_pide_confirmar_y_luego_da_de_baja(self):
        Notificacion.objects.create(usuario=self.viajera, texto='Aviso', correo_pendiente=True)
        self.enviar()
        token = token_baja_avisos(self.viajera)
        self.assertIn(f'https://infotrip.example/baja-avisos/?t={token}', mail.outbox[0].body)
        pagina = self.client.get('/baja-avisos/', {'t': token})
        self.assertContains(pagina, 'Dejar de recibirlos')
        self.viajera.refresh_from_db()
        self.assertTrue(self.viajera.avisos_correo)  # Abrir el enlace no basta: un antivirus puede hacerlo.
        self.assertContains(self.client.post('/baja-avisos/', {'t': token}), 'ya no te enviaremos')
        self.viajera.refresh_from_db()
        self.assertFalse(self.viajera.avisos_correo)

    def test_enlace_alterado_no_cambia_nada(self):
        self.assertContains(self.client.post('/baja-avisos/', {'t': 'alterado'}), 'no es válido')
        self.viajera.refresh_from_db()
        self.assertTrue(self.viajera.avisos_correo)

    def test_se_cambia_desde_el_perfil(self):
        self.client.force_login(self.viajera)
        self.assertContains(self.client.get('/perfil/'), 'name="avisos_correo"')
