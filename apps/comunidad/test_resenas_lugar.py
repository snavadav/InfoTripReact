"""Reseñas de lugares y "¿Sigue abierto?": moderación, privacidad de la ubicación y baja de cuenta."""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from PIL import Image
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.destinos.models import Lugar, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import TEXTO_ELIMINADO, anonimizar_cuenta
from .models import ConfirmacionLugar, Notificacion, ReporteResenaLugar, ResenaLugar
from .moderacion import moderar
from .selectors import estado_de_lugar


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        crear = Usuario.objects.create_user
        self.ana = crear('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = crear('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.eva = crear('eva@example.com', 'Eva', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.moderador = Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.lugar = Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', municipio=municipio,
                                          latitud='19.945000', longitud='-103.757000', osm_id='node/1')
        self.api = f'/api/v1/lugares/{self.lugar.pk}/'
        self.datos = {'calificacion': 5, 'texto': 'Muy rico', 'fecha_visita': timezone.localdate().isoformat()}
        self.client.force_authenticate(self.ana)

    def resena(self, autor=None, estado='publicado', **campos):
        return ResenaLugar.objects.create(lugar=self.lugar, autor=autor or self.ana, calificacion=4, texto='Bien',
                                          fecha_visita=timezone.localdate(), estado=estado, **campos)


class ResenasTests(Base):
    def test_queda_pendiente_y_no_se_ve_hasta_publicarla(self):
        respuesta = self.client.post(self.api + 'resenas/', self.datos, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data['estado'], 'pendiente')
        self.assertEqual(self.client.get(self.api + 'resenas/').data['count'], 0)
        self.assertEqual(Evento.objects.filter(nombre='resena_lugar_enviada').count(), 1)

    def test_valores_invalidos(self):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        for cambio in [{'calificacion': 0}, {'calificacion': 6}, {'texto': ''}, {'fecha_visita': manana},
                       {'latitud': 19.9}, {'latitud': 91, 'longitud': 0}]:
            self.assertEqual(self.client.post(self.api + 'resenas/', {**self.datos, **cambio}, format='json').status_code, 400, cambio)
        self.assertFalse(ResenaLugar.objects.exists())

    def test_una_por_persona_pero_se_puede_volver_a_escribir_tras_retirarla(self):
        self.client.post(self.api + 'resenas/', self.datos, format='json')
        self.assertEqual(self.client.post(self.api + 'resenas/', self.datos, format='json').status_code, 400)
        self.assertEqual(self.client.delete(self.api + 'mi-opinion/').status_code, 204)
        self.assertEqual(ResenaLugar.objects.get().estado, 'retirado')
        self.assertEqual(self.client.post(self.api + 'resenas/', self.datos, format='json').status_code, 201)

    def test_requiere_sesion_y_lugar_activo(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.api + 'resenas/', self.datos, format='json').status_code, 401)
        self.assertEqual(self.client.post(self.api + 'estado/', {'abierto': True}, format='json').status_code, 401)
        self.assertEqual(self.client.get(self.api + 'mi-opinion/').status_code, 401)
        self.client.force_authenticate(self.ana)
        Lugar.objects.filter(pk=self.lugar.pk).update(es_activo=False)
        self.assertEqual(self.client.post(self.api + 'resenas/', self.datos, format='json').status_code, 404)
        self.assertEqual(self.client.get(self.api + 'resenas/').status_code, 404)
        self.assertEqual(self.client.post(self.api + 'estado/', {'abierto': True}, format='json').status_code, 404)
        self.assertEqual(self.client.get(f'/lugares/{self.lugar.pk}/').status_code, 404)

    def test_editar_vuelve_a_revision(self):
        self.resena()
        respuesta = self.client.patch(self.api + 'mi-opinion/', {'texto': 'Cambió'}, format='json')
        self.assertEqual((respuesta.data['estado'], respuesta.data['texto']), ('pendiente', 'Cambió'))
        self.client.force_authenticate(self.leo)
        self.assertEqual(self.client.patch(self.api + 'mi-opinion/', {'texto': 'x'}, format='json').status_code, 400)

    def test_comprobar_ubicacion_guarda_solo_el_resultado(self):
        cerca = {**self.datos, 'latitud': 19.9451, 'longitud': -103.7571}
        respuesta = self.client.post(self.api + 'resenas/', cerca, format='json')
        self.assertTrue(respuesta.data['ubicacion_comprobada'])
        self.assertNotIn('latitud', respuesta.data)
        campos = {campo.name for campo in ResenaLugar._meta.get_fields()}
        self.assertFalse(campos & {'latitud', 'longitud'})
        self.client.force_authenticate(self.leo)
        lejos = {**self.datos, 'latitud': 20.5, 'longitud': -103.3}
        self.assertFalse(self.client.post(self.api + 'resenas/', lejos, format='json').data['ubicacion_comprobada'])

    def test_la_ubicacion_no_se_puede_declarar_directamente(self):
        respuesta = self.client.post(self.api + 'resenas/', {**self.datos, 'ubicacion_comprobada': True}, format='json')
        self.assertFalse(respuesta.data['ubicacion_comprobada'])

    def test_moderar_avisa_con_enlace_al_lugar_y_mide(self):
        resena = self.resena(estado='pendiente')
        self.assertTrue(moderar(resena, self.moderador, 'publicado', 'Revisada'))
        aviso = Notificacion.objects.get(usuario=self.ana)
        self.assertIn('Fonda Doña Ana', aviso.texto)
        self.assertEqual(aviso.enlace, f'/lugares/{self.lugar.pk}/')
        self.assertEqual(resena.revisiones.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='resena_lugar_publicada').count(), 1)

    def test_retirada_no_se_puede_moderar(self):
        self.assertFalse(moderar(self.resena(estado='retirado'), self.moderador, 'publicado', 'Intento'))

    def test_mis_resenas(self):
        self.resena()
        self.resena(autor=self.leo)
        self.assertEqual([r['autor_nombre'] for r in self.client.get('/api/v1/mis-resenas-lugar/').data['results']], ['Ana'])


def foto():
    salida = BytesIO()
    Image.new('RGB', (40, 30), 'teal').save(salida, format='PNG')
    return SimpleUploadedFile('foto.png', salida.getvalue(), content_type='image/png')


class FotoYGastoTests(Base):
    def setUp(self):
        super().setUp()
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=carpeta)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

    def test_guarda_foto_limpia_con_miniatura_y_gasto(self):
        respuesta = self.client.post(self.api + 'resenas/', {**self.datos, 'imagen': foto(), 'monto': '250.50'}, format='multipart')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        resena = ResenaLugar.objects.get()
        self.assertTrue(resena.imagen.name.endswith('.jpg'))
        self.assertTrue(resena.miniatura)
        self.assertEqual(resena.monto, Decimal('250.50'))

    def test_rechaza_lo_que_no_es_imagen_y_montos_invalidos(self):
        falsa = SimpleUploadedFile('falsa.jpg', b'<script>alert(1)</script>', content_type='image/jpeg')
        self.assertEqual(self.client.post(self.api + 'resenas/', {**self.datos, 'imagen': falsa}, format='multipart').status_code, 400)
        self.assertEqual(self.client.post(self.api + 'resenas/', {**self.datos, 'monto': '-1'}, format='json').status_code, 400)
        self.assertFalse(ResenaLugar.objects.exists())

    def test_el_gasto_solo_aplica_a_comer_y_dormir(self):
        Lugar.objects.filter(pk=self.lugar.pk).update(tipo='farmacia', subtipo='pharmacy')
        self.assertEqual(self.client.post(self.api + 'resenas/', {**self.datos, 'monto': '10'}, format='json').status_code, 400)
        self.assertNotContains(self.client.get(f'/lugares/{self.lugar.pk}/'), 'name="monto"')

    def test_editar_sin_foto_conserva_la_que_habia(self):
        self.client.post(self.api + 'resenas/', {**self.datos, 'imagen': foto()}, format='multipart')
        nombre = ResenaLugar.objects.get().imagen.name
        self.client.patch(self.api + 'mi-opinion/', {'texto': 'Cambió'}, format='multipart')
        self.assertEqual(ResenaLugar.objects.get().imagen.name, nombre)

    def test_gasto_habitual_exige_tres_resenas_publicadas_y_recientes(self):
        pagina = f'/lugares/{self.lugar.pk}/'
        self.resena(monto=100)
        self.resena(autor=self.leo, monto=300)
        self.assertNotContains(self.client.get(pagina), 'lo habitual')
        self.resena(autor=self.eva, monto=200, estado='pendiente')
        self.assertNotContains(self.client.get(pagina), 'lo habitual')
        ResenaLugar.objects.filter(autor=self.eva).update(estado='publicado')
        self.assertContains(self.client.get(pagina), '$200 MXN')
        self.assertContains(self.client.get(pagina), 'por persona')
        ResenaLugar.objects.filter(autor=self.eva).update(fecha_visita=timezone.localdate() - timedelta(days=400))
        self.assertNotContains(self.client.get(pagina), 'lo habitual')

    def test_hospedaje_se_expresa_por_noche(self):
        Lugar.objects.filter(pk=self.lugar.pk).update(tipo='dormir', subtipo='hotel')
        self.assertContains(self.client.get(f'/lugares/{self.lugar.pk}/'), 'gastaste por noche')

    def test_la_foto_publicada_se_muestra_y_la_pendiente_no(self):
        self.client.post(self.api + 'resenas/', {**self.datos, 'imagen': foto()}, format='multipart')
        pagina = f'/lugares/{self.lugar.pk}/'
        self.assertNotContains(self.client.get(pagina), 'community-photo')
        ResenaLugar.objects.update(estado='publicado')
        self.assertContains(self.client.get(pagina), 'community-photo')

    def test_baja_de_cuenta_borra_la_foto_y_el_gasto(self):
        self.client.post(self.api + 'resenas/', {**self.datos, 'imagen': foto(), 'monto': '5'}, format='multipart')
        resena = ResenaLugar.objects.get()
        archivo, almacen = resena.imagen.name, resena.imagen.storage
        with self.captureOnCommitCallbacks(execute=True):
            anonimizar_cuenta(self.ana)
        resena.refresh_from_db()
        self.assertEqual((resena.imagen.name, resena.miniatura.name, resena.monto), ('', '', None))
        self.assertFalse(almacen.exists(archivo))


class SigueAbiertoTests(Base):
    def responder(self, usuario, abierto):
        self.client.force_authenticate(usuario)
        return self.client.post(self.api + 'estado/', {'abierto': abierto}, format='json')

    def test_cuenta_y_repetir_cambia_la_respuesta(self):
        self.assertEqual(self.responder(self.ana, True).data['abiertos'], 1)
        datos = self.responder(self.ana, False).data
        self.assertEqual((datos['abiertos'], datos['cerrados']), (0, 1))
        self.assertEqual(ConfirmacionLugar.objects.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='lugar_confirmado').count(), 1)

    def test_valor_invalido(self):
        self.assertEqual(self.client.post(self.api + 'estado/', {'abierto': 'tal vez'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.api + 'estado/', {}, format='json').status_code, 400)

    def test_posible_cierre_exige_dos_personas_y_mayoria(self):
        self.responder(self.ana, False)
        self.assertFalse(estado_de_lugar(self.lugar)['posible_cierre'])
        self.responder(self.leo, False)
        self.assertTrue(estado_de_lugar(self.lugar)['posible_cierre'])
        self.responder(self.eva, True)
        self.assertTrue(estado_de_lugar(self.lugar)['posible_cierre'])
        ConfirmacionLugar.objects.filter(autor=self.eva).update(abierto=True)
        ConfirmacionLugar.objects.filter(autor=self.leo).update(abierto=True)
        self.assertFalse(estado_de_lugar(self.lugar)['posible_cierre'])

    def test_no_oculta_el_lugar_por_si_solo(self):
        self.responder(self.ana, False)
        self.responder(self.leo, False)
        self.lugar.refresh_from_db()
        self.assertTrue(self.lugar.es_activo)
        self.assertContains(self.client.get(f'/lugares/{self.lugar.pk}/'), 'ya cerró. Confírmalo')

    def test_lo_antiguo_y_las_cuentas_inactivas_no_cuentan(self):
        self.responder(self.ana, False)
        self.responder(self.leo, False)
        ConfirmacionLugar.objects.filter(autor=self.ana).update(fecha=timezone.localdate() - timedelta(days=400))
        Usuario.objects.filter(pk=self.leo.pk).update(es_activo=False)
        self.assertEqual(estado_de_lugar(self.lugar)['cerrados'], 0)


class ReportesTests(Base):
    def test_reportar_una_vez_y_no_la_propia(self):
        resena = self.resena(autor=self.leo)
        url = f'/api/v1/resenas-lugar/{resena.pk}/reportar/'
        self.assertEqual(self.client.post(url, {'motivo': 'Falso'}, format='json').status_code, 201)
        self.assertEqual(self.client.post(url, {'motivo': 'Otra vez'}, format='json').status_code, 400)
        self.assertEqual(ReporteResenaLugar.objects.count(), 1)
        self.client.force_authenticate(self.leo)
        self.assertEqual(self.client.post(url, {'motivo': 'Mía'}, format='json').status_code, 400)

    def test_lo_no_publicado_no_se_reporta(self):
        resena = self.resena(autor=self.leo, estado='pendiente')
        self.assertEqual(self.client.post(f'/api/v1/resenas-lugar/{resena.pk}/reportar/', {'motivo': 'x'}, format='json').status_code, 404)

    def test_resolver_el_reporte_desde_el_admin_oculta_la_resena(self):
        resena = self.resena(autor=self.leo)
        reporte = ReporteResenaLugar.objects.create(resena=resena, autor=self.ana, motivo='Falso')
        self.client.force_login(self.moderador)
        respuesta = self.client.post('/admin/comunidad/reporteresenalugar/', {
            'action': 'resolver_ocultando', '_selected_action': [reporte.pk]})
        self.assertEqual(respuesta.status_code, 302)
        resena.refresh_from_db()
        reporte.refresh_from_db()
        self.assertEqual(resena.estado, 'oculto')
        self.assertTrue(reporte.resuelto)


class ModeracionEnAdminTests(Base):
    def test_cola_y_publicar(self):
        resena = self.resena(autor=self.leo, estado='pendiente')
        ConfirmacionLugar.objects.create(lugar=self.lugar, autor=self.ana, abierto=False, fecha=timezone.localdate())
        self.client.force_login(self.moderador)
        cola = self.client.get('/admin/moderacion/')
        self.assertContains(cola, 'Reseñas de lugares pendientes')
        self.assertContains(cola, 'Fonda Doña Ana · Leo')
        self.assertContains(cola, 'Lugares que alguien dice que cerraron')
        self.client.post('/admin/comunidad/resenalugar/', {'action': 'publicar', '_selected_action': [resena.pk]})
        resena.refresh_from_db()
        self.assertEqual(resena.estado, 'publicado')


class BajaDeCuentaTests(Base):
    def test_borra_lo_personal_y_conserva_el_historial_anonimo(self):
        resena = self.resena()
        ConfirmacionLugar.objects.create(lugar=self.lugar, autor=self.ana, abierto=True, fecha=timezone.localdate())
        anonimizar_cuenta(self.ana)
        resena.refresh_from_db()
        self.assertEqual((resena.estado, resena.texto), ('retirado', TEXTO_ELIMINADO))
        self.assertFalse(ConfirmacionLugar.objects.exists())


class PaginaTests(Base):
    def url(self):
        return f'/lugares/{self.lugar.pk}/'

    def test_muestra_datos_y_credito_y_sin_resenas_no_se_indexa(self):
        Lugar.objects.filter(pk=self.lugar.pk).update(telefono='33 1234', sitio_web='https://fonda.mx', horario='Mo-Su 09:00')
        pagina = self.client.get(self.url())
        for texto in ('Fonda Doña Ana', 'tel:331234', 'https://fonda.mx', 'Mo-Su 09:00', 'colaboradores de OpenStreetMap',
                      'noindex', 'Sin reseñas todavía', 'js/lugar.js'):
            self.assertContains(pagina, texto)

    def test_con_resenas_publicadas_muestra_promedio_y_se_indexa(self):
        self.resena(ubicacion_comprobada=True)
        self.resena(autor=self.leo, estado='pendiente', )
        pagina = self.client.get(self.url())
        self.assertContains(pagina, '4.0 / 5')
        self.assertContains(pagina, '1 reseña')
        self.assertContains(pagina, 'class="visit-badge"', count=1)
        self.assertNotContains(pagina, 'noindex')

    def test_la_api_y_la_ficha_de_destino_llevan_a_la_ficha_del_lugar(self):
        self.resena()
        sitio = self.client.get('/api/v1/lugares/', {'sur': 19.9, 'oeste': -103.8, 'norte': 20, 'este': -103.7}).data['resultados'][0]
        self.assertEqual((sitio['url'], sitio['num_resenas'], sitio['calificacion_promedio']), (self.url(), 1, 4.0))
