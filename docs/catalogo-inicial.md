# Catálogo inicial

El comando `cargar_destinos_iniciales` carga cinco localidades reales y no sobrescribe ni reactiva registros existentes. Las regiones son agrupaciones turísticas de la app, no una división administrativa oficial. No carga reseñas, precios, servicios ni fotografías de terceros.

Selección contrastada con el catálogo turístico [Visita Jalisco](https://visitjalisco.mx/places). Descripciones breves redactadas para esta aplicación.

Coordenadas orientativas de las localidades, consultadas el 8 de septiembre de 2026, redondeadas a seis decimales. No representan entradas a un establecimiento ni un punto de encuentro:

| Localidad | Latitud | Longitud | Fuente |
|---|---:|---:|---|
| Tequila | 20.879439 | -103.835647 | https://es.wikipedia.org/wiki/Tequila_(Jalisco) |
| Puerto Vallarta | 20.641300 | -105.223300 | https://es.wikipedia.org/wiki/Puerto_Vallarta |
| Chapala | 20.298056 | -103.190278 | https://es.wikipedia.org/wiki/Chapala |
| Mazamitla | 19.916111 | -103.020556 | https://es.wikipedia.org/wiki/Mazamitla |
| Tapalpa | 19.945000 | -103.757778 | https://es.wikipedia.org/wiki/Tapalpa |

```powershell
.\.venv314\Scripts\python.exe -B manage.py cargar_destinos_iniciales --settings=infotrip.settings_local
```

Los dos archivos de fotografía existentes de Tequila y Puerto Vallarta se conservan. Los demás destinos muestran un estado sin foto hasta que se aprueben aportes fotográficos.
