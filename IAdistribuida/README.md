# IA distribuida: semáforos como agentes

Sistema multiagente en el que cada semáforo es un agente autónomo con visión local
(solo ve su propio cruce) y que puede comunicarse con otros agentes.

## Archivos
| Archivo | Qué muestra |
|---|---|
| `etapa1_semaforo.py` | Un agente (percibir → decidir → actuar). Semáforo fijo vs. reactivo. |
| `etapa3_dos_cruces.py` | Dos agentes con visión local, sin comunicación. |
| `etapa4_ola_verde.py` | Los agentes se envían mensajes (ola verde) y se mide el equilibrio entre métricas. |
| `etapa5_semaforos.html` | Simulación visual completa: comunicación, tope de justicia y fallo de un cruce. |

## Cómo ejecutarlo
- Versión visual: abre `etapa5_semaforos.html` en el navegador (no necesita internet ni instalar nada).
- Versión en consola: `python etapa4_ola_verde.py` (los `.py` deben estar en la misma carpeta; solo usan la librería estándar de Python).

## Conceptos que ilustra
- Agente: entidad autónoma que percibe, decide y actúa.
- Visión local: ningún agente conoce el sistema completo.
- Coordinación por mensajes: A avisa a B de los autos que le envía.
- Compromiso entre métricas: reducir paradas en rojo puede aumentar la espera total.
- Robustez: si un agente falla, el resto sigue funcionando.
