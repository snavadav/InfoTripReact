# Módulo 1: catálogo de destinos

Implementa la base de datos y una API pública de solo consulta. La interfaz de la portada sigue siendo estática; el panel de administración turístico, mapa, reseñas, fotos y precios corresponden a módulos posteriores.

## Modelo de datos

- Región → municipios → destinos. El municipio determina la región del destino, evitando información duplicada.
- Destino ↔ categorías y Destino ↔ servicios (relaciones muchos a muchos).
- Destino incluye nombre, slug único y explícito, descripción, dirección opcional, coordenadas obligatorias, estado activo y fechas.
- Los slugs son identificadores estables: cambiar el nombre no cambia la URL automáticamente.
- Latitud entre -90 y 90; longitud entre -180 y 180, con validadores y restricciones en base de datos.
- Los municipios y regiones referenciados no pueden eliminarse. Desactivar un destino lo oculta del listado y del detalle público.
- Los catálogos geográficos y de clasificación se consultan aunque aún no tengan destinos.
- El alcance geográfico es Jalisco; estos modelos no constituyen las 38 entidades mencionadas en la presentación. No se cargan datos geográficos sin validar.

## Preparación

Desde la raíz del repositorio, con Python 3.14 y PostgreSQL configurado mediante `.env`:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

La migración `apps/destinos/migrations/0001_initial.py` crea las tablas, relaciones, índice y restricciones. No usar `--fake` para crear este módulo. No se aplicó esta migración al PostgreSQL del usuario durante el desarrollo.

Se actualizaron Pillow a 12.3.0 y psycopg2-binary a 2.9.12 para el entorno de Python 3.14 usado en las pruebas. Las demás dependencias directas mantienen sus versiones.

## API

Todos los endpoints admiten GET/HEAD/OPTIONS, sin exigir iniciar sesión. POST/PUT/PATCH/DELETE no están habilitados. Un token inválido enviado explícitamente puede producir un error de autenticación.

| Ruta | Resultado |
| --- | --- |
| `/api/v1/destinos/` | Listado paginado de destinos activos |
| `/api/v1/destinos/<slug>/` | Detalle; 404 si no existe o está desactivado |
| `/api/v1/regiones/` | Regiones |
| `/api/v1/municipios/` | Municipios con su región |
| `/api/v1/categorias/` | Categorías |
| `/api/v1/servicios/` | Servicios |

Los listados devuelven `count`, `next`, `previous` y `results`, con 20 elementos por página y orden estable por nombre e ID. Usar `?page=2` para avanzar.

Filtros opcionales de destinos, combinables mediante AND:

- `q`: texto en nombre, descripción o nombre del municipio (máximo 200 caracteres).
- `categoria`, `municipio`, `region`, `servicio`: slug del catálogo correspondiente.

Ejemplo: `/api/v1/destinos/?q=senderos&categoria=naturaleza&region=region-prueba`.

Los filtros mal formados devuelven 400; un slug válido sin coincidencias devuelve un listado vacío. Los parámetros no reconocidos se ignoran. No hay filtros de precio ni calificación porque esos datos aún no existen.

Cada destino devuelve su municipio y región, categorías y servicios anidados. Las coordenadas se serializan como cadenas decimales; el futuro mapa puede convertirlas con `Number(...)`.

## Crear un registro de prueba antes del módulo de administración

En una base de desarrollo, ejecutar `python manage.py shell` y usar este ejemplo sintético. No representa un destino turístico real:

```python
from apps.destinos.models import Region, Municipio, Categoria, Destino
region, _ = Region.objects.get_or_create(slug='region-prueba', defaults={'nombre': 'Región de prueba'})
municipio, _ = Municipio.objects.get_or_create(slug='municipio-prueba', defaults={'nombre': 'Municipio de prueba', 'region': region})
categoria, _ = Categoria.objects.get_or_create(slug='categoria-prueba', defaults={'nombre': 'Categoría de prueba'})
destino, _ = Destino.objects.get_or_create(slug='destino-prueba', defaults={
    'nombre': 'Destino de prueba', 'descripcion': 'Registro sintético para desarrollo',
    'municipio': municipio, 'latitud': '20.000000', 'longitud': '-103.000000',
})
destino.full_clean()
destino.categorias.add(categoria)
```

Consultar `/api/v1/destinos/destino-prueba/`. El futuro módulo de administración reemplazará este procedimiento manual.

## Verificación

```powershell
python -B manage.py test apps.destinos --settings=infotrip.settings_test
python -B manage.py makemigrations --check --dry-run --settings=infotrip.settings_test
```

`settings_test` usa SQLite en memoria y un hasher rápido exclusivamente para pruebas. No usarlo para ejecutar producción. Las pruebas aplican las migraciones en la base temporal, sin tocar PostgreSQL.

Las 10 pruebas cubren listados, detalle, destinos ocultos, filtros combinados, entradas inválidas, catálogos, rechazo de escritura, coordenadas, slugs únicos, eliminación protegida y número constante de consultas al listar destinos. Queda pendiente comprobar la migración contra el PostgreSQL del entorno de despliegue.
