from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.comunidad.models import Aporte, Comentario, Notificacion, Reporte
from apps.datos.models import EjecucionTarea
from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario

CLAVE = 'Clave-segura-483!'


class SaludYListasDelAdminTests(TestCase):
    def setUp(self):
        self.jefa = Usuario.objects.create_superuser('jefa@example.com', 'Je', 'Fa', CLAVE)
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='Mirador', slug='mirador', municipio=municipio, descripcion='-',
                                              latitud=20, longitud=-103)
        self.client.force_login(self.jefa)

    def test_inicio_del_admin_muestra_cola_correos_y_tareas(self):
        viejo = Comentario.objects.create(tipo='idea', texto='Algo')
        Comentario.objects.filter(pk=viejo.pk).update(creado=timezone.now() - timedelta(days=3, hours=1))
        Notificacion.objects.create(usuario=self.jefa, texto='x', correo_intentos=Notificacion.MAX_INTENTOS_CORREO)
        corrida = EjecucionTarea.objects.create(tarea='osm', resultado='error', mensaje='fallo')
        respuesta = self.client.get('/admin/')
        self.assertContains(respuesta, 'Estado del sitio')
        self.assertContains(respuesta, 'lo más antiguo espera desde hace 3 días')
        self.assertContains(respuesta, f'/admin/datos/ejecuciontarea/{corrida.pk}/change/')
        self.assertContains(respuesta, 'Aún no ha corrido')
        # La lista de apps de Django sigue debajo.
        self.assertContains(respuesta, '/admin/comunidad/aporte/')

    def test_cola_vacia_no_inventa_antiguedad(self):
        respuesta = self.client.get('/admin/')
        self.assertContains(respuesta, 'Estado del sitio')
        self.assertNotContains(respuesta, 'lo más antiguo')

    def test_metricas_con_fichas_mas_vistas_y_periodo_anterior(self):
        for _ in range(3):
            Evento.objects.create(nombre='ficha_vista', destino='mirador')
        Evento.objects.create(nombre='ficha_vista', destino='ya-no-existe')
        antiguo = Evento.objects.create(nombre='ficha_vista', destino='mirador')
        Evento.objects.filter(pk=antiguo.pk).update(creado=timezone.now() - timedelta(days=45))
        Comentario.objects.create(tipo='idea', texto='Algo')
        contexto = self.client.get('/admin/metricas/').context
        self.assertEqual(contexto['mas_vistos'][0], {'slug': 'mirador', 'nombre': 'Mirador', 'total': 3})
        fila = next(e for e in contexto['eventos'] if e['nombre'] == 'ficha_vista')
        self.assertEqual((fila['dias_30'], fila['previos_30']), (4, 1))
        self.assertEqual(contexto['en_cola'], 1)

    def test_lista_de_reportes_no_consulta_por_fila(self):
        autor = Usuario.objects.create_user('a@example.com', 'Ana', 'P', CLAVE)

        def reportar(n):
            for i in range(n):
                persona = Usuario.objects.create_user(f'r{Usuario.objects.count()}@example.com', 'R', 'P', CLAVE)
                aporte = Aporte.objects.create(autor=autor, destino=self.destino, tipo='gasto', texto=f't{i}',
                                               fecha_visita=timezone.localdate(), monto=1, concepto='comida',
                                               estado='publicado')
                Reporte.objects.create(aporte=aporte, autor=persona, motivo='m')

        reportar(2)
        con_dos = len(self.consultas('/admin/comunidad/reporte/'))
        reportar(6)
        self.assertEqual(len(self.consultas('/admin/comunidad/reporte/')), con_dos)

    def consultas(self, ruta):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as capturadas:
            self.assertEqual(self.client.get(ruta).status_code, 200)
        return capturadas.captured_queries

    def test_desactivar_cuentas_no_toca_superusuarios_ni_la_propia(self):
        persona = Usuario.objects.create_user('p@example.com', 'Pe', 'P', CLAVE)
        self.client.post('/admin/usuarios/usuario/', {
            'action': 'desactivar', '_selected_action': [persona.pk, self.jefa.pk]}, follow=True)
        persona.refresh_from_db()
        self.jefa.refresh_from_db()
        self.assertFalse(persona.es_activo)
        self.assertTrue(self.jefa.es_activo)

    def test_ocultar_destinos_deja_constancia_en_el_historial(self):
        from django.contrib.admin.models import LogEntry
        self.client.post('/admin/destinos/destino/', {
            'action': 'ocultar', '_selected_action': [self.destino.pk]}, follow=True)
        self.destino.refresh_from_db()
        self.assertFalse(self.destino.es_activo)
        entrada = LogEntry.objects.get(object_id=str(self.destino.pk))
        self.assertEqual(entrada.user, self.jefa)
        self.assertIn('Ocultado', entrada.get_change_message())
