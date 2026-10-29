"""La dependencia entre módulos va en un solo sentido: destinos usa comunidad solo mediante selectors."""
import ast
from pathlib import Path
from django.test import SimpleTestCase

APPS = Path(__file__).resolve().parent.parent


def importaciones(ruta):
    """Módulos importados por un archivo, indicando si la importación está dentro de una función."""
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    funciones = [nodo for nodo in ast.walk(arbol) if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))]
    internas = {id(hijo) for funcion in funciones for hijo in ast.walk(funcion)}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            yield nodo.module, id(nodo) in internas
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                yield alias.name, id(nodo) in internas


def codigo(app):
    return [ruta for ruta in (APPS / app).rglob('*.py') if 'migrations' not in ruta.parts and not ruta.name.startswith('test')]


class DependenciasTests(SimpleTestCase):
    def test_sin_importaciones_dentro_de_funciones(self):
        for app in ('comunidad', 'destinos', 'usuarios', 'core'):
            for ruta in codigo(app):
                for modulo, interna in importaciones(ruta):
                    self.assertFalse(interna, f'{ruta.relative_to(APPS)} importa {modulo} dentro de una función')

    def test_destinos_solo_usa_selectors_y_modelos_de_comunidad(self):
        for ruta in codigo('destinos'):
            for modulo, _ in importaciones(ruta):
                if modulo.startswith('apps.comunidad'):
                    self.assertIn(modulo, ('apps.comunidad.selectors', 'apps.comunidad.models'), ruta.name)

    def test_comunidad_no_importa_vistas_de_destinos(self):
        for ruta in codigo('comunidad'):
            for modulo, _ in importaciones(ruta):
                if modulo.startswith('apps.destinos'):
                    self.assertEqual(modulo, 'apps.destinos.models', ruta.name)

    def test_core_no_depende_de_ninguna_app(self):
        for ruta in codigo('core'):
            for modulo, _ in importaciones(ruta):
                self.assertFalse(modulo.startswith('apps.'), ruta.name)
