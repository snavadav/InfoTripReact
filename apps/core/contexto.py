"""Datos comunes a todas las plantillas."""
from django.conf import settings


def seo(request):
    return {'url_base': settings.PUBLIC_BASE_URL, 'url_canonica': settings.PUBLIC_BASE_URL + request.path}
