"""Pantalla del personal para etiquetar lugares, uno a la vez y sin JavaScript."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.destinos.models import Lugar

from .models import EtiquetaLugar, PrediccionLugar
from .muestreo import progreso, siguiente, siguiente_dudoso

RESPUESTAS = {'si': True, 'no': False, 'no_se': None}
PERMISO = 'curador.add_etiquetalugar'


def etiquetar(request):
    if not request.user.has_perm(PERMISO):
        return render(request, 'admin/etiquetar_lugares.html', {'sin_permiso': True, 'title': 'Etiquetar lugares'},
                      status=403)
    if request.method == 'POST':
        respuesta = request.POST.get('respuesta')
        if respuesta in RESPUESTAS:
            lugar = get_object_or_404(Lugar, pk=request.POST.get('lugar'))
            EtiquetaLugar.objects.update_or_create(lugar=lugar, autor=request.user,
                                                   defaults={'util': RESPUESTAS[respuesta]})
        else:
            messages.error(request, 'Respuesta no válida.')
        modo = 'dudas' if request.POST.get('modo') == 'dudas' else 'muestra'
        return redirect(f"{reverse('etiquetar-lugares')}?modo={modo}")
    por_tipo, total = progreso()
    hay_modelo = PrediccionLugar.objects.exists()
    modo = 'dudas' if request.GET.get('modo') == 'dudas' and hay_modelo else 'muestra'
    lugar = siguiente_dudoso(request.user) if modo == 'dudas' else siguiente(request.user)
    return render(request, 'admin/etiquetar_lugares.html', {
        'title': 'Etiquetar lugares', 'lugar': lugar, 'modo': modo, 'hay_modelo': hay_modelo,
        'por_tipo': por_tipo, 'total': total,
        'mias': EtiquetaLugar.objects.filter(autor=request.user).count(),
        'fuente': lugar and ('DENUE (INEGI)' if lugar.denue_id else 'OpenStreetMap' if lugar.osm_id else 'Comunidad'),
    })
