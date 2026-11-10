"""Datos siempre al día. Ninguna prueba sale a la red: HTTP e IA están simulados."""
import json
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.destinos.models import Destino, Lugar, Municipio, ReferenciaCosto, Region
from apps.destinos.test_osm import lugar as nodo, respuesta
from apps.usuarios.models import Usuario
from . import lector, tareas
from .admin import EjecucionTareaAdmin, FuenteOficialAdmin, PropuestaActualizacionAdmin
from .models import EjecucionTarea, FuenteOficial, PropuestaActualizacion, dominio_prohibido, validar_url_oficial
from .moderacion import PropuestaNoAplicable, aprobar, rechazar

URL = 'https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=1027'
ROBOTS = 'https://sic.cultura.gob.mx/robots.txt'
PAGINA = ('<html><head><title>Museo</title><script>var precio = "$999";</script></head><body>'
          '<h1>Museo Cabañas</h1><p>Horario: martes a domingo de 10:00 a 18:00 hrs.</p>'
          '<p>Costo de entrada general: $90.00 pesos. Martes, entrada libre.</p></body></html>')


def http(paginas):
    """Simula _pedir: {url: (estado, tipo, texto)}. Lo no listado responde 404."""
    def pedir(url):
        estado, tipo, texto = paginas.get(url, (404, '', ''))
        return estado, tipo, texto.encode('utf-8'), url
    return pedir


def sitio(robots='User-agent: *\nAllow: /\n', pagina=PAGINA, tipo='text/html; charset=utf-8'):
    return http({ROBOTS: (200, 'text/plain', robots), URL: (200, tipo, pagina)})


def ia(encontrado=True, valor='90', cita='Costo de entrada general: $90.00 pesos.', stop='end_turn'):
    cliente = MagicMock()
    texto = json.dumps({'encontrado': encontrado, 'valor': valor, 'cita': cita})
    cliente.messages.create.return_value = SimpleNamespace(
        stop_reason=stop, content=[SimpleNamespace(type='thinking'), SimpleNamespace(type='text', text=texto)])
    return cliente


class Datos(TestCase):
    def setUp(self):
        region = Region.objects.create(nombre='Centro', slug='centro')
        self.municipio = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=region)
        self.destino = Destino.objects.create(nombre='Instituto Cultural Cabañas', slug='instituto-cultural-cabanas',
                                              municipio=self.municipio, descripcion='-', latitud=20.6, longitud=-103.3)
        self.referencia = ReferenciaCosto.objects.create(
            destino=self.destino, concepto='entrada', monto=80, descripcion='Museo Cabañas, entrada general.',
            fuente_nombre='Sistema de Información Cultural', fuente_url=URL, fecha_consulta=date(2026, 11, 9))
        self.fuente = FuenteOficial.objects.create(nombre='SIC', url=URL, tipo_dato='precio', destino=self.destino,
                                                   referencia=self.referencia)
        self.moderador = Usuario.objects.create_superuser('mod@example.com', 'Leo', 'Prueba', 'Clave-segura-483!')

    def revisar(self, pedir, cliente=None, fuentes=None):
        cliente = cliente or ia()
        with patch.object(lector, '_pedir', side_effect=pedir):
            conteos = lector.revisar_fuentes(fuentes, cliente=cliente, pausa=0)
        self.fuente.refresh_from_db()
        return conteos, cliente


class LectorTests(Datos):
    def test_robots_que_prohibe_se_salta_sin_descargar_ni_llamar_a_la_ia(self):
        pedir = MagicMock(side_effect=sitio(robots='User-agent: InfoTrip\nDisallow: /ficha.php\n'))
        conteos, cliente = self.revisar(pedir)
        self.assertEqual(conteos['robots'], 1)
        self.assertEqual(self.fuente.estado, 'robots')
        self.assertEqual([llamada.args[0] for llamada in pedir.call_args_list], [ROBOTS])
        cliente.messages.create.assert_not_called()
        self.assertFalse(PropuestaActualizacion.objects.exists())

    def test_robots_bloqueado_o_caido_no_descarga_y_sin_robots_si(self):
        with patch.object(lector, '_pedir', side_effect=http({ROBOTS: (403, '', '')})):
            self.assertFalse(lector.permitido_por_robots(URL))
        with patch.object(lector, '_pedir', side_effect=lector.ErrorLector('sin red')):
            self.assertFalse(lector.permitido_por_robots(URL))
        with patch.object(lector, '_pedir', side_effect=http({})):
            self.assertTrue(lector.permitido_por_robots(URL))

    def test_extraccion_valida_crea_la_propuesta_y_no_publica(self):
        conteos, cliente = self.revisar(sitio())
        self.assertEqual(conteos, {'propuesta': 1, 'revisadas': 1})
        propuesta = PropuestaActualizacion.objects.get()
        self.assertEqual((propuesta.dato_anterior, propuesta.dato_nuevo, propuesta.estado), ('80.00', '90.00', 'pendiente'))
        self.assertEqual((propuesta.url, propuesta.fecha_consulta), (URL, timezone.localdate()))
        self.assertEqual(propuesta.cita, 'Costo de entrada general: $90.00 pesos.')
        self.referencia.refresh_from_db()
        self.assertEqual(self.referencia.monto, Decimal('80'))  # Nada se publica sin aprobación.
        argumentos = cliente.messages.create.call_args.kwargs
        self.assertEqual(argumentos['model'], 'claude-haiku-5-5')
        self.assertEqual(argumentos['output_config']['format']['type'], 'json_schema')
        self.assertNotIn('var precio', argumentos['messages'][0]['content'])  # Solo texto visible.
        self.assertEqual(len(self.fuente.huella), 64)

    def test_sin_cambio_de_huella_no_llama_a_la_ia(self):
        self.revisar(sitio())
        self.fuente.ultima_revision = None
        self.fuente.save()
        conteos, cliente = self.revisar(sitio())
        self.assertEqual(conteos['sin_cambios'], 1)
        cliente.messages.create.assert_not_called()
        self.assertEqual(PropuestaActualizacion.objects.count(), 1)

    def test_cita_que_no_aparece_se_descarta(self):
        conteos, _ = self.revisar(sitio(), ia(cita='Entrada general: $90 pesos.'))
        self.assertEqual(conteos['descartada'], 1)
        self.assertFalse(PropuestaActualizacion.objects.exists())

    def test_valor_incoherente_se_descarta(self):
        for valor in ('noventa', '95', '-5', '999999'):
            with self.subTest(valor=valor):
                self.assertIsNone(lector.validar_extraccion(
                    {'valor': valor, 'cita': 'Costo de entrada general: $90.00 pesos.'},
                    lector.texto_visible(PAGINA, 'text/html'), 'precio'))

    def test_montos_y_horarios(self):
        self.assertEqual(lector.validar_monto('1,200', 'Tarifa $1,200.00'), Decimal('1200.00'))
        self.assertEqual(lector.validar_monto('0', 'Martes, entrada libre.'), Decimal('0'))
        self.assertIsNone(lector.validar_monto('0', 'Entrada: $90'))
        self.assertEqual(lector.validar_horario('Martes a domingo, 10:00 a 18:00', 'de 10:00 a 18:00 hrs'),
                         'Martes a domingo, 10:00 a 18:00')
        self.assertIsNone(lector.validar_horario('Todos los días', 'Abierto todos los días'))
        self.assertIsNone(lector.validar_horario('Lunes de 9:00 a 14:00', 'de 10:00 a 18:00'))

    def test_misma_propuesta_no_se_repite_y_dato_igual_no_se_propone(self):
        self.revisar(sitio())
        self.fuente.huella = ''
        self.fuente.save()
        self.revisar(sitio(), fuentes=[self.fuente])
        self.assertEqual(PropuestaActualizacion.objects.count(), 1)
        self.assertIn('Ya se había propuesto', self.fuente.nota)
        self.fuente.huella = ''
        self.fuente.save()
        conteos, _ = self.revisar(sitio(), ia(valor='80', cita='Costo de entrada general: $90.00 pesos.'),
                                  fuentes=[self.fuente])
        self.assertEqual(conteos['descartada'], 1)  # 80 no está en la cita.

    def test_horario_de_un_lugar(self):
        hotel = Lugar.objects.create(nombre='Hotel', tipo='dormir', subtipo='hotel', latitud=20.6, longitud=-103.3)
        fuente = FuenteOficial.objects.create(nombre='Ayuntamiento', url=URL, tipo_dato='horario', lugar=hotel)
        cliente = ia(valor='Martes a domingo de 10:00 a 18:00',
                     cita='Horario: martes a domingo de 10:00 a 18:00 hrs.')
        conteos, _ = self.revisar(sitio(), cliente, fuentes=[fuente])
        self.assertEqual(conteos['propuesta'], 1)
        propuesta = fuente.propuestas.get()
        self.assertEqual((propuesta.dato_anterior, propuesta.tipo_dato), ('', 'horario'))
        self.assertIn('horario de atención', cliente.messages.create.call_args.kwargs['messages'][0]['content'])

    def test_sin_dato_formato_errores_y_respuestas_incompletas(self):
        conteos, _ = self.revisar(sitio(), ia(encontrado=False))
        self.assertEqual(conteos['sin_dato'], 1)
        self.fuente.huella = ''
        self.fuente.save()
        conteos, _ = self.revisar(sitio(), ia(stop='max_tokens'), fuentes=[self.fuente])
        self.assertEqual(conteos['sin_dato'], 1)
        self.fuente.huella = ''
        self.fuente.save()
        conteos, _ = self.revisar(sitio(pagina='<p>Bienvenidos al museo.</p>'), fuentes=[self.fuente])
        self.assertEqual((conteos['sin_dato'], self.fuente.nota), (1, 'La página cambió, pero no menciona el dato.'))
        conteos, _ = self.revisar(sitio(tipo='application/pdf'), fuentes=[self.fuente])
        self.assertEqual(self.fuente.estado, 'formato')
        conteos, _ = self.revisar(http({URL: (500, '', '')}), fuentes=[self.fuente])
        self.assertEqual((self.fuente.estado, self.fuente.nota), ('error', 'El sitio respondió 500.'))
        rota = MagicMock()
        rota.messages.create.return_value = SimpleNamespace(stop_reason='end_turn',
                                                            content=[SimpleNamespace(type='text', text='no es json')])
        self.fuente.huella = ''
        self.fuente.save()
        self.assertEqual(self.revisar(sitio(), rota, fuentes=[self.fuente])[0]['sin_dato'], 1)

    def test_si_la_ia_falla_no_se_guarda_la_huella_para_reintentar(self):
        cliente = MagicMock()
        cliente.messages.create.side_effect = RuntimeError('caída')
        conteos, _ = self.revisar(sitio(), cliente)
        self.assertEqual((conteos['error'], self.fuente.huella), (1, ''))

    def test_redireccion_a_sitio_prohibido_y_paginas_enormes(self):
        def a_google(url):
            return 200, 'text/html', b'<p>$90</p>', 'https://www.google.com/maps'
        with patch.object(lector, '_pedir', side_effect=a_google), self.assertRaises(lector.ErrorLector):
            lector.descargar_texto(URL)
        with patch.object(lector, '_pedir', return_value=(200, 'text/html', b'x' * (lector.BYTES_MAXIMOS + 1), URL)):
            with self.assertRaisesMessage(lector.ErrorLector, 'demasiado grande'):
                lector.descargar_texto(URL)

    def test_texto_visible_y_fragmento(self):
        texto = lector.texto_visible(PAGINA, 'text/html')
        self.assertNotIn('999', texto)
        self.assertNotIn('<', texto)
        self.assertIn('Costo de entrada general: $90.00 pesos.', texto)
        self.assertEqual(lector.texto_visible('hola\n  mundo', 'text/plain'), 'hola mundo')
        largo = ('relleno ' * 2000) + 'Entrada $50' + (' relleno' * 2000)
        fragmento = lector.fragmento_relevante(largo, 'precio')
        self.assertIn('Entrada $50', fragmento)
        self.assertLessEqual(len(fragmento), lector.CARACTERES_MAXIMOS)
        self.assertEqual(lector.fragmento_relevante('sin nada útil', 'horario'), '')

    def test_descarga_real_usa_agente_propio_y_tiempo_maximo(self):
        respuesta_http = MagicMock(status=200, headers={'Content-Type': 'text/html'})
        respuesta_http.read.return_value = b'<p>hola</p>'
        respuesta_http.geturl.return_value = URL
        respuesta_http.__enter__.return_value = respuesta_http
        with patch('urllib.request.urlopen', return_value=respuesta_http) as abrir:
            self.assertEqual(lector._pedir(URL)[0], 200)
        peticion = abrir.call_args.args[0]
        self.assertEqual(peticion.get_header('User-agent'), 'InfoTrip/1.0 (+https://infotrip.online)')
        self.assertEqual(abrir.call_args.kwargs['timeout'], lector.SEGUNDOS_MAXIMOS)
        respuesta_http.read.assert_called_with(lector.BYTES_MAXIMOS + 1)

    @override_settings(ANTHROPIC_API_KEY='sk-prueba-no-real', IA_MODELO='claude-haiku-5-5')
    def test_cliente_oficial_con_la_clave_del_entorno(self):
        cliente = lector.cliente_ia()
        self.assertEqual(cliente.api_key, 'sk-prueba-no-real')

    def test_solo_revisa_las_que_tocan(self):
        self.fuente.ultima_revision = timezone.now() - timedelta(days=3)
        self.fuente.save()
        self.assertEqual(lector.pendientes_de_revisar(), [])
        self.fuente.ultima_revision = timezone.now() - timedelta(days=8)
        self.fuente.save()
        self.assertEqual(lector.pendientes_de_revisar(), [self.fuente])


class DominiosTests(Datos):
    def test_dominio_prohibido_rechazado(self):
        for url in ('https://www.google.com/maps/place/x', 'https://maps.google.com.mx/', 'https://goo.gl/abc',
                    'https://www.tripadvisor.com.mx/x', 'https://m.facebook.com/museo', 'https://instagram.com/x',
                    'https://www.booking.com/hotel', 'https://es.airbnb.mx/rooms/1'):
            with self.subTest(url=url):
                self.assertTrue(dominio_prohibido(url))
                with self.assertRaises(ValidationError):
                    validar_url_oficial(url)
        for url in (URL, 'https://www.jalisco.gob.mx/', 'https://www.inah.gob.mx/', 'https://museobooking-ficticio.mx'):
            self.assertFalse(dominio_prohibido(url), url)
        with self.assertRaises(ValidationError):
            validar_url_oficial('http://sic.cultura.gob.mx/')

    def test_el_modelo_no_acepta_fuentes_prohibidas_ni_incoherentes(self):
        mala = FuenteOficial(nombre='TA', url='https://www.tripadvisor.com/x', tipo_dato='precio', destino=self.destino,
                             referencia=self.referencia)
        with self.assertRaises(ValidationError):
            mala.full_clean()
        for cambios in ({'destino': None}, {'referencia': None}, {'tipo_dato': 'horario'}):
            with self.subTest(cambios=cambios):
                fuente = FuenteOficial(nombre='SIC', url=URL, tipo_dato='precio', destino=self.destino,
                                       referencia=self.referencia)
                for campo, valor in cambios.items():
                    setattr(fuente, campo, valor)
                with self.assertRaises(ValidationError):
                    fuente.clean()
        otro = Destino.objects.create(nombre='Otro', slug='otro', municipio=self.municipio, descripcion='-',
                                      latitud=20, longitud=-103)
        with self.assertRaises(ValidationError):
            FuenteOficial(nombre='SIC', url=URL, tipo_dato='precio', destino=otro, referencia=self.referencia).clean()

    def test_una_fuente_prohibida_que_se_cuela_se_desactiva_sin_descargar(self):
        FuenteOficial.objects.filter(pk=self.fuente.pk).update(url='https://www.facebook.com/museo')
        self.fuente.refresh_from_db()
        pedir = MagicMock()
        conteos, cliente = self.revisar(pedir)
        pedir.assert_not_called()
        self.assertFalse(self.fuente.activo)
        self.assertEqual(conteos['error'], 1)


class AprobacionTests(Datos):
    def propuesta(self, **campos):
        datos = dict(fuente=self.fuente, tipo_dato='precio', dato_anterior='80.00', dato_nuevo='90.00',
                     cita='Costo: $90.00', url=URL, fecha_consulta=date(2026, 11, 10))
        return PropuestaActualizacion.objects.create(**{**datos, **campos})

    def test_aprobar_actualiza_la_referencia_con_la_fecha_de_consulta(self):
        propuesta = self.propuesta()
        self.assertTrue(aprobar(propuesta, self.moderador))
        self.referencia.refresh_from_db()
        self.assertEqual((self.referencia.monto, self.referencia.fecha_consulta), (Decimal('90'), date(2026, 11, 10)))
        propuesta.refresh_from_db()
        self.assertEqual((propuesta.estado, propuesta.revisado_por), ('aprobada', self.moderador))
        self.assertFalse(aprobar(propuesta, self.moderador))

    def test_aprobar_un_horario_guarda_su_fuente(self):
        fuente = FuenteOficial.objects.create(nombre='SIC', url=URL, tipo_dato='horario', destino=self.destino)
        aprobar(self.propuesta(fuente=fuente, tipo_dato='horario', dato_anterior='', dato_nuevo='Martes a domingo 10:00'),
                self.moderador)
        self.destino.refresh_from_db()
        self.assertEqual((self.destino.horario, self.destino.horario_fuente_url, self.destino.horario_fecha_consulta),
                         ('Martes a domingo 10:00', URL, date(2026, 11, 10)))

    def test_rechazar_descarta_sin_tocar_el_dato(self):
        propuesta = self.propuesta()
        self.assertTrue(rechazar(propuesta, self.moderador))
        self.assertFalse(rechazar(propuesta, self.moderador))
        self.referencia.refresh_from_db()
        self.assertEqual(self.referencia.monto, Decimal('80'))
        self.assertEqual(PropuestaActualizacion.objects.get().estado, 'rechazada')

    def test_referencia_borrada_no_se_puede_aplicar(self):
        propuesta = self.propuesta()
        self.referencia.delete()
        with self.assertRaises(PropuestaNoAplicable):
            aprobar(propuesta, self.moderador)

    def test_acciones_del_admin(self):
        peticion = RequestFactory().post('/admin/')
        peticion.user = self.moderador
        peticion._messages = MagicMock()
        modelo_admin = PropuestaActualizacionAdmin(PropuestaActualizacion, AdminSite())
        uno, dos = self.propuesta(), self.propuesta(dato_nuevo='95.00')
        modelo_admin.aprobar(peticion, PropuestaActualizacion.objects.filter(pk=uno.pk))
        modelo_admin.rechazar(peticion, PropuestaActualizacion.objects.filter(pk=dos.pk))
        self.assertEqual(list(PropuestaActualizacion.objects.values_list('estado', flat=True)), ['aprobada', 'rechazada'])
        self.assertEqual(modelo_admin.cambio(uno), '80.00 → 90.00')
        self.assertIn('ver fuente', modelo_admin.ver_fuente(uno))
        self.assertEqual(modelo_admin.objetivo(uno), self.destino)
        tres = self.propuesta()
        self.referencia.delete()
        modelo_admin.aprobar(peticion, PropuestaActualizacion.objects.filter(pk=tres.pk))
        self.assertEqual(PropuestaActualizacion.objects.get(pk=tres.pk).estado, 'pendiente')
        FuenteOficialAdmin(FuenteOficial, AdminSite()).revisar_de_nuevo(peticion, FuenteOficial.objects.all())

    def test_la_cola_muestra_dato_anterior_nuevo_y_la_fuente(self):
        self.propuesta()
        self.client.force_login(self.moderador)
        pagina = self.client.get('/admin/moderacion/')
        self.assertContains(pagina, 'Actualizaciones de fuentes oficiales: 1')
        self.assertContains(pagina, 'Instituto Cultural Cabañas · Precio: 80.00 → 90.00')
        self.assertContains(pagina, f'href="{URL.replace("&", "&amp;")}"')
        self.assertContains(pagina, 'ver fuente')
        self.assertEqual(self.client.get('/admin/datos/propuestaactualizacion/').status_code, 200)
        self.assertEqual(self.client.get('/admin/datos/fuenteoficial/').status_code, 200)

    def test_el_grupo_de_moderacion_puede_aprobar(self):
        call_command('crear_moderacion', stdout=StringIO())
        persona = Usuario.objects.create_user('m2@example.com', 'Ana', 'P', 'Clave-segura-483!')
        persona.es_staff = True
        persona.save()
        persona.groups.add(Group.objects.get(name='Moderación'))
        persona = Usuario.objects.get(pk=persona.pk)
        self.assertTrue(persona.has_perm('datos.change_propuestaactualizacion'))
        self.assertFalse(persona.has_perm('datos.add_fuenteoficial'))


class SembrarTests(Datos):
    def test_siembra_desde_el_csv_sin_duplicar(self):
        call_command('cargar_referencias_costo', stdout=StringIO())
        salida = StringIO()
        call_command('sembrar_fuentes_oficiales', stdout=salida)
        self.assertIn('fuentes creadas', salida.getvalue())
        total = FuenteOficial.objects.count()
        self.assertGreater(total, 1)
        call_command('sembrar_fuentes_oficiales', stdout=StringIO())
        self.assertEqual(FuenteOficial.objects.count(), total)
        self.assertTrue(all(not dominio_prohibido(url) for url in FuenteOficial.objects.values_list('url', flat=True)))

    def test_pdf_inactivo_y_dominios_prohibidos_rechazados(self):
        Destino.objects.create(nombre='Autopista', slug='autopista', municipio=self.municipio, descripcion='-',
                               latitud=20, longitud=-103)
        ReferenciaCosto.objects.create(destino=Destino.objects.get(slug='autopista'), concepto='transporte', monto=10,
                                       descripcion='Caseta', fuente_nombre='CAPUFE',
                                       fuente_url='https://pot.capufe.mx/tarifas.pdf', fecha_consulta=date(2026, 1, 1))
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as archivo:
            archivo.write('destino,concepto,monto,descripcion,fuente_nombre,fuente_url,fecha_consulta,fecha_fuente\n'
                          'autopista,transporte,10,Caseta,CAPUFE,https://pot.capufe.mx/tarifas.pdf,2026-01-01,\n'
                          'autopista,entrada,10,X,TA,https://www.tripadvisor.com/x,2026-01-01,\n'
                          'no-existe,entrada,10,X,SIC,https://sic.cultura.gob.mx/x,2026-01-01,\n')
        salida = StringIO()
        call_command('sembrar_fuentes_oficiales', archivo=archivo.name, stdout=salida)
        os.unlink(archivo.name)
        self.assertIn('Sin referencia cargada: 1. Rechazadas por dominio: 1.', salida.getvalue())
        self.assertFalse(FuenteOficial.objects.get(url='https://pot.capufe.mx/tarifas.pdf').activo)
        with self.assertRaises(CommandError):
            call_command('sembrar_fuentes_oficiales', archivo='no-existe.csv', stdout=StringIO())

    def test_el_csv_no_pisa_un_precio_aprobado_despues(self):
        call_command('cargar_referencias_costo', stdout=StringIO())
        referencia = ReferenciaCosto.objects.exclude(pk=self.referencia.pk).get(destino=self.destino)
        fuente = FuenteOficial.objects.create(nombre='SIC', url=referencia.fuente_url, tipo_dato='precio',
                                              destino=self.destino, referencia=referencia)
        aprobar(PropuestaActualizacion.objects.create(
            fuente=fuente, tipo_dato='precio', dato_anterior='80.00', dato_nuevo='95.00', cita='$95',
            url=fuente.url, fecha_consulta=date(2026, 11, 10)), self.moderador)
        salida = StringIO()
        call_command('cargar_referencias_costo', stdout=salida)
        self.assertIn('1 conservadas', salida.getvalue())
        referencia.refresh_from_db()
        self.assertEqual(referencia.monto, Decimal('95'))


IMPORTAR_LUGARES = 'apps.destinos.management.commands.importar_lugares.descargar'
IMPORTAR_DENUE = 'apps.destinos.management.commands.importar_denue.descargar'


class AusentesTests(TestCase):
    def importar(self, *nodos):
        with patch(IMPORTAR_LUGARES, return_value=respuesta(*nodos)):
            return tareas.osm()

    def test_lugar_desaparecido_se_marca_y_no_se_borra(self):
        uno = nodo(1, 'Fonda Uno', 19.9, -103.5, amenity='restaurant')
        dos = nodo(2, 'Café Dos', 19.91, -103.5, amenity='cafe', opening_hours='Mo-Fr 08:00-14:00')
        self.assertEqual(self.importar(uno, dos)['creados'], 2)
        conteos = self.importar(dict(uno, tags={'name': 'Fonda Uno Renovada', 'amenity': 'restaurant'}))
        self.assertEqual((conteos['actualizados'], conteos['posiblemente_cerrados']), (1, 1))
        ausente = Lugar.objects.get(osm_id='node/2')
        self.assertTrue(ausente.posiblemente_cerrado and ausente.es_activo)
        self.assertEqual(ausente.ausente_desde, timezone.localdate())
        self.assertEqual(Lugar.objects.get(osm_id='node/1').nombre, 'Fonda Uno Renovada')
        self.assertEqual(Lugar.objects.count(), 2)
        # Si vuelve a aparecer, se quita la marca sola.
        conteos = self.importar(uno, dos)
        self.assertEqual(conteos['reaparecidos'], 1)
        self.assertFalse(Lugar.objects.get(osm_id='node/2').posiblemente_cerrado)

    def test_actualiza_horario_salvo_el_aprobado_de_una_fuente_oficial(self):
        dos = nodo(2, 'Café Dos', 19.91, -103.5, amenity='cafe', opening_hours='Mo-Fr 08:00-14:00')
        self.importar(dos)
        self.assertEqual(Lugar.objects.get().horario, 'Mo-Fr 08:00-14:00')
        self.importar(dict(dos, tags={**dos['tags'], 'opening_hours': 'Mo-Su 09:00-20:00'}))
        self.assertEqual(Lugar.objects.get().horario, 'Mo-Su 09:00-20:00')
        Lugar.objects.update(horario='Lunes a domingo 9:00 a 21:00', horario_fuente_url=URL)
        self.importar(dos)
        self.assertEqual(Lugar.objects.get().horario, 'Lunes a domingo 9:00 a 21:00')

    def test_una_persona_decide_en_la_cola(self):
        uno, dos = nodo(1, 'Fonda Uno', 19.9, -103.5, amenity='restaurant'), nodo(2, 'Bar', 19.9, -103.5, amenity='bar')
        self.importar(uno, dos)
        self.importar(uno)
        moderador = Usuario.objects.create_superuser('mod@example.com', 'Leo', 'Prueba', 'Clave-segura-483!')
        self.client.force_login(moderador)
        pagina = self.client.get('/admin/moderacion/')
        self.assertContains(pagina, 'Lugares que ya no aparecen en su fuente (OpenStreetMap o DENUE): 1')
        self.assertContains(pagina, 'Bar · ')
        from apps.destinos.admin import LugarAdmin
        peticion = RequestFactory().post('/admin/')
        peticion.user = moderador
        LugarAdmin(Lugar, AdminSite()).sigue_abierto(peticion, Lugar.objects.filter(osm_id='node/2'))
        bar = Lugar.objects.get(osm_id='node/2')
        self.assertFalse(bar.posiblemente_cerrado)
        self.assertTrue(bar.protegido)
        self.importar(uno)  # Ya verificado: no se vuelve a marcar.
        self.assertFalse(Lugar.objects.get(osm_id='node/2').posiblemente_cerrado)

    @override_settings(DENUE_TOKEN='clave-de-prueba')
    def test_denue_tambien_marca_ausentes(self):
        from apps.destinos.test_denue import registro
        with patch(IMPORTAR_DENUE, return_value=[registro(1), registro(2, nombre='HOTEL VALLE', Latitud='19.99')]):
            tareas.denue()
        with patch(IMPORTAR_DENUE, return_value=[registro(1)]):
            conteos = tareas.denue()
        self.assertEqual(conteos['posiblemente_cerrados'], 1)
        self.assertTrue(Lugar.objects.get(denue_id='2').posiblemente_cerrado)


class TareasTests(TestCase):
    def test_tarea_sin_claves_se_salta_y_queda_registrada(self):
        for nombre in ('denue', 'fuentes_oficiales'):
            with self.subTest(tarea=nombre):
                registro = tareas.ejecutar(nombre)
                self.assertEqual(registro.resultado, 'saltada')
                self.assertIn('Falta', registro.mensaje)
                self.assertIsNotNone(registro.fin)
        self.assertEqual(EjecucionTarea.objects.count(), 2)

    def test_registro_de_ejecucion_con_conteos_y_errores(self):
        with patch(IMPORTAR_LUGARES, return_value=respuesta(nodo(1, 'Fonda', 19.9, -103.5, amenity='restaurant'))):
            registro = tareas.ejecutar('osm')
        self.assertEqual((registro.resultado, registro.conteos['creados']), ('exito', 1))
        from apps.destinos.osm import ErrorOverpass
        with patch(IMPORTAR_LUGARES, side_effect=ErrorOverpass('saturado')):
            registro = tareas.ejecutar('osm')
        self.assertEqual(registro.resultado, 'error')
        self.assertIn('saturado', registro.mensaje)
        self.assertEqual(str(registro), 'Lugares de OpenStreetMap · Error')

    def test_calendario(self):
        self.assertTrue(tareas.toca('osm'))
        registro = EjecucionTarea.objects.create(tarea='osm', resultado='exito')
        self.assertFalse(tareas.toca('osm'))
        self.assertTrue(tareas.toca('osm', registro.inicio + timedelta(days=7)))
        EjecucionTarea.objects.create(tarea='denue', resultado='exito')
        self.assertFalse(tareas.toca('denue', timezone.now() + timedelta(days=20)))
        self.assertTrue(tareas.toca('denue', timezone.now() + timedelta(days=31)))
        saltada = EjecucionTarea.objects.create(tarea='fuentes_oficiales', resultado='saltada')
        self.assertTrue(tareas.toca('fuentes_oficiales', saltada.inicio + timedelta(days=1)))

    @override_settings(TAREAS_PROGRAMADAS='denue, desconocida')
    def test_comando_corre_lo_que_toca_y_se_salta_sin_claves(self):
        salida = StringIO()
        call_command('ejecutar_tareas', stdout=salida)
        self.assertIn('denue: saltada · Falta DENUE_TOKEN', salida.getvalue())
        salida = StringIO()
        call_command('ejecutar_tareas', stdout=salida)
        self.assertIn('Ninguna tarea pendiente.', salida.getvalue())

    @override_settings(TAREAS_PROGRAMADAS='')
    def test_vacio_apaga_todo_y_tarea_forzada(self):
        call_command('ejecutar_tareas', stdout=StringIO())
        self.assertFalse(EjecucionTarea.objects.exists())
        with patch(IMPORTAR_LUGARES, return_value=respuesta(nodo(1, 'Fonda', 19.9, -103.5, amenity='restaurant'))):
            salida = StringIO()
            call_command('ejecutar_tareas', tarea='osm', stdout=salida)
        self.assertIn('osm: éxito · creados 1', salida.getvalue())
        with patch(IMPORTAR_LUGARES, return_value={'elements': []}), self.assertRaises(CommandError):
            call_command('ejecutar_tareas', tarea='osm', stdout=StringIO())

    @override_settings(ANTHROPIC_API_KEY='sk-prueba-no-real')
    def test_fuentes_oficiales_con_clave(self):
        with patch.object(lector, 'revisar_fuentes', return_value={'revisadas': 0}) as revisar:
            registro = tareas.ejecutar('fuentes_oficiales')
        revisar.assert_called_once()
        self.assertEqual((registro.resultado, registro.conteos), ('exito', {'revisadas': 0}))

    def test_comando_del_lector_sin_clave_no_hace_nada(self):
        salida = StringIO()
        with patch.object(lector, '_pedir') as pedir:
            call_command('revisar_fuentes_oficiales', stdout=salida)
        pedir.assert_not_called()
        self.assertIn('Falta ANTHROPIC_API_KEY', salida.getvalue())

    @override_settings(ANTHROPIC_API_KEY='sk-prueba-no-real')
    def test_comando_del_lector_con_clave(self):
        with patch('apps.datos.management.commands.revisar_fuentes_oficiales.revisar_fuentes',
                   return_value={'revisadas': 0}) as revisar:
            salida = StringIO()
            call_command('revisar_fuentes_oficiales', fuente=[1], pausa=0, stdout=salida)
            call_command('revisar_fuentes_oficiales', pausa=0, stdout=StringIO())
        self.assertEqual(revisar.call_args_list[0].args[0], [])
        self.assertIn('revisadas: 0', salida.getvalue())

    def test_admin_de_ejecuciones_es_solo_lectura(self):
        registro = EjecucionTarea.objects.create(tarea='osm', resultado='exito', conteos={'creados': 3})
        modelo_admin = EjecucionTareaAdmin(EjecucionTarea, AdminSite())
        peticion = RequestFactory().get('/admin/')
        self.assertFalse(modelo_admin.has_add_permission(peticion))
        self.assertFalse(modelo_admin.has_change_permission(peticion, registro))
        self.assertFalse(modelo_admin.has_delete_permission(peticion, registro))
        self.assertEqual(modelo_admin.resumen(registro), 'creados 3')
        registro.mensaje = 'Falta DENUE_TOKEN'
        self.assertEqual(modelo_admin.resumen(registro), 'Falta DENUE_TOKEN')
