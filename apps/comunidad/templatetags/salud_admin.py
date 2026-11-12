"""Bloque de salud del inicio del admin (templates/admin/index.html)."""
from django import template

from apps.comunidad.salud import resumen

register = template.Library()


@register.simple_tag
def salud_del_sitio():
    return resumen()
