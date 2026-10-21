"""BACKROOM: experiencia 3D de terror liminal; la habitacion es la amenaza.

Controles: WASD mover, raton mirar, espacio saltar, F linterna, R reiniciar (al final), ESC salir.
Requiere: pip install ursina

Novedades de esta version:
  - Geometria de paredes fusionada en una sola malla (mucho menos lag).
  - Suelo y techo permanentes: el jugador ya no se hunde al cambiar el mapa.
  - Zona fija alrededor del jugador: su habitacion se conserva y cambia lo de alrededor.
  - Apagon de camara durante el cambio, sin cuenta atras.
  - Shader estilo camara analogica (grano, aberracion, viñeta, scanlines).
  - Sistema de CORDURA con alucinaciones (siluetas, pasos fantasma, reloj, flechas que mienten...).
"""
import math
import random
from pathlib import Path

from panda3d.core import PNMImage, Texture as PandaTexture
from ursina import *
from ursina import Texture as UrsinaTexture
from ursina.prefabs.first_person_controller import FirstPersonController

# ----------------------------------------------------------------------------
# AJUSTES (aqui puedes tocar el juego sin buscar por todo el codigo)
# ----------------------------------------------------------------------------
CELDA = 5.5
LADO = 21                         # cuadricula grande de salas y corredores
ALTO_MURO = 4.2
GROSOR_MURO = 0.18                # pared visible fina; la colision sigue cubriendo la celda
COLOR_PAPEL = (180, 157, 91)

USAR_SHADER = True                # False si el efecto de camara da problemas
MOSTRAR_FPS = True                # contador de FPS para medir el rendimiento
USAR_LUCES_PUNTUALES = True       # False = quita las PointLight (mas FPS)
RADIO_FIJO = 1                    # 1 = zona fija de 3x3 celdas; 2 = 5x5

INTERVALO_MIN = 45.0              # segundos entre cambios del laberinto (se acorta con la locura)
INTERVALO_MAX = 70.0

# Cordura (puntos por segundo)
CORDURA_BASE = -0.20              # el tiempo en este lugar te desgasta siempre
CORDURA_LUZ = 0.48                # bajo un fluorescente recuperas lentamente
CORDURA_OSCURO = -0.42            # la oscuridad desgasta con mas rapidez
CORDURA_SIN_LINTERNA = -0.50      # extra si ademas tienes la linterna apagada
RADIO_LUZ = 7.0                   # distancia a la que un fluorescente "cuenta"

VELOCIDAD_CAMINAR = 3.4
VELOCIDAD_SPRINT = 6.2
ENERGIA_SPRINT_MAX = 100.0
COSTO_SPRINT = 34.0               # energia por segundo mientras corre
RECUPERACION_SPRINT = 22.0        # energia por segundo al caminar
MULTIPLICADOR_REFRESCO = 1.38
DURACION_REFRESCO = 10.0
CORDURA_AGUA_ALMENDRA = 32.0
T_ENTIDAD_CIEGA = 58.0            # tiempo antes de que despierte la entidad ciega
FOV_NORMAL = 82.0
FOV_ZOOM_MIN = 48.0
FOV_ZOOM_MAX = 96.0
PASO_ZOOM = 5.0

FRASES_LOCURA = ("NO HAY SALIDA", "TE ESTA MIRANDO", "YA PASASTE POR AQUI",
                 "NO ESTAS SOLO", "VUELVE A EMPEZAR", "NUNCA HUBO SALIDA")


# ----------------------------------------------------------------------------
# TEXTURAS PROCEDURALES
# ----------------------------------------------------------------------------
def crear_textura(nombre, tipo, lado=256):
    """Material tileable con grano, variacion de tono y desgaste integrado."""
    imagen = PNMImage(lado, lado, 3)
    rng = random.Random(nombre)
    ruido = [[rng.random() for _ in range(8)] for _ in range(8)]

    def valor_ruido(x, y, escala):
        gx, gy = x / escala, y / escala
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        # Suavizado evita parches cuadrados y el modulo mantiene la textura tileable.
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a, b = ruido[iy % 8][ix % 8], ruido[iy % 8][(ix + 1) % 8]
        c, d = ruido[(iy + 1) % 8][ix % 8], ruido[(iy + 1) % 8][(ix + 1) % 8]
        arriba, abajo = a + (b - a) * fx, c + (d - c) * fx
        return arriba + (abajo - arriba) * fy

    for y in range(lado):
        for x in range(lado):
            nubes = valor_ruido(x, y, 32)
            grano = (valor_ruido(x, y, 8) - 0.5) * 0.10 + (rng.random() - 0.5) * 0.075
            if tipo == "papel":
                # Papel oliva de estilo art-deco: columnas y chevrones repetidos,
                # marcados como en el papel tapiz de la referencia.
                u, v = x % 32 - 16, y % 48
                chevron = (5 < v < 21
                           and abs(abs(u) - (v - 5) * 0.50) < 1.15)
                tallo = abs(u) < 0.72 and 5 < v < 43
                rombo = abs(u) < 1.35 and (v < 4 or 44 < v)
                relieve = -0.105 if chevron or tallo else (-0.07 if rombo else 0)
                relieve -= 0.035 if x % 32 < 2 else 0
                junta = -0.085 if x % 128 < 2 else 0
                humedad = max(0, nubes - 0.58) * 0.24
                # Amarillo limon apagado, con un matiz oliva (aprox. RGB 196, 186, 92).
                base = (0.77 + grano + relieve + junta - humedad,
                        0.73 + grano + relieve + junta - humedad * 0.91,
                        0.36 + grano * 0.72 + relieve * 0.55 + junta - humedad * 0.62)
            elif tipo == "alfombra":
                # Fibras verticales y manchas amplias, como moqueta gastada y humeda.
                fibra = (rng.random() - 0.5) * 0.13 + (0.018 if x % 3 == 0 else -0.006)
                mancha = max(0, nubes - 0.48) * 0.28
                hilo = -0.035 if y % 64 < 1 else 0
                # Moqueta gris oliva (aprox. RGB 112, 104, 72), con desgaste y manchas.
                base = (0.44 + grano + fibra - mancha + hilo,
                        0.41 + grano + fibra - mancha * 0.83 + hilo,
                        0.28 + grano * 0.7 + fibra - mancha * 0.63 + hilo)
            else:
                # Placas de techo con halos amarillos y suciedad alrededor de las juntas.
                junta = -0.15 if x % 64 < 2 or y % 64 < 2 else 0
                halo = max(0, nubes - 0.62) * 0.12
                # Plafon crema (aprox. RGB 200, 190, 140), envejecido en las juntas.
                base = (0.78 + grano + junta - halo,
                        0.74 + grano + junta - halo,
                        0.55 + grano * 0.7 + junta - halo * 0.78)
            imagen.setXel(x, y, *(max(0.0, min(1.0, c)) for c in base))

    textura = PandaTexture(nombre)
    textura.load(imagen)
    textura.setWrapU(PandaTexture.WM_repeat)
    textura.setWrapV(PandaTexture.WM_repeat)
    textura.setMinfilter(PandaTexture.FT_linear)
    textura.setMagfilter(PandaTexture.FT_linear)
    return UrsinaTexture(textura)


TEXTURA_PAPEL = crear_textura("papel_backrooms", "papel")
TEXTURA_ALFOMBRA = crear_textura("alfombra_backrooms", "alfombra")
TEXTURA_TECHO = crear_textura("losetas_techo_backrooms", "techo")
DIRECTORIO = Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# ESTADO GLOBAL DEL JUEGO (todo lo que cambia vive aqui)
# ----------------------------------------------------------------------------
class Estado:
    t = 0.0                       # tiempo total de "grabacion"
    cordura = 100.0
    techo = 100.0                 # maximo de cordura recuperable (baja con cada cambio)
    cambios = 0
    fase = "juego"                # "juego" o "fin"
    fin_t = 0.0
    glitch = 0.0                  # intensidad de distorsion de la camara
    fundido = 0.0                 # apagon posterior al cambio
    susto_activo = False
    susto_t = 0.0
    susto_enfriamiento = 0.0
    susto_yaw = 0.0
    susto_pitch = 0.0
    susto_yaw_inicio = 0.0
    susto_pitch_inicio = 0.0
    alerta_t = 0.0
    linterna = True
    # alucinaciones
    t_silueta = 25.0
    t_reloj = 25.0
    t_mensaje = 30.0
    desfase_reloj = 0.0
    ecos = []                     # pasos fantasma pendientes (segundos hasta sonar)
    mov_antes = False
    ultimo_seg = -1
    ultima_cordura = -1
    alpha_velo = -1
    energia_sprint = ENERGIA_SPRINT_MAX
    ultima_energia_sprint = -1
    t_corrida = 0.0
    t_consumible = 9.0
    agua_inventario = 0
    refresco_inventario = 0
    refresco_t = 0.0
    zoom_ui_t = 0.0
    fallo_linterna = 0.0
    ruido_t = 0.0
    ruido_x = 0.0
    ruido_z = 0.0
    ruido_intensidad = 0.0
    corrida_ruido_t = 0.0


E = Estado()


# ----------------------------------------------------------------------------
# VENTANA, AUDIO Y AMBIENTE
# ----------------------------------------------------------------------------
app = Ursina(title="BACKROOM | El laberinto cambiante")
window.color = color.rgb32(10, 11, 9)
window.fps_counter.enabled = MOSTRAR_FPS
window.exit_button.visible = False
try:
    window.entity_counter.enabled = False
    window.collider_counter.enabled = False
except Exception:
    pass
camera.fov = FOV_NORMAL
zoom_fov = FOV_NORMAL
try:
    # Evita que superficies muy cercanas desaparezcan al mirar junto a una pared.
    camera.lens.setNearFar(0.04, 180)
except Exception:
    pass

# Si colocas aquí una copia local y autorizada del audio de referencia,
# se usará como ambiente. Mientras no esté, se mantiene el zumbido original.
RUTAS_AMBIENTE = (
    DIRECTORIO / "backroom_sounds" / "ambiente_backrooms_loop.wav",
    DIRECTORIO / "backroom_sounds" / "ambiente_backrooms.ogg",
    DIRECTORIO / "backroom_sounds" / "ambiente_backrooms.wav",
    DIRECTORIO / "backroom_sounds" / "zumbido_nivel_0.wav",
)
archivo_zumbido = next((ruta for ruta in RUTAS_AMBIENTE if ruta.is_file()), None)
zumbido_ambiente = None
if archivo_zumbido:
    try:
        zumbido_ambiente = Audio(archivo_zumbido, volume=0.50, loop=True, group="ambient")
    except Exception:
        # La ambientacion visual debe funcionar aunque el equipo no tenga audio disponible.
        zumbido_ambiente = None

pasos = []
for variante in (1, 2):
    archivo_paso = DIRECTORIO / "backroom_sounds" / f"paso_alfombra_{variante}.wav"
    if archivo_paso.is_file():
        try:
            pasos.append(Audio(archivo_paso, autoplay=False, auto_destroy=False, volume=0.34))
        except Exception:
            pass

# Niebla lineal: lo lejano se pierde en la oscuridad (mas inquietante que ver todo el pasillo).
scene.fog_color = color.rgb32(8, 7, 4)
scene.fog_density = (6, 46)
ambiente = AmbientLight(color=color.rgb32(20, 18, 12))


# ----------------------------------------------------------------------------
# OBJETOS DEL MUNDO
# ----------------------------------------------------------------------------
class Mancha(Entity):
    """Mancha irregular de humedad y suciedad sobre la moqueta."""
    def __init__(self, **kwargs):
        super().__init__(model="sphere", collider=None, **kwargs)


class Fixture(Entity):
    """Tubo fluorescente viejo: vibra y pierde intensidad sin apagarse del todo."""
    def __init__(self, semilla=0, **kwargs):
        super().__init__(**kwargs)
        self.semilla = semilla * 9.0
        self.t = semilla * 3.0
        self.intensidad = 1.0
        self.intensidad_objetivo = 1.0
        self.proximo_tartamudeo = random.uniform(1.0, 5.5)
        self.duracion_tartamudeo = 0.0
        self.luz = None
        if USAR_LUCES_PUNTUALES:
            self.luz = PointLight(parent=self, position=(0, -0.24, 0),
                                  color=color.rgb32(236, 238, 187))
            self.luz._light.setAttenuation(Vec3(1, 0, 0.028))
        Entity(parent=self, model="cube", position=(0, -0.10, 0), scale=(2.3, 0.08, 0.72),
               color=color.rgb32(62, 54, 39), unlit=True)
        self.tubo = Entity(parent=self, model="cube", position=(0, -0.16, 0), scale=(1.95, 0.04, 0.45),
                           color=color.rgb32(238, 236, 193), unlit=True)
        self.tubo_halo = Entity(parent=self, model="cube", position=(0, -0.19, 0),
                                scale=(2.08, 0.018, 0.53),
                                color=color.rgba32(198, 190, 120, 55), unlit=True)

    def update(self):
        dt = time.dt
        self.t += dt
        # Con menos cordura los fluorescentes fallan mucho mas a menudo.
        estres = 1.0 + (100.0 - E.cordura) / 35.0
        self.proximo_tartamudeo -= dt * estres
        if self.proximo_tartamudeo <= 0:
            self.intensidad_objetivo = random.uniform(0.20, 0.48)
            self.duracion_tartamudeo = random.uniform(0.045, 0.16)
            self.proximo_tartamudeo = random.uniform(1.1, 5.8)
        if self.duracion_tartamudeo > 0:
            self.duracion_tartamudeo -= dt
        else:
            self.intensidad_objetivo = 1.0
        # Variacion constante y breve bajada: nunca hay un apagado limpio.
        temblor = 0.035 * math.sin(self.t * 43 + self.semilla) + 0.018 * math.sin(self.t * 91)
        self.intensidad += (self.intensidad_objetivo - self.intensidad) * min(1, dt * 13)
        brillo = max(0.16, min(1.0, self.intensidad + temblor))
        self.tubo.color = color.rgb32(int(100 + 138 * brillo), int(102 + 136 * brillo), int(80 + 120 * brillo))
        self.tubo_halo.color = color.rgba32(198, 190, 120, int(25 + 52 * brillo))
        if self.luz:
            self.luz.color = color.rgb32(int(236 * brillo), int(238 * brillo), int(187 * brillo))


# ----------------------------------------------------------------------------
# LABERINTO
# ----------------------------------------------------------------------------
class Laberinto:
    """Laberinto procedural; las flechas marcan el camino corto hasta la salida."""
    def __init__(self):
        self.raiz = None
        self.base = None
        self.grupo_muros = None
        self.mapa = []
        self.camino = []
        self.fixtures = []
        self.semilla = random.randrange(1_000_000)
        self.reloj = 0.0
        self.intervalo = INTERVALO_MAX
        self.tiempo_aviso = INTERVALO_MAX
        self.celda_jugador = (1, 1)
        self.puerta_imitada = None
        self.puerta_imitada_revelada = False
        self.tiempo_mirando_puerta = 0.0
        self.crear_base()
        self.reconstruir(None)

    # --- utilidades de coordenadas -----------------------------------------
    @staticmethod
    def a_mundo(gx, gz):
        centro = (LADO - 1) / 2
        return (gx - centro) * CELDA, (gz - centro) * CELDA

    @staticmethod
    def celda_de(x, z):
        centro = (LADO - 1) / 2
        return round(x / CELDA + centro), round(z / CELDA + centro)

    def libre(self, x, z):
        gx, gz = self.celda_de(x, z)
        return 0 <= gx < LADO and 0 <= gz < LADO and not self.mapa[gz][gx]

    def linea_libre(self, x0, z0, x1, z1):
        """True si no hay ninguna pared entre los dos puntos (para las alucinaciones)."""
        dist = math.hypot(x1 - x0, z1 - z0)
        pasos_n = max(1, int(dist / 0.8))
        for i in range(pasos_n + 1):
            k = i / pasos_n
            if not self.libre(x0 + (x1 - x0) * k, z0 + (z1 - z0) * k):
                return False
        return True

    def hay_luz_cerca(self, x, z, radio):
        r2 = radio * radio
        for f in self.fixtures:
            if ((f.x - x) ** 2 + (f.z - z) ** 2 < r2
                    and self.linea_libre(x, z, f.x, f.z)):
                return True
        return False

    # --- generacion del mapa -------------------------------------------------
    def generar_mapa(self, fijas=None, origen=(1, 1)):
        rng = random.Random(self.semilla)
        mapa = [[True for _ in range(LADO)] for _ in range(LADO)]
        inicio = (1, 1)
        mapa[inicio[1]][inicio[0]] = False
        pila = [inicio]
        while pila:
            x, z = pila[-1]
            opciones = [(x + dx, z + dz, dx, dz)
                        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2))
                        if 1 <= x + dx < LADO - 1 and 1 <= z + dz < LADO - 1
                        and mapa[z + dz][x + dx]]
            if not opciones:
                pila.pop()
                continue
            nx, nz, dx, dz = rng.choice(opciones)
            mapa[z + dz // 2][x + dx // 2] = False
            mapa[nz][nx] = False
            pila.append((nx, nz))

        # Abre bastantes muros para crear cruces, pasillos anchos y pequeñas plazas.
        for gz in range(2, LADO - 2):
            for gx in range(2, LADO - 2):
                if mapa[gz][gx] and rng.random() < 0.19:
                    mapa[gz][gx] = False

        # Salas amplias de oficina que rompen la sensacion de un laberinto uniforme.
        # Sus formas y tamaños cambian en cada reconstruccion del nivel.
        for _ in range(12):
            ancho = rng.choice((2, 3, 3, 4, 5))
            fondo = rng.choice((2, 3, 4, 4, 5))
            ox = rng.randint(2, LADO - ancho - 2)
            oz = rng.randint(2, LADO - fondo - 2)
            for gz in range(oz, oz + fondo):
                for gx in range(ox, ox + ancho):
                    mapa[gz][gx] = False

        # Zona fija: la habitacion donde esta el jugador se conserva tal cual.
        if fijas:
            for (fx, fz), valor in fijas.items():
                mapa[fz][fx] = valor
            mapa[origen[1]][origen[0]] = False

        # Sella el borde para que no exista una salida accidental hacia el exterior.
        mapa[0][1] = True
        # Primer tramo recto SOLO en la primera generacion (el despertar del jugador).
        if not fijas:
            for gx in range(1, 6):
                mapa[1][gx] = False
            mapa[2][5] = False
        mapa[LADO - 1][LADO - 2] = False

        # Une cada bolsillo aislado al recorrido: nada del mapa es decorado inaccesible.
        while True:
            alcanzables = {origen}
            cola = [origen]
            for x, z in cola:
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    vecino = (x + dx, z + dz)
                    vx, vz = vecino
                    if (0 <= vx < LADO and 0 <= vz < LADO and not mapa[vz][vx]
                            and vecino not in alcanzables):
                        alcanzables.add(vecino)
                        cola.append(vecino)
            aisladas = [(gx, gz) for gz in range(LADO) for gx in range(LADO)
                        if not mapa[gz][gx] and (gx, gz) not in alcanzables]
            if not aisladas:
                break
            meta = min(aisladas,
                       key=lambda p: min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in alcanzables))
            origen_c = min(alcanzables, key=lambda q: abs(meta[0] - q[0]) + abs(meta[1] - q[1]))
            x, z = origen_c
            while x != meta[0]:
                x += 1 if meta[0] > x else -1
                mapa[z][x] = False
            while z != meta[1]:
                z += 1 if meta[1] > z else -1
                mapa[z][x] = False
        return mapa, rng

    def camino_corto(self, inicio, meta):
        cola = [inicio]
        anterior = {inicio: None}
        for actual in cola:
            if actual == meta:
                break
            x, z = actual
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                vecino = (x + dx, z + dz)
                vx, vz = vecino
                if (0 <= vx < LADO and 0 <= vz < LADO and not self.mapa[vz][vx]
                        and vecino not in anterior):
                    anterior[vecino] = actual
                    cola.append(vecino)
        if meta not in anterior:
            return []
        ruta, nodo = [], meta
        while nodo is not None:
            ruta.append(nodo)
            nodo = anterior[nodo]
        return list(reversed(ruta))

    def toca_hueco(self, gx, gz):
        """True si la pared tiene alguna celda abierta alrededor (si no, nadie la ve)."""
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                px, pz = gx + dx, gz + dz
                if 0 <= px < LADO and 0 <= pz < LADO and not self.mapa[pz][px]:
                    return True
        return False

    # --- construccion --------------------------------------------------------
    def crear_base(self):
        """Suelo y techo permanentes: nunca se destruyen, asi el jugador no se hunde."""
        ancho = LADO * CELDA
        self.base = Entity(name="base_laberinto")
        Entity(parent=self.base, model="cube", name="moqueta", position=(0, -0.18, 0),
               scale=(ancho, 0.36, ancho), texture=TEXTURA_ALFOMBRA,
               texture_scale=(LADO * 2.8, LADO * 2.8), color=color.white, collider="box")
        Entity(parent=self.base, model="cube", name="techo", position=(0, ALTO_MURO + 0.18, 0),
               scale=(ancho, 0.36, ancho), texture=TEXTURA_TECHO, texture_scale=(LADO, LADO),
               color=color.white)

    def reconstruir(self, jugador):
        fijas, origen = None, (1, 1)
        if jugador is not None:
            gx, gz = self.celda_de(jugador.x, jugador.z)
            gx = max(1, min(LADO - 2, gx))
            gz = max(1, min(LADO - 2, gz))
            origen = (gx, gz)
            # Copia de la zona alrededor del jugador: esa habitacion se mantiene.
            fijas = {(x, z): self.mapa[z][x]
                     for z in range(max(1, gz - RADIO_FIJO), min(LADO - 1, gz + RADIO_FIJO + 1))
                     for x in range(max(1, gx - RADIO_FIJO), min(LADO - 1, gx + RADIO_FIJO + 1))}

        if self.raiz:
            destroy(self.raiz)
        self.fixtures = []
        self.puerta_imitada = None
        self.puerta_imitada_revelada = False
        self.tiempo_mirando_puerta = 0.0
        self.raiz = Entity(name="laberinto")
        self.grupo_muros = Entity(parent=self.raiz)
        self.grupo_zocalos = Entity(parent=self.raiz)
        self.grupo_remates = Entity(parent=self.raiz)
        self.semilla = random.randrange(1_000_000)
        self.mapa, rng = self.generar_mapa(fijas, origen)
        self.celda_jugador = origen
        self.camino = self.camino_corto(origen, (LADO - 2, LADO - 2))
        self.dibujar_mundo(rng, origen if fijas else None)
        self.dibujar_flechas(rng)
        self.dibujar_salida()
        self.dibujar_salida_imitada(rng)
        self.reloj = 0.0
        factor = 0.58 + 0.42 * (E.cordura / 100.0)    # con menos cordura cambia mas seguido
        self.intervalo = random.uniform(INTERVALO_MIN, INTERVALO_MAX) * factor
        self.tiempo_aviso = self.intervalo

    def dibujar_mundo(self, rng, zona_fija):
        abiertas = []
        alto_zocalo = 0.30
        grueso_zocalo = 0.085
        colores_zocalo = color.rgb32(79, 76, 54)
        color_remate = color.rgb32(126, 118, 77)
        for gz in range(LADO):
            for gx in range(LADO):
                wx, wz = self.a_mundo(gx, gz)
                if self.mapa[gz][gx]:
                    if not self.toca_hueco(gx, gz):
                        continue          # pared interior: no se dibuja ni colisiona
                    pos = (wx, ALTO_MURO / 2, wz)
                    esc = (CELDA, ALTO_MURO, CELDA)
                    # La geometria visible son paneles finos sobre las caras expuestas.
                    # La colision conserva el volumen de la celda para que no se atraviese.
                    Entity(parent=self.raiz, name="colision_pared", position=pos, scale=esc,
                           collider="box")
                    # Pared y zocalo solo en las caras que dan a un espacio transitable.
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, nz = gx + dx, gz + dz
                        if not (0 <= nx < LADO and 0 <= nz < LADO) or self.mapa[nz][nx]:
                            continue
                        if dx:
                            borde = wx + dx * CELDA / 2
                            pos_panel = (borde - dx * GROSOR_MURO / 2, ALTO_MURO / 2, wz)
                            esc_panel = (GROSOR_MURO, ALTO_MURO - alto_zocalo, CELDA + 0.02)
                            pos_panel = (pos_panel[0], alto_zocalo + (ALTO_MURO - alto_zocalo) / 2, wz)
                            x = borde - dx * grueso_zocalo / 2
                            pos_zocalo = (x, alto_zocalo / 2, wz)
                            esc_zocalo = (grueso_zocalo, alto_zocalo, CELDA + 0.02)
                            pos_remate = (borde - dx * 0.022, alto_zocalo - 0.025, wz)
                            esc_remate = (0.044, 0.05, CELDA + 0.02)
                        else:
                            borde = wz + dz * CELDA / 2
                            pos_panel = (wx, ALTO_MURO / 2, borde - dz * GROSOR_MURO / 2)
                            esc_panel = (CELDA + 0.02, ALTO_MURO - alto_zocalo, GROSOR_MURO)
                            pos_panel = (wx, alto_zocalo + (ALTO_MURO - alto_zocalo) / 2, pos_panel[2])
                            z = borde - dz * grueso_zocalo / 2
                            pos_zocalo = (wx, alto_zocalo / 2, z)
                            esc_zocalo = (CELDA + 0.02, alto_zocalo, grueso_zocalo)
                            pos_remate = (wx, alto_zocalo - 0.025, borde - dz * 0.022)
                            esc_remate = (CELDA + 0.02, 0.05, 0.044)
                        Entity(parent=self.grupo_muros, model="cube", position=pos_panel,
                               scale=esc_panel, color=color.white)
                        Entity(parent=self.grupo_zocalos, model="cube", position=pos_zocalo,
                               scale=esc_zocalo, color=colores_zocalo)
                        Entity(parent=self.grupo_remates, model="cube", position=pos_remate,
                               scale=esc_remate, color=color_remate)
                else:
                    abiertas.append((gx, gz))
                    if rng.random() < 0.09:
                        Mancha(parent=self.raiz,
                               position=(wx + rng.uniform(-1.7, 1.7), 0.012,
                                         wz + rng.uniform(-1.7, 1.7)),
                               scale=(rng.uniform(0.22, 0.65), 0.012, rng.uniform(0.25, 0.8)),
                               color=color.rgb32(rng.randint(61, 74), rng.randint(57, 69), rng.randint(37, 49)))

        # TODAS las paredes en UNA sola malla: de ~1000 llamadas de dibujo a 1.
        self.grupo_muros.combine()
        self.grupo_muros.texture = TEXTURA_PAPEL
        self.grupo_muros.texture_scale = (2, 1.5)
        # Se combinan por separado para conservar el rendimiento del escenario.
        self.grupo_zocalos.combine()
        self.grupo_remates.combine()

        # Columnas: nunca dentro ni pegadas a la zona fija (el jugador podria quedar atrapado).
        ruta = set(self.camino)

        def lejos_de_zona(gx, gz):
            if zona_fija is None:
                return True
            return max(abs(gx - zona_fija[0]), abs(gz - zona_fija[1])) > RADIO_FIJO + 1

        candidatas = [(gx, gz) for gx, gz in abiertas
                      if (gx, gz) not in ruta and 2 <= gx < LADO - 2 and 2 <= gz < LADO - 2
                      and lejos_de_zona(gx, gz)
                      and all(not self.mapa[gz + dz][gx + dx]
                              for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        rng.shuffle(candidatas)
        for gx, gz in candidatas[:min(9, len(candidatas))]:
            wx, wz = self.a_mundo(gx, gz)
            Entity(parent=self.raiz, model="cube", name="columna",
                   position=(wx, ALTO_MURO / 2, wz), scale=(0.82, ALTO_MURO, 0.82),
                   texture=TEXTURA_PAPEL, texture_scale=(1, 1.5),
                   color=color.white, collider="box")

        # La mayoria de los focos acompañan los pasillos principales; unos pocos
        # aparecen en salas laterales para crear zonas aisladas de luz.
        lugares_luz = set()
        for indice in range(2, len(self.camino), 4):
            if rng.random() < 0.82:
                lugares_luz.add(self.camino[indice])
        for celda in abiertas:
            if rng.random() < 0.035:
                lugares_luz.add(celda)
        lugares_luz = list(lugares_luz)
        rng.shuffle(lugares_luz)
        for paneles, (gx, gz) in enumerate(lugares_luz[:12]):
            wx, wz = self.a_mundo(gx, gz)
            f = Fixture(parent=self.raiz, position=(wx, ALTO_MURO - 0.12, wz), semilla=rng.random())
            self.fixtures.append(f)
            # Algunos cables cruzan el plafon y cuelgan un poco sobre el pasillo.
            if paneles % 4 == 1:
                largo = rng.uniform(2.4, 4.0)
                yaw = rng.choice((0, 90, 180, 270))
                Entity(parent=self.raiz, model="cube", name="cable_techo",
                       position=(wx, ALTO_MURO - 0.25, wz), rotation_y=yaw,
                       scale=(0.045, 0.045, largo), color=color.rgb32(30, 27, 21), collider=None)
                Entity(parent=self.raiz, model="cube", name="cable_colgante",
                       position=(wx + rng.uniform(-0.35, 0.35), ALTO_MURO - 0.62, wz),
                       scale=(0.035, 0.72, 0.035), color=color.rgb32(23, 21, 18), collider=None)

    def dibujar_flechas(self, rng):
        """Flechas simples hechas con geometria, sin archivos ni texturas externas."""
        if len(self.camino) < 2:
            return
        p_mentira = max(0.0, min(0.5, (70.0 - E.cordura) / 100.0 + 0.02 * E.cambios))
        ocupadas = set()
        for i in range(0, len(self.camino) - 1, 2):
            x, z = self.camino[i]
            nx, nz = self.camino[i + 1]
            dx, dz = nx - x, nz - z
            laterales = [(-dz, dx), (dz, -dx)]
            rng.shuffle(laterales)
            elegido = None
            for sx, sz in laterales:
                wxi, wzi = x + sx, z + sz
                if (0 <= wxi < LADO and 0 <= wzi < LADO and self.mapa[wzi][wxi]
                        and (wxi, wzi) not in ocupadas):
                    elegido = (wxi, wzi, sx, sz)
                    break
            if elegido is None:
                continue
            wxi, wzi, sx, sz = elegido
            ocupadas.add((wxi, wzi))
            normal_x, normal_z = -sx, -sz
            if (normal_x, normal_z) == (0, 1):
                yaw = 0
            elif (normal_x, normal_z) == (0, -1):
                yaw = 180
            elif (normal_x, normal_z) == (1, 0):
                yaw = 90
            else:
                yaw = -90
            world_x, world_z = self.a_mundo(wxi, wzi)
            sign = Entity(parent=self.raiz, name="flecha_pintada",
                          position=(world_x + normal_x * (CELDA / 2 + 0.002), 1.9,
                                    world_z + normal_z * (CELDA / 2 + 0.002)),
                          rotation_y=yaw, texture=None, collider=None)
            dot = dx * math.cos(math.radians(yaw)) - dz * math.sin(math.radians(yaw))
            invertir = (dot < 0) != (rng.random() < p_mentira)
            marca = Entity(parent=sign, rotation_z=180 if invertir else 0)
            tinta = color.rgb32(34, 31, 22)

            def trazo(a, b, ancho):
                x0, y0 = a
                x1, y1 = b
                largo = math.hypot(x1 - x0, y1 - y0)
                angulo = math.degrees(math.atan2(y1 - y0, x1 - x0))
                Entity(parent=marca, model="cube",
                       position=((x0 + x1) / 2, (y0 + y1) / 2, 0.012),
                       rotation_z=angulo, scale=(largo, ancho, 0.012),
                       color=tinta, texture=None, collider=None, unlit=True)

            # Asta recta y punta abierta: se lee como flecha incluso a distancia.
            trazo((-0.82, 0), (0.78, 0), 0.095)
            trazo((0.18, 0.40), (0.86, 0), 0.105)
            trazo((0.18, -0.40), (0.86, 0), 0.105)

    def dibujar_salida(self):
        gx, gz = LADO - 2, LADO - 1
        wx, wz = self.a_mundo(gx, gz)
        marco = color.rgb32(133, 127, 83)
        Entity(parent=self.raiz, model="cube", name="marco_salida",
               position=(wx - 1.72, 1.7, wz), scale=(0.22, 3.4, 0.28), color=marco)
        Entity(parent=self.raiz, model="cube", name="marco_salida",
               position=(wx + 1.72, 1.7, wz), scale=(0.22, 3.4, 0.28), color=marco)
        Entity(parent=self.raiz, model="cube", name="dintel_salida",
               position=(wx, 3.32, wz), scale=(3.65, 0.22, 0.28), color=marco)
        Entity(parent=self.raiz, model="quad", position=(wx, 1.65, wz - 0.015),
               rotation_y=180, scale=(3.15, 3.25), color=color.rgb32(30, 32, 25), unlit=True)
        Text(parent=self.raiz, text="SALIDA", position=(wx, 3.52, wz - 0.18),
             rotation_y=180, scale=3, color=color.rgb32(184, 177, 121),
             billboard=False, origin=(0, 0))

    def posicion_salida(self):
        return self.a_mundo(LADO - 2, LADO - 1)

    def dibujar_salida_imitada(self, rng):
        """Una salida convincente pintada sobre una pared solida: la habitacion copia."""
        if len(self.camino) < 8:
            return
        candidatos = []
        inicio = max(2, len(self.camino) // 4)
        fin = max(inicio + 1, (len(self.camino) * 3) // 4)
        for indice in range(inicio, min(fin, len(self.camino))):
            x, z = self.camino[indice]
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                px, pz = x + dx, z + dz
                if 1 <= px < LADO - 1 and 1 <= pz < LADO - 1 and self.mapa[pz][px]:
                    candidatos.append((px, pz, -dx, -dz))
        if not candidatos:
            return

        gx, gz, normal_x, normal_z = rng.choice(candidatos)
        wx, wz = self.a_mundo(gx, gz)
        if normal_z == 1:
            yaw = 0
        elif normal_z == -1:
            yaw = 180
        elif normal_x == 1:
            yaw = 90
        else:
            yaw = -90
        self.puerta_imitada = Entity(
            parent=self.raiz, name="salida_imitada",
            position=(wx + normal_x * (CELDA / 2 + 0.055), 0,
                      wz + normal_z * (CELDA / 2 + 0.055)),
            rotation_y=yaw)
        self.puerta_imitada.enabled = True
        self.puerta_imitada_revelada = False
        self.tiempo_mirando_puerta = 0.0

        marco = color.rgb32(133, 127, 83)
        Entity(parent=self.puerta_imitada, model="cube", position=(-1.48, 1.62, 0),
               scale=(0.18, 3.24, 0.12), color=marco)
        Entity(parent=self.puerta_imitada, model="cube", position=(1.48, 1.62, 0),
               scale=(0.18, 3.24, 0.12), color=marco)
        Entity(parent=self.puerta_imitada, model="cube", position=(0, 3.22, 0),
               scale=(3.12, 0.16, 0.12), color=marco)
        Entity(parent=self.puerta_imitada, model="quad", position=(0, 1.62, 0.015),
               scale=(2.75, 3.05), color=color.rgb32(31, 30, 23), unlit=True)
        Text(parent=self.puerta_imitada, text="SALIDA", position=(0, 3.42, 0.025),
             scale=2.55, color=color.rgb32(184, 177, 121), origin=(0, 0))

    def observar_imitacion(self, jugador, dt):
        """Revela la copia si el jugador se detiene a examinarla."""
        if not self.puerta_imitada or self.puerta_imitada_revelada:
            return False
        dx = self.puerta_imitada.x - jugador.x
        dz = self.puerta_imitada.z - jugador.z
        distancia = math.hypot(dx, dz)
        if distancia > 5.0 or distancia < 0.01:
            self.tiempo_mirando_puerta = 0.0
            return False
        direccion = Vec3(dx / distancia, 0, dz / distancia)
        mirada = Vec3(jugador.forward.x, 0, jugador.forward.z).normalized()
        if mirada.dot(direccion) > 0.72:
            self.tiempo_mirando_puerta += dt
            if self.tiempo_mirando_puerta >= 2.2:
                self.puerta_imitada.enabled = False
                self.puerta_imitada_revelada = True
                return True
        else:
            self.tiempo_mirando_puerta = max(0.0, self.tiempo_mirando_puerta - dt * 1.8)
        return False

    def actualizar(self, dt, jugador):
        """Cuenta atras INTERNA (el jugador no la ve). True cuando el mapa cambia."""
        self.reloj += dt
        self.tiempo_aviso = max(0.0, self.intervalo - self.reloj)
        if self.reloj >= self.intervalo:
            self.reconstruir(jugador)
            return True
        return False


# ----------------------------------------------------------------------------
# ALUCINACIONES
# ----------------------------------------------------------------------------
class Silueta(Entity):
    """Figura oscura en el borde de la vision. Desaparece si la miras; si no, se acerca."""
    def __init__(self):
        super().__init__(enabled=False)
        negro = color.rgb32(3, 3, 3)
        Entity(parent=self, model="cube", position=(0, 0.40, 0), scale=(0.34, 0.80, 0.22), color=negro, unlit=True)
        Entity(parent=self, model="cube", position=(0, 1.20, 0), scale=(0.52, 0.80, 0.26), color=negro, unlit=True)
        Entity(parent=self, model="sphere", position=(0, 1.78, 0), scale=0.33, color=negro, unlit=True)
        # Durante el susto aparecen dos reflejos apagados en una cara que antes no tenia rasgos.
        self.ojos = [
            Entity(parent=self, model="sphere", position=(-0.085, 1.82, 0.145),
                   scale=0.055, color=color.rgb32(205, 193, 122), unlit=True, enabled=False),
            Entity(parent=self, model="sphere", position=(0.085, 1.82, 0.145),
                   scale=0.055, color=color.rgb32(205, 193, 122), unlit=True, enabled=False),
        ]
        # Brazos demasiado largos: lo justo para que algo no cuadre.
        for lado in (-1, 1):
            Entity(parent=self, model="cube", position=(0.34 * lado, 0.85, 0),
                   scale=(0.07, 1.25, 0.07), color=negro, unlit=True)
        self.vida = 0.0
        self.mirada = 0.0

    def intentar_aparecer(self):
        # Busca una celda visible y coloca la figura pegada al borde de una pared,
        # como si se hubiera asomado desde una esquina para observar al jugador.
        for _ in range(36):
            lado = random.choice((-1, 1))
            yaw = jugador.rotation_y + lado * random.uniform(32, 122)
            distancia = random.uniform(7.5, 13.5)
            tx = jugador.x + math.sin(math.radians(yaw)) * distancia
            tz = jugador.z + math.cos(math.radians(yaw)) * distancia
            if not laberinto.libre(tx, tz):
                continue
            if not laberinto.linea_libre(jugador.x, jugador.z, tx, tz):
                continue

            gx, gz = laberinto.celda_de(tx, tz)
            paredes_vecinas = [(dx, dz) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                               if 0 <= gx + dx < LADO and 0 <= gz + dz < LADO
                               and laberinto.mapa[gz + dz][gx + dx]]
            if not paredes_vecinas:
                continue

            dx, dz = random.choice(paredes_vecinas)
            centro_x, centro_z = laberinto.a_mundo(gx, gz)
            margen = random.uniform(0.32, 0.58)
            px = centro_x + dx * (CELDA / 2 - margen)
            pz = centro_z + dz * (CELDA / 2 - margen)
            if math.hypot(px - jugador.x, pz - jugador.z) < 6.5:
                continue
            if not laberinto.linea_libre(jugador.x, jugador.z, px, pz):
                continue

            self.position = (px, 0, pz)
            self.rotation_y = math.degrees(math.atan2(jugador.x - px, jugador.z - pz))
            self.vida = random.uniform(6.5, 9.5)
            self.mirada = 0.0
            self.enabled = True
            return True
        return False

    def ocultar(self):
        self.enabled = False
        self.scale = Vec3(1, 1, 1)
        for ojo in self.ojos:
            ojo.enabled = False

    def actualizar(self, dt):
        if not self.enabled or E.susto_activo:
            return
        self.vida -= dt
        dx, dz = jugador.x - self.x, jugador.z - self.z
        dist = math.hypot(dx, dz)
        if dist < 6.0 or self.vida <= 0:
            self.enabled = False
            return
        rel = (math.degrees(math.atan2(-dx, -dz)) - jugador.rotation_y + 180) % 360 - 180
        if abs(rel) < 22:
            self.mirada += dt
            if self.mirada > 0.4:                 # la miraste: desaparece y te cuesta cordura
                self.enabled = False
                E.cordura = max(0.0, E.cordura - 5.0)
                E.glitch = max(E.glitch, 1.2)
        else:
            self.mirada = max(0.0, self.mirada - dt)
            # Si no la miras, avanza despacio hacia ti.
            self.x += dx / dist * 0.5 * dt
            self.z += dz / dist * 0.5 * dt


class Consumible(Entity):
    """Botella/can construida con primitivas; no requiere archivos de textura."""
    def __init__(self, tipo, posicion):
        super().__init__(position=posicion, texture=None, collider=None)
        self.tipo = tipo
        self.altura_base = 0.05
        if tipo == "agua":
            tono = color.rgb32(112, 157, 151)
            Entity(parent=self, model="sphere", position=(0, 0.43, 0),
                   scale=(0.30, 0.72, 0.30), color=tono, texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.84, 0),
                   scale=(0.15, 0.20, 0.15), color=color.rgb32(157, 177, 152),
                   texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.45, 0),
                   scale=(0.31, 0.18, 0.31), color=color.rgb32(206, 198, 164),
                   texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.96, 0),
                   scale=(0.19, 0.09, 0.19), color=color.rgb32(183, 174, 133),
                   texture=None, unlit=True)
        else:
            tono = color.rgb32(132, 54, 43)
            Entity(parent=self, model="cube", position=(0, 0.37, 0),
                   scale=(0.34, 0.68, 0.34), color=tono, texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.72, 0),
                   scale=(0.31, 0.045, 0.31), color=color.rgb32(166, 158, 133),
                   texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.75, 0),
                   scale=(0.12, 0.025, 0.12), color=color.rgb32(80, 76, 64),
                   texture=None, unlit=True)
            Entity(parent=self, model="cube", position=(0, 0.39, 0),
                   scale=(0.35, 0.16, 0.35), color=color.rgb32(195, 166, 91),
                   texture=None, unlit=True)
        self.fase = random.uniform(0, math.tau)
        self.t = 0.0

    def update(self):
        self.t += time.dt
        self.rotation_y += 38 * time.dt
        self.y = self.altura_base + math.sin(self.t * 2.4 + self.fase) * 0.10


class EntidadCiega(Entity):
    """Silueta sobrenatural que escucha, investiga y solo persigue con certeza suficiente.

    Estados: acecho -> investigacion -> busqueda -> persecucion. No consulta la
    posicion del jugador para elegir destino salvo durante una persecucion confirmada.
    """
    def __init__(self):
        super().__init__(enabled=False, collider=None)
        self.color_sombra = color.rgb32(1, 2, 2)
        # Silueta irregular, casi fundida con la niebla. Sin ojos ni rasgos faciales.
        Entity(parent=self, model="cube", position=(0, 1.15, 0),
               scale=(0.24, 1.42, 0.18), color=self.color_sombra, unlit=True)
        Entity(parent=self, model="sphere", position=(0.02, 2.02, 0.01),
               scale=(0.22, 0.38, 0.20), color=self.color_sombra, unlit=True)
        for side in (-1, 1):
            Entity(parent=self, model="cube", position=(side * 0.20, 1.05, 0.01),
                   rotation_z=side * -13, scale=(0.075, 1.30, 0.075),
                   color=self.color_sombra, unlit=True)
        self.activa = False
        self.estado = "acecho"
        self.ruta = []
        self.indice_ruta = 0
        self.t_ruta = 0.0
        self.t_estado = 0.0
        self.t_pasos = 0.0
        self.confianza = 0.0
        self.objetivo = None
        self.ultima_posicion = None
        self.velocidad = 2.35
        self.t_perdida = 0.0
        self.distancia_previa = 999.0

    def activar(self):
        """Aparece lejos, solo en una zona transitable conectada."""
        origen = laberinto.celda_de(jugador.x, jugador.z)
        candidatos = []
        for gz in range(1, LADO - 1):
            for gx in range(1, LADO - 1):
                if laberinto.mapa[gz][gx]:
                    continue
                wx, wz = laberinto.a_mundo(gx, gz)
                distancia = math.hypot(wx - jugador.x, wz - jugador.z)
                if distancia >= 24:
                    candidatos.append((distancia, gx, gz))
        random.shuffle(candidatos)
        for distancia, gx, gz in sorted(candidatos, reverse=True)[:24]:
            ruta = laberinto.camino_corto(origen, (gx, gz))
            if len(ruta) >= 5:
                wx, wz = laberinto.a_mundo(gx, gz)
                self.position = (wx, 0.02, wz)
                self.activa = True
                self.enabled = True
                self.estado = "acecho"
                self.confianza = 0.0
                self.ruta = []
                self.objetivo = None
                self.t_estado = random.uniform(4.0, 8.0)
                self.t_pasos = random.uniform(1.0, 2.5)
                self.t_perdida = 0.0
                return True
        return False

    def recibir_ruido(self, x, z, intensidad):
        if not self.activa or E.fase != "juego":
            return
        distancia = math.hypot(self.x - x, self.z - z)
        # La cordura baja aumenta el alcance, pero los muros amortiguan el sonido.
        locura = 1.0 - E.cordura / 100.0
        alcance = (7.0 + locura * 15.0) * max(0.35, intensidad)
        if distancia > alcance:
            return
        if not laberinto.linea_libre(self.x, self.z, x, z):
            alcance *= 0.62
            if distancia > alcance:
                return
        calidad = max(0.0, 1.0 - distancia / max(alcance, 0.1))
        self.confianza = min(1.0, self.confianza + intensidad * (0.20 + calidad * 0.48)
                             * (0.75 + locura * 0.8))
        # Solo guarda la fuente del ruido, no la posicion actual del jugador.
        self.ultima_posicion = (x, z)
        self.objetivo = (x, z)
        if self.estado not in ("persecucion", "busqueda"):
            self.estado = "investigacion"
            self.t_estado = 5.5 + self.confianza * 4.0
            self.t_ruta = 0.0

    def actualizar(self, dt, corriendo):
        if not self.activa:
            return False
        if not laberinto.libre(self.x, self.z):
            self.activa = False
            self.enabled = False
            return False

        locura = 1.0 - E.cordura / 100.0
        # A cordura baja se vuelve sensible a ruidos leves y mantiene mas tiempo la pista.
        if self.estado == "acecho":
            self.confianza = max(0.0, self.confianza - dt * 0.035)
            self.t_estado -= dt
            self.t_pasos -= dt
            if self.t_pasos <= 0:
                # Microdesplazamiento ocasional: parece cambiar de lugar sin ser visto.
                if random.random() < 0.45 + locura * 0.35:
                    self.rotation_y += random.choice((-35, 35, 70, -70))
                self.t_pasos = random.uniform(2.2, 5.0) * (1.0 - locura * 0.25)
            if self.confianza >= 0.72:
                self.estado = "busqueda"
                self.t_estado = 4.5
            elif self.t_estado <= 0:
                self.t_estado = random.uniform(3.0, 7.0)

        elif self.estado == "investigacion":
            self.t_estado -= dt
            if self.confianza >= (0.86 - locura * 0.17):
                self.estado = "persecucion"
                self.t_perdida = 0.0
                self.objetivo = (jugador.x, jugador.z)  # confirma al jugador solo en este umbral
                self.t_ruta = 0.0
            elif self.t_estado <= 0:
                self.estado = "busqueda"
                self.t_estado = 5.0 + locura * 3.0

        elif self.estado == "busqueda":
            self.t_estado -= dt
            self.confianza = max(0.0, self.confianza - dt * (0.07 - locura * 0.025))
            if self.confianza >= (0.88 - locura * 0.18):
                self.estado = "persecucion"
                self.t_perdida = 0.0
                self.objetivo = (jugador.x, jugador.z)
                self.t_ruta = 0.0
            elif self.t_estado <= 0 or self.confianza < 0.12:
                self.estado = "acecho"
                self.objetivo = None
                self.t_estado = random.uniform(4.0, 8.0)
                self.ruta = []

        elif self.estado == "persecucion":
            self.t_perdida += dt
            # La persecucion no es omnisciente: si no hay nuevos ruidos, va al ultimo punto
            # conocido y pierde confianza con el tiempo.
            if self.ultima_posicion:
                self.objetivo = self.ultima_posicion
            self.confianza = max(0.0, self.confianza - dt * (0.025 if locura > 0.65 else 0.055))
            if self.confianza < 0.28 and self.t_perdida > 3.0:
                self.estado = "busqueda"
                self.t_estado = 5.0
                self.objetivo = self.ultima_posicion
                self.ruta = []

        # Recalcula la ruta con poca frecuencia para evitar coste innecesario.
        self.t_ruta -= dt
        if self.t_ruta <= 0:
            if self.estado == "persecucion":
                meta = laberinto.celda_de(jugador.x, jugador.z)
                # La ruta apunta al ultimo lugar detectado; el jugador puede despistarla.
                if self.ultima_posicion and self.t_perdida > 0.65:
                    meta = laberinto.celda_de(*self.ultima_posicion)
            elif self.objetivo:
                meta = laberinto.celda_de(*self.objetivo)
            else:
                meta = None
            inicio = laberinto.celda_de(self.x, self.z)
            self.ruta = laberinto.camino_corto(inicio, meta) if meta else []
            self.indice_ruta = 1 if len(self.ruta) > 1 else 0
            self.t_ruta = 0.65 if self.estado == "persecucion" else 1.0

        if self.ruta and self.estado in ("investigacion", "busqueda", "persecucion"):
            gx, gz = self.ruta[min(self.indice_ruta, len(self.ruta) - 1)]
            tx, tz = laberinto.a_mundo(gx, gz)
            dx, dz = tx - self.x, tz - self.z
            distancia = math.hypot(dx, dz)
            if distancia < 0.45 and self.indice_ruta < len(self.ruta) - 1:
                self.indice_ruta += 1
                gx, gz = self.ruta[self.indice_ruta]
                tx, tz = laberinto.a_mundo(gx, gz)
                dx, dz = tx - self.x, tz - self.z
                distancia = math.hypot(dx, dz)
            if distancia > 0.01:
                base = self.velocidad + locura * 0.65
                if self.estado == "persecucion":
                    base += 0.85
                paso = min(distancia, base * dt)
                self.x += dx / distancia * paso
                self.z += dz / distancia * paso
                self.rotation_y = math.degrees(math.atan2(dx, dz))

        # La forma se pierde en la niebla; a cordura baja se distingue un poco mas.
        self.y = 0.02 + math.sin(E.t * 2.2) * 0.035
        distancia_jugador = math.hypot(self.x - jugador.x, self.z - jugador.z)
        if self.estado == "persecucion" and distancia_jugador < 1.25:
            return True
        # No termina la partida por estar cerca durante el acecho: debe confirmar primero.
        return False


# ----------------------------------------------------------------------------
# JUGADOR Y CAMARA
# ----------------------------------------------------------------------------
laberinto = Laberinto()
inicio_x, inicio_z = laberinto.a_mundo(1, 1)
jugador = FirstPersonController(position=(inicio_x, 0, inicio_z),
                                height=1.65, speed=0, gravity=0, jump_height=0.65)
jugador.cursor.enabled = False
jugador.grounded = False
jugador.camera_pivot.y = 0.34
jugador.camera_pivot.rotation_x = 68
jugador.camera_pivot.rotation_z = -4
jugador.mouse_sensitivity = Vec2(0, 0)
mouse.locked = False
mouse.visible = False

# El pasillo inicial siempre avanza hacia +X.
rumbo_inicial = 90.0
jugador.rotation_y = rumbo_inicial - 5
intro_activo = True
intro_reloj = 0.0
INTRO_DURACION = 5.7

silueta = Silueta()
entidad_ciega = EntidadCiega()
consumibles = []


def iniciar_susto():
    """Hace que la camara encuentre la silueta y esta irrumpa en primer plano."""
    if (not silueta.enabled or E.susto_activo or E.susto_enfriamiento > 0
            or E.fase != "juego" or intro_activo):
        return
    dx, dz = silueta.x - jugador.x, silueta.z - jugador.z
    distancia = max(0.1, math.hypot(dx, dz))
    E.susto_activo = True
    E.susto_t = 0.0
    E.susto_enfriamiento = 22.0
    E.susto_yaw_inicio = jugador.rotation_y
    E.susto_pitch_inicio = jugador.camera_pivot.rotation_x
    E.susto_yaw = math.degrees(math.atan2(dx, dz))
    E.susto_pitch = max(-18.0, min(18.0,
        math.degrees(math.atan2(jugador.camera_pivot.y - 1.78, distancia))))
    jugador.mouse_sensitivity = Vec2(0, 0)
    jugador.speed = 0
    jugador.gravity = 0
    jugador.jump_height = 0
    E.glitch = max(E.glitch, 0.75)


def actualizar_susto(dt):
    """Giro corto, irrupcion de la figura y recuperacion del control."""
    if E.susto_enfriamiento > 0 and not E.susto_activo:
        E.susto_enfriamiento = max(0.0, E.susto_enfriamiento - dt)
    if not E.susto_activo:
        return

    E.susto_t += dt
    # Primero la mirada se clava en el sitio donde se vio la figura.
    p = max(0.0, min(1.0, E.susto_t / 0.24))
    p = p * p * (3.0 - 2.0 * p)
    diferencia_yaw = (E.susto_yaw - E.susto_yaw_inicio + 180) % 360 - 180
    jugador.rotation_y = E.susto_yaw_inicio + diferencia_yaw * p
    jugador.camera_pivot.rotation_x = E.susto_pitch_inicio + (E.susto_pitch - E.susto_pitch_inicio) * p

    # Cuando el jugador ya mira, la silueta se acerca de golpe, como un fotograma imposible.
    if E.susto_t >= 0.30:
        factor = min(1.0, (E.susto_t - 0.30) / 0.16)
        distancia = 2.0 - factor * 0.62
        frente = camera.world_position + camera.forward * distancia
        silueta.position = (frente.x, jugador.y, frente.z)
        silueta.rotation_y = jugador.rotation_y + 180
        silueta.scale = (1.8 + factor * 0.5, 1.0 + factor * 0.12, 1.25)
        silueta.enabled = True
        for ojo in silueta.ojos:
            ojo.enabled = True
        if E.susto_t < 0.62:
            E.glitch = max(E.glitch, 0.9)

    if E.susto_t >= 1.05:
        silueta.ocultar()
        E.cordura = max(0.0, E.cordura - 16.0)
        E.glitch = max(E.glitch, 1.8)
        E.susto_activo = False
        E.susto_t = 0.0
        jugador.mouse_sensitivity = Vec2(40, 40)
        jugador.speed = VELOCIDAD_CAMINAR
        jugador.gravity = 1
        jugador.jump_height = 0.65
        # Un instante de desorientacion tras el susto, no una inmovilizacion larga.
        mostrar_alerta("NO DEBISTE MIRAR", 1.0)


def suave(valor):
    valor = max(0.0, min(1.0, valor))
    return valor * valor * (3 - 2 * valor)


def actualizar_intro(dt):
    """Despierta en el suelo, se incorpora y examina lentamente el lugar."""
    global intro_activo, intro_reloj
    if not intro_activo:
        return
    intro_reloj += dt
    t = intro_reloj
    if t < 1.7:
        p = suave(t / 1.7)
        jugador.camera_pivot.y = 0.34 + 1.31 * p
        jugador.camera_pivot.rotation_x = 68 - 48 * p
        jugador.camera_pivot.rotation_z = -4 * (1 - p)
        jugador.rotation_y = rumbo_inicial - 5 + 5 * p
    elif t < 2.9:
        p = suave((t - 1.7) / 1.2)
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation_x = 20 - 7 * p
        jugador.rotation_y = rumbo_inicial - 48 * p
    elif t < 4.25:
        p = suave((t - 2.9) / 1.35)
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation_x = 13 + 2 * math.sin(p * math.pi)
        jugador.rotation_y = rumbo_inicial - 48 + 96 * p
    elif t < INTRO_DURACION:
        p = suave((t - 4.25) / (INTRO_DURACION - 4.25))
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation_x = 13 * (1 - p)
        jugador.camera_pivot.rotation_z = 0.4 * (1 - p)
        jugador.rotation_y = rumbo_inicial + 48 * (1 - p)
    else:
        intro_activo = False
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation = Vec3.zero
        jugador.rotation_y = rumbo_inicial
        jugador.speed = VELOCIDAD_CAMINAR
        jugador.gravity = 1
        jugador.grounded = True
        jugador.air_time = 0
        jugador.mouse_sensitivity = Vec2(40, 40)
        mouse.locked = True
        mouse.visible = False


linterna = SpotLight(parent=camera, position=(0, 0, 0), rotation=(0, 0, 0),
                     color=color.rgb32(245, 243, 210))
linterna._light.getLens().setFov(42)
linterna._light.getLens().setNearFar(0.12, 27)
linterna._light.setExponent(24)
COLOR_LINTERNA = color.rgb32(245, 243, 210)
COLOR_APAGADA = color.rgb32(0, 0, 0)

# ----------------------------------------------------------------------------
# SHADER DE CAMARA (estilo videocamara analogica / Outlast)
# ----------------------------------------------------------------------------
if USAR_SHADER:
    shader_camara = Shader(fragment='''
#version 140
uniform sampler2D tex;
uniform float tiempo;
uniform float glitch;
uniform float locura;
in vec2 uv;
out vec4 color;
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    vec2 d = uv - 0.5;
    vec2 u = uv + d * dot(d, d) * (0.08 + locura * 0.10);
    // Aberracion reducida: conserva el aspecto VHS sin desdoblar paredes enteras.
    float ab = 0.00065 + glitch * 0.0042 + locura * 0.0012;
    vec3 c = vec3(texture(tex, u + vec2(ab, 0.0)).r,
                  texture(tex, u).g,
                  texture(tex, u - vec2(ab, 0.0)).b);
    c += (hash(uv * 800.0 + tiempo) - 0.5) * (0.025 + glitch * 0.12 + locura * 0.025);
    c *= 0.98 + 0.02 * sin(uv.y * 700.0);
    float g = dot(c, vec3(0.3, 0.59, 0.11));
    c = mix(c, vec3(g), locura * 0.45);
    // Tinte global sutil amarillo-verde, como fluorescentes envejecidos.
    c *= vec3(1.025, 1.035, 0.95);
    float v = smoothstep(0.30 - locura * 0.12, 0.85 - locura * 0.15, length(d) * 1.2);
    c *= 1.0 - v;
    color = vec4(c, 1.0);
}
''')
    camera.shader = shader_camara
    camera.set_shader_input("tiempo", 0.0)
    camera.set_shader_input("glitch", 0.0)
    camera.set_shader_input("locura", 0.0)

# ----------------------------------------------------------------------------
# HUD
# ----------------------------------------------------------------------------
hud = Text(parent=camera.ui, text="", position=(-0.84, 0.38), scale=0.72,
           color=color.rgb32(191, 185, 157), background=True)
cord_texto = Text(parent=camera.ui, text="CORDURA", position=(-0.84, 0.345), scale=0.6,
                  color=color.rgb32(171, 176, 154))
cord_fondo = Entity(parent=camera.ui, model="quad", origin=(-0.5, 0), position=(-0.84, 0.318, -0.8),
                    scale=(0.25, 0.012), color=color.rgba32(0, 0, 0, 140), unlit=True)
cord_barra = Entity(parent=camera.ui, model="quad", origin=(-0.5, 0), position=(-0.84, 0.318, -0.85),
                    scale=(0.25, 0.012), color=color.rgb32(170, 176, 150), unlit=True)
objetivo = Text(parent=camera.ui, text="SIGUE LAS FLECHAS PINTADAS", position=(0, 0.43),
                origin=(0, 0), scale=0.72, color=color.rgb32(182, 174, 135))
centro = Text(parent=camera.ui, text="·", position=(0, 0), origin=(0, 0), scale=1.2,
              color=color.rgba32(195, 190, 166, 150))
mensaje = Text(parent=camera.ui,
               text="WASD MOVER · SHIFT CORRER · ESPACIO SALTAR · F LINTERNA\n1 AGUA · 2 REFRESCO · RUEDA ZOOM",
               position=(-0.84, -0.46), origin=(-0.5, 0), scale=0.58,
               color=color.rgb32(146, 143, 128), background=True)
energia_texto = Text(parent=camera.ui, text="AIRE", position=(-0.84, 0.287), scale=0.54,
                     color=color.rgb32(160, 164, 137))
energia_fondo = Entity(parent=camera.ui, model="quad", origin=(-0.5, 0),
                       position=(-0.84, 0.262, -0.8), scale=(0.25, 0.009),
                       color=color.rgba32(0, 0, 0, 140), unlit=True)
energia_barra = Entity(parent=camera.ui, model="quad", origin=(-0.5, 0),
                       position=(-0.84, 0.262, -0.85), scale=(0.25, 0.009),
                       color=color.rgb32(153, 174, 120), unlit=True)
zoom_texto = Text(parent=camera.ui, text="", position=(0.84, 0.38), origin=(1, 0),
                  scale=0.58, color=color.rgb32(171, 176, 154), enabled=False)
inventario_texto = Text(parent=camera.ui, text="1 AGUA 0   ·   2 REFRESCO 0",
                        position=(0.84, 0.32), origin=(1, 0), scale=0.64,
                        color=color.rgb32(191, 185, 157), background=True)
amenaza_texto = Text(parent=camera.ui, text="", position=(0, 0.36), origin=(0, 0),
                      scale=0.76, color=color.rgb32(166, 133, 101), enabled=False)
alerta = Text(parent=camera.ui, text="", position=(0, 0.16, -0.7), origin=(0, 0), scale=1.45,
              color=color.rgb32(214, 196, 130), enabled=False)
fin_texto = Text(parent=camera.ui, text="", position=(0, 0.06, -0.7), origin=(0, 0), scale=1.8,
                 color=color.rgb32(214, 196, 130), enabled=False)
fin_sub = Text(parent=camera.ui, text="PULSA R PARA DESPERTAR DE NUEVO", position=(0, -0.06, -0.7),
               origin=(0, 0), scale=0.85, color=color.rgb32(150, 146, 125), enabled=False)

# Marco de videocamara analogica: REC, contador y esquinas de visor.
rec_dot = Entity(parent=camera.ui, model="circle", position=(0.70, 0.44, -0.85),
                 scale=0.012, color=color.rgb32(231, 49, 37), unlit=True)
rec_texto = Text(parent=camera.ui, text="REC", position=(0.73, 0.43), scale=0.78,
                 color=color.rgb32(231, 73, 58))
cam_texto = Text(parent=camera.ui, text="CAM-01   /   CINTA 01", position=(-0.84, 0.44),
                 scale=0.66, color=color.rgb32(171, 176, 154))
reloj_cinta = Text(parent=camera.ui, text="00:00:00", position=(0.84, -0.44),
                   origin=(1, 0), scale=0.7, color=color.rgb32(190, 191, 170))
for lado_x in (-0.86, 0.86):
    for lado_y in (-0.43, 0.43):
        sx = 1 if lado_x < 0 else -1
        sy = 1 if lado_y < 0 else -1
        Entity(parent=camera.ui, model="quad", position=(lado_x + sx * 0.028, lado_y, -0.8),
               scale=(0.056, 0.003), color=color.rgba32(205, 204, 183, 115), unlit=True)
        Entity(parent=camera.ui, model="quad", position=(lado_x, lado_y + sy * 0.028, -0.8),
               scale=(0.003, 0.056), color=color.rgba32(205, 204, 183, 115), unlit=True)
banda_cinta = Entity(parent=camera.ui, model="quad", position=(0, -0.45, -0.78),
                     scale=(1.72, 0.006), color=color.rgba32(196, 190, 158, 9), unlit=True)
Entity(parent=camera.ui, model="quad", position=(0, 0.485, -0.74),
       scale=(1.72, 0.025), color=color.rgba32(0, 0, 0, 28), unlit=True)
Entity(parent=camera.ui, model="quad", position=(0, -0.485, -0.74),
       scale=(1.72, 0.025), color=color.rgba32(0, 0, 0, 35), unlit=True)

# Velo negro para los apagones (esta DETRAS del REC, asi la camara "sigue grabando").
velo = Entity(parent=camera.ui, model="quad", scale=(2, 1), z=-0.6,
              color=color.rgba32(0, 0, 0, 0), unlit=True, enabled=False)

# ----------------------------------------------------------------------------
# SONIDO DE PASOS
# ----------------------------------------------------------------------------
paso_siguiente = 0
distancia_paso = 0.0


def reproducir_paso(volumen=0.34):
    """Alterna dos pisadas amortiguadas para simular caminar sobre moqueta."""
    global paso_siguiente
    if not pasos:
        return
    audio = pasos[paso_siguiente % len(pasos)]
    paso_siguiente += 1
    try:
        audio.volume = volumen
        audio.play()
    except Exception:
        pass


def crear_consumible():
    """Coloca agua o refresco en una sala libre y accesible."""
    if len(consumibles) >= 3:
        return False
    ocupadas = {laberinto.celda_de(obj.x, obj.z) for obj in consumibles}
    candidatas = []
    for gz in range(1, LADO - 1):
        for gx in range(1, LADO - 1):
            if laberinto.mapa[gz][gx] or (gx, gz) in ocupadas:
                continue
            wx, wz = laberinto.a_mundo(gx, gz)
            if math.hypot(wx - jugador.x, wz - jugador.z) < 7.0:
                continue
            if entidad_ciega.activa and math.hypot(wx - entidad_ciega.x, wz - entidad_ciega.z) < 5.0:
                continue
            candidatas.append((wx, wz))
    if not candidatas:
        return False
    wx, wz = random.choice(candidatas)
    consumibles.append(Consumible(random.choice(("agua", "refresco")), (wx, 0, wz)))
    return True


def recoger_consumibles():
    for objeto in tuple(consumibles):
        if math.hypot(jugador.x - objeto.x, jugador.z - objeto.z) < 1.25:
            if objeto.tipo == "agua":
                E.agua_inventario += 1
                mostrar_alerta("AGUA DE ALMENDRA · PULSA 1 PARA USAR", 2.2)
            else:
                E.refresco_inventario += 1
                mostrar_alerta("REFRESCO · PULSA 2 PARA USAR", 2.2)
            consumibles.remove(objeto)
            destroy(objeto)


def consumir_agua():
    if E.agua_inventario <= 0:
        mostrar_alerta("NO TIENES AGUA DE ALMENDRA", 1.5)
        return
    E.agua_inventario -= 1
    E.cordura = min(E.techo, E.cordura + CORDURA_AGUA_ALMENDRA)
    E.glitch = max(0.0, E.glitch - 0.7)
    E.t_silueta = max(E.t_silueta, 12.0)
    mostrar_alerta("EL ZUMBIDO SE ALEJA UN INSTANTE", 2.2)


def consumir_refresco():
    if E.refresco_inventario <= 0:
        mostrar_alerta("NO TIENES REFRESCO", 1.5)
        return
    E.refresco_inventario -= 1
    E.refresco_t = max(E.refresco_t, DURACION_REFRESCO)
    mostrar_alerta("REFRESCO · MAS RAPIDO Y RECUPERAS AIRE", 2.2)


def limpiar_consumibles():
    for objeto in consumibles:
        destroy(objeto)
    consumibles.clear()


# ----------------------------------------------------------------------------
# LOGICA DE JUEGO
# ----------------------------------------------------------------------------
def mostrar_alerta(texto, segundos):
    alerta.text = texto
    alerta.enabled = True
    E.alerta_t = segundos


def terminar(titulo):
    E.fase = "fin"
    E.fin_t = 0.0
    E.susto_activo = False
    E.susto_t = 0.0
    jugador.speed = 0
    jugador.mouse_sensitivity = Vec2(40, 40)
    jugador.gravity = 1
    jugador.jump_height = 0.65
    fin_texto.text = titulo
    alerta.enabled = False
    amenaza_texto.enabled = False
    silueta.ocultar()


def reiniciar():
    global zoom_fov
    E.cordura = 100.0
    E.techo = 100.0
    E.cambios = 0
    E.energia_sprint = ENERGIA_SPRINT_MAX
    E.t_corrida = 0.0
    E.t_consumible = 9.0
    E.agua_inventario = 0
    E.refresco_inventario = 0
    E.refresco_t = 0.0
    E.zoom_ui_t = 0.0
    E.fallo_linterna = 0.0
    E.susto_activo = False
    E.susto_t = 0.0
    E.susto_enfriamiento = 0.0
    E.fase = "juego"
    E.fundido = 1.5
    E.glitch = 0.0
    E.ecos = []
    E.desfase_reloj = 0.0
    E.t_silueta = random.uniform(20, 35)
    E.t_reloj = random.uniform(20, 35)
    E.t_mensaje = random.uniform(25, 40)
    limpiar_consumibles()
    entidad_ciega.activa = False
    entidad_ciega.enabled = False
    entidad_ciega.estado = "acecho"
    entidad_ciega.confianza = 0.0
    entidad_ciega.ruta = []
    entidad_ciega.objetivo = None
    entidad_ciega.ultima_posicion = None
    E.corrida_ruido_t = 0.0
    amenaza_texto.enabled = False
    laberinto.reconstruir(None)
    x, z = laberinto.a_mundo(1, 1)
    jugador.position = (x, 0.2, z)
    jugador.rotation_y = rumbo_inicial
    jugador.camera_pivot.rotation_x = 0
    jugador.mouse_sensitivity = Vec2(40, 40)
    jugador.gravity = 1
    jugador.jump_height = 0.65
    jugador.speed = VELOCIDAD_CAMINAR
    zoom_fov = FOV_NORMAL
    zoom_texto.enabled = False
    fin_texto.enabled = False
    fin_sub.enabled = False
    silueta.ocultar()


def input(key):
    global zoom_fov
    if E.susto_activo and key != "escape":
        return
    if key == "1" and E.fase == "juego" and not intro_activo:
        consumir_agua()
    elif key == "2" and E.fase == "juego" and not intro_activo:
        consumir_refresco()
    elif key == "f" and E.fase == "juego":
        E.linterna = not E.linterna
    elif key in ("scroll up", "scroll down") and E.fase == "juego" and not intro_activo:
        cambio_zoom = -PASO_ZOOM if key == "scroll up" else PASO_ZOOM
        zoom_fov = max(FOV_ZOOM_MIN, min(FOV_ZOOM_MAX, zoom_fov + cambio_zoom))
        zoom_texto.text = f"ZOOM {int(FOV_NORMAL * 100 / zoom_fov)}%  ·  V RESTABLECER"
        zoom_texto.enabled = True
        E.zoom_ui_t = 2.0
    elif key == "v" and E.fase == "juego":
        zoom_fov = FOV_NORMAL
        zoom_texto.text = "ZOOM 100%"
        zoom_texto.enabled = True
        E.zoom_ui_t = 1.2
    elif key == "r" and E.fase == "fin" and E.fin_t > 2.0:
        reiniciar()
    elif key == "escape":
        application.quit()


def actualizar_cordura(dt):
    en_luz = laberinto.hay_luz_cerca(jugador.x, jugador.z, RADIO_LUZ)
    delta = CORDURA_BASE
    if en_luz:
        delta += CORDURA_LUZ
    else:
        delta += CORDURA_OSCURO
        if not E.linterna:
            delta += CORDURA_SIN_LINTERNA
    if delta > 0:
        E.cordura = max(E.cordura, min(E.techo, E.cordura + delta * dt))
    else:
        E.cordura = max(0.0, E.cordura + delta * dt)


def actualizar_alucinaciones(dt, moviendo, corriendo=False):
    c = E.cordura

    # La cinta pierde estabilidad cada vez mas a menudo cuando baja la cordura.
    if c < 65 and random.random() < dt * (0.06 + (65 - c) * 0.012):
        E.glitch = max(E.glitch, random.uniform(0.18, 0.46))

    # 1) Siluetas que se asoman junto a esquinas (menos de 82).
    if c < 82:
        E.t_silueta -= dt * (1.45 if corriendo else 1.0)
        if not silueta.enabled and E.t_silueta <= 0:
            if silueta.intentar_aparecer():
                if c < 55:
                    iniciar_susto()
                E.t_silueta = random.uniform(10, 22) * (0.35 + 0.65 * c / 100.0)
            else:
                E.t_silueta = 1.0         # no habia hueco libre: reintenta pronto
    silueta.actualizar(dt)

    # 2) Pasos fantasma (menos de 75): un eco desfasado, y pasos que siguen cuando te detienes.
    for i in range(len(E.ecos) - 1, -1, -1):
        E.ecos[i] -= dt
        if E.ecos[i] <= 0:
            E.ecos.pop(i)
            reproducir_paso(0.14)
    if E.mov_antes and not moviendo and c < 72:
        E.ecos.extend([0.7 * (k + 1) for k in range(random.randint(2, 4))])
    E.mov_antes = moviendo

    # 3) El reloj de la cinta salta hacia atras (menos de 55).
    if c < 50:
        E.t_reloj -= dt
        if E.t_reloj <= 0:
            E.desfase_reloj = max(-E.t + 1.0, E.desfase_reloj - random.uniform(20, 160))
            E.t_reloj = random.uniform(15, 35)
            E.glitch = max(E.glitch, 0.35)

    # 4) Mensajes que parpadean en pantalla (menos de 45).
    if c < 40:
        E.t_mensaje -= dt
        if E.t_mensaje <= 0:
            mostrar_alerta(random.choice(FRASES_LOCURA), 0.3)
            E.glitch = max(E.glitch, 0.7)
            E.t_mensaje = random.uniform(18, 40)


def update():
    dt = min(time.dt, 1 / 20)
    E.t += dt
    actualizar_intro(dt)

    # --- reloj de la cinta (solo se reescribe el texto cuando cambia el segundo) ---
    seg_total = max(0, int(E.t + E.desfase_reloj))
    if seg_total != E.ultimo_seg:
        E.ultimo_seg = seg_total
        m, s = divmod(seg_total, 60)
        h, m = divmod(m, 60)
        reloj_cinta.text = f"{h:02d}:{m:02d}:{s:02d}"
    rec_dot.enabled = int(E.t * 2) % 2 == 0
    banda_cinta.y = 0.47 - (E.t * 0.035 % 0.94)

    # --- pantalla final ---
    if E.fase == "fin":
        E.fin_t += dt
        if E.fin_t > 1.5 and not fin_texto.enabled:
            fin_texto.enabled = True
        if E.fin_t > 2.5 and not fin_sub.enabled:
            fin_sub.enabled = True
        aplicar_velo(min(1.0, E.fin_t / 2.0))
        aplicar_shader(dt)
        return

    if not intro_activo and E.refresco_t > 0:
        E.refresco_t = max(0.0, E.refresco_t - dt)
    multiplicador = MULTIPLICADOR_REFRESCO if E.refresco_t > 0 else 1.0
    recuperacion = RECUPERACION_SPRINT * (1.8 if E.refresco_t > 0 else 1.0)

    # Sprint con reserva de aire: correr permite escapar, pero agota el impulso.
    teclas_sprint = any(held_keys.get(tecla, 0)
                        for tecla in ("shift", "left shift", "right shift"))
    corriendo = bool(teclas_sprint and not intro_activo and E.energia_sprint > 0.5)
    if intro_activo:
        jugador.speed = 0
        E.energia_sprint = min(ENERGIA_SPRINT_MAX,
                               E.energia_sprint + recuperacion * dt)
    elif corriendo:
        jugador.speed = VELOCIDAD_SPRINT * multiplicador
        E.energia_sprint = max(0.0, E.energia_sprint - COSTO_SPRINT * dt)
        if E.energia_sprint <= 0:
            corriendo = False
            jugador.speed = VELOCIDAD_CAMINAR * multiplicador
    else:
        jugador.speed = VELOCIDAD_CAMINAR * multiplicador
        E.energia_sprint = min(ENERGIA_SPRINT_MAX,
                               E.energia_sprint + recuperacion * dt)

    # --- movimiento, cambio del laberinto y pasos ---
    posicion_anterior = Vec3(jugador.x, 0, jugador.z)
    cambio = laberinto.actualizar(dt, jugador)
    posicion_actual = Vec3(jugador.x, 0, jugador.z)
    desplaz = (posicion_actual - posicion_anterior).length()
    moviendo = desplaz > 0.002 and not intro_activo

    global distancia_paso
    if intro_activo or cambio or desplaz > 1.0:
        distancia_paso = 0.0
    elif jugador.grounded and desplaz > 0.002:
        distancia_paso += desplaz
        paso_actual = 1.05 if corriendo else 1.55
        if distancia_paso >= paso_actual:
            reproducir_paso(0.52 if corriendo else 0.34)
            # El sonido real del jugador es la principal forma de ser detectado.
            if entidad_ciega.activa:
                entidad_ciega.recibir_ruido(jugador.x, jugador.z, 1.0 if corriendo else 0.52)
            distancia_paso -= paso_actual
            # Eco fantasma: cuanta menos cordura, mas probable.
            if E.cordura < 75 and random.random() < (75 - E.cordura) / 75 * 0.8:
                E.ecos.append(random.uniform(0.3, 0.6))
    else:
        distancia_paso = min(distancia_paso, 0.35)

    # --- eventos ---
    if cambio:
        limpiar_consumibles()
        E.t_consumible = 5.0
        entidad_ciega.ruta = []
        entidad_ciega.t_ruta = 0.0
        E.cambios += 1
        E.techo = max(35.0, 100.0 - 8.0 * E.cambios)
        E.cordura = max(0.0, E.cordura - 8.0)
        E.fundido = 1.7
        E.glitch = 1.25
        silueta.ocultar()
        mostrar_alerta("LAS PAREDES SE HAN MOVIDO", 3.0)
    if laberinto.observar_imitacion(jugador, dt):
        E.cordura = max(0.0, E.cordura - 12.0)
        E.glitch = 2.0
        mostrar_alerta("LA PUERTA NUNCA ESTUVO AHI", 3.0)

    # --- cordura y alucinaciones ---
    if not intro_activo:
        E.t_corrida += dt
        actualizar_cordura(dt)
        actualizar_alucinaciones(dt, moviendo, corriendo)
        actualizar_susto(dt)

        # Segunda amenaza: no ve al jugador; necesita reunir suficientes señales.
        if (not entidad_ciega.activa and E.fase == "juego"
                and (E.t_corrida >= T_ENTIDAD_CIEGA or E.cordura <= 48)):
            if entidad_ciega.activar():
                E.glitch = max(E.glitch, 0.38)
                mostrar_alerta("NO HAGAS RUIDO", 2.4)
        if entidad_ciega.activa:
            if corriendo:
                E.corrida_ruido_t -= dt
                if E.corrida_ruido_t <= 0:
                    entidad_ciega.recibir_ruido(jugador.x, jugador.z, 0.78)
                    E.corrida_ruido_t = 0.42
            if entidad_ciega.actualizar(dt, corriendo):
                terminar("ALGO TE ENCONTRO")
        amenaza_texto.enabled = entidad_ciega.activa and E.fase == "juego"
        if amenaza_texto.enabled:
            if entidad_ciega.estado == "persecucion":
                amenaza_texto.text = "TE HA ENCONTRADO"
            elif entidad_ciega.estado in ("investigacion", "busqueda"):
                amenaza_texto.text = "HA OIDO ALGO"
            else:
                amenaza_texto.text = ""
            amenaza_texto.enabled = bool(amenaza_texto.text)

        # Los objetos aparecen en salas abiertas; el inventario se conserva al cambiar el mapa.
        E.t_consumible -= dt
        if E.t_consumible <= 0:
            creado = crear_consumible()
            E.t_consumible = random.uniform(15.0, 21.0) if creado else 4.0
        recoger_consumibles()

        sx, sz = laberinto.posicion_salida()
        if math.hypot(jugador.x - sx, jugador.z - sz) < 2.2:
            terminar("SALISTE... O ESO CREES")
        elif E.cordura <= 0 and not E.susto_activo:
            terminar("YA NO RECUERDAS LA SALIDA")

    # --- alerta temporal ---
    if E.alerta_t > 0:
        E.alerta_t -= dt
        if E.alerta_t <= 0:
            alerta.enabled = False

    # --- HUD (solo se reescribe lo que cambia) ---
    nuevo = f"LINTERNA: {'ENCENDIDA' if E.linterna else 'APAGADA'}"
    if nuevo != hud.text:
        hud.text = nuevo
    contador = f"1 AGUA {E.agua_inventario}   ·   2 REFRESCO {E.refresco_inventario}"
    if E.refresco_t > 0:
        contador += f"   ·   TURBO {E.refresco_t:0.0f}s"
    if contador != inventario_texto.text:
        inventario_texto.text = contador
    cint = int(E.cordura)
    if cint != E.ultima_cordura:
        E.ultima_cordura = cint
        cord_barra.scale_x = 0.25 * E.cordura / 100.0
        l = 1.0 - E.cordura / 100.0
        cord_barra.color = color.rgb32(int(170 + 60 * l), int(176 - 120 * l), int(150 - 110 * l))

    energia_int = int(E.energia_sprint)
    if energia_int != E.ultima_energia_sprint:
        E.ultima_energia_sprint = energia_int
        energia_barra.scale_x = 0.25 * E.energia_sprint / ENERGIA_SPRINT_MAX
        if E.energia_sprint < 20:
            energia_barra.color = color.rgb32(184, 91, 63)
        elif E.energia_sprint < 45:
            energia_barra.color = color.rgb32(184, 151, 75)
        else:
            energia_barra.color = color.rgb32(153, 174, 120)

    if E.zoom_ui_t > 0:
        E.zoom_ui_t = max(0.0, E.zoom_ui_t - dt)
        if E.zoom_ui_t == 0:
            zoom_texto.enabled = False

    # --- linterna: fallos breves, espaciados y mas probables con poca cordura ---
    encendida = E.linterna
    if encendida and E.cordura < 45:
        if E.fallo_linterna > 0:
            E.fallo_linterna = max(0.0, E.fallo_linterna - dt)
            encendida = False
        elif random.random() < dt * (0.025 + (45 - E.cordura) * 0.003):
            E.fallo_linterna = random.uniform(0.12, 0.48)
            encendida = False
    linterna.color = COLOR_LINTERNA if encendida else COLOR_APAGADA

    # --- zumbido: sube al acercarse un cambio ---
    if zumbido_ambiente:
        objetivo_vol = 0.66 if laberinto.tiempo_aviso <= 5 else 0.50
        if zumbido_ambiente.volume != objetivo_vol:
            zumbido_ambiente.volume = objetivo_vol

    # --- apagon + shader ---
    if E.fundido > 0:
        E.fundido = max(0.0, E.fundido - dt)
        a = min(1.0, E.fundido)
    elif laberinto.tiempo_aviso < 1.2:
        a = min(1.0, (1.2 - laberinto.tiempo_aviso) / 1.0)
    else:
        a = 0.0
    aplicar_velo(a)
    aplicar_shader(dt)

    # --- camara: respiracion de la grabacion y latido con poca cordura ---
    if not intro_activo:
        locura = 1.0 - E.cordura / 100.0
        intensidad_mov = min(1.0, desplaz * 5)
        jugador.camera_pivot.rotation_z = (math.sin(E.t * 1.8) * (0.10 + locura * 0.28)
                                           + math.sin(E.t * 8.0) * locura * 0.045)
        # Movimiento de camara muy contenido para no cortar las paredes cercanas.
        camera.position = (math.sin(E.t * 2.2) * 0.006 * intensidad_mov,
                           math.sin(E.t * 3.1) * 0.004 * intensidad_mov, 0)
        latido = max(0.0, math.sin(E.t * (1.4 + locura * 2.2))) ** 8 * locura * 4.0
        fov_objetivo = zoom_fov + latido
        camera.fov += (fov_objetivo - camera.fov) * min(1.0, dt * 8.0)


def aplicar_velo(a):
    alpha = int(255 * a)
    if alpha != E.alpha_velo:
        E.alpha_velo = alpha
        velo.color = color.rgba32(0, 0, 0, alpha)
        velo.enabled = alpha > 2


def aplicar_shader(dt):
    E.glitch = max(0.0, E.glitch - dt)
    if USAR_SHADER:
        camera.set_shader_input("tiempo", E.t % 100.0)
        camera.set_shader_input("glitch", min(1.0, E.glitch))
        camera.set_shader_input("locura", max(0.0, min(1.0, 1.0 - E.cordura / 100.0)))


if __name__ == "__main__":
    app.run()
