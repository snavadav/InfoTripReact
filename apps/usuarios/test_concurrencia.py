"""Concurrencia del login en dos pasos. Solo PostgreSQL: SQLite no tiene bloqueos de fila."""
import re
import threading
import time
from unittest import skipUnless
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient, APITransactionTestCase

from . import verificacion
from .models import CodigoAcceso, Usuario


def en_paralelo(peticion, veces=2):
    """Lanza las peticiones a la vez; cada hilo usa y cierra su propia conexión."""
    barrera = threading.Barrier(veces)
    estados = []

    def ejecutar():
        try:
            barrera.wait()
            estados.append(peticion(APIClient()).status_code)
        finally:
            connection.close()

    hilos = [threading.Thread(target=ejecutar) for _ in range(veces)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)
    return sorted(estados)


def con_pausa(funcion):
    """Ensancha la ventana de carrera dentro de la transacción del login."""
    def envoltura(*args, **kwargs):
        time.sleep(0.3)
        return funcion(*args, **kwargs)
    return envoltura


@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL (settings.test_postgres).')
class ConcurrenciaLoginTests(APITransactionTestCase):
    def setUp(self):
        cache.clear()
        Usuario.objects.create_user('paralelo@example.com', 'Ana', 'Viaje', 'Prueba-segura-493!')
        self.credenciales = {'email': 'paralelo@example.com', 'password': 'Prueba-segura-493!'}

    def test_dos_logins_simultaneos_envian_un_solo_codigo(self):
        with patch.object(verificacion, 'hash_credencial', con_pausa(verificacion.hash_credencial)):
            estados = en_paralelo(lambda cliente: cliente.post('/api/v1/auth/login/', self.credenciales))
        self.assertEqual(estados, [200, 429])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(CodigoAcceso.objects.count(), 1)

    def test_un_codigo_solo_se_canjea_una_vez_aunque_lleguen_a_la_vez(self):
        respuesta = self.client.post('/api/v1/auth/login/', self.credenciales)
        datos = {'desafio': respuesta.data['desafio'],
                 'codigo': re.search(r'\b[0-9]{6}\b', mail.outbox[-1].body).group()}
        with patch.object(verificacion, 'hash_codigo', con_pausa(verificacion.hash_codigo)):
            estados = en_paralelo(lambda cliente: cliente.post('/api/v1/auth/verificar-codigo/', datos))
        self.assertEqual(estados, [200, 400])
        self.assertTrue(CodigoAcceso.objects.get().consumido)
