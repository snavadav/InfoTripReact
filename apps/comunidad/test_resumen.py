from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from apps.comunidad.management.commands.crear_moderacion import GRUPO
from apps.comunidad.models import Comentario
from apps.datos.models import EjecucionTarea
from apps.usuarios.models import Usuario


class ResumenModeracionTests(TestCase):
    def setUp(self):
        cache.clear()
        hora = mock.patch('apps.comunidad.management.commands.resumen_moderacion.HORA_MINIMA', 0)
        hora.start()
        self.addCleanup(hora.stop)
        self.moderadora = Usuario.objects.create_user('moderadora@example.com', 'Mode', 'Radora', 'clave-segura-123')
        self.moderadora.groups.add(Group.objects.create(name=GRUPO))
        Usuario.objects.create_user('viajero@example.com', 'Via', 'Jero', 'clave-segura-123')

    def correr(self, **opciones):
        salida = StringIO()
        call_command('resumen_moderacion', stdout=salida, **opciones)
        return salida.getvalue()

    def test_sin_pendientes_no_envia(self):
        self.assertIn('Nada pendiente', self.correr())
        self.assertEqual(mail.outbox, [])

    def test_envia_totales_solo_al_equipo_y_una_vez_al_dia(self):
        Comentario.objects.create(tipo='idea', texto='Texto privado de una persona')
        Comentario.objects.create(tipo='problema', texto='Otro texto')
        self.assertIn('Resumen enviado a 1 personas', self.correr())
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['moderadora@example.com'])
        self.assertEqual(correo.subject, 'InfoTrip: 2 por revisar')
        self.assertIn('Comentarios del sitio sin atender: 2', correo.body)
        self.assertIn('/admin/moderacion/', correo.body)
        # Solo totales: nada de lo que escribió la comunidad sale por correo.
        self.assertNotIn('Texto privado', correo.body)
        self.assertIn('ya se envió', self.correr())
        self.assertEqual(len(mail.outbox), 1)
        self.correr(forzar=True)
        self.assertEqual(len(mail.outbox), 2)

    def test_de_madrugada_espera(self):
        Comentario.objects.create(tipo='idea', texto='Algo')
        with mock.patch('apps.comunidad.management.commands.resumen_moderacion.HORA_MINIMA', 25):
            self.assertIn('no se envía', self.correr())
        self.assertEqual(mail.outbox, [])
        # No gastó el envío del día: a su hora sí sale.
        self.correr()
        self.assertEqual(len(mail.outbox), 1)

    def test_avisa_de_tareas_con_error(self):
        EjecucionTarea.objects.create(tarea='osm', resultado='error', mensaje='fallo')
        self.correr()
        self.assertEqual(mail.outbox[0].subject, 'InfoTrip: fallos en tareas o correos')
        self.assertIn('Tareas programadas con error: 1', mail.outbox[0].body)

    def test_superusuario_inactivo_no_recibe(self):
        Usuario.objects.create_superuser('jefa@example.com', 'Je', 'Fa', 'clave-segura-123')
        inactivo = Usuario.objects.create_superuser('fuera@example.com', 'Fue', 'Ra', 'clave-segura-123')
        inactivo.es_activo = False
        inactivo.save()
        Comentario.objects.create(tipo='idea', texto='Algo')
        self.correr()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['jefa@example.com', 'moderadora@example.com'])
