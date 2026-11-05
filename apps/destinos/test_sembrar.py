"""Contenido de fuentes públicas: siempre citado y nunca simula la experiencia de una persona."""
import json
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from apps.comunidad.models import Aporte, CORREO_EQUIPO, Colaboracion, ConfirmacionLugar, ResenaLugar, VisitaComprobada
from apps.comunidad.selectors import cronistas
from apps.usuarios.models import Usuario
from .fotos import FOTOS_CATALOGO
from .management.commands.sembrar_contenido import ARCHIVO
from .models import Destino, Municipio, Region

SITIO = {'nombre': 'Museo Nuevo', 'destino': None, 'municipio': 'Tapalpa', 'latitud': 19.9, 'longitud': -103.7,
         'categoria': 'Ciudad y cultura', 'direccion': 'Juárez 2', 'descripcion': 'Un museo. Fuente: SIC.',
         'fuente': 'https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=1', 'consultado': '2026-10-30',
         'datos': {'horarios': 'Martes a domingo de 10 a 17 h', 'precios': 'Entrada libre', 'contacto': 'Teléfono: 33 1'}}


class Base(TestCase):
    def sembrar(self, *sitios, **opciones):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'c.json')
            with open(ruta, 'w', encoding='utf-8') as salida:
                json.dump(list(sitios), salida)
            texto = StringIO()
            call_command('sembrar_contenido', archivo=ruta, stdout=texto, **opciones)
        return texto.getvalue()

    def existente(self, descripcion, slug='museo-viejo', **campos):
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=Region.objects.create(nombre='S', slug='s'))
        return Destino.objects.create(nombre='Museo Viejo', slug=slug, municipio=municipio, descripcion=descripcion,
                                      latitud='19.9', longitud='-103.7', **campos)


class CargaTests(Base):
    def test_crea_el_destino_y_los_datos_publicados_con_su_fuente(self):
        self.sembrar(SITIO)
        destino = Destino.objects.get()
        self.assertTrue(destino.es_activo)
        self.assertEqual((destino.nombre, destino.direccion, destino.categorias.get().nombre),
                         ('Museo Nuevo', 'Juárez 2', 'Ciudad y cultura'))
        datos = Colaboracion.objects.filter(destino=destino)
        self.assertEqual(set(datos.values_list('campo', flat=True)), {'horarios', 'precios', 'contacto'})
        for dato in datos:
            self.assertEqual((dato.estado, dato.tipo, str(dato.fecha_dato)), ('publicado', 'correccion', '2026-10-30'))
            self.assertIn('Sistema de Información Cultural', dato.fuente)
            self.assertIn('table_id=1', dato.fuente)

    def test_repetir_no_duplica(self):
        self.sembrar(SITIO)
        salida = self.sembrar(SITIO)
        self.assertEqual((Destino.objects.count(), Colaboracion.objects.count()), (1, 3))
        self.assertIn('Ya existían: 1', salida)

    def test_nunca_crea_experiencias_de_personas(self):
        self.sembrar(SITIO)
        for modelo in (Aporte, ResenaLugar, ConfirmacionLugar, VisitaComprobada):
            self.assertFalse(modelo.objects.exists(), modelo.__name__)

    def test_solo_reemplaza_el_texto_automatico(self):
        automatico = self.existente('Museo en Tapalpa, Jalisco. Todavía no tenemos una descripción: si lo conoces...')
        self.sembrar({**SITIO, 'destino': automatico.slug})
        automatico.refresh_from_db()
        self.assertEqual(automatico.descripcion, 'Un museo. Fuente: SIC.')
        Destino.objects.filter(pk=automatico.pk).update(descripcion='Escrita por el equipo')
        self.sembrar({**SITIO, 'destino': automatico.slug})
        automatico.refresh_from_db()
        self.assertEqual(automatico.descripcion, 'Escrita por el equipo')

    def test_no_pisa_lo_que_aportan_las_personas(self):
        destino = self.existente('Texto')
        ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'x')
        propio = Colaboracion.objects.create(destino=destino, autor=ana, tipo='correccion', campo='horarios', texto='De Ana',
                                             fuente='Visita', fecha_dato='2026-10-01', estado='publicado')
        self.sembrar({**SITIO, 'destino': destino.slug})
        propio.refresh_from_db()
        self.assertEqual(propio.texto, 'De Ana')

    def test_si_el_destino_no_existe_en_esta_base_lo_avisa_y_sigue(self):
        salida = self.sembrar({**SITIO, 'destino': 'no-existe'}, {**SITIO, 'nombre': 'Otro Museo'})
        self.assertIn('Sin destino en esta base: 1', salida)
        self.assertEqual(Destino.objects.get().nombre, 'Otro Museo')

    def test_simular_no_guarda_nada(self):
        self.assertIn('Se crearían 1', self.sembrar(SITIO, simular=True))
        self.assertFalse(Destino.objects.exists())
        self.assertFalse(Usuario.objects.filter(email=CORREO_EQUIPO).exists())


class CuentaDelEquipoTests(Base):
    def test_no_puede_iniciar_sesion(self):
        self.sembrar(SITIO)
        self.assertFalse(Usuario.objects.get(email=CORREO_EQUIPO).has_usable_password())

    def test_no_compite_como_cronista(self):
        self.sembrar(SITIO)
        self.assertEqual(cronistas(), [])

    def test_la_ficha_la_firma_el_equipo_y_muestra_la_fuente(self):
        self.sembrar(SITIO)
        ficha = self.client.get('/destinos/museo-nuevo/')
        self.assertContains(ficha, 'Equipo InfoTrip')
        self.assertContains(ficha, 'Sistema de Información Cultural')
        self.assertContains(ficha, 'Martes a domingo de 10 a 17 h')


class ArchivoTests(TestCase):
    """El archivo incluido en el repositorio debe cumplir las reglas, no solo el comando."""

    def setUp(self):
        self.sitios = json.loads(Path(ARCHIVO).read_text(encoding='utf-8'))

    def test_al_menos_cien_sitios_con_fuente_y_fecha(self):
        self.assertGreaterEqual(len(self.sitios), 100)
        for sitio in self.sitios:
            self.assertTrue(sitio['fuente'].startswith('https://'), sitio['nombre'])
            self.assertEqual(sitio['consultado'], '2026-10-30')

    def test_solo_campos_practicos_validos_y_sin_acentos_danados(self):
        validos = {clave for clave, _ in Colaboracion.CAMPOS}
        texto = json.dumps(self.sitios, ensure_ascii=False)
        self.assertNotIn('Ã', texto)
        for sitio in self.sitios:
            self.assertTrue(set(sitio['datos']) <= validos, sitio['nombre'])

    def test_los_costos_no_quedan_dentro_de_los_horarios(self):
        for sitio in self.sitios:
            self.assertNotRegex(sitio['datos'].get('horarios', ''), r'\$|Entrada (libre|general|gratuita)', sitio['nombre'])

    def test_todo_lo_nuevo_se_puede_ubicar(self):
        for sitio in self.sitios:
            if not sitio['destino']:
                self.assertTrue(sitio['municipio'], sitio['nombre'])
                self.assertTrue(18.8 <= sitio['latitud'] <= 22.9, sitio['nombre'])
                self.assertTrue(-105.8 <= sitio['longitud'] <= -101.4, sitio['nombre'])


class FotosTests(TestCase):
    def test_cada_foto_tiene_autor_licencia_y_archivos(self):
        raiz = Path(__file__).resolve().parents[2] / 'static'
        for slug, foto in FOTOS_CATALOGO.items():
            self.assertTrue(foto['autor'] and foto['licencia'] and foto['licencia_url'] and foto['fuente'], slug)
            self.assertTrue((raiz / foto['imagen']).exists(), foto['imagen'])
            self.assertTrue((raiz / foto['miniatura']).exists(), foto['miniatura'])
