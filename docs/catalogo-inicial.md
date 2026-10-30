# Catálogo inicial

El comando `cargar_destinos_iniciales` carga 15 localidades reales y no sobrescribe ni reactiva registros existentes. Las regiones son agrupaciones turísticas de la app, no una división administrativa oficial. No carga reseñas, precios, servicios ni fotografías de terceros.

Selección contrastada con el catálogo turístico [Visita Jalisco](https://visitjalisco.mx/places). Descripciones breves redactadas para esta aplicación.

Coordenadas orientativas de las localidades, consultadas el 8 de septiembre de 2026, redondeadas a seis decimales. No representan entradas a un establecimiento ni un punto de encuentro:

| Localidad | Latitud | Longitud | Fuente |
|---|---:|---:|---|
| Tequila | 20.879439 | -103.835647 | https://es.wikipedia.org/wiki/Tequila_(Jalisco) |
| Puerto Vallarta | 20.641300 | -105.223300 | https://es.wikipedia.org/wiki/Puerto_Vallarta |
| Chapala | 20.298056 | -103.190278 | https://es.wikipedia.org/wiki/Chapala |
| Mazamitla | 19.916111 | -103.020556 | https://es.wikipedia.org/wiki/Mazamitla |
| Tapalpa | 19.945000 | -103.757778 | https://es.wikipedia.org/wiki/Tapalpa |
| Guadalajara | 20.676389 | -103.342222 | https://es.wikipedia.org/wiki/Guadalajara_(M%C3%A9xico) |
| Tlaquepaque | 20.583333 | -103.350000 | https://es.wikipedia.org/wiki/Municipio_de_San_Pedro_Tlaquepaque |
| Tonalá | 20.623333 | -103.245556 | https://es.wikipedia.org/wiki/Tonal%C3%A1_(Jalisco) |
| Ajijic | 20.300278 | -103.272222 | https://es.wikipedia.org/wiki/Ajijic |
| Guachimontones | 20.695149 | -103.835719 | https://es.wikipedia.org/wiki/Guachimontones |
| San Sebastián del Oeste | 20.760833 | -104.851667 | https://es.wikipedia.org/wiki/San_Sebasti%C3%A1n_del_Oeste |
| Mascota | 20.525556 | -104.782222 | https://es.wikipedia.org/wiki/Mascota_(Jalisco) |
| Talpa de Allende | 20.381389 | -104.818056 | https://es.wikipedia.org/wiki/Talpa_de_Allende |
| Lagos de Moreno | 21.361389 | -101.935000 | https://es.wikipedia.org/wiki/Lagos_de_Moreno |
| Barra de Navidad | 19.208056 | -104.680556 | https://es.wikipedia.org/wiki/Barra_de_Navidad_(Jalisco) |

Las coordenadas de esta segunda tanda se consultaron el 30 de octubre de 2026. Fotos, autores y licencias en `apps/destinos/fotos.py` y en `/creditos/`. Datos prácticos: ver [sembrar contenido](sembrar-contenido.md).

```powershell
.\.venv314\Scripts\python.exe -B manage.py cargar_destinos_iniciales --settings=infotrip.settings_local
```

Los dos archivos de fotografía existentes de Tequila y Puerto Vallarta se conservan. Los demás destinos muestran un estado sin foto hasta que se aprueben aportes fotográficos.
