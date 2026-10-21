"""
ECHO//NULL — 3D LIDAR LAB
Prototipo experimental en Ursina + Python.

Instalación:
    python -m pip install ursina
Ejecución:
    python echo_null.py

Controles:
    WASD                 Moverse
    Ratón                Mirar alrededor
    ESPACIO              Saltar
    1                    Barrido horizontal continuo
    2                    Pulso radial 3D
    E                    Disparar un pulso radial
    TAB                  Mostrar/ocultar nube de puntos
    C                    Borrar la reconstrucción
    ESC                  Liberar el ratón / salir
"""

from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from pathlib import Path
from copy import copy
import math
import random

# Panda3D no puede abrir directamente texturas desde esta ruta sincronizada de
# Windows en algunos entornos. Pillow sí puede leerlas; cargarlas desde memoria
# evita que Ursina reciba una textura nula durante el arranque.
import ursina.texture_importer as texture_importer
import ursina.entity as ursina_entity
from PIL import Image

_load_texture_original = texture_importer.load_texture

def load_texture_from_image(name, folder=None, use_cache=True, filtering="default"):
    if not isinstance(name, (str, Path)):
        return _load_texture_original(name, folder, use_cache, filtering)
    if isinstance(name, str) and name.startswith("data:image/png;base64"):
        return _load_texture_original(name, folder, use_cache, filtering)
    name = str(name)
    if use_cache and name in texture_importer.imported_textures:
        cached = texture_importer.imported_textures[name]
        return copy(cached) if cached is not None else None
    folders = (folder,) if folder is not None else (
        texture_importer.application.textures_compressed_folder,
        texture_importer.application.asset_folder,
        texture_importer.application.internal_textures_folder,
    )
    for base in folders:
        pattern = "**/" + name if "." in name else "**/" + name + ".*"
        for filename in base.glob(pattern):
            if filename.suffix.lower() not in (".png", ".jpg", ".jpeg", ".tif", ".gif"):
                continue
            image = Image.open(filename).convert("RGBA")
            texture = Texture(image, filtering=filtering)
            texture_importer.imported_textures[name] = texture
            return copy(texture)
    return _load_texture_original(name, folder, use_cache, filtering)

texture_importer.load_texture = load_texture_from_image
ursina_entity.load_texture = load_texture_from_image

app = Ursina(title="ECHO//NULL — 3D LIDAR LAB", borderless=False)
window.color = color.rgb(7, 10, 16)
window.fps_counter.enabled = True
window.exit_button.visible = False
window.fullscreen = False

# --------------------------- CONFIGURACIÓN ---------------------------

SCAN_RANGE = 22
SWEEP_DEGREES_PER_SECOND = 150
SWEEP_RAY_STEP = 5
SWEEP_ELEVATIONS = (-12, -5, 0, 5, 12)
PULSE_RAYS = 520
POINT_SCALE = 0.045
MAX_POINTS = 14000

CYAN = color.rgb(65, 225, 245)
CYAN_DIM = color.rgb(22, 110, 130)
WHITE = color.rgb(225, 240, 245)
MUTED = color.rgb(145, 165, 180)
ORANGE = color.rgb(255, 190, 85)

scan_points = []
scan_mode = "off"
sweep_angle = 0.0
scan_visible = True
last_pulse_count = 0
message_timer = 0.0
scan_count = 0

# --------------------------- ESCENARIO 3D ---------------------------

def solid(name, position, scale, tint, collider="box"):
    return Entity(
        name=name,
        model="cube",
        position=position,
        scale=scale,
        color=tint,
        collider=collider,
        texture="white_cube",
    )

# Suelo y techo de la sala principal.
solid("Floor", (0, -0.15, 0), (28, 0.3, 22), color.rgb(35, 41, 48))
solid("Ceiling", (0, 5.2, 0), (28, 0.25, 22), color.rgb(28, 34, 42))

wall_color = color.rgb(76, 88, 99)
trim_color = color.rgb(49, 59, 69)

# Paredes exteriores; se dejan aperturas para conectar habitaciones.
# Norte y sur
solid("North wall left", (-8, 2.5, 11), (12, 5, 0.35), wall_color)
solid("North wall right", (9, 2.5, 11), (10, 5, 0.35), wall_color)
solid("South wall", (0, 2.5, -11), (28, 5, 0.35), wall_color)
# Oeste y este
solid("West wall", (-14, 2.5, 0), (0.35, 5, 22), wall_color)
solid("East wall", (14, 2.5, 0), (0.35, 5, 22), wall_color)

# Particiones interiores con aberturas para puertas.
# División de la sala en zona oeste/centro/este.
solid("Partition west upper", (-5, 2.0, 4.5), (0.28, 4, 5.0), trim_color)
solid("Partition west lower", (-5, 2.0, -5.2), (0.28, 4, 4.0), trim_color)
solid("Partition east upper", (5, 2.0, 5.0), (0.28, 4, 4.0), trim_color)
solid("Partition east lower", (5, 2.0, -4.7), (0.28, 4, 5.0), trim_color)

# Paredes transversales que crean recovecos y pequeños espacios.
solid("Cross wall A left", (-10.5, 2.0, 2.0), (6.5, 4, 0.28), trim_color)
solid("Cross wall A right", (-1.0, 2.0, 2.0), (7.5, 4, 0.28), trim_color)
solid("Cross wall B left", (0.0, 2.0, -2.0), (9.0, 4, 0.28), trim_color)
solid("Cross wall B right", (10.5, 2.0, -2.0), (7.0, 4, 0.28), trim_color)
solid("Back partition", (8.5, 2.0, 7.0), (8.5, 4, 0.28), trim_color)

# Algunos objetos sólidos para comprobar la detección a diferentes alturas.
solid("Crate A", (-9.0, 0.7, -5.0), (1.5, 1.4, 1.5), color.rgb(91, 78, 61))
solid("Crate B", (1.4, 0.55, 7.0), (1.1, 1.1, 1.1), color.rgb(92, 100, 107))
solid("Pillar", (10.8, 1.7, 5.0), (0.75, 3.4, 0.75), color.rgb(66, 77, 88))
solid("Low block", (9.5, 0.45, -7.2), (2.4, 0.9, 1.3), color.rgb(82, 91, 99))

# Luces de ambiente y puntos de luz básicos.
AmbientLight(color=color.rgb(115, 125, 145))
for pos in [(-8, 4.65, 6), (0, 4.65, 0), (8, 4.65, -6)]:
    lamp = Entity(model="cube", position=pos, scale=(2.0, 0.08, 0.3),
                  color=color.rgb(170, 205, 215), unlit=True)
    PointLight(parent=lamp, y=-0.25, color=color.rgb(130, 190, 205), range=10)

# Líneas de orientación en el suelo, solo visuales; sin collider.
for x in range(-12, 13, 2):
    Entity(model="cube", position=(x, 0.012, 0), scale=(0.018, 0.01, 20),
           color=color.rgba(95, 125, 145, 65), unlit=True, collider=None)
for z in range(-10, 11, 2):
    Entity(model="cube", position=(0, 0.013, z), scale=(26, 0.01, 0.018),
           color=color.rgba(95, 125, 145, 65), unlit=True, collider=None)

# --------------------------- JUGADOR ---------------------------

player = FirstPersonController(
    position=(-10, 1.8, -7.5),
    speed=5,
    jump_height=1.5,
    gravity=0.8,
)
player.cursor.visible = False
player.mouse_sensitivity = Vec2(40, 40)
player.collider = "box"
player.height = 1.8
player.camera_pivot.y = 1.65
camera.fov = 90

# --------------------------- INTERFAZ ---------------------------

crosshair = Text("+", origin=(0, 0), scale=1.3, color=CYAN, position=(0, 0))
title = Text("ECHO//NULL  |  3D LIDAR LAB", position=(-0.86, 0.46),
             scale=1.15, color=CYAN)
mode_text = Text("MODO: INACTIVO", position=(-0.86, 0.405), scale=0.85, color=WHITE)
data_text = Text("PUNTOS: 0  |  PULSOS: 0", position=(-0.86, 0.365),
                 scale=0.8, color=MUTED)
help_text = Text(
    "WASD mover  |  Ratón mirar  |  1 barrido  |  2 modo pulso  |  E pulso único\n"
    "TAB mostrar/ocultar puntos  |  C borrar nube  |  ESC liberar/salir",
    position=(-0.86, -0.46), scale=0.72, color=MUTED,
)
message_text = Text("", position=(-0.2, 0.42), scale=0.85, color=ORANGE)
reticle_label = Text("LIDAR", position=(0.02, -0.045), scale=0.55, color=CYAN)

# --------------------------- MOTOR DE ESCANEO ---------------------------

def create_point(position, strength=1.0):
    """Añade un punto visible y persistente en la nube 3D."""
    if len(scan_points) >= MAX_POINTS:
        old = scan_points.pop(0)
        destroy(old)
    # Pequeña variación de color según la distancia estimada.
    tint = color.rgb(
        int(25 + 35 * strength),
        int(100 + 130 * strength),
        int(130 + 115 * strength),
    )
    point = Entity(
        model="sphere",
        position=position,
        scale=POINT_SCALE * (0.75 + 0.45 * strength),
        color=tint,
        unlit=True,
        collider=None,
    )
    scan_points.append(point)
    point.enabled = scan_visible

def cast_lidar_ray(direction):
    """Lanza un rayo contra la geometría colisionable y registra el impacto."""
    origin = camera.world_position
    hit = raycast(
        origin=origin,
        direction=direction,
        distance=SCAN_RANGE,
        ignore=[player],
        debug=False,
    )
    if hit.hit:
        # Desplazamiento minúsculo hacia fuera para evitar parpadeo visual.
        point_pos = hit.world_point + hit.world_normal * 0.012
        strength = max(0.15, 1.0 - hit.distance / SCAN_RANGE)
        create_point(point_pos, strength)
        return True
    return False

def do_radial_pulse():
    """Distribución aproximadamente uniforme de rayos sobre una esfera."""
    global scan_count, last_pulse_count, message_timer
    before = len(scan_points)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(PULSE_RAYS):
        y = 1.0 - (i / float(PULSE_RAYS - 1)) * 2.0
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden_angle * i
        x = math.cos(theta) * radius
        z = math.sin(theta) * radius
        direction = Vec3(x, y, z)
        cast_lidar_ray(direction)
    scan_count += 1
    last_pulse_count = len(scan_points) - before
    message_text.text = f"PULSO COMPLETADO: {last_pulse_count} nuevos puntos"
    message_timer = 2.5
    data_text.text = f"PUNTOS: {len(scan_points)}  |  PULSOS: {scan_count}"

def sweep_scan_step(dt):
    """Barrido horizontal de 360 grados con varias capas de elevación."""
    global sweep_angle
    sweep_angle = (sweep_angle + SWEEP_DEGREES_PER_SECOND * dt) % 360
    # Cada frame emite un pequeño abanico; el giro completo acumula la nube.
    for elevation in SWEEP_ELEVATIONS:
        yaw = math.radians(sweep_angle)
        pitch = math.radians(elevation)
        direction = Vec3(
            math.sin(yaw) * math.cos(pitch),
            math.sin(pitch),
            math.cos(yaw) * math.cos(pitch),
        )
        cast_lidar_ray(direction)

def clear_cloud():
    global scan_points, scan_count
    for point in scan_points:
        destroy(point)
    scan_points = []
    scan_count = 0
    data_text.text = "PUNTOS: 0  |  PULSOS: 0"
    message_text.text = "NUBE DE PUNTOS BORRADA"
    global message_timer
    message_timer = 2.0

def update():
    global scan_mode, message_timer

    if scan_mode == "sweep":
        sweep_scan_step(time.dt)

    if message_timer > 0:
        message_timer -= time.dt
        if message_timer <= 0:
            message_text.text = ""

    # Evita que el jugador abandone completamente el área de prueba.
    player.x = clamp(player.x, -13.0, 13.0)
    player.z = clamp(player.z, -10.0, 10.0)

    # HUD: orientación y estado.
    mode_name = {
        "off": "INACTIVO",
        "sweep": "BARRIDO HORIZONTAL",
        "pulse": "MODO PULSO (E PARA EMITIR)",
    }.get(scan_mode, "INACTIVO")
    new_mode_text = f"MODO: {mode_name}"
    if mode_text.text != new_mode_text:
        mode_text.text = new_mode_text

    new_data_text = f"PUNTOS: {len(scan_points)}  |  PULSOS: {scan_count}"
    if data_text.text != new_data_text:
        data_text.text = new_data_text

def input(key):
    global scan_mode, scan_visible

    if key == "1":
        scan_mode = "sweep"
        message_text.text = "BARRIDO HORIZONTAL ACTIVADO"
        global message_timer
        message_timer = 2.0
    elif key == "2":
        scan_mode = "pulse"
        message_text.text = "MODO PULSO RADIAL: PULSA E"
        message_timer = 2.0
    elif key == "e":
        do_radial_pulse()
    elif key == "tab":
        scan_visible = not scan_visible
        for point in scan_points:
            point.enabled = scan_visible
        message_text.text = "NUBE VISIBLE" if scan_visible else "NUBE OCULTA"
        message_timer = 1.5
    elif key == "c":
        clear_cloud()
    elif key == "escape":
        if mouse.locked:
            mouse.locked = False
            player.enabled = False
            message_text.text = "RATÓN LIBERADO — ESC para volver / Q para salir"
            message_timer = 3.0
        else:
            mouse.locked = True
            player.enabled = True
    elif key == "q":
        application.quit()

# Una pequeña leyenda en el escenario para ayudar a reconocer la escala.
Entity(model="cube", position=(-10, 0.02, -8.8), scale=(1, 0.025, 1),
       color=color.rgb(70, 125, 145), collider=None)
Text("INICIO", world_parent=scene, position=(-10.5, 0.15, -8.8),
     scale=5, billboard=True, color=WHITE)

print("ECHO//NULL 3D LIDAR LAB iniciado.")
print("1: barrido horizontal | 2: modo pulso | E: pulso | TAB: nube | C: limpiar")
app.run()

