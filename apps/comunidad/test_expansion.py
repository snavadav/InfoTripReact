from datetime import timedelta
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from apps.usuarios.models import Usuario
from apps.destinos.models import Destino, Region, Municipio
from .models import Colaboracion, RevisionColaboracion, Favorito, Viaje
from .admin import ColaboracionAdmin
from .practica import ficha_practica


class ExpansionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client=APIClient()
        self.user=Usuario.objects.create_user('uno@example.com','Uno','Prueba','test',es_verificado=True)
        self.other=Usuario.objects.create_user('dos@example.com','Dos','Prueba','test',es_verificado=True)
        self.staff=Usuario.objects.create_superuser('staff@example.com','Editor','Prueba','test')
        region=Region.objects.create(nombre='Region',slug='region')
        municipio=Municipio.objects.create(nombre='Municipio',slug='municipio',region=region)
        self.destino=Destino.objects.create(nombre='Destino',slug='destino',municipio=municipio,descripcion='Lugar',latitud=20,longitud=-103)
        self.second=Destino.objects.create(nombre='Otro',slug='otro',municipio=municipio,descripcion='Otro',latitud=20,longitud=-103)
        self.client.force_authenticate(self.user)
        self.url='/api/v1/destinos/destino/colaboraciones/'
        self.payload={'tipo':'correccion','campo':'horarios','texto':'De 9 a 18','fuente':'Consulta al lugar','fecha_dato':str(timezone.localdate())}
        self.admin=ColaboracionAdmin(Colaboracion,AdminSite())
        self.request=RequestFactory().post('/admin/');self.request.user=self.staff

    def create(self, **kwargs):
        data={**self.payload,**kwargs}
        response=self.client.post(self.url,data,format='json')
        self.assertEqual(response.status_code,201,response.data)
        return Colaboracion.objects.get(pk=response.data['id'])

    def publish(self, item):
        self.admin.publicar(self.request,Colaboracion.objects.filter(pk=item.pk))

    def trip(self):
        return Viaje.objects.create(autor=self.user,nombre='Escapada',destino='Destino',fecha_inicio='2026-10-01',fecha_fin='2026-10-03',personas=2,presupuesto='1000')

    def test_correction_pending_and_moderation_history(self):
        item=self.create(estado='publicado')
        self.assertEqual(item.estado,'pendiente')
        self.assertIsNone(ficha_practica(self.destino)[0]['dato'])
        self.publish(item)
        self.assertEqual(ficha_practica(self.destino)[0]['dato'].pk,item.pk)
        self.assertEqual(RevisionColaboracion.objects.count(),1)
        self.publish(item)
        self.assertEqual(RevisionColaboracion.objects.count(),1)
        self.admin.ocultar(self.request,Colaboracion.objects.filter(pk=item.pk))
        self.assertIsNone(ficha_practica(self.destino)[0]['dato'])
        self.assertEqual(RevisionColaboracion.objects.count(),2)

    def test_versions_use_observation_date_and_restore(self):
        older=self.create(texto='Dato anterior',fecha_dato=str(timezone.localdate()-timedelta(days=3)));self.publish(older)
        newer=self.create(texto='Dato nuevo');self.publish(newer)
        field=ficha_practica(self.destino)[0]
        self.assertEqual(field['dato'].pk,newer.pk)
        self.assertEqual(field['historial'][0].pk,older.pk)
        self.admin.ocultar(self.request,Colaboracion.objects.filter(pk=newer.pk))
        self.assertEqual(ficha_practica(self.destino)[0]['dato'].pk,older.pk)

    def test_correction_validation(self):
        for key,value in [('campo',''),('fuente',''),('fecha_dato',None),('fecha_dato',str(timezone.localdate()+timedelta(days=1))),('texto','')]:
            response=self.client.post(self.url,{**self.payload,key:value},format='json')
            self.assertEqual(response.status_code,400,(key,response.data))

    def test_questions_answers_and_hidden_parent(self):
        question=self.create(tipo='pregunta',campo='',texto='¿Se puede caminar?')
        response=self.client.post(self.url,{'tipo':'respuesta','pregunta':question.pk,'texto':'Sí'},format='json')
        self.assertEqual(response.status_code,400)
        self.publish(question)
        answer=self.create(tipo='respuesta',campo='',pregunta=question.pk,texto='Respuesta específica')
        page=self.client.get('/destinos/destino/')
        self.assertContains(page,'¿Se puede caminar?')
        self.assertNotContains(page,'Respuesta específica')
        self.publish(answer)
        self.assertContains(self.client.get('/destinos/destino/'),'Respuesta específica')
        self.admin.ocultar(self.request,Colaboracion.objects.filter(pk=question.pk))
        self.assertNotContains(self.client.get('/destinos/destino/'),'Respuesta específica')
        self.assertNotContains(self.client.get('/destinos/destino/'),'¿Se puede caminar?')

    def test_reject_wrong_destination_and_type(self):
        q=self.create(tipo='pregunta',campo='');self.publish(q)
        response=self.client.post('/api/v1/destinos/otro/colaboraciones/',{'tipo':'respuesta','pregunta':q.pk,'texto':'Otra'},format='json')
        self.assertEqual(response.status_code,400)
        correction=self.create();self.publish(correction)
        response=self.client.post(self.url,{'tipo':'respuesta','pregunta':correction.pk,'texto':'Otra'},format='json')
        self.assertEqual(response.status_code,400)

    def test_anonymous_and_inactive_destinations(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url,self.payload,format='json').status_code,401)
        self.assertEqual(self.client.get('/api/v1/favoritos/').status_code,401)
        self.client.force_authenticate(self.user)
        self.destino.es_activo=False;self.destino.save()
        self.assertEqual(self.client.post(self.url,self.payload,format='json').status_code,404)
        self.assertEqual(self.client.put('/api/v1/favoritos/destino/').status_code,404)

    def test_favorites_private_idempotent_and_removable_when_inactive(self):
        url='/api/v1/favoritos/destino/'
        self.assertEqual(self.client.put(url).status_code,200)
        self.client.put(url)
        self.assertEqual(Favorito.objects.count(),1)
        self.client.force_authenticate(self.other)
        self.assertFalse(self.client.get(url).data['favorito'])
        self.assertEqual(self.client.get('/api/v1/favoritos/').data['count'],0)
        self.client.delete(url);self.assertEqual(Favorito.objects.count(),1)
        self.client.force_authenticate(self.user)
        self.destino.es_activo=False;self.destino.save()
        self.assertFalse(self.client.get('/api/v1/favoritos/').data['results'][0]['activo'])
        self.assertEqual(self.client.delete(url).status_code,204)
        self.assertFalse(Favorito.objects.exists())

    def test_link_place_preserves_trip_and_ownership(self):
        trip=self.trip();url=f'/api/v1/mis-viajes/{trip.pk}/lugares/'
        for _ in range(2):self.assertEqual(self.client.post(url,{'slug':'destino'},format='json').status_code,200)
        self.assertEqual(trip.lugares.count(),1)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url,{'slug':'otro'},format='json').status_code,404)
        self.assertEqual(trip.lugares.count(),1)

    def test_agenda_persists_sorts_and_validates_date_changes(self):
        trip=self.trip();url=f'/api/v1/mis-viajes/{trip.pk}/'
        agenda=[{'dia':3,'hora':'12:00','titulo':'Comer','notas':'Reserva'},{'dia':1,'hora':'','titulo':'Pasear','notas':''}]
        response=self.client.patch(url,{'actividades':agenda,'pendientes':[{'texto':'Comprar boletos','hecho':True}],'notas':'Mis notas'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['actividades'][0]['dia'],1)
        trip.refresh_from_db();self.assertTrue(trip.pendientes[0]['hecho']);self.assertEqual(trip.notas,'Mis notas')
        self.assertEqual(self.client.patch(url,{'fecha_fin':'2026-10-02'},format='json').status_code,400)
        self.assertEqual(self.client.patch(url,{'fecha_fin':'2026-10-02','actividades':[]},format='json').status_code,200)
        for bad in [{'dia':0,'hora':'12:00','titulo':'No','notas':''},{'dia':1,'hora':'25:00','titulo':'No','notas':''}]:
            self.assertEqual(self.client.patch(url,{'actividades':[bad]},format='json').status_code,400)

    def test_new_inactive_places_rejected_existing_preserved(self):
        trip=self.trip();trip.lugares.add(self.destino)
        self.destino.es_activo=False;self.destino.save()
        url=f'/api/v1/mis-viajes/{trip.pk}/'
        self.assertEqual(self.client.patch(url,{'lugares':[self.destino.pk]},format='json').status_code,200)
        self.second.es_activo=False;self.second.save()
        self.assertEqual(self.client.patch(url,{'lugares':[self.second.pk]},format='json').status_code,400)

    def test_unknown_data_escaped_content_and_pages(self):
        self.assertContains(self.client.get('/destinos/destino/'),'Sin confirmar',count=8)
        item=self.create(texto='<script>alert(1)</script>');self.publish(item)
        page=self.client.get('/destinos/destino/')
        self.assertNotContains(page,'<script>alert(1)</script>')
        self.assertContains(page,'&lt;script&gt;')
        self.assertContains(self.client.get('/favoritos/'),'favorites-list')
        self.assertContains(self.client.get('/mis-viajes/'),'trip-activities')
