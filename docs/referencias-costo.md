# Referencias oficiales de costo

La sección de costos de cada destino tiene dos partes que nunca se mezclan:

- **Lo que reportan los viajeros**: mediana, mínimo y máximo con al menos 3 reportes del último año.
- **Referencia oficial**: precios que publica una fuente oficial, cada uno con su fuente, su fecha de consulta y, si la da, la fecha de actualización de la fuente. No entran en la mediana ni cuentan para el mínimo de reportes.

Nunca se estima ni se completa un precio. Si no hay fuente oficial, no hay fila.

## Cargar

```bash
python manage.py cargar_referencias_costo
```

Lee `apps/destinos/datos/referencias_costo.csv`. Se puede repetir: una fila con el mismo destino, concepto, descripción y fuente se actualiza en vez de duplicarse. Si alguna fila es inválida (monto, concepto, URL sin https o fecha futura), no se carga nada. Los destinos que no existen en la base se omiten con un aviso; en producción existen porque vienen de `importar_osm` y `cargar_destinos_iniciales`.

## Columnas del CSV

| Columna | Contenido |
|---|---|
| `destino` | Slug del destino |
| `concepto` | `entrada`, `comida`, `transporte` o `alojamiento` |
| `monto` | Pesos mexicanos; `0` cuando la fuente dice entrada libre |
| `descripcion` | A qué corresponde el precio, como lo publica la fuente |
| `fuente_nombre`, `fuente_url` | Quién lo publica y dónde (https) |
| `fecha_consulta` | Día en que se revisó la fuente (AAAA-MM-DD) |
| `fecha_fuente` | Última modificación o entrada en vigor que indica la fuente; vacío si no la da |

Para actualizar un precio, vuelve a consultar la fuente y cambia el monto y las fechas. Para retirar uno, bórralo desde `/admin/` y también del CSV.

## Fuentes usadas (consulta del 9 de noviembre de 2026)

| Fuente | Qué aporta | Fecha de la fuente |
|---|---|---|
| [Sistema de Información Cultural](https://sic.cultura.gob.mx/) (Secretaría de Cultura federal) | Entrada a 29 museos con destino propio; 15 de ellos con entrada libre | "Fecha de última modificación" de cada ficha, de 2019 a 2026 |
| [Reporte de tarifa vigente de la SICT](https://app.sct.gob.mx/sibuac_internet/ControllerUI?action=CmdTarifaRep1&countVias=124&radioTipoIva=2&radioSel=1&selectVia=29) | Casetas de los tramos Guadalajara–Zapotlanejo, Tonalá–Guadalajara, Zapotlanejo–Tepatitlán y Zapotlanejo–Lagos de Moreno, automóvil | En vigor desde el 13/04/2026 |
| [CAPUFE, Tarifas vigentes 2026](https://pot.capufe.mx/gobmx/transparencia/Doc/TransparenciaF/Tarifas/Vigentes/2026/Tarifas-vigentes-2026.pdf) | Casetas Acatlán y Sayula Troncal de Guadalajara–Colima, automóvil | En vigor desde el 13/04/2026 |
| [SITEUR, Tarifas y transferencias](https://www.siteur.gob.mx/index.php/forma-de-pago/tarifas-y-transferencias) | Viaje en Mi Tren, Tren Ligero o Mi Macro: $11 tarifa completa | No indica fecha |

Algunas fichas del SIC no se han actualizado en años (la más antigua, de 2019). La página muestra esa fecha junto al precio para que el viajero lo juzgue.

## Lo que no se pudo confirmar

- **Zona arqueológica de Guachimontones**: la [página del INAH](https://lugares.inah.gob.mx/es/mundial/6502) y la [ficha del SIC](https://sic.cultura.gob.mx/ficha.php?table=zona_arqueologica&table_id=155) dan horario, pero no precio. El Centro Interpretativo publica $30 (SIC y [museosdejalisco.com](https://museosdejalisco.com/espacio-guachimontones/)), pero ninguna fuente dice si cubre la zona. Por eso solo se registró en el destino del Centro Interpretativo.
- **Casetas hacia Tequila y Puerto Vallarta**: el reporte de la SICT de Guadalajara–Tepic no dice qué caseta se paga en el trayecto desde Guadalajara hasta Tequila, y no se encontró una tarifa oficial para el tramo hacia Puerto Vallarta. No se registraron.
- **Chapala, Ajijic, Tapalpa y Mazamitla**: ninguna tarifa oficial de caseta nombra estos destinos. No se registraron.
- **Autobuses foráneos**: las tarifas son de empresas privadas y cambian por fecha y horario; no hay una tarifa oficial publicada.
- **Fichas del SIC sin precio claro**: Museo de Cera ("dos boletos"), Museo Regional de la Cerámica (solo "domingo entrada libre") y las fichas sin costos (Casa Museo de Doña Conchita, Museo de las Ánimas, Museo Regional Cristero, Museo de Paleontología, Museo de El Arenal). Se omitieron.
- **Museo Regional de Guadalajara en el sitio del INAH**: la página del INAH muestra horario, pero no precio. Se tomó de la ficha del SIC, que lo atribuye al INAH.
