"""Carga datos prácticos y descripciones de fuentes públicas, citando cada una. Guía: docs/sembrar-contenido.md

Solo trae información comprobable. Nunca crea reseñas, gastos, visitas ni calificaciones: esas solo pueden venir
de personas que fueron. Se puede repetir: no pisa descripciones editadas ni datos de otras personas.
"""
import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.comunidad.models import CORREO_EQUIPO, Colaboracion
from apps.destinos.models import Categoria, Destino
from apps.usuarios.models import Usuario
from .importar_osm import municipio_de

ARCHIVO = Path(__file__).resolve().parents[2] / 'datos' / 'contenido_inicial.json'
# Texto automático de importar_osm: se reemplaza; cualquier otra descripción la escribió alguien y se respeta.
TEXTO_AUTOMATICO = 'Todavía no tenemos una descripción'
SIC = 'Sistema de Información Cultural, Secretaría de Cultura'


def cuenta_del_equipo():
    """Firma lo que no aportó un viajero. No puede iniciar sesión y no compite como cronista."""
    cuenta = Usuario.objects.filter(email=CORREO_EQUIPO).first()
    if cuenta:
        return cuenta
    cuenta = Usuario(email=CORREO_EQUIPO, nombre='Equipo InfoTrip', apellido='', es_verificado=True)
    cuenta.set_unusable_password()
    cuenta.save()
    return cuenta


class Command(BaseCommand):
    help = 'Carga datos prácticos y descripciones de fuentes públicas, con su cita. No crea reseñas ni gastos.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(ARCHIVO), help='Archivo de contenido.')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')

    def handle(self, *args, archivo, simular, **opciones):
        try:
            with open(archivo, encoding='utf-8') as entrada:
                sitios = json.load(entrada)
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {archivo}: {error}') from error
        conteo = {'nuevos': 0, 'existentes': 0, 'descripciones': 0, 'datos': 0, 'sin_destino': 0}
        # atomic: un fallo a mitad no deja una carga parcial; al simular siempre se revierte.
        with transaction.atomic():
            equipo = cuenta_del_equipo()
            for sitio in sitios:
                self.cargar(sitio, equipo, conteo)
            if simular:
                transaction.set_rollback(True)
        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f"{accion} {conteo['nuevos']} destinos. Ya existían: {conteo['existentes']}. Descripciones: "
            f"{conteo['descripciones']}. Datos prácticos: {conteo['datos']}. "
            f"Sin destino en esta base: {conteo['sin_destino']}."))

    def cargar(self, sitio, equipo, conteo):
        destino = self.destino_de(sitio, conteo)
        if destino is None:
            return
        cambios = []
        if sitio.get('descripcion') and (not destino.descripcion or TEXTO_AUTOMATICO in destino.descripcion):
            destino.descripcion = sitio['descripcion']
            cambios.append('descripcion')
            conteo['descripciones'] += 1
        if sitio.get('direccion') and not destino.direccion:
            destino.direccion = sitio['direccion'][:300]
            cambios.append('direccion')
        if cambios:
            destino.save(update_fields=[*cambios, 'fecha_actualizacion'])
        fecha = date.fromisoformat(sitio['consultado'])
        fuente = f"{SIC}: {sitio['fuente']}" if 'sic.cultura.gob.mx' in sitio['fuente'] else sitio['fuente']
        for campo, texto in sitio.get('datos', {}).items():
            Colaboracion.objects.update_or_create(
                destino=destino, autor=equipo, tipo='correccion', campo=campo,
                defaults={'texto': texto[:1500], 'fuente': fuente[:300], 'fecha_dato': fecha, 'estado': 'publicado'},
            )
            conteo['datos'] += 1

    def destino_de(self, sitio, conteo):
        if sitio.get('destino'):
            destino = Destino.objects.filter(slug=sitio['destino']).first()
            # El slug viene de una importación: en otra base puede no existir. Se avisa y se sigue.
            conteo['existentes' if destino else 'sin_destino'] += 1
            return destino
        slug = slugify(sitio['nombre'])[:200]
        destino = Destino.objects.filter(slug=slug).first()
        if destino:
            conteo['existentes'] += 1
            return destino
        destino = Destino.objects.create(
            nombre=sitio['nombre'][:200], slug=slug, descripcion=sitio.get('descripcion', ''),
            municipio=municipio_de(sitio['municipio']), latitud=sitio['latitud'], longitud=sitio['longitud'],
            direccion=sitio.get('direccion', '')[:300],
        )
        if sitio.get('categoria'):
            categoria, _ = Categoria.objects.get_or_create(
                nombre=sitio['categoria'], defaults={'slug': slugify(sitio['categoria'])}
            )
            destino.categorias.add(categoria)
        conteo['nuevos'] += 1
        return destino
