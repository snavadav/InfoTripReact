"""
InfoTrip — apps/usuarios/urls.py
Rutas de la API de autenticación
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView,
    RegistroView,
    LogoutView,
    PerfilView,
    CambiarPasswordView,
)

urlpatterns = [
    path('registro/',         RegistroView.as_view(),       name='auth-registro'),
    path('login/',            LoginView.as_view(),          name='auth-login'),
    path('logout/',           LogoutView.as_view(),         name='auth-logout'),
    path('token/refresh/',    TokenRefreshView.as_view(),   name='auth-token-refresh'),
    path('perfil/',           PerfilView.as_view(),         name='auth-perfil'),
    path('cambiar-password/', CambiarPasswordView.as_view(),name='auth-cambiar-password'),
]