from django.shortcuts import render


def index(request):
    return render(request, 'index.html')  # antes era 'base/index.html'


def login_view(request):
    """Vista de login"""
    return render(request, 'login.html')


def registro_view(request):
    """Vista de registro"""
    return render(request, 'registro.html')