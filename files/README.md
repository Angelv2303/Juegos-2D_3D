# Juegos y pruebas de Machine Learning con Python

Proyecto de clase: pruebas de TensorFlow, experimentos con MNIST y tres videojuegos hechos en Python.

## Contenido

| Archivo | Qué es |
|---|---|
| `pong_2d.py` | Pong en 2D con pygame. Tres modos: PC vs Usuario, PC vs Usuario + Usuario (equipo) y Usuario vs Usuario. |
| `pong_3d.py` | El mismo Pong en 3D con Ursina, con los mismos tres modos. |
| `agario_2d.py` | Juego estilo agar.io: mundo grande, comida, NPC que cazan y huyen, cámara con zoom, minimapa y ranking. |
| `test_tensorflow.py` | Prueba de que TensorFlow quedó bien instalado. |
| `mnist_entrenamiento.py` | Red neuronal que reconoce dígitos escritos a mano (MNIST). |

## Instalación

Se recomienda usar un entorno virtual:

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Mac / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Si PowerShell dice que la ejecución de scripts está deshabilitada, ejecuta una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

> **Nota sobre versiones de Python:** TensorFlow, pygame y Panda3D (que usa Ursina) tardan en publicar
> instaladores para las versiones nuevas de Python. Si `pip install` falla con
> `No matching distribution found`, prueba con Python 3.11 o 3.12.

## Cómo ejecutar los juegos

```bash
python pong_2d.py
python pong_3d.py
python agario_2d.py
```

### Controles

**Pong (2D y 3D)**
- Usuario 1: `W` / `S`
- Usuario 2: flechas arriba / abajo
- En el modo 1 se pueden usar ambos juegos de teclas
- `1`, `2`, `3`: elegir modo en el menú
- `P`: pausa, `M` (3D) o `ESC` (2D): volver al menú, `ENTER`: revancha

**Agar 2D**
- Mouse (o `W A S D` / flechas): mover la célula
- `ESPACIO`: sprint (gasta masa)
- `P`: pausa, `ENTER`: volver a jugar, `ESC`: salir

## Cómo funciona

- **Pong:** la PC sigue la pelota con una regla simple y es más lenta que la pelota, así que se le puede ganar apuntando con los bordes de la paleta.
- **Agar 2D:** cada NPC decide cada fracción de segundo si huir de una célula más grande, cazar a una más pequeña, ir hacia la comida más cercana o vagar. El mundo usa una rejilla espacial para buscar comida rápido.

## Ideas para seguir

- Reemplazar las reglas de la PC y de los NPC por un agente entrenado con aprendizaje por refuerzo.
- Probar autoencoders o GAN con MNIST.
