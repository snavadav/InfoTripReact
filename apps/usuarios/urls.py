"""
InfoTrip — apps/usuarios/urls.py
Rutas de la API de autenticación
"""

from django.urls import path
from .verificacion import LoginView, VerificarCodigoView, CorreoRefreshView
from .views import (
    RegistroView,
    LogoutView,
    PerfilView,
    CambiarPasswordView,
)

from .recuperacion import RecuperarView, RestablecerView

urlpatterns = [
    path('recuperar/', RecuperarView.as_view(), name='auth-recuperar'),
    path('restablecer/', RestablecerView.as_view(), name='auth-restablecer'),
    path('registro/',         RegistroView.as_view(),       name='auth-registro'),
    path('login/',            LoginView.as_view(),          name='auth-login'),
    path('verificar-codigo/', VerificarCodigoView.as_view(), name='auth-verificar-codigo'),
    path('logout/',           LogoutView.as_view(),         name='auth-logout'),
    path('token/refresh/',    CorreoRefreshView.as_view(),   name='auth-token-refresh'),
    path('perfil/',           PerfilView.as_view(),         name='auth-perfil'),
    path('cambiar-password/', CambiarPasswordView.as_view(),name='auth-cambiar-password'),
]
