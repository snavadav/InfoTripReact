from copy import deepcopy
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Viaje


class ViajesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='viajero@example.com', nombre='Uno', apellido='Prueba', password='test')
        self.other = get_user_model().objects.create_user(email='otro@example.com', nombre='Dos', apellido='Prueba', password='test')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.data = {'nombre':'Escapada', 'destino':'Zona por explorar', 'fecha_inicio':'2026-10-01', 'fecha_fin':'2026-10-02', 'personas':4, 'presupuesto':'2000.00', 'gastos':[
            {'concepto':'transporte','descripcion':'Ida y vuelta','monto':'600.00','cantidad':1,'reparto':'compartido'},
            {'concepto':'comida','descripcion':'Comida','monto':'100.00','cantidad':2,'reparto':'individual'}]}

    def create(self):
        response=self.client.post('/api/v1/mis-viajes/',self.data,format='json')
        self.assertEqual(response.status_code,201,response.data)
        return response.data

    def test_totals_and_persistence(self):
        item=self.create()
        self.assertEqual(item['resumen'],{'total':'1400.00','por_persona':'350.00','disponible':'600.00'})
        self.assertEqual(Viaje.objects.get().gastos[0]['monto'],'600.00')
        result=self.client.get('/api/v1/mis-viajes/').data
        self.assertEqual(result['results'][0]['id'],item['id'])

    def test_owner_isolation(self):
        item=self.create()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/v1/mis-viajes/').data['count'],0)
        url=f"/api/v1/mis-viajes/{item['id']}/"
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.patch(url,{'nombre':'Ajeno'},format='json').status_code,404)
        self.assertEqual(self.client.delete(url).status_code,404)

    def test_anonymous_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/mis-viajes/').status_code,401)
        self.assertEqual(self.client.post('/api/v1/mis-viajes/',self.data,format='json').status_code,401)

    def test_invalid_values(self):
        for field,value in [('personas',0),('personas',101),('personas',1.5),('presupuesto','-1'),('fecha_fin','2026-09-30'),('nombre','')]:
            data={**self.data,field:value}
            self.assertEqual(self.client.post('/api/v1/mis-viajes/',data,format='json').status_code,400,(field,value))
        for field,value in [('monto','-1'),('monto','NaN'),('cantidad',0),('cantidad',1.5),('reparto','inventado'),('concepto','inventado')]:
            data=deepcopy(self.data);data['gastos'][0][field]=value
            self.assertEqual(self.client.post('/api/v1/mis-viajes/',data,format='json').status_code,400,(field,value))
        data={**self.data,'gastos':self.data['gastos']*51}
        self.assertEqual(self.client.post('/api/v1/mis-viajes/',data,format='json').status_code,400)

    def test_update_recalculates_and_checks_dates(self):
        item=self.create();url=f"/api/v1/mis-viajes/{item['id']}/"
        response=self.client.patch(url,{'personas':2},format='json')
        self.assertEqual(response.data['resumen']['total'],'1000.00')
        self.assertEqual(self.client.patch(url,{'fecha_inicio':'2026-10-03'},format='json').status_code,400)
        self.assertEqual(self.client.delete(url).status_code,204)
        self.assertFalse(Viaje.objects.exists())

    def test_rounding_empty_and_over_budget(self):
        self.data['personas']=3;self.data['presupuesto']='0.00';self.data['gastos']=self.data['gastos'][:1];self.data['gastos'][0]['monto']='1.00'
        item=self.create()
        self.assertEqual(item['resumen'],{'total':'1.00','por_persona':'0.33','disponible':'-1.00'})
        response=self.client.patch(f"/api/v1/mis-viajes/{item['id']}/",{'gastos':[]},format='json')
        self.assertEqual(response.data['resumen']['total'],'0.00')

    def test_page_integrations(self):
        response=self.client.get('/mis-viajes/')
        self.assertContains(response,'trip-form')
        self.assertContains(response,'js/viajes.js')
        self.assertContains(response,'data-trips="/mis-viajes/"')
