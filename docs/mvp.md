# MVP de InfoTrip

Qué incluye la primera versión, cómo dejarla lista en una instalación nueva y cómo probarla con personas reales antes de abrirla. Falta publicarla en internet, que se hará después.

## Qué puede hacer una persona

| Quiero… | Dónde |
|---|---|
| Encontrar un destino y verlo en el mapa | `/` y `/destinos/` |
| Ver qué hay cerca: comer, dormir, comprar, gasolina, farmacia, cajero | **Cerca de mí** en `/destinos/` |
| Saber horarios, precios y contacto, con su fuente | Ficha de cada destino |
| Saber cuánto se gasta | `/costos/` y ficha, cuando hay 3 reportes por concepto |
| Opinar sobre un destino o un lugar | Ficha, con cuenta; pasa por moderación |
| Planear una escapada y dividir gastos | `/mis-viajes/` y su bote |
| Avisar de un problema o proponer una idea | **Enviar comentarios**, en el pie de cada página |

## Instalación nueva, en orden

Corre los comandos en este orden. Todos se pueden repetir sin duplicar nada.

```bash
python manage.py migrate
```

```bash
python manage.py cargar_destinos_iniciales
```

```bash
python manage.py importar_osm
```

```bash
python manage.py curar_catalogo
```

```bash
python manage.py importar_lugares
```

```bash
python manage.py importar_denue
```

```bash
python manage.py sembrar_contenido
```

```bash
python manage.py crear_moderacion
```

`importar_osm` deja los destinos ocultos: publícalos en el admin. En esta copia local se publicaron todos y `curar_catalogo` ocultó después 163 que no servían. `importar_denue` necesita `DENUE_TOKEN` en `.env`.

## Curación del catálogo

`curar_catalogo` aplica `apps/destinos/datos/curacion.json`, revisado a mano el 3 de noviembre de 2026:

- **Oculta 163 destinos de OpenStreetMap** con nombres inventados ("Trône Du Roi Dakk", "Montara Belvidejo"), genéricos ("Mirador", "Mirador Número Uno") o que no son destinos (temazcales, un club de golf, una oficina).
- **Corrige 8 nombres** de museos, como "Museum Los Abuelos" por "Museo Los Abuelos". La dirección web no cambia.
- **Une la categoría "Lagos" con "Lago".**

Nada se borra. Para volver a publicar lo ocultado:

```bash
python manage.py curar_catalogo --revertir
```

Si OpenStreetMap trae algún lugar más que no sirva, ocúltalo en el admin o agrégalo al archivo.

## Equipo de moderación

Quien modera no necesita ser superusuario. Primero debe registrarse en el sitio; después:

```bash
python manage.py crear_moderacion --agregar correo@ejemplo.com
```

Puede revisar `/admin/moderacion/`, publicar u ocultar contenido, resolver reportes, atender comentarios y corregir destinos y lugares. No puede borrar, crear cuentas ni cambiar permisos.

**Rutina diaria del piloto:** revisar la cola completa, que también incluye las propuestas de lugares, las reseñas, los lugares que alguien dice que cerraron y los comentarios del sitio. Un aporte que espera días desanima a quien lo hizo.

## Piloto con personas reales

El objetivo es reunir uso real: al menos 35 personas, para el análisis del Módulo 4 (punto 4.4), y contenido que hoy no existe. Hoy hay 0 reseñas, 0 gastos y 0 datos prácticos aportados por personas.

1. **Equipo primero:** cada integrante escribe, en destinos que de verdad conozca, al menos 3 gastos (entrada, comida, transporte), una reseña y un dato práctico con su fuente. Con 3 gastos por concepto, `/costos/` empieza a mostrar cifras.
2. **35 o más personas durante 2 a 4 semanas:** compañeros, familia o amistades. Pídeles estas tareas:
   - Buscar un destino y abrir su ficha.
   - Usar **Cerca de mí** o el botón **Comer** en el mapa.
   - Crear una cuenta y confirmar el correo.
   - Escribir una reseña o un gasto de un lugar donde hayan estado.
   - Planear una escapada; si van en grupo, usar el bote.
   - Enviar al menos un comentario: qué les costó trabajo y qué les gustó.
3. **Medir:** `/admin/metricas/` cuenta eventos, embudos y retención; los comentarios están en `/admin/comunidad/comentario/`. Anota la fecha de inicio y de fin del piloto para el documento final.

**Reglas:** nadie debe inventar reseñas ni gastos; solo cuenta lo vivido. La cuenta "Equipo InfoTrip" firma lo que viene de fuentes públicas y no cuenta como persona.

## Antes de abrirlo al público

- Publicarlo en internet con HTTPS. Se hará después.
- Revisar los textos legales y llenar `CONTACTO_PRIVACIDAD`.
- Configurar un correo de envío para producción: sin él nadie puede registrarse.
- Cambiar la contraseña de PostgreSQL y generar un `SECRET_KEY` nuevo para producción.
- Confirmar por teléfono los horarios oficiales de los museos que se vayan a mostrar: la fuente puede estar atrasada.
