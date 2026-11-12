from django.apps import AppConfig

from .cache_catalogo import conectar_senales


class DestinosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.destinos'
    verbose_name = 'Catálogo de destinos'

    def ready(self):
        conectar_senales()
