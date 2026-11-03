"""Lo que necesita el piloto: comentarios del sitio, equipo de moderación y curación del catálogo."""
import json
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.destinos.management.commands.curar_catalogo import ARCHIVO
from apps.destinos.models import Categoria, Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import anonimizar_cuenta
from .models import Aporte, Comentario

URL = '/api/v1/comentarios/'


class ComentariosTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)

    def test_sin_sesion_se_guarda_sin_cuenta(self):
        respuesta = self.client.post(URL, {'tipo': 'problema', 'texto': 'No carga el mapa', 'pagina': '/destinos/'}, format='json')
        self.assertEqual(respuesta.status_code, 201)
        comentario = Comentario.objects.get()
        self.assertEqual((comentario.usuario, comentario.pagina, comentario.atendido), (None, '/destinos/', False))
        self.assertEqual(Evento.objects.filter(nombre='comentario_enviado').count(), 1)

    def test_con_sesion_se_asocia_a_la_cuenta(self):
        self.client.force_authenticate(self.ana)
        self.client.post(URL, {'tipo': 'idea', 'texto': 'Más playas'}, format='json')
        self.assertEqual(Comentario.objects.get().usuario, self.ana)

    def test_valores_invalidos_y_pagina_externa(self):
        for cambio in [{'texto': ''}, {'texto': 'x' * 1001}, {'tipo': 'inventado'}]:
            self.assertEqual(self.client.post(URL, {'tipo': 'otro', 'texto': 'Hola', **cambio}, format='json').status_code, 400)
        self.client.post(URL, {'tipo': 'otro', 'texto': 'Hola', 'pagina': '//malo.example/x'}, format='json')
        self.client.post(URL, {'tipo': 'otro', 'texto': 'Hola', 'pagina': 'https://malo.example'}, format='json')
        self.assertEqual(set(Comentario.objects.values_list('pagina', flat=True)), {''})

    def test_campo_trampa_y_limite(self):
        self.assertEqual(self.client.post(URL, {'tipo': 'otro', 'texto': 'Spam', 'sitio_web': 'x'}, format='json').status_code, 201)
        self.assertFalse(Comentario.objects.exists())
        for _ in range(9):
            self.client.post(URL, {'tipo': 'otro', 'texto': 'Hola'}, format='json')
        self.assertEqual(self.client.post(URL, {'tipo': 'otro', 'texto': 'Hola'}, format='json').status_code, 429)

    def test_no_se_leen_por_la_api(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_pagina_y_enlace_en_el_pie(self):
        pagina = self.client.get('/comentarios/', {'desde': '/destinos/'})
        self.assertContains(pagina, 'id="comentario-form"')
        self.assertContains(pagina, 'data-desde="/destinos/"')
        self.assertContains(self.client.get('/comentarios/', {'desde': 'https://malo.example'}), 'data-desde=""')
        # La página, no la API: comparten el nombre "comentarios" en la URL.
        self.assertContains(self.client.get('/destinos/'), 'href="/comentarios/?desde=/destinos/"')

    def test_baja_de_cuenta_borra_sus_comentarios(self):
        Comentario.objects.create(usuario=self.ana, tipo='idea', texto='Mi teléfono es 333')
        Comentario.objects.create(tipo='idea', texto='Anónimo')
        anonimizar_cuenta(self.ana)
        self.assertEqual(list(Comentario.objects.values_list('texto', flat=True)), ['Anónimo'])


class ModeracionTests(APITestCase):
    def setUp(self):
        self.leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        autor = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'x')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=Region.objects.create(nombre='S', slug='s'))
        destino = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-', latitud=19.9, longitud=-103.7)
        self.aporte = Aporte.objects.create(destino=destino, autor=autor, tipo='resena', texto='Bonito', calificacion=5,
                                            fecha_visita=timezone.localdate())

    def test_quien_modera_publica_sin_ser_superusuario_ni_borrar(self):
        call_command('crear_moderacion', agregar='LEO@example.com', stdout=StringIO())
        self.leo.refresh_from_db()
        self.assertTrue(self.leo.es_staff)
        self.assertFalse(self.leo.is_superuser)
        self.client.force_login(self.leo)
        self.assertContains(self.client.get('/admin/moderacion/'), 'Aportes pendientes')
        self.client.post('/admin/comunidad/aporte/', {'action': 'publicar', '_selected_action': [self.aporte.pk]})
        self.aporte.refresh_from_db()
        self.assertEqual(self.aporte.estado, 'publicado')
        self.assertFalse(self.leo.has_perm('usuarios.change_usuario'))
        self.assertFalse(self.leo.has_perm('comunidad.delete_aporte'))
        self.assertEqual(self.client.get('/admin/usuarios/usuario/').status_code, 403)

    def test_repetir_no_duplica_y_correo_inexistente(self):
        call_command('crear_moderacion', stdout=StringIO())
        call_command('crear_moderacion', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('crear_moderacion', agregar='nadie@example.com', stdout=StringIO())


class CuracionTests(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Zapopan', slug='zapopan', region=Region.objects.create(nombre='C', slug='c'))
        self.crear = lambda nombre, osm, **campos: Destino.objects.create(
            nombre=nombre, slug=nombre.lower().replace(' ', '-'), municipio=municipio, descripcion='-', latitud=20.6,
            longitud=-103.4, osm_id=osm, **campos)

    def curar(self, curacion, **opciones):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'c.json')
            Path(ruta).write_text(json.dumps(curacion), encoding='utf-8')
            salida = StringIO()
            call_command('curar_catalogo', archivo=ruta, stdout=salida, **opciones)
        return salida.getvalue()

    def test_oculta_renombra_une_y_se_puede_revertir(self):
        oculto = self.crear('Mirador JBBPDA 1', 'node/1')
        museo = self.crear('Museo', 'node/2')
        lagos, lago = Categoria.objects.create(nombre='Lagos', slug='lagos'), Categoria.objects.create(nombre='Lago', slug='lago')
        museo.categorias.add(lagos)
        curacion = {'ocultar': [{'osm_id': 'node/1', 'nombre': 'x'}, {'osm_id': 'node/9', 'nombre': 'y'}],
                    'renombrar': {'node/2': 'Museo Interpretativo de El Arenal'}, 'unir_categorias': {'Lagos': 'Lago'}}
        salida = self.curar(curacion)
        self.assertIn('Ocultados: 1', salida)
        self.assertIn('no en esta base: 1', salida)
        oculto.refresh_from_db()
        museo.refresh_from_db()
        self.assertFalse(oculto.es_activo)
        self.assertEqual((museo.nombre, museo.slug), ('Museo Interpretativo de El Arenal', 'museo'))
        self.assertEqual(list(museo.categorias.all()), [lago])
        self.assertIn('Publicados de nuevo: 1', self.curar(curacion, revertir=True))
        oculto.refresh_from_db()
        self.assertTrue(oculto.es_activo)

    def test_simular_no_cambia_nada(self):
        self.crear('Horse Stable', 'node/1')
        self.curar({'ocultar': [{'osm_id': 'node/1', 'nombre': 'x'}], 'renombrar': {}, 'unir_categorias': {}}, simular=True)
        self.assertTrue(Destino.objects.get().es_activo)

    def test_el_archivo_incluido_es_valido(self):
        curacion = json.loads(Path(ARCHIVO).read_text(encoding='utf-8'))
        self.assertGreater(len(curacion['ocultar']), 100)
        self.assertTrue(all(fila['osm_id'].split('/')[0] in ('node', 'way', 'relation') for fila in curacion['ocultar']))
        self.assertEqual(curacion['unir_categorias'], {'Lagos': 'Lago'})
