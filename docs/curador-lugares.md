# Curador de lugares (aprendizaje automático)

InfoTrip importó 45,453 lugares para comer, dormir y servicios, del DENUE (INEGI) y de OpenStreetMap. Las reglas de
importación quitan lo obvio: nombres genéricos, comedores industriales y negocios muy pequeños en la zona
metropolitana. Aun así, nadie puede revisar a mano lo que queda.

El **curador** es un modelo que aprende del equipo **qué lugares le sirven a un viajero**. Con eso, el equipo revisa
primero lo que probablemente sobra.

**El curador solo sugiere.** No oculta ni publica nada: eso lo decide siempre una persona.

## 1. Etiquetar (el equipo)

1. Da acceso a cada persona: `python manage.py crear_moderacion --agregar correo@ejemplo.com`.
2. Entra a `/admin/etiquetar-lugares/`. Ahí se muestra un lugar a la vez y se responde **Sí le sirve**, **No le
   sirve** o **No sé**. Los atajos de teclado son Alt+S, Alt+N y Alt+X.

La pregunta para decidir es: *si un viajero llega a este municipio, ¿querría encontrar este lugar en el mapa?*

- **Muestra al azar** (modo inicial): se alternan los tipos de lugar, para que no dominen los restaurantes, y se
  sigue un orden pseudoaleatorio fijo, igual para todas las personas. Es la muestra con la que se mide el modelo.
- **Que dos personas etiqueten los mismos lugares.** Así se mide el acuerdo entre personas (kappa de Cohen). Si el
  acuerdo es bajo, el criterio no está claro y hay que acordarlo antes de entrenar.
- **Ninguna etiqueta se genera automáticamente.** Los lugares inactivos no cuentan como "no sirve": se retiraron
  porque desaparecieron del DENUE, no porque alguien los revisara.

**Meta:** al menos 200 lugares con respuesta y 20 de cada respuesta. Lo recomendable es llegar a 600 o más.

## 2. Medir y entrenar

```bash
python manage.py entrenar_curador --reporte docs/experimentos/curador-AAAA-MM-DD.csv
```

El comando compara tres métodos con **validación cruzada estratificada de 5 pliegues**: cada lugar lo predice un
modelo que no lo vio al entrenar.

| Método | Qué ve |
|---|---|
| Regla actual | Nada: todo lo importado sirve. Es la línea base. |
| Modelo sin nombre | Tipo, subtipo, fuente, teléfono, sitio web, horario, dirección, zona metropolitana y distancia al destino más cercano |
| Modelo completo | Lo anterior más el **nombre**, leído por fragmentos de 2 a 4 letras (TF-IDF, sin acentos ni mayúsculas) |

En los tres casos se usa una regresión logística con clases balanceadas.

Las medidas se calculan sobre los lugares que **no** sirven, que son los que el curador debe encontrar:

- **Precisión:** de los que marca como "no sirve", cuántos lo son.
- **Exhaustividad:** de los que no sirven, cuántos encuentra.
- **F1:** combina las dos anteriores.
- **AUC:** qué tan bien ordena los lugares de "más probable que sirva" a "menos probable".

Al final, el comando entrena el modelo completo con todas las etiquetas y lo guarda en `var/curador.joblib`. Esa
carpeta no se versiona.

## 3. Aplicar y revisar

```bash
python manage.py aplicar_curador
```

El comando califica todos los lugares. Después hay dos formas de revisar:

- **`/admin/curador/prediccionlugar/`**, con el filtro "Probablemente no sirve (< 30 %)". Muestra la lista de
  lugares para que alguien decida si los oculta (desde la ficha del lugar).
- **Modo "casos dudosos"** en `/admin/etiquetar-lugares/` (**aprendizaje activo**). Muestra primero los lugares
  donde el modelo está más indeciso, porque ahí cada respuesta le enseña más.
  - Estas etiquetas sirven para entrenar, pero no son una muestra al azar.
  - Para reportar resultados, conviene medir con las etiquetas de la muestra.

El ciclo es: etiquetar → entrenar → aplicar → etiquetar casos dudosos → volver a entrenar.

## Código

| Archivo | Qué hace |
|---|---|
| `apps/curador/models.py` | `EtiquetaLugar` (decisión de una persona) y `PrediccionLugar` (opinión del modelo) |
| `apps/curador/muestreo.py` | Qué lugar mostrar: muestra al azar o caso dudoso |
| `apps/curador/caracteristicas.py` | De `Lugar` a datos para el modelo; mayoría de votos; kappa de Cohen |
| `apps/curador/modelo.py` | Modelo y evaluación con scikit-learn, sin Django |

## Limitaciones

- Aprende el criterio del equipo. Si el criterio cambia, hay que volver a etiquetar una parte y volver a entrenar.
- No ve fotos ni reseñas, solo los datos del directorio.
- Con pocas etiquetas, las medidas varían mucho. Por eso se reportan con validación cruzada y no con una sola
  partición de los datos.
