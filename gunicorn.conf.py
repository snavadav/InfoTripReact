"""Configuración que gunicorn carga sola desde el directorio de trabajo (/app en la imagen).

El registro de accesos no incluye la cadena de consulta: ahí van búsquedas de direcciones (`?q=`), coordenadas
de la búsqueda inversa (`?lat=&lon=`) y el enlace de baja de avisos (`?t=`). Solo método, ruta y estado.
"""
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s "%(a)s"'
