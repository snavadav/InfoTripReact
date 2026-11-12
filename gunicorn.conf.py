"""Configuración que gunicorn carga sola desde el directorio de trabajo (/app en la imagen).

El registro de accesos no incluye la cadena de consulta: ahí van búsquedas de direcciones (`?q=`), coordenadas
de la búsqueda inversa (`?lat=&lon=`) y el enlace de baja de avisos (`?t=`). Solo método, ruta y estado.
El último campo es la duración de la petición en microsegundos: con él se calcula el p95 por ruta
(docs/operacion.md).
"""
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s "%(a)s" %(D)s'
# Cada proceso se renueva tras unas mil peticiones: una fuga de memoria no crece sin límite en un servidor de 2 GB.
max_requests = 1000
max_requests_jitter = 100
