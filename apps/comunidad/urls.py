from django.urls import path
from .views import PublicarView, MisAportesView, EditarAporteView, ReportarView
from .viajes import CompartirViajeView, MisViajesView, ViajeView, VincularLugarView
from .practica import ColaboracionesView, ConfirmarDatoView, FavoritosView, FavoritoView, ReportarColaboracionView
from .avisos import NotificacionesView, NotificacionesLeidasView
from .bote import (
    BoteView, ConfirmarPagoView, GastoBoteView, GastosBoteView, InvitarAmigosView, LugaresBoteView, MisBotesView,
    PagoBoteView, PagosBoteView, ParticipanteBoteView, PublicarBoteView, UnirseBoteView,
)
from .comentarios import ComentariosView
from .cuenta import EliminarCuentaView
from .negocios import InteresNegocioView
from .pasaporte import CompartirPasaporteView, FotoPasaporteView, ImagenFotoPasaporteView, MiPasaporteView
from .propuestas_lugar import PropuestasLugarView
from .resenas_lugar import (
    EstadoLugarView, MiOpinionLugarView, MisResenasLugarView, ReportarResenaLugarView, ResenasLugarView,
)
from .visitas import VisitaView
urlpatterns = [
    path('mi-cuenta/eliminar/', EliminarCuentaView.as_view(), name='eliminar-cuenta'),
    path('notificaciones/', NotificacionesView.as_view(), name='notificaciones'),
    path('notificaciones/leidas/', NotificacionesLeidasView.as_view(), name='notificaciones-leidas'),
    path('mis-viajes/<int:pk>/lugares/', VincularLugarView.as_view(), name='vincular-lugar'),
    path('mis-viajes/<int:pk>/compartir/', CompartirViajeView.as_view(), name='compartir-viaje'),
    path('mis-viajes/<int:pk>/bote/', BoteView.as_view(), name='bote'),
    path('mis-viajes/<int:pk>/bote/gastos/', GastosBoteView.as_view(), name='bote-gastos'),
    path('mis-viajes/<int:pk>/bote/gastos/<int:gasto>/', GastoBoteView.as_view(), name='bote-gasto'),
    path('mis-viajes/<int:pk>/bote/participantes/<int:participante>/', ParticipanteBoteView.as_view(),
         name='bote-participante'),
    path('mis-viajes/<int:pk>/bote/pagos/', PagosBoteView.as_view(), name='bote-pagos'),
    path('mis-viajes/<int:pk>/bote/pagos/<int:pago>/', PagoBoteView.as_view(), name='bote-pago'),
    path('mis-viajes/<int:pk>/bote/pagos/<int:pago>/confirmar/', ConfirmarPagoView.as_view(),
         name='bote-pago-confirmar'),
    path('mis-viajes/<int:pk>/bote/invitar/', InvitarAmigosView.as_view(), name='bote-invitar'),
    path('mis-viajes/<int:pk>/bote/lugares/', LugaresBoteView.as_view(), name='bote-lugares'),
    path('mis-viajes/<int:pk>/bote/publicar/', PublicarBoteView.as_view(), name='bote-publicar'),
    path('botes/<uuid:enlace>/unirse/', UnirseBoteView.as_view(), name='bote-unirse'),
    path('mis-botes/', MisBotesView.as_view(), name='mis-botes'),
    path('destinos/<slug:slug>/visita/', VisitaView.as_view(), name='visita'),
    path('negocios/interes/', InteresNegocioView.as_view(), name='interes-negocio'),
    path('comentarios/', ComentariosView.as_view(), name='comentarios-api'),
    path('lugares/propuestas/', PropuestasLugarView.as_view(), name='lugar-propuestas'),
    path('lugares/<int:pk>/resenas/', ResenasLugarView.as_view(), name='lugar-resenas'),
    path('lugares/<int:pk>/mi-opinion/', MiOpinionLugarView.as_view(), name='lugar-mi-opinion'),
    path('lugares/<int:pk>/estado/', EstadoLugarView.as_view(), name='lugar-estado'),
    path('resenas-lugar/<int:pk>/reportar/', ReportarResenaLugarView.as_view(), name='resena-lugar-reportar'),
    path('mis-resenas-lugar/', MisResenasLugarView.as_view(), name='mis-resenas-lugar'),
    path('mi-pasaporte/', MiPasaporteView.as_view(), name='mi-pasaporte'),
    path('mi-pasaporte/compartir/', CompartirPasaporteView.as_view(), name='compartir-pasaporte'),
    path('mi-pasaporte/<slug:slug>/foto/', FotoPasaporteView.as_view(), name='mi-pasaporte-foto'),
    path('mi-pasaporte/<slug:slug>/foto/imagen/', ImagenFotoPasaporteView.as_view(),
         name='mi-pasaporte-foto-imagen'),
    path('destinos/<slug:slug>/colaboraciones/', ColaboracionesView.as_view(), name='colaboraciones'),
    path('colaboraciones/<int:pk>/confirmar/', ConfirmarDatoView.as_view(), name='confirmar-dato'),
    path('colaboraciones/<int:pk>/reportar/', ReportarColaboracionView.as_view(), name='reportar-colaboracion'),
    path('favoritos/', FavoritosView.as_view(), name='favoritos-api'),
    path('favoritos/<slug:slug>/', FavoritoView.as_view(), name='favorito-api'),
    path('mis-viajes/', MisViajesView.as_view(), name='mis-viajes-api'),
    path('mis-viajes/<int:pk>/', ViajeView.as_view(), name='viaje-api'),
    path('destinos/<slug:slug>/aportes/', PublicarView.as_view(), name='aporte-crear'),
    path('mis-aportes/', MisAportesView.as_view(), name='mis-aportes'),
    path('aportes/<int:pk>/', EditarAporteView.as_view(), name='aporte-editar'),
    path('aportes/<int:pk>/reportar/', ReportarView.as_view(), name='aporte-reportar'),
]
