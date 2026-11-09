"""Rutas compartidas: enlace público, caducidad, borrado, Google Maps y calendario."""
import json
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .exportar import MAXIMO_WAYPOINTS, enlace_google_maps
from .models import DIAS_DE_VIDA_ANONIMA, RutaCompartida
from . import test_planeador
from .test_planeador import proximo

URL = '/api/v1/rutas/compartidas/'
LATITUD, LONGITUD = 20.68123, -103.34987


class CompartirTests(APITestCase):
    # Los mismos destinos, horarios y precios que las pruebas del planeador.
    setUp = test_planeador.PlaneadorTests.setUp

    def datos(self, **cambios):
        return {'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 2, 'hora_inicio': '09:00',
                'hora_fin': '19:00', 'intereses': ['ciudad-y-cultura'], 'ritmo': 'normal', 'personas': 2,
                'presupuesto': None, 'regresar': True, **cambios}

    def compartir(self, **cambios):
        return self.client.post(URL, self.datos(**cambios), format='json')

    def test_compartir_sin_cuenta_da_enlace_publico_que_caduca(self):
        respuesta = self.compartir()
        self.assertEqual(respuesta.status_code, 201)
        ruta = RutaCompartida.objects.get()
        self.assertIsNone(ruta.autor)
        self.assertEqual(respuesta.json()['url'], f'/planeador/r/{ruta.enlace}/')
        esperado = timezone.now() + timedelta(days=DIAS_DE_VIDA_ANONIMA)
        self.assertLess(abs((ruta.caduca - esperado).total_seconds()), 60)
        self.assertEqual(ruta.titulo, 'Ruta de 2 días desde Guadalajara')
        self.assertEqual(ruta.parametros['municipio'], 'guadalajara')
        # El plan guardado es el mismo que da el planeador para esa petición.
        planeado = self.client.post('/api/v1/rutas/planear/', self.datos(), format='json').json()
        self.assertEqual([[p['destino']['nombre'] for p in d['paradas']] for d in ruta.plan['dias']],
                         [[p['destino']['nombre'] for p in d['paradas']] for d in planeado['dias']])
        self.assertEqual(Evento.objects.filter(nombre='ruta_compartida').count(), 1)

        pagina = self.client.get(ruta.get_absolute_url())
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, '<meta name="robots" content="noindex">', html=True)
        self.assertContains(pagina, 'property="og:title" content="Ruta de 2 días desde Guadalajara — InfoTrip"')
        self.assertContains(pagina, 'Hospicio Cabañas')
        self.assertContains(pagina, 'Armar mi propia ruta')
        self.assertContains(pagina, 'href="https://wa.me/?text=')
        self.assertContains(pagina, f'href="/planeador/r/{ruta.enlace}/calendario.ics"')
        self.assertContains(pagina, 'https://www.google.com/maps/dir/?api=1')
        # Sin scripts en línea: la CSP los bloquearía. Solo el JSON de datos, que no se ejecuta.
        self.assertEqual(re.findall(r'<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>', pagina.content.decode()),
                         [])

    def test_con_cuenta_queda_en_el_perfil_y_se_puede_borrar(self):
        ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'x')
        self.client.force_authenticate(ana)
        self.assertEqual(self.compartir().status_code, 201)
        ruta = RutaCompartida.objects.get()
        self.assertEqual(ruta.autor, ana)
        self.assertIsNone(ruta.caduca)
        lista = self.client.get(URL).json()['rutas']
        self.assertEqual([r['enlace'] for r in lista], [str(ruta.enlace)])

        # Otra persona no la ve en su lista ni puede borrarla.
        beto = Usuario.objects.create_user('beto@example.com', 'Beto', 'P', 'x')
        self.client.force_authenticate(beto)
        self.assertEqual(self.client.get(URL).json()['rutas'], [])
        self.assertEqual(self.client.delete(f'{URL}{ruta.enlace}/').status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.delete(f'{URL}{ruta.enlace}/').status_code, 401)
        self.assertEqual(self.client.get(URL).status_code, 401)

        self.client.force_authenticate(ana)
        self.assertEqual(self.client.delete(f'{URL}{ruta.enlace}/').status_code, 204)
        self.assertFalse(RutaCompartida.objects.exists())
        self.assertEqual(self.client.get(ruta.get_absolute_url()).status_code, 404)

    def test_enlace_caducado(self):
        self.compartir()
        ruta = RutaCompartida.objects.get()
        RutaCompartida.objects.filter(pk=ruta.pk).update(caduca=timezone.now() - timedelta(minutes=1))
        pagina = self.client.get(ruta.get_absolute_url())
        self.assertEqual(pagina.status_code, 410)
        self.assertContains(pagina, 'Este enlace caducó', status_code=410)
        self.assertContains(pagina, 'Armar mi propia ruta', status_code=410)
        self.assertEqual(self.client.get(f'{ruta.get_absolute_url()}calendario.ics').status_code, 404)
        self.assertEqual(self.client.get('/planeador/r/00000000-0000-0000-0000-000000000000/').status_code, 404)
        # Al compartir otra, las caducadas se borran.
        self.compartir()
        self.assertFalse(RutaCompartida.objects.filter(pk=ruta.pk).exists())
        self.assertEqual(RutaCompartida.objects.vigentes().count(), 1)

    def test_desde_mi_ubicacion_no_guarda_coordenadas(self):
        datos = self.datos(latitud=LATITUD, longitud=LONGITUD)
        del datos['municipio']
        respuesta = self.client.post(URL, datos, format='json')
        self.assertEqual(respuesta.status_code, 201)
        ruta = RutaCompartida.objects.get()
        self.assertEqual(ruta.origen_nombre, 'Cerca de Guadalajara')
        self.assertEqual(ruta.plan['origen'], {'nombre': 'Cerca de Guadalajara'})
        self.assertEqual(ruta.parametros['desde'], 'ubicacion')
        guardado = json.dumps([ruta.parametros, ruta.plan, ruta.titulo])
        for valor in (LATITUD, LONGITUD):
            self.assertNotIn(str(valor), guardado)
            self.assertNotIn(str(round(valor, 2)), guardado)
        self.assertNotIn('latitud', json.dumps(ruta.parametros))
        pagina = self.client.get(ruta.get_absolute_url()).content.decode()
        self.assertNotIn(str(LATITUD), pagina)
        self.assertIn('Ruta de 2 días desde Cerca de Guadalajara', pagina)
        # El enlace a Google Maps del primer día sale desde donde esté quien lo abra.
        self.assertNotIn('origin=', re.search(r'https://www\.google\.com/maps/dir/[^"]+', pagina).group())

    def test_calendario_ics_valido(self):
        self.compartir()
        ruta = RutaCompartida.objects.get()
        respuesta = self.client.get(f'{ruta.get_absolute_url()}calendario.ics')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertIn('attachment; filename="ruta-infotrip-', respuesta['Content-Disposition'])
        texto = respuesta.content.decode('utf-8')
        self.assertTrue(texto.startswith('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'))
        self.assertTrue(texto.endswith('END:VCALENDAR\r\n'))
        # Todas las líneas terminan en CRLF y miden 75 octetos o menos.
        self.assertNotIn('\n', texto.replace('\r\n', ''))
        for linea in texto.split('\r\n'):
            self.assertLessEqual(len(linea.encode('utf-8')), 75, linea)
        desplegado = texto.replace('\r\n ', '')
        paradas = [(d['fecha'], p) for d in ruta.plan['dias'] for p in d['paradas']]
        self.assertEqual(desplegado.count('BEGIN:VEVENT'), len(paradas))
        self.assertEqual(desplegado.count('BEGIN:VEVENT'), desplegado.count('END:VEVENT'))
        self.assertIn('TZID:America/Mexico_City', desplegado)
        fecha, primera = paradas[0]
        inicio = f'DTSTART;TZID=America/Mexico_City:{fecha.replace("-", "")}T{primera["inicio"].replace(":", "")}00'
        self.assertIn(inicio, desplegado)
        self.assertIn(f'SUMMARY:{primera["destino"]["nombre"]}', desplegado)
        self.assertEqual(len(set(re.findall(r'^UID:(.+)$', desplegado, re.M))), len(paradas))
        # Los textos con comas o punto y coma van escapados.
        self.assertIn('LOCATION:Hospicio Cabañas\\, Guadalajara\\, Jalisco', desplegado)

    def test_google_maps_por_dia(self):
        plan = self.client.post('/api/v1/rutas/planear/', self.datos(dias=1), format='json').json()
        enlace = plan['dias'][0]['google_maps']
        consulta = parse_qs(urlparse(enlace['url']).query)
        origen = f'{plan["origen"]["latitud"]},{plan["origen"]["longitud"]}'
        # Sale del municipio y regresa a él, pasando por las paradas en orden.
        self.assertEqual(consulta['origin'], [origen])
        self.assertEqual(consulta['destination'], [origen])
        paradas = [f'{p["destino"]["latitud"]},{p["destino"]["longitud"]}' for p in plan['dias'][0]['paradas']]
        self.assertEqual(consulta['waypoints'][0].split('|'), paradas)
        # Desde la ubicación: ni origen ni regreso con sus coordenadas.
        datos = self.datos(dias=1, latitud=LATITUD, longitud=LONGITUD)
        del datos['municipio']
        url = self.client.post('/api/v1/rutas/planear/', datos, format='json').json()['dias'][0]['google_maps']['url']
        self.assertNotIn(str(LATITUD), url)

    def test_google_maps_respeta_el_limite_de_paradas(self):
        paradas = [{'destino': {'latitud': 20 + i / 100, 'longitud': -103}} for i in range(14)]
        enlace = enlace_google_maps(paradas, origen='20.5,-103.3')
        consulta = parse_qs(urlparse(enlace['url']).query)
        self.assertEqual(len(consulta['waypoints'][0].split('|')), MAXIMO_WAYPOINTS)
        self.assertEqual((enlace['incluidas'], enlace['total']), (MAXIMO_WAYPOINTS + 1, 14))
        self.assertIsNone(enlace_google_maps([]))

    def test_peticion_invalida_y_limite(self):
        self.assertEqual(self.compartir(intereses=[]).status_code, 400)
        self.assertFalse(RutaCompartida.objects.exists())
        codigos = [self.compartir(intereses=[]).status_code for _ in range(10)]
        self.assertEqual(codigos[-1], 429)
