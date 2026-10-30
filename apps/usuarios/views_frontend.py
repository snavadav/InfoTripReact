from django.shortcuts import render
from .models import Usuario
from .sesion import usuario_de_baja_avisos


def login_view(request):
    """Vista de login"""
    return render(request, 'login.html')


def registro_view(request):
    """Vista de registro"""
    return render(request, 'registro.html')


def baja_avisos(request):
    """Enlace de los correos: GET solo pregunta (los antivirus abren enlaces); POST desactiva sin iniciar sesión."""
    token = request.POST.get('t') if request.method == 'POST' else request.GET.get('t')
    usuario = Usuario.objects.filter(pk=usuario_de_baja_avisos(token or '')).first()
    hecho = False
    if request.method == 'POST' and usuario:
        usuario.avisos_correo = False
        usuario.save(update_fields=['avisos_correo'])
        hecho = True
    contexto = {'valido': usuario is not None, 'hecho': hecho, 'token': token}
    return render(request, 'comunidad/baja_avisos.html', contexto)
