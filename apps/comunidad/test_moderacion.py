"""Moderación unificada (recomendación 6): moderar() y la migración que conserva el historial."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario
from .models import Aporte, Colaboracion, Decision, RevisionColaboracion
from .moderacion import moderar


class ModerarTests(TestCase):
    def setUp(self):
        self.autor = Usuario.objects.create_user('autor@example.com', 'Ana', 'Prueba', 'Clave-segura-483!')
        self.moderador = Usuario.objects.create_superuser('mod@example.com', 'Leo', 'Prueba', 'Clave-segura-483!')
        region = Region.objects.create(nombre='Región', slug='region')
        municipio = Municipio.objects.create(nombre='Municipio', slug='municipio', region=region)
        self.destino = Destino.objects.create(nombre='Destino', slug='destino', municipio=municipio,
                                              descripcion='Lugar', latitud=20, longitud=-103)

    def aporte(self, **cambios):
        datos = dict(autor=self.autor, destino=self.destino, tipo='resena', texto='Reseña',
                     fecha_visita=timezone.localdate(), calificacion=4)
        return Aporte.objects.create(**{**datos, **cambios})

    def colaboracion(self):
        return Colaboracion.objects.create(autor=self.autor, destino=self.destino, tipo='pregunta', texto='¿Abre hoy?')

    def test_misma_regla_y_mismo_historial_para_aportes_y_colaboraciones(self):
        for objeto, historial in [(self.aporte(), Decision), (self.colaboracion(), RevisionColaboracion)]:
            with self.subTest(modelo=type(objeto).__name__):
                self.assertTrue(moderar(objeto, self.moderador, 'publicado', 'Revisado'))
                objeto.refresh_from_db()
                self.assertEqual(objeto.estado, 'publicado')
                registro = historial.objects.get()
                self.assertEqual((registro.moderador, registro.estado_anterior, registro.estado_nuevo, registro.motivo),
                                 (self.moderador, 'pendiente', 'publicado', 'Revisado'))

    def test_sin_cambio_no_registra_salvo_que_se_pida(self):
        aporte = self.aporte(estado='publicado')
        self.assertFalse(moderar(aporte, self.moderador, 'publicado', 'Repetido'))
        self.assertFalse(Decision.objects.exists())
        self.assertFalse(moderar(aporte, self.moderador, 'publicado', 'Reporte desestimado', registrar_sin_cambio=True))
        self.assertEqual(Decision.objects.get().estado_nuevo, 'publicado')

    def test_aporte_retirado_no_se_modera(self):
        aporte = self.aporte(estado='retirado')
        self.assertFalse(moderar(aporte, self.moderador, 'publicado', 'Intento'))
        aporte.refresh_from_db()
        self.assertEqual(aporte.estado, 'retirado')
        self.assertFalse(Decision.objects.exists())

    def test_motivo_de_colaboracion_admite_hasta_1000_caracteres(self):
        moderar(self.colaboracion(), self.moderador, 'oculto', 'x' * 1000)
        self.assertEqual(len(RevisionColaboracion.objects.get().motivo), 1000)


class MigracionHistorialTests(TransactionTestCase):
    """Aplica 0004 sobre datos creados con el esquema anterior y comprueba que no se pierde nada."""
    antes = [('comunidad', '0003_viaje_actividades_viaje_lugares_viaje_notas_and_more')]
    despues = [('comunidad', '0004_registro_moderacion_unificado')]

    def migrar(self, objetivo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(objetivo)
        return executor.loader.project_state(objetivo).apps

    def tearDown(self):
        # Deja la base en la última migración para las demás pruebas.
        self.migrar(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_historial_se_conserva_al_aplicar_y_revertir(self):
        apps = self.migrar(self.antes)
        Usuario = apps.get_model('usuarios', 'Usuario')
        Region, Municipio = apps.get_model('destinos', 'Region'), apps.get_model('destinos', 'Municipio')
        Destino = apps.get_model('destinos', 'Destino')
        Colaboracion = apps.get_model('comunidad', 'Colaboracion')
        Revision = apps.get_model('comunidad', 'RevisionColaboracion')
        usuario = Usuario.objects.create(email='historial@example.com', nombre='Ana', apellido='Prueba')
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-', latitud=20, longitud=-103)
        item = Colaboracion.objects.create(destino=destino, autor=usuario, tipo='pregunta', texto='¿?', estado='oculto')
        original = Revision.objects.create(colaboracion=item, moderador=usuario, anterior='pendiente', nuevo='oculto',
                                           motivo='Motivo previo')

        apps = self.migrar(self.despues)
        revision = apps.get_model('comunidad', 'RevisionColaboracion').objects.get()
        self.assertEqual((revision.pk, revision.estado_anterior, revision.estado_nuevo, revision.motivo, revision.creado),
                         (original.pk, 'pendiente', 'oculto', 'Motivo previo', original.creado))

        apps = self.migrar(self.antes)
        revision = apps.get_model('comunidad', 'RevisionColaboracion').objects.get()
        self.assertEqual((revision.anterior, revision.nuevo, revision.motivo), ('pendiente', 'oculto', 'Motivo previo'))
