from datetime import timedelta
from django.core.management import call_command
from io import StringIO
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, RequestFactory
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from apps.usuarios.models import Usuario
from apps.destinos.models import Destino, Region, Municipio
from .models import Aporte, Reporte, Decision
from .admin import AporteAdmin, ReporteAdmin
from .selectors import resumen


class ComunidadTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.temp = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.override.disable)
        self.user = Usuario.objects.create_user('ana@example.com','Ana','Prueba','Clave-segura-483!',es_verificado=True)
        self.other = Usuario.objects.create_user('leo@example.com','Leo','Prueba','Clave-segura-483!',es_verificado=True)
        self.staff = Usuario.objects.create_superuser('admin@example.com','Admin','Prueba','Clave-segura-483!')
        region = Region.objects.create(nombre='Región',slug='region')
        municipio = Municipio.objects.create(nombre='Municipio',slug='municipio',region=region)
        self.destino = Destino.objects.create(nombre='Destino',slug='destino',municipio=municipio,descripcion='Lugar',latitud=20,longitud=-103)
        self.url = '/api/v1/destinos/destino/aportes/'
        self.payload = dict(tipo='resena',texto='Experiencia real de prueba',fecha_visita=str(timezone.localdate()),calificacion=4)

    def login(self, user=None):
        token = RefreshToken.for_user(user or self.user)
        token['correo_confirmado'] = True
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(token.access_token))

    def aporte(self, **kwargs):
        datos = dict(autor=self.user,destino=self.destino,tipo='resena',texto='Aporte prueba',fecha_visita=timezone.localdate(),calificacion=4)
        datos.update(kwargs)
        return Aporte.objects.create(**datos)

    def test_anonimo_y_correo_sin_verificar_no_publican(self):
        self.assertEqual(self.client.post(self.url,self.payload).status_code,401)
        self.user.es_verificado=False;self.user.save()
        self.login()
        self.assertEqual(self.client.post(self.url,self.payload).status_code,401)

    def test_publicar_pendiente_y_una_resena_por_destino(self):
        self.login()
        respuesta=self.client.post(self.url,dict(self.payload,estado='publicado',autor=self.other.pk))
        self.assertEqual(respuesta.status_code,201,respuesta.data)
        aporte=Aporte.objects.get()
        self.assertEqual(aporte.autor,self.user)
        self.assertEqual(aporte.estado,'pendiente')
        self.assertEqual(self.client.post(self.url,self.payload).status_code,400)
        self.assertEqual(self.client.get(self.url).data['count'],0)
        self.assertEqual(self.client.get('/api/v1/mis-aportes/').data['count'],1)

    def test_calificacion_y_fecha_invalidas(self):
        self.login()
        for cambios in [dict(calificacion=0),dict(calificacion=6),dict(fecha_visita=str(timezone.localdate()+timedelta(days=1))),dict(texto='')]:
            self.assertEqual(self.client.post(self.url,dict(self.payload,**cambios)).status_code,400)
        self.assertEqual(Aporte.objects.count(),0)

    def test_publicacion_edicion_retiro_y_permisos(self):
        aporte=self.aporte()
        request=RequestFactory().post('/admin/');request.user=self.staff
        admin=AporteAdmin(Aporte,AdminSite())
        admin.publicar(request,Aporte.objects.all())
        self.assertEqual(Decision.objects.count(),1)
        self.assertEqual(self.client.get(self.url).data['count'],1)
        self.login(self.other)
        url=f'/api/v1/aportes/{aporte.pk}/'
        self.assertEqual(self.client.patch(url,{'texto':'Intento ajeno'}).status_code,404)
        self.assertEqual(self.client.delete(url).status_code,404)
        self.login()
        self.assertEqual(self.client.patch(url,{'texto':'Edición propia'}).status_code,200)
        aporte.refresh_from_db();self.assertEqual(aporte.estado,'pendiente')
        self.assertEqual(self.client.get(self.url).data['count'],0)
        self.assertEqual(self.client.delete(url).status_code,204)
        aporte.refresh_from_db();self.assertEqual(aporte.estado,'retirado')
        admin.publicar(request,Aporte.objects.all())
        aporte.refresh_from_db();self.assertEqual(aporte.estado,'retirado')
        self.assertEqual(self.client.post(self.url,self.payload).status_code,201)

    def test_reportar_duplicado_y_resolucion_con_historial(self):
        aporte=self.aporte(estado='publicado')
        self.login(self.other)
        url=f'/api/v1/aportes/{aporte.pk}/reportar/'
        self.assertEqual(self.client.post(url,{'motivo':'Información incorrecta'}).status_code,201)
        self.assertEqual(self.client.post(url,{'motivo':'Otra vez'}).status_code,400)
        request=RequestFactory().post('/admin/');request.user=self.staff
        ReporteAdmin(Reporte,AdminSite()).resolver_ocultando(request,Reporte.objects.all())
        aporte.refresh_from_db();self.assertEqual(aporte.estado,'oculto')
        self.assertTrue(Reporte.objects.get().resuelto)
        self.assertEqual(Decision.objects.get().moderador,self.staff)
        self.assertEqual(self.client.get(self.url).data['count'],0)

    def test_reporte_solo_sobre_contenido_publico_ajeno(self):
        aporte=self.aporte(estado='publicado')
        self.login()
        self.assertEqual(self.client.post(f'/api/v1/aportes/{aporte.pk}/reportar/',{'motivo':'Propio'}).status_code,400)
        self.login(self.other)
        aporte.estado='pendiente';aporte.save()
        self.assertEqual(self.client.post(f'/api/v1/aportes/{aporte.pk}/reportar/',{'motivo':'Oculto'}).status_code,404)

    def test_fotografia_se_reescribe_y_rechaza_archivos_invalidos(self):
        self.login()
        image=BytesIO();Image.new('RGB',(30,30),'blue').save(image,'PNG')
        data=dict(tipo='foto',texto='Foto de visita',fecha_visita=str(timezone.localdate()),imagen=SimpleUploadedFile('foto.png',image.getvalue(),content_type='image/png'))
        respuesta=self.client.post(self.url,data,format='multipart')
        self.assertEqual(respuesta.status_code,201,respuesta.data)
        aporte=Aporte.objects.get();self.assertTrue(aporte.imagen.name.endswith('.jpg'))
        data['imagen']=SimpleUploadedFile('falsa.jpg',b'<script>alert(1)</script>',content_type='image/jpeg')
        self.assertEqual(self.client.post(self.url,data,format='multipart').status_code,400)
        data['imagen']=SimpleUploadedFile('grande.png',image.getvalue()+b'x'*(5*1024*1024),content_type='image/png')
        self.assertEqual(self.client.post(self.url,data,format='multipart').status_code,400)

    def test_gastos_por_concepto_y_periodo_sin_mezclar_unidades(self):
        for monto,concepto,dias,estado in [(100,'comida',1,'publicado'),(300,'comida',2,'publicado'),(900,'alojamiento',1,'publicado'),(999,'comida',400,'publicado'),(900,'comida',1,'pendiente')]:
            self.aporte(tipo='gasto',calificacion=None,monto=monto,concepto=concepto,fecha_visita=timezone.localdate()-timedelta(days=dias),estado=estado)
        gastos={fila['concepto']:fila for fila in resumen(self.destino)['gastos']}
        self.assertEqual(gastos['comida']['promedio'],Decimal(200))
        self.assertEqual(gastos['comida']['cantidad'],2)
        self.assertEqual(gastos['alojamiento']['promedio'],Decimal(900))
        self.assertEqual(self.client.get('/destinos/',{'concepto':'comida','precio_max':'250'}).context['pagina'].paginator.count,1)
        self.assertEqual(self.client.get('/destinos/',{'concepto':'comida','precio_max':'150'}).context['pagina'].paginator.count,0)
        self.assertEqual(self.client.get('/api/v1/destinos/',{'precio_max':'150'}).status_code,400)

    def test_filtro_nota_y_paginacion_sin_none(self):
        self.aporte(estado='publicado')
        self.assertEqual(self.client.get('/destinos/',{'calificacion_min':'4'}).context['pagina'].paginator.count,1)
        self.assertEqual(self.client.get('/destinos/',{'calificacion_min':'5'}).context['pagina'].paginator.count,0)
        response=self.client.get('/destinos/')
        self.assertNotIn('None',response.context['filtros'])
        self.assertEqual(self.client.get('/api/v1/destinos/',{'calificacion_min':'4'}).data['count'],1)

    def test_destino_y_autor_inactivos_no_aparecen(self):
        self.aporte(estado='publicado')
        self.user.es_activo=False;self.user.save()
        self.assertEqual(self.client.get(self.url).data['count'],0)
        self.user.es_activo=True;self.user.save()
        self.destino.es_activo=False;self.destino.save()
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.login();self.assertEqual(self.client.post(self.url,self.payload).status_code,404)

    def test_html_escapa_aportes_y_no_expone_email(self):
        self.aporte(estado='publicado',texto='<script>alert(1)</script>')
        response=self.client.get('/destinos/destino/')
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertNotContains(response,self.user.email)

    def test_gasto_negativo_y_campos_de_otro_tipo(self):
        self.login()
        data=dict(tipo='gasto',texto='Entrada',fecha_visita=str(timezone.localdate()),concepto='entrada',monto='-1')
        self.assertEqual(self.client.post(self.url,data).status_code,400)
        self.assertEqual(self.client.post(self.url,dict(self.payload,monto=10)).status_code,400)

    def test_admin_catalogo_y_moderacion_disponibles(self):
        self.client.force_login(self.staff)
        for url in ['/admin/destinos/destino/', '/admin/destinos/destino/add/', '/admin/comunidad/aporte/', '/admin/comunidad/reporte/', '/admin/comunidad/decision/', '/admin/usuarios/usuario/add/']:
            self.assertEqual(self.client.get(url).status_code,200,url)

    def test_foto_publicada_aparece_en_portada_y_oculta_no(self):
        self.login()
        image=BytesIO();Image.new('RGB',(30,30),'blue').save(image,'PNG')
        self.client.post(self.url,dict(tipo='foto',texto='Foto azul',fecha_visita=str(timezone.localdate()),imagen=SimpleUploadedFile('foto.png',image.getvalue(),content_type='image/png')),format='multipart')
        aporte=Aporte.objects.get()
        self.assertEqual(self.client.get('/').context['exploracion'][0]['foto_url'],'')
        aporte.estado='publicado';aporte.save()
        self.assertEqual(self.client.get('/').context['exploracion'][0]['foto_url'],aporte.imagen.url)
        aporte.estado='oculto';aporte.save()
        self.assertEqual(self.client.get('/').context['exploracion'][0]['foto_url'],'')

    def test_carga_inicial_idempotente_conserva_ediciones(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('cargar_destinos_iniciales',stdout=StringIO())
        self.assertEqual(Destino.objects.count(),16)
        tequila=Destino.objects.get(slug='tequila');tequila.es_activo=False;tequila.descripcion='Edición propia';tequila.save()
        call_command('cargar_destinos_iniciales',stdout=StringIO())
        tequila.refresh_from_db();self.assertFalse(tequila.es_activo);self.assertEqual(tequila.descripcion,'Edición propia')
        self.assertEqual(Destino.objects.count(),16)


class MiniaturasTests(APITestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.override.disable)
        self.user = Usuario.objects.create_user('foto@example.com', 'Ana', 'P', 'Clave-segura-483!', es_verificado=True)
        token = RefreshToken.for_user(self.user)
        token['correo_confirmado'] = True
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-', latitud=20, longitud=-103)

    def subir(self):
        imagen = BytesIO()
        Image.new('RGB', (2000, 1000), 'blue').save(imagen, 'PNG')
        return self.client.post('/api/v1/destinos/d/aportes/', {
            'tipo': 'foto', 'texto': 'Foto', 'fecha_visita': str(timezone.localdate()),
            'imagen': SimpleUploadedFile('a.png', imagen.getvalue(), content_type='image/png')}, format='multipart')

    def test_subir_una_foto_crea_su_miniatura_y_las_paginas_la_usan(self):
        self.assertEqual(self.subir().status_code, 201)
        aporte = Aporte.objects.get()
        with Image.open(aporte.miniatura.path) as miniatura:
            self.assertEqual((miniatura.width, miniatura.format), (800, 'JPEG'))
        with Image.open(aporte.imagen.path) as original:
            self.assertEqual(original.width, 2000)
        Aporte.objects.update(estado='publicado')
        self.assertContains(self.client.get('/destinos/d/'), f'src="{aporte.miniatura.url}"')
        self.assertContains(self.client.get('/destinos/'), f'src="{aporte.miniatura.url}"')

    def test_el_comando_completa_fotos_antiguas_y_se_puede_repetir(self):
        self.subir()
        aporte = Aporte.objects.get()
        Aporte.objects.update(miniatura='')
        call_command('generar_miniaturas', stdout=StringIO())
        aporte.refresh_from_db()
        self.assertTrue(aporte.miniatura)
        nombre = aporte.miniatura.name
        call_command('generar_miniaturas', stdout=StringIO())
        aporte.refresh_from_db()
        self.assertEqual(aporte.miniatura.name, nombre)
