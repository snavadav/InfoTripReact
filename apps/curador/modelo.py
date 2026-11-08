"""El modelo del curador: aprende de las etiquetas del equipo si un lugar le sirve a un viajero.

No depende de Django: recibe filas (diccionarios) y etiquetas, así se puede probar y medir por separado.

- El nombre se lee por fragmentos de 2 a 4 letras (TF-IDF), sin acentos ni mayúsculas: así "Taquería",
  "TAQUERIA" y "Tacos el Güero" comparten pistas, y un nombre mal escrito no queda fuera.
- Tipo, subtipo y fuente van como categorías; teléfono, sitio web, horario, dirección, zona metropolitana y
  distancia al destino más cercano, como números.
- Regresión logística con clases balanceadas: los "no sirve" son minoría y no deben perderse.
"""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORIAS = ['tipo', 'subtipo', 'fuente']
NUMEROS = ['tiene_telefono', 'tiene_web', 'tiene_horario', 'tiene_direccion', 'metropolitana', 'log_km_destino',
           'palabras']
COLUMNAS = ['nombre'] + CATEGORIAS + NUMEROS
VERSION = 1


def matriz(filas):
    """Lista de diccionarios → arreglo de objetos con las columnas en orden fijo (sin pandas)."""
    return np.array([[fila[columna] for columna in COLUMNAS] for fila in filas], dtype=object)


def crear(con_nombre=True, semilla=0):
    """Con `con_nombre=False` es la línea base que solo ve tipo, fuente y datos de contacto."""
    posicion = {columna: i for i, columna in enumerate(COLUMNAS)}
    transformadores = [
        ('categorias', OneHotEncoder(handle_unknown='ignore'), [posicion[c] for c in CATEGORIAS]),
        ('numeros', StandardScaler(), [posicion[c] for c in NUMEROS]),
    ]
    if con_nombre:
        texto = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4), min_df=2, strip_accents='unicode',
                                lowercase=True, sublinear_tf=True)
        transformadores.insert(0, ('nombre', texto, posicion['nombre']))
    return Pipeline([
        ('columnas', ColumnTransformer(transformadores)),
        ('clasificador', LogisticRegression(class_weight='balanced', max_iter=2000, random_state=semilla)),
    ])


def medidas(reales, probabilidades, umbral=0.5):
    """Medidas sobre la clase "no sirve", que es la que el curador debe encontrar."""
    reales = np.asarray(reales, dtype=bool)
    no_sirve_real = ~reales
    no_sirve_predicho = np.asarray(probabilidades) < umbral
    precision, exhaustividad, f1, _ = precision_recall_fscore_support(
        no_sirve_real, no_sirve_predicho, average='binary', zero_division=0)
    return {
        'exactitud': accuracy_score(no_sirve_real, no_sirve_predicho),
        'precision_no_sirve': precision, 'exhaustividad_no_sirve': exhaustividad, 'f1_no_sirve': f1,
        'auc': roc_auc_score(reales, probabilidades) if len(set(reales)) == 2 else float('nan'),
        'verdaderos_no': int((no_sirve_real & no_sirve_predicho).sum()),
        'falsos_no': int((~no_sirve_real & no_sirve_predicho).sum()),
        'no_detectados': int((no_sirve_real & ~no_sirve_predicho).sum()),
        'verdaderos_si': int((~no_sirve_real & ~no_sirve_predicho).sum()),
    }


def evaluar(filas, etiquetas, pliegues=5, semilla=0):
    """Validación cruzada estratificada: cada lugar se predice con un modelo que no lo vio al entrenar.

    Compara tres métodos: la regla actual (todo lo importado sirve), el modelo sin el nombre y el modelo completo.
    """
    x, y = matriz(filas), np.asarray(etiquetas, dtype=bool)
    division = StratifiedKFold(n_splits=pliegues, shuffle=True, random_state=semilla)
    resultados = {'regla_actual': medidas(y, np.ones(len(y)))}
    for nombre, con_nombre in (('modelo_sin_nombre', False), ('modelo_completo', True)):
        probabilidades = cross_val_predict(crear(con_nombre, semilla), x, y, cv=division,
                                           method='predict_proba')[:, 1]
        resultados[nombre] = medidas(y, probabilidades)
    return resultados


def entrenar(filas, etiquetas, semilla=0):
    return crear(True, semilla).fit(matriz(filas), np.asarray(etiquetas, dtype=bool))


def probabilidad_de_servir(modelo, filas):
    return modelo.predict_proba(matriz(filas))[:, 1]
