"""Moderación de contenido comunitario (aportes y colaboraciones) con una sola regla."""


def moderar(objeto, moderador, estado, motivo, registrar_sin_cambio=False):
    """Cambia el estado de un objeto Moderable y deja constancia en su historial.

    El llamador bloquea la fila (select_for_update) dentro de una transacción. Un estado en
    ESTADOS_SIN_MODERACION no se cambia, y si el estado no cambia no se registra nada salvo con
    `registrar_sin_cambio` (por ejemplo, al desestimar un reporte). Devuelve True si cambió el estado.
    """
    anterior = objeto.estado
    cambia = anterior != estado
    if cambia and anterior in objeto.ESTADOS_SIN_MODERACION:
        return False
    if not cambia and not registrar_sin_cambio:
        return False
    if cambia:
        objeto.estado = estado
        objeto.save(update_fields=objeto.CAMPOS_AL_MODERAR)
    objeto.registrar_moderacion(moderador=moderador, estado_anterior=anterior, estado_nuevo=estado, motivo=motivo)
    return cambia
