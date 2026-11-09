"""Pasaporte de Pueblos Mágicos: sellos por visita comprobada, fotos propias y tarjeta para compartir."""
import os
from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import anonimizar_cuenta
from .models import FotoPasaporte, Notificacion, PasaporteCompartido, VisitaComprobada
from .moderacion import moderar
from .selectors import PUEBLOS_MAGICOS


class ListaTests(SimpleTestCase):
    def test_son_doce_pueblos_sin_repetir(self):
        self.assertEqual(len(PUEBLOS_MAGICOS), 12)
        self.assertEqual(len(dict(PUEBLOS_MAGICOS)), 12)


class PasaporteBase(APITestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                                  region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.tapalpa = self.destino('tapalpa')
        self.mazamitla = self.destino('mazamitla', latitud='19.916111', longitud='-103.020556')
        self.client.force_authenticate(self.ana)

    def destino(self, slug, latitud='19.945', longitud='-103.757778', **campos):
        return Destino.objects.create(nombre=slug.title(), slug=slug, municipio=self.municipio, descripcion='-',
                                      latitud=latitud, longitud=longitud, **campos)

    def visitar(self, destino=None, usuario=None):
        return VisitaComprobada.objects.create(autor=usuario or self.ana, destino=destino or self.tapalpa,
                                               fecha=timezone.localdate())


class MiPasaporteTests(PasaporteBase):
    def sellos(self):
        return {s['slug']: s for s in self.client.get('/api/v1/mi-pasaporte/').data['sellos']}

    def test_cuenta_solo_los_sellos_propios(self):
        self.visitar()
        self.visitar(self.mazamitla, self.leo)
        datos = self.client.get('/api/v1/mi-pasaporte/').data
        self.assertEqual((datos['total'], datos['de'], datos['enlace']), (1, 12, None))
        self.assertTrue(self.sellos()['tapalpa']['sello'])
        self.assertFalse(self.sellos()['mazamitla']['sello'])

    def test_pueblo_sin_ficha_no_esta_disponible(self):
        self.assertFalse(self.sellos()['cocula']['disponible'])
        self.assertTrue(self.sellos()['tapalpa']['disponible'])
        self.destino('cocula', es_activo=False)
        self.assertFalse(self.sellos()['cocula']['disponible'])

    def test_destino_que_no_es_pueblo_magico_no_da_sello(self):
        self.visitar(self.destino('guadalajara'))
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').data['total'], 0)

    def test_ocultar_el_destino_retira_el_sello_de_la_cuenta(self):
        self.visitar()
        Destino.objects.filter(pk=self.tapalpa.pk).update(es_activo=False)
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').data['total'], 0)

    def test_requiere_sesion(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/mi-pasaporte/compartir/').status_code, 401)


class GanarSelloTests(PasaporteBase):
    def comprobar(self, slug='tapalpa', latitud=19.95, longitud=-103.75):
        return self.client.post(f'/api/v1/destinos/{slug}/visita/', {'latitud': latitud, 'longitud': longitud},
                                format='json')

    def test_comprobar_en_un_pueblo_da_sello_avisa_y_mide(self):
        self.assertTrue(self.comprobar().data['sello'])
        aviso = Notificacion.objects.get(usuario=self.ana)
        self.assertIn('1 de 12', aviso.texto)
        self.assertEqual(aviso.enlace, '/pasaporte/')
        self.assertEqual(Evento.objects.filter(nombre='sello_obtenido', destino='tapalpa').count(), 1)

    def test_repetir_no_vuelve_a_avisar(self):
        self.comprobar()
        self.assertTrue(self.comprobar().data['sello'])
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='sello_obtenido').count(), 1)

    def test_otro_lugar_comprueba_sin_sello(self):
        self.destino('guadalajara')
        self.assertFalse(self.comprobar('guadalajara').data['sello'])
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(Evento.objects.filter(nombre='sello_obtenido').exists())


class TarjetaTests(PasaporteBase):
    def enlace(self):
        return self.client.post('/api/v1/mi-pasaporte/compartir/').data['enlace']

    def test_la_tarjeta_muestra_nombre_y_sellos_sin_fechas_ni_correo(self):
        self.visitar()
        enlace = self.enlace()
        self.assertEqual(self.enlace(), enlace)
        self.client.force_authenticate(None)
        pagina = self.client.get(f'/pasaporte/{enlace}/')
        self.assertContains(pagina, 'Ana lleva 1 de 12')
        self.assertContains(pagina, 'noindex')
        self.assertContains(pagina, 'passport-stamp--done', count=1)
        self.assertNotContains(pagina, 'ana@example.com')
        self.assertNotContains(pagina, timezone.localdate().strftime('%d/%m/%Y'))

    def test_retirar_invalida_el_enlace(self):
        enlace = self.enlace()
        self.assertEqual(self.client.delete('/api/v1/mi-pasaporte/compartir/').status_code, 204)
        self.assertEqual(self.client.get(f'/pasaporte/{enlace}/').status_code, 404)

    def test_enlace_inexistente_o_de_cuenta_inactiva(self):
        self.assertEqual(self.client.get('/pasaporte/00000000-0000-0000-0000-000000000000/').status_code, 404)
        enlace = self.enlace()
        Usuario.objects.filter(pk=self.ana.pk).update(es_activo=False)
        self.assertEqual(self.client.get(f'/pasaporte/{enlace}/').status_code, 404)

    def test_eliminar_la_cuenta_borra_la_tarjeta(self):
        self.enlace()
        anonimizar_cuenta(self.ana)
        self.assertFalse(PasaporteCompartido.objects.exists())


class PaginasTests(PasaporteBase):
    def test_pagina_publica_con_los_doce_pueblos(self):
        self.client.force_authenticate(None)
        pagina = self.client.get('/pasaporte/')
        self.assertContains(pagina, 'class="passport-stamp"', count=12)
        self.assertContains(pagina, '/destinos/tapalpa/')
        self.assertContains(pagina, 'Aún sin ficha')
        self.assertContains(pagina, 'no está afiliado')
        self.assertContains(self.client.get('/sitemap.xml'), '/pasaporte/')

    def test_la_ficha_avisa_solo_en_los_pueblos(self):
        self.assertContains(self.client.get('/destinos/tapalpa/'), 'suma un sello')
        self.destino('guadalajara')
        self.assertNotContains(self.client.get('/destinos/guadalajara/'), 'suma un sello')


def foto_con_gps(lado=2000):
    """Imagen con EXIF de cámara y coordenadas GPS, como la que sale de un teléfono."""
    imagen = Image.new('RGB', (lado, lado // 2), (40, 120, 90))
    exif = Image.Exif()
    exif[0x010F] = 'CamaraDePrueba'
    exif[0x8825] = {1: 'N', 2: (20.0, 40.0, 12.0), 3: 'W', 4: (103.0, 21.0, 5.0)}
    salida = BytesIO()
    imagen.save(salida, format='JPEG', exif=exif.tobytes())
    return SimpleUploadedFile('foto.jpg', salida.getvalue(), content_type='image/jpeg')


class FotoBase(PasaporteBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        carpeta = TemporaryDirectory()
        ajuste = override_settings(MEDIA_ROOT=carpeta.name)
        ajuste.enable()
        self.addCleanup(carpeta.cleanup)
        self.addCleanup(ajuste.disable)
        self.url = '/api/v1/mi-pasaporte/tapalpa/foto/'

    def subir(self, archivo=None, **datos):
        return self.client.post(self.url, {'imagen': archivo or foto_con_gps(), **datos}, format='multipart')

    def compartir(self):
        return self.client.post('/api/v1/mi-pasaporte/compartir/').data['enlace']

    def moderar_foto(self, estado):
        moderador = Usuario.objects.create_superuser(f'mod-{estado}@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        moderar(FotoPasaporte.objects.get(), moderador, estado, 'Prueba')


class SubirFotoTests(FotoBase):
    def test_sin_visita_comprobada_se_rechaza(self):
        respuesta = self.subir()
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('comprueba tu visita', str(respuesta.data))
        self.assertFalse(FotoPasaporte.objects.exists())

    def test_solo_pueblos_del_pasaporte(self):
        self.visitar(self.destino('guadalajara'))
        respuesta = self.client.post('/api/v1/mi-pasaporte/guadalajara/foto/', {'imagen': foto_con_gps()},
                                     format='multipart')
        self.assertEqual(respuesta.status_code, 404)

    def test_quita_exif_y_gps_y_reduce_el_tamano(self):
        self.visitar()
        respuesta = self.subir()
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        foto = FotoPasaporte.objects.get()
        with Image.open(foto.imagen.path) as guardada:
            self.assertEqual(guardada.format, 'JPEG')
            self.assertLessEqual(max(guardada.size), 1600)
            self.assertEqual(len(guardada.getexif()), 0)
            self.assertNotIn('exif', guardada.info)
        with open(foto.imagen.path, 'rb') as archivo:
            contenido = archivo.read()
        self.assertNotIn(b'CamaraDePrueba', contenido)
        self.assertNotIn(b'Exif', contenido)

    def test_privada_por_defecto_y_no_va_a_la_cola(self):
        self.visitar()
        datos = self.subir().data
        self.assertEqual((datos['mostrar'], datos['estado'], datos['visible_en_compartido']), (False, 'pendiente', False))
        self.assertFalse(FotoPasaporte.objects.filter(mostrar=True).exists())

    def test_rechaza_lo_que_no_es_imagen_o_es_muy_grande(self):
        self.visitar()
        falsa = SimpleUploadedFile('falsa.jpg', b'<script>alert(1)</script>', content_type='image/jpeg')
        self.assertEqual(self.subir(falsa).status_code, 400)
        gif = BytesIO()
        Image.new('RGB', (10, 10)).save(gif, format='GIF')
        self.assertEqual(self.subir(SimpleUploadedFile('a.gif', gif.getvalue(), content_type='image/gif')).status_code, 400)
        grande = SimpleUploadedFile('g.jpg', foto_con_gps().read() + b'x' * (5 * 1024 * 1024), content_type='image/jpeg')
        self.assertEqual(self.subir(grande).status_code, 400)
        self.assertFalse(FotoPasaporte.objects.exists())

    def test_reemplazar_vuelve_a_revision_y_borra_el_archivo_anterior(self):
        self.visitar()
        with self.captureOnCommitCallbacks(execute=True):
            self.subir(mostrar=True)
        anterior = FotoPasaporte.objects.get().imagen.path
        self.moderar_foto('publicado')
        with self.captureOnCommitCallbacks(execute=True):
            datos = self.subir(mostrar=True).data
        self.assertEqual(datos['estado'], 'pendiente')
        self.assertEqual(FotoPasaporte.objects.count(), 1)
        self.assertFalse(os.path.exists(anterior))

    def test_solo_su_autor_ve_el_archivo(self):
        self.visitar()
        self.subir()
        url = '/api/v1/mi-pasaporte/tapalpa/foto/imagen/'
        respuesta = self.client.get(url)
        self.assertEqual(respuesta['Content-Type'], 'image/jpeg')
        self.assertIn('no-store', respuesta['Cache-Control'])
        self.client.force_authenticate(self.leo)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_aparece_en_mi_pasaporte_y_se_puede_borrar(self):
        self.visitar()
        self.subir()
        sello = next(s for s in self.client.get('/api/v1/mi-pasaporte/').data['sellos'] if s['slug'] == 'tapalpa')
        self.assertEqual(sello['fecha'], timezone.localdate())
        self.assertTrue(sello['foto']['url'].startswith('/api/v1/mi-pasaporte/tapalpa/foto/imagen/'))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(FotoPasaporte.objects.exists())

    def test_eliminar_la_cuenta_borra_la_foto_y_su_archivo(self):
        self.visitar()
        self.subir()
        ruta = FotoPasaporte.objects.get().imagen.path
        with self.captureOnCommitCallbacks(execute=True):
            anonimizar_cuenta(self.ana)
        self.assertFalse(FotoPasaporte.objects.exists())
        self.assertFalse(os.path.exists(ruta))


class FotoEnPasaporteCompartidoTests(FotoBase):
    def setUp(self):
        super().setUp()
        self.visitar()
        self.enlace = self.compartir()
        self.foto_publica = f'/pasaporte/{self.enlace}/foto/tapalpa/'

    def publico(self):
        self.client.force_authenticate(None)
        pagina = self.client.get(f'/pasaporte/{self.enlace}/')
        self.client.force_authenticate(self.ana)
        return pagina

    def test_privada_no_aparece_aunque_este_aprobada(self):
        self.subir()
        self.moderar_foto('publicado')
        self.assertNotContains(self.publico(), self.foto_publica)
        self.assertEqual(self.client.get(self.foto_publica).status_code, 404)

    def test_marcada_pero_sin_aprobar_usa_la_foto_del_catalogo(self):
        self.subir(mostrar=True)
        self.assertNotContains(self.publico(), self.foto_publica)
        self.assertEqual(self.client.get(self.foto_publica).status_code, 404)
        self.moderar_foto('oculto')
        self.assertNotContains(self.publico(), self.foto_publica)

    def test_marcada_y_aprobada_se_muestra(self):
        self.subir(mostrar=True)
        self.moderar_foto('publicado')
        self.assertContains(self.publico(), self.foto_publica)
        self.client.force_authenticate(None)
        respuesta = self.client.get(self.foto_publica)
        self.assertEqual(respuesta['Content-Type'], 'image/jpeg')
        self.assertIn('aprobamos tu foto', Notificacion.objects.get(usuario=self.ana).texto.lower())

    def test_desmarcar_o_dejar_de_compartir_la_retira(self):
        self.subir(mostrar=True)
        self.moderar_foto('publicado')
        self.client.patch(self.url, {'mostrar': False}, format='json')
        self.assertNotContains(self.publico(), self.foto_publica)
        self.assertEqual(self.client.get(self.foto_publica).status_code, 404)
        self.client.patch(self.url, {'mostrar': True}, format='json')
        self.assertContains(self.publico(), self.foto_publica)
        self.client.delete('/api/v1/mi-pasaporte/compartir/')
        self.assertEqual(self.client.get(self.foto_publica).status_code, 404)

    def test_la_cola_solo_recibe_las_que_se_quieren_mostrar(self):
        self.subir()
        moderador = Usuario.objects.create_superuser('mod@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        self.client.force_login(moderador)
        self.assertNotContains(self.client.get('/admin/moderacion/'), 'Fotos de pasaporte por revisar (1)')
        self.client.patch(self.url, {'mostrar': True}, format='json')
        self.assertContains(self.client.get('/admin/moderacion/'), 'Tapalpa · Ana')
        foto = FotoPasaporte.objects.get()
        respuesta = self.client.get(f'/admin/comunidad/fotopasaporte/{foto.pk}/imagen/')
        self.assertEqual(respuesta['Content-Type'], 'image/jpeg')


class PasaporteCompartidoSinFechasTests(FotoBase):
    def test_el_sello_dice_solo_visitado_sin_fechas(self):
        VisitaComprobada.objects.create(autor=self.ana, destino=self.tapalpa, fecha=date(2026, 11, 14))
        enlace = self.compartir()
        self.client.force_authenticate(None)
        pagina = self.client.get(f'/pasaporte/{enlace}/')
        self.assertContains(pagina, 'Ana lleva 1 de 12')
        self.assertContains(pagina, '>VISITADO<')
        self.assertContains(pagina, 'aria-label="Tapalpa, visitado"')
        html = pagina.content.decode().lower()
        for texto in ['2026-11-14', '14/11/2026', '14 de noviembre', '14 nov', 'noviembre', 'datetime=', 'visitado ·']:
            self.assertNotIn(texto, html)
