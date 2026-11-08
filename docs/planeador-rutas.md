# Planeador de rutas

`/planeador/` arma un itinerario de 1 a 3 días por Jalisco. La persona elige:

- desde dónde sale: un municipio o su ubicación, que no se guarda;
- la fecha, el horario y los días;
- sus intereses y su ritmo;
- cuántas personas van y el presupuesto para entradas.

La app decide **qué visitar y en qué orden**. Respeta el horario de cada sitio, el fin de cada día, el regreso al punto de salida y el presupuesto. También sugiere dónde comer y dónde dormir.

## Datos que usa

| Dato | Origen | Si falta |
|---|---|---|
| Destinos y coordenadas | Catálogo (OpenStreetMap curado y Sistema de Información Cultural) | — |
| Horarios | Datos prácticos publicados; los lee `apps/rutas/horarios.py` | Supone 10:00–17:00, o 8:00–19:00 al aire libre, y lo avisa |
| Precio de entrada | Datos prácticos publicados ("Entrada general $45", "Domingos: entrada libre") | No lo suma al total y lo avisa |
| Dónde comer y dormir | Lugares del DENUE (INEGI) y de OpenStreetMap | Lo dice |
| Tiempo de manejo | Distancia en línea recta × 1.35, a 30 km/h en ciudad y 70 km/h en carretera, más 10 min para estacionar | Es un estimado y la página lo dice |

El lector entiende los 93 horarios y los 71 precios reales del catálogo. Las pruebas recorren todos esos textos. Cuando un sitio solo se visita con cita previa, el lector no adivina un horario.

## El problema

Es el **problema del orientador con ventanas de tiempo** (*orienteering problem with time windows*), en varios días:

- Hay más sitios de los que caben en el viaje.
- Cada sitio vale un puntaje: 1.0 si coincide con los intereses y 0.2 si no. Suma 0.2 si tiene horario publicado y 0.1 si tiene precio.
- Cada visita tarda según la categoría y el ritmo elegido.
- Un sitio solo se puede visitar mientras está abierto.

La función objetivo, o **aptitud**, es la suma de los puntajes de los sitios visitados menos 0.002 por minuto al volante. Ese término solo desempata itinerarios de interés parecido.

## Los métodos (`apps/rutas/optimizador.py`)

El optimizador no depende de Django: recibe datos simples y se puede medir por separado.

- **Decodificador.** Convierte un orden de sitios en itinerario. Llena cada día con los sitios que caben, en ese orden, y reserva una hora para comer entre 13:30 y 16:00. Cada día empieza donde terminó el anterior.
- **Voraz.** En cada paso va al sitio que da más puntaje por minuto invertido. Es rápido, pero miope.
- **Genético puro.** Empieza con 60 órdenes al azar y evoluciona hasta 150 generaciones. Se detiene si pasan 40 generaciones sin mejorar. Usa:
  - selección por torneo de 3;
  - cruce de orden (OX) con probabilidad de 0.9;
  - mutación con probabilidad de 0.3: intercambio, inversión de un tramo o mover un sitio;
  - élite de 2.
- **Genético híbrido**, el que usa la página. Es igual al puro, pero el 25 % de la población inicial sale de la solución voraz y de variaciones suyas.

Con la misma semilla, cada método da siempre el mismo plan.

## Experimento

```bash
python manage.py experimento_rutas --corridas 35 --salida experimento.csv
```

El experimento usa 12 escenarios reales (`ESCENARIOS` en `apps/rutas/management/commands/experimento_rutas.py`). Varían el origen (Guadalajara, Zapopan, Tlaquepaque, Puerto Vallarta, Tequila, Chapala y Tapalpa), de 1 a 3 días, los intereses, el ritmo, las personas y el presupuesto. Se probaron en sábado y en lunes.

En cada escenario, el voraz corre una vez y cada genético corre 35 veces, con las semillas 1 a 35. En total son 852 ejecuciones. El resultado del 8 de noviembre de 2026, con 354 destinos públicos, está en [experimentos/rutas-2026-11-08.csv](experimentos/rutas-2026-11-08.csv).

| Método | n | Aptitud media | Desv. est. | Sitios | km | Segundos |
|---|---|---|---|---|---|---|
| Voraz | 12 | 11.702 | 5.476 | 10.50 | 152.2 | 0.001 |
| Genético puro | 420 | 11.300 | 4.742 | 10.08 | 151.8 | 1.015 |
| Genético híbrido | 420 | 12.173 | 5.230 | 10.84 | 143.6 | 0.737 |

La prueba de signos compara cada corrida con el voraz del mismo escenario:

| Método | Mejora | Empata | Empeora | Diferencia media | p |
|---|---|---|---|---|---|
| Genético puro | 213 | 18 | 189 | −0.401 | 0.25 |
| Genético híbrido | 388 | 32 | 0 | +0.472 | 3.2 × 10⁻¹¹⁷ |

Por escenario, el híbrido mejora al voraz entre +0.2 % y +39 %. Las mayores mejoras están en Chapala (+39.0 %), Tequila (+14.6 %) y Tapalpa (+9.5 %): ahí el voraz se gasta el día en sitios cercanos y ya no llega a los que valen más. En Guadalajara, con muchos museos juntos, el voraz ya es casi óptimo y la mejora es de +0.2 a +2.5 %.

**Lectura:**

- **El genético puro no basta.** Con 45 candidatos, empezar solo con órdenes al azar no supera de forma significativa al voraz (p = 0.25), y en promedio queda por debajo.
- **El híbrido nunca queda por debajo del voraz.** Lo mejora en 388 de 420 corridas, con 8 km menos de recorrido en promedio y menos de 1.3 s por plan.

## Limitaciones

- Solo considera viajes en auto. No toma en cuenta transporte público ni tráfico.
- Los tiempos de manejo son estimados, no de rutas por carretera.
- Los horarios dependen de la fuente. Si no hay un horario publicado, se supone uno y la página lo avisa.
- El puntaje no usa todavía las calificaciones de la comunidad, porque aún no hay reseñas reales.
