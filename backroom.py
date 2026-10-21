"""BACKROOM: experiencia 3D de terror liminal; la habitacion es la amenaza.

Controles: WASD mover, raton mirar, espacio saltar, F linterna, R reiniciar (al final), ESC salir.
Requiere: pip install ursina

Novedades de esta version:
  - Geometria de paredes fusionada en una sola malla (mucho menos lag).
  - Suelo y techo permanentes: el jugador ya no se hunde al cambiar el mapa.
  - Zona fija alrededor del jugador: su habitacion se conserva y cambia lo de alrededor.
  - Apagon de camara durante el cambio, sin cuenta atras.
  - Umbrales que llevan a zonas nuevas, con materiales e iluminacion diferentes.
  - Shader estilo camara analogica (grano, aberracion, viñeta, scanlines).
  - Sistema de CORDURA con alucinaciones (siluetas, pasos fantasma, reloj, flechas que mienten...).
"""
import math
import random
from pathlib import Path
from time import perf_counter

from panda3d.core import PNMImage, Texture as PandaTexture
from ursina import *
from ursina import Texture as UrsinaTexture
from ursina.prefabs.first_person_controller import FirstPersonController

# ----------------------------------------------------------------------------
# AJUSTES (aqui puedes tocar el juego sin buscar por todo el codigo)
# ----------------------------------------------------------------------------
CELDA = 5.5
LADO = 31                         # cada zona es amplia; los umbrales llevan a nuevas zonas
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
            elif tipo == "concreto":
                # Hormigón de servicio: juntas, filtraciones y zonas reparadas.
                junta = -0.095 if x % 64 < 2 or y % 96 < 2 else 0
                humedad = max(0, nubes - 0.46) * 0.23
                parche = -0.055 if valor_ruido(x, y, 48) < 0.34 else 0
                base = (0.43 + grano + junta + parche - humedad,
                        0.44 + grano + junta + parche - humedad,
                        0.37 + grano * 0.8 + junta + parche - humedad * 0.8)
            elif tipo == "loseta":
                # Baldosas viejas de un corredor institucional, con juntas oscuras.
                junta = -0.17 if x % 64 < 2 or y % 64 < 2 else 0
                mancha = max(0, nubes - 0.58) * 0.17
                base = (0.52 + grano + junta - mancha,
                        0.53 + grano + junta - mancha,
                        0.46 + grano * 0.8 + junta - mancha * 0.8)
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
TEXTURA_CONCRETO = crear_textura("hormigon_servicio", "concreto")
TEXTURA_LOSETAS = crear_textura("losetas_institucionales", "loseta")
DIRECTORIO = Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# ESTADO GLOBAL DEL JUEGO (todo lo que cambia vive aqui)
# ----------------------------------------------------------------------------
class Estado:
    t = 0.0                       # tiempo total de "grabacion"
    cordura = 100.0
    techo = 100.0                 # maximo de cordura recuperable (baja con cada cambio)
    cambios = 0
    nivel_actual = 0
    fase = "menu"                 # "menu", "opciones", "juego" o "fin"
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
    t_evento_mental = 0.0       # separa las alucinaciones fuertes
    t_glitch = 0.0              # evita lanzar distorsion cada frame
    desfase_reloj = 0.0
    ecos = []                     # pasos fantasma pendientes (segundos hasta sonar)
    mov_antes = False
    ultimo_seg = -1
    ultima_cordura = -1
    ultima_fase_cordura = None
    alpha_velo = -1
    energia_sprint = ENERGIA_SPRINT_MAX
    ultima_energia_sprint = -1
    t_corrida = 0.0
    t_consumible = 9.0
    agua_inventario = 0
    refresco_inventario = 0
    refresco_t = 0.0
    volumen = 0.65
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
# Algunas instalaciones de Ursina no incluyen OpenSans-Regular.ttf. En Windows
# usamos Arial como respaldo para conservar la legibilidad de menús y avisos.
if not (application.fonts_folder / Text.default_font).is_file():
    fuente_respaldo = Path("C:/Windows/Fonts/arial.ttf")
    if fuente_respaldo.is_file():
        application.fonts_folder = fuente_respaldo.parent
        Text.default_font = fuente_respaldo.name
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

# Los niveles comparten geometría procedural, pero cambian materiales, luz y niebla.
# Al superar la última zona, el ciclo vuelve a empezar con más desgaste visual.
PERFILES_ZONA = (
    {
        "nombre": "NIVEL 0  /  EL LOBBY",
        "pared": TEXTURA_PAPEL, "suelo": TEXTURA_ALFOMBRA, "techo": TEXTURA_TECHO,
        "tinte_pared": (255, 255, 255), "tinte_suelo": (255, 255, 255),
        "tinte_techo": (255, 255, 255), "zocalo": (79, 76, 54), "remate": (126, 118, 77),
        "luz": (236, 238, 187), "ambiente": (20, 18, 12), "niebla": (8, 7, 4),
        "escala_pared": (2, 1.5),
    },
    {
        "nombre": "NIVEL 1  /  PASILLOS DE SERVICIO",
        "pared": TEXTURA_CONCRETO, "suelo": TEXTURA_ALFOMBRA, "techo": TEXTURA_TECHO,
        "tinte_pared": (207, 215, 198), "tinte_suelo": (182, 191, 174),
        "tinte_techo": (177, 183, 163), "zocalo": (63, 70, 61), "remate": (93, 105, 86),
        "luz": (180, 205, 188), "ambiente": (14, 18, 15), "niebla": (7, 11, 9),
        "escala_pared": (2, 1.5),
    },
    {
        "nombre": "NIVEL 2  /  MÓDULOS INTERIORES",
        "pared": TEXTURA_PAPEL, "suelo": TEXTURA_LOSETAS, "techo": TEXTURA_CONCRETO,
        "tinte_pared": (210, 204, 161), "tinte_suelo": (187, 188, 163),
        "tinte_techo": (162, 166, 149), "zocalo": (64, 62, 49), "remate": (106, 96, 68),
        "luz": (214, 194, 143), "ambiente": (17, 16, 12), "niebla": (9, 8, 5),
        "escala_pared": (2, 1.5),
    },
)


def perfil_de_zona(indice):
    """Devuelve uno de los ambientes y oscurece el ciclo con cada vuelta."""
    perfil = PERFILES_ZONA[indice % len(PERFILES_ZONA)].copy()
    perfil["ciclo"] = indice // len(PERFILES_ZONA)
    return perfil


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
        self.tono_base = kwargs.pop("tono", (236, 238, 187))
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
                                  color=color.rgb32(*self.tono_base))
            self.luz._light.setAttenuation(Vec3(1, 0, 0.028))
        Entity(parent=self, model="cube", position=(0, -0.10, 0), scale=(2.3, 0.08, 0.72),
               color=color.rgb32(62, 54, 39), unlit=True)
        self.tubo = Entity(parent=self, model="cube", position=(0, -0.16, 0), scale=(1.95, 0.04, 0.45),
                           color=color.rgb32(*self.tono_base), unlit=True)
        self.tubo_halo = Entity(parent=self, model="cube", position=(0, -0.19, 0),
                                scale=(2.08, 0.018, 0.53),
                                color=color.rgba32(*(int(c * 0.78) for c in self.tono_base), 55),
                                unlit=True)

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
        factor_luz = 0.42 + 0.58 * brillo
        self.tubo.color = color.rgb32(*(int(c * factor_luz) for c in self.tono_base))
        self.tubo_halo.color = color.rgba32(
            *(int(c * 0.78) for c in self.tono_base), int(25 + 52 * brillo))
        if self.luz:
            self.luz.color = color.rgb32(*(int(c * brillo) for c in self.tono_base))


# ----------------------------------------------------------------------------
# LABERINTO
# ----------------------------------------------------------------------------
class Laberinto:
    """Zona procedural; las flechas conducen a un umbral que lleva más adentro."""
    def __init__(self):
        self.raiz = None
        self.base = None
        self.suelo = None
        self.techo = None
        self.grupo_muros = None
        self.nivel = 0
        self.perfil = perfil_de_zona(0)
        self.mapa = []
        self.camino = []
        self.fixtures = []
        self.celdas_colision_pared = 0
        self.colliders_pared = 0
        self.reconstruccion_en_curso = False
        self._iter_reconstruccion = None
        self._raiz_anterior = None
        self._rng_reconstruccion = None
        self._grupos_combinacion = []
        self._indice_grupo_combinacion = 0
        self._estado_combinacion = None
        self._jugador_reconstruccion = None
        self._gravedad_previa = 1
        self._salto_previo = 0.65
        self._transicion_nivel = False
        self.nivel_acaba_de_cambiar = False
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
        self.suelo = Entity(parent=self.base, model="cube", name="moqueta", position=(0, -0.18, 0),
                            scale=(ancho, 0.36, ancho), texture=self.perfil["suelo"],
                            texture_scale=(LADO * 2.8, LADO * 2.8), color=color.white,
                            collider="box")
        self.techo = Entity(parent=self.base, model="cube", name="techo",
                            position=(0, ALTO_MURO + 0.18, 0), scale=(ancho, 0.36, ancho),
                            texture=self.perfil["techo"], texture_scale=(LADO, LADO),
                            color=color.white)

    def aplicar_perfil(self):
        """Cambia el aspecto global al cruzar a una nueva zona."""
        ciclo = self.perfil.get("ciclo", 0)
        oscurecer = max(0.60, 1.0 - ciclo * 0.09)

        def tono(clave):
            return color.rgb32(*(max(0, min(255, int(c * oscurecer)))
                                 for c in self.perfil[clave]))

        self.suelo.texture = self.perfil["suelo"]
        self.suelo.color = tono("tinte_suelo")
        self.techo.texture = self.perfil["techo"]
        self.techo.color = tono("tinte_techo")
        ambiente.color = tono("ambiente")
        scene.fog_color = tono("niebla")
        self.grupo_muros.color = tono("tinte_pared")

    def _preparar_reconstruccion(self, jugador, conservar_anterior):
        self.perfil = perfil_de_zona(self.nivel)
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

        raiz_anterior = self.raiz if conservar_anterior else None
        if self.raiz and not conservar_anterior:
            destroy(self.raiz)
        self.fixtures = []
        self.puerta_imitada = None
        self.puerta_imitada_revelada = False
        self.tiempo_mirando_puerta = 0.0
        self.raiz = Entity(name="laberinto", enabled=not conservar_anterior)
        self.grupo_muros = Entity(parent=self.raiz)
        self.grupo_zocalos = Entity(parent=self.raiz)
        self.grupo_remates = Entity(parent=self.raiz)
        self.semilla = random.randrange(1_000_000)
        self.mapa, rng = self.generar_mapa(fijas, origen)
        self.celda_jugador = origen
        self.camino = self.camino_corto(origen, (LADO - 2, LADO - 2))
        return rng, origen if fijas else None, raiz_anterior

    def _finalizar_reconstruccion(self, rng, raiz_anterior=None):
        self.dibujar_flechas(rng)
        self.dibujar_salida()
        self.dibujar_salida_imitada(rng)
        self.nivel_acaba_de_cambiar = self._transicion_nivel
        self.aplicar_perfil()
        if self._transicion_nivel:
            jugador = self._jugador_reconstruccion
            x, z = self.a_mundo(1, 1)
            jugador.position = (x, 0.2, z)
            jugador.rotation_y = rumbo_inicial
            jugador.camera_pivot.y = 1.65
            jugador.camera_pivot.rotation = Vec3.zero
            jugador.grounded = False
            self.nivel_acaba_de_cambiar = True
        self.reloj = 0.0
        factor = 0.58 + 0.42 * (E.cordura / 100.0)    # con menos cordura cambia mas seguido
        self.intervalo = random.uniform(INTERVALO_MIN, INTERVALO_MAX) * factor
        self.tiempo_aviso = self.intervalo
        if raiz_anterior:
            raiz_anterior.enabled = False
        self.raiz.enabled = True
        if raiz_anterior:
            destroy(raiz_anterior)
        self._raiz_anterior = None
        self._iter_reconstruccion = None
        self.reconstruccion_en_curso = False
        if self._jugador_reconstruccion:
            self._jugador_reconstruccion.gravity = self._gravedad_previa
            self._jugador_reconstruccion.jump_height = self._salto_previo
        self._jugador_reconstruccion = None
        self._transicion_nivel = False

    def reconstruir(self, jugador):
        """Reconstrucción inmediata usada al arrancar y reiniciar la partida."""
        rng, zona_fija, _ = self._preparar_reconstruccion(jugador, False)
        for _ in self.dibujar_mundo_en_pasos(rng, zona_fija):
            pass
        self._combinar_mundo()
        self._finalizar_reconstruccion(rng)

    def iniciar_reconstruccion(self, jugador):
        """Prepara otro mapa mientras conserva el anterior hasta completar el nuevo."""
        if self.reconstruccion_en_curso:
            return
        self.nivel_acaba_de_cambiar = False
        rng, zona_fija, self._raiz_anterior = self._preparar_reconstruccion(jugador, True)
        self._rng_reconstruccion = rng
        self._iter_reconstruccion = self.dibujar_mundo_en_pasos(rng, zona_fija)
        self.reconstruccion_en_curso = True
        self._jugador_reconstruccion = jugador
        self._gravedad_previa = jugador.gravity
        self._salto_previo = jugador.jump_height
        jugador.speed = 0
        jugador.gravity = 0
        jugador.jump_height = 0

    def iniciar_nueva_zona(self, jugador, nivel):
        """Construye una zona nueva mientras una transición oscura oculta el cambio."""
        if self.reconstruccion_en_curso:
            return False
        self.nivel = nivel
        self._transicion_nivel = True
        rng, zona_fija, self._raiz_anterior = self._preparar_reconstruccion(None, True)
        self._rng_reconstruccion = rng
        self._iter_reconstruccion = self.dibujar_mundo_en_pasos(rng, zona_fija)
        self.reconstruccion_en_curso = True
        self._jugador_reconstruccion = jugador
        self._gravedad_previa = jugador.gravity
        self._salto_previo = jugador.jump_height
        jugador.speed = 0
        jugador.gravity = 0
        jugador.jump_height = 0
        return True

    def avanzar_reconstruccion(self):
        """Construye filas y combina vértices por lotes; True cuando está listo."""
        if not self.reconstruccion_en_curso:
            return False

        if self._iter_reconstruccion is not None:
            try:
                next(self._iter_reconstruccion)
                return False
            except StopIteration:
                self._iter_reconstruccion = None
                self._preparar_combinacion_progresiva()

        if self._avanzar_combinacion_progresiva():
            self._finalizar_reconstruccion(self._rng_reconstruccion,
                                           self._raiz_anterior)
            self._rng_reconstruccion = None
            self._grupos_combinacion = []
            self._estado_combinacion = None
            return True
        return False

    def _combinar_mundo(self):
        self.grupo_muros.combine()
        self.grupo_muros.texture = self.perfil["pared"]
        self.grupo_muros.texture_scale = self.perfil["escala_pared"]
        self.grupo_zocalos.combine()
        self.grupo_remates.combine()

    def _preparar_combinacion_progresiva(self):
        self._grupos_combinacion = [
            (self.grupo_muros, self.perfil["pared"], self.perfil["escala_pared"]),
            (self.grupo_zocalos, None, None),
            (self.grupo_remates, None, None),
        ]
        self._indice_grupo_combinacion = 0
        self._estado_combinacion = None

    def _iniciar_grupo_combinacion(self):
        while self._indice_grupo_combinacion < len(self._grupos_combinacion):
            grupo, textura, escala_textura = self._grupos_combinacion[
                self._indice_grupo_combinacion]
            elementos = [entidad for entidad in grupo.children if entidad.model is not None]
            if elementos:
                self._estado_combinacion = {
                    "grupo": grupo,
                    "textura": textura,
                    "escala_textura": escala_textura,
                    "elementos": elementos,
                    "indice": 0,
                    "offset": 0,
                    "vertices": [],
                    "triangulos": [],
                    "uvs": [],
                    "colores": [],
                }
                return True
            self._indice_grupo_combinacion += 1
        return False

    def _avanzar_combinacion_progresiva(self):
        limite = perf_counter() + 0.006
        while perf_counter() < limite:
            if self._estado_combinacion is None and not self._iniciar_grupo_combinacion():
                return True

            estado = self._estado_combinacion
            if estado["indice"] >= len(estado["elementos"]):
                grupo = estado["grupo"]
                grupo.model = Mesh(vertices=estado["vertices"],
                                   triangles=estado["triangulos"],
                                   uvs=estado["uvs"], colors=estado["colores"],
                                   mode="triangle")
                if estado["textura"]:
                    grupo.texture = estado["textura"]
                    grupo.texture_scale = estado["escala_textura"]
                for entidad in estado["elementos"]:
                    destroy(entidad)
                self._estado_combinacion = None
                self._indice_grupo_combinacion += 1
                continue

            entidad = estado["elementos"][estado["indice"]]
            modelo = entidad.model
            if not hasattr(modelo, "vertices") or not modelo.vertices:
                modelo = load_model(modelo.name, use_deepcopy=True)
                entidad.model = modelo
                entidad.origin = entidad.origin

            transformacion = modelo.getTransform(estado["grupo"]).getMat()
            vertices = modelo.vertices
            estado["vertices"].extend(
                Vec3(*transformacion.xformPoint(Vec3(*vertice))) for vertice in vertices)
            triangulos = modelo.triangles or list(range(len(vertices)))
            indices = []
            for triangulo in triangulos:
                if isinstance(triangulo, int):
                    indices.append(triangulo)
                elif len(triangulo) == 3:
                    indices.extend(triangulo)
                elif len(triangulo) == 4:
                    indices.extend((triangulo[0], triangulo[1], triangulo[2],
                                    triangulo[2], triangulo[3], triangulo[0]))
            indices = [indice + estado["offset"] for indice in indices]
            estado["triangulos"].extend(
                (indices[i], indices[i + 1], indices[i + 2])
                for i in range(0, len(indices) - 1, 3))
            estado["offset"] += len(vertices)

            if modelo.uvs:
                estado["uvs"].extend(
                    (uv * entidad.texture_scale) + entidad.texture_offset
                    for uv in modelo.uvs)
            else:
                estado["uvs"].extend((0, 0) for _ in vertices)
            if modelo.colors:
                estado["colores"].extend(
                    Color(*color_vertice) * entidad.color for color_vertice in modelo.colors)
            else:
                estado["colores"].extend((entidad.color,) * len(vertices))
            estado["indice"] += 1
        return False

    def dibujar_mundo_en_pasos(self, rng, zona_fija):
        abiertas = []
        self.celdas_colision_pared = 0
        self.colliders_pared = 0
        alto_zocalo = 0.30
        grueso_zocalo = 0.085
        colores_zocalo = color.rgb32(*self.perfil["zocalo"])
        color_remate = color.rgb32(*self.perfil["remate"])
        for gz in range(LADO):
            fila_colision = []
            for gx in range(LADO):
                wx, wz = self.a_mundo(gx, gz)
                if self.mapa[gz][gx]:
                    if not self.toca_hueco(gx, gz):
                        continue          # pared interior: no se dibuja ni colisiona
                    # Guardamos las celdas sólidas para agrupar colisiones contiguas
                    # al final. La unión de cajas conserva exactamente sus límites.
                    fila_colision.append(gx)
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

            # Una caja por tramo horizontal conserva la unión de las celdas.
            self.celdas_colision_pared += len(fila_colision)
            if fila_colision:
                inicio = anterior = fila_colision[0]
                for gx in fila_colision[1:] + [None]:
                    if gx is not None and gx == anterior + 1:
                        anterior = gx
                        continue
                    centro_x, centro_z = self.a_mundo((inicio + anterior) / 2, gz)
                    Entity(parent=self.raiz, name="colision_pared",
                           position=(centro_x, ALTO_MURO / 2, centro_z),
                           scale=((anterior - inicio + 1) * CELDA, ALTO_MURO, CELDA),
                           collider="box")
                    self.colliders_pared += 1
                    if gx is not None:
                        inicio = anterior = gx

            if gz < LADO - 1:
                yield gz

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
                   texture=self.perfil["pared"], texture_scale=(1, 1.5),
                   color=color.rgb32(*self.perfil["tinte_pared"]), collider="box")

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
            f = Fixture(parent=self.raiz, position=(wx, ALTO_MURO - 0.12, wz),
                        semilla=rng.random(), tono=self.perfil["luz"])
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
        self.puerta_imitada.es_alucinacion = True
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
        """Cuenta atrás interna; inicia la reconstrucción al vencer el temporizador."""
        if self.reconstruccion_en_curso:
            return False
        self.reloj += dt
        self.tiempo_aviso = max(0.0, self.intervalo - self.reloj)
        if self.reloj >= self.intervalo:
            self.iniciar_reconstruccion(jugador)
        return False


# ----------------------------------------------------------------------------
# ALUCINACIONES
# ----------------------------------------------------------------------------
class Silueta(Entity):
    """Figura oscura en el borde de la vision. Desaparece si la miras; si no, se acerca."""
    def __init__(self):
        super().__init__(enabled=False)
        self.es_alucinacion = True
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

    Estados: acecho -> investigacion -> busqueda -> persecucion. Navega por ecos
    imperfectos; solo comprueba proximidad fisica al jugador para cerrar la persecucion.
    """
    def __init__(self):
        super().__init__(enabled=False, collider=None)
        self.amenaza_real = True
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
        self.t_reintento_activacion = 0.0

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
                self.t_reintento_activacion = 0.0
                return True
        return False

    def recibir_ruido(self, x, z, intensidad):
        if not self.activa or E.fase != "juego":
            return
        distancia = math.hypot(self.x - x, self.z - z)
        # La cordura baja aumenta el alcance, pero los muros amortiguan y distorsionan el sonido.
        locura = 1.0 - E.cordura / 100.0
        alcance = (7.0 + locura * 15.0) * max(0.35, intensidad)
        if distancia > alcance:
            return False
        bloqueado = not laberinto.linea_libre(self.x, self.z, x, z)
        if bloqueado:
            alcance *= 0.62
        if distancia > alcance:
            return False
        calidad = max(0.0, 1.0 - distancia / max(alcance, 0.1))
        claridad = 0.68 if bloqueado else 1.0
        self.confianza = min(
            1.0, self.confianza + intensidad * (0.18 + calidad * 0.50)
            * (0.75 + locura * 0.8) * claridad
        )

        # No recibe coordenadas perfectas: distancia, ruido bajo y paredes degradan
        # la localizacion. Esto tambien evita que el camino revele nuestra posicion.
        error = (0.25 + (1.0 - calidad) * 2.4 + (1.0 - intensidad) * 1.3
                 + locura * 0.45 + (1.1 if bloqueado else 0.0))
        angulo = random.uniform(0.0, math.tau)
        radio = math.sqrt(random.random()) * error
        estimacion = (x + math.cos(angulo) * radio, z + math.sin(angulo) * radio)
        self.ultima_posicion = estimacion
        self.objetivo = estimacion
        self.t_perdida = 0.0
        if self.estado != "persecucion":
            self.estado = "investigacion"
            self.t_estado = 5.5 + self.confianza * 4.0
            self.t_ruta = 0.0
        return True

    @staticmethod
    def _celda_objetivo(posicion):
        """Convierte un eco aproximado en la celda transitable mas cercana."""
        if posicion is None:
            return None
        gx, gz = laberinto.celda_de(*posicion)
        gx = max(1, min(LADO - 2, gx))
        gz = max(1, min(LADO - 2, gz))
        if not laberinto.mapa[gz][gx]:
            return gx, gz

        for radio in range(1, 4):
            candidatas = []
            for cz in range(max(1, gz - radio), min(LADO - 1, gz + radio + 1)):
                for cx in range(max(1, gx - radio), min(LADO - 1, gx + radio + 1)):
                    if not laberinto.mapa[cz][cx]:
                        candidatas.append((cx, cz))
            if candidatas:
                return min(candidatas, key=lambda celda: abs(celda[0] - gx) + abs(celda[1] - gz))
        return None

    def actualizar(self, dt, corriendo):
        if not self.activa:
            return False
        if not laberinto.libre(self.x, self.z):
            self.activa = False
            self.enabled = False
            self.t_reintento_activacion = 2.0
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
                self.objetivo = self.ultima_posicion
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
                self.objetivo = self.ultima_posicion
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
            self.confianza = max(0.0, self.confianza - dt * (0.075 - locura * 0.02))
            if self.confianza < 0.28 and self.t_perdida > 3.0:
                self.estado = "busqueda"
                self.t_estado = 5.0
                self.objetivo = self.ultima_posicion
                self.ruta = []

        # Recalcula la ruta con poca frecuencia para evitar coste innecesario.
        self.t_ruta -= dt
        if self.t_ruta <= 0:
            if self.estado == "persecucion":
                # Incluso durante la persecucion solo sigue la ultima senal oida.
                meta = self._celda_objetivo(self.ultima_posicion or self.objetivo)
            elif self.objetivo:
                meta = self._celda_objetivo(self.objetivo)
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
        if (self.estado == "persecucion" and distancia_jugador < 1.25
                and laberinto.linea_libre(self.x, self.z, jugador.x, jugador.z)):
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
objetivo = Text(parent=camera.ui, text="SIGUE LAS FLECHAS · BUSCA EL UMBRAL", position=(0, 0.43),
                origin=(0, 0), scale=0.72, color=color.rgb32(182, 174, 135))
centro = Text(parent=camera.ui, text="+", position=(0, 0), origin=(0, 0), scale=1.2,
              color=color.rgba32(195, 190, 166, 150))
mensaje = Text(parent=camera.ui,
               text="WASD MOVER | SHIFT CORRER | ESPACIO SALTAR | F LINTERNA\n1 AGUA | 2 REFRESCO | RUEDA ZOOM",
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
inventario_texto = Text(parent=camera.ui, text="1 AGUA 0   |   2 REFRESCO 0",
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
decoracion_cinta = []
for lado_x in (-0.86, 0.86):
    for lado_y in (-0.43, 0.43):
        sx = 1 if lado_x < 0 else -1
        sy = 1 if lado_y < 0 else -1
        decoracion_cinta.append(Entity(parent=camera.ui, model="quad",
                                       position=(lado_x + sx * 0.028, lado_y, -0.8),
                                       scale=(0.056, 0.003),
                                       color=color.rgba32(205, 204, 183, 115), unlit=True))
        decoracion_cinta.append(Entity(parent=camera.ui, model="quad",
                                       position=(lado_x, lado_y + sy * 0.028, -0.8),
                                       scale=(0.003, 0.056),
                                       color=color.rgba32(205, 204, 183, 115), unlit=True))
banda_cinta = Entity(parent=camera.ui, model="quad", position=(0, -0.45, -0.78),
                     scale=(1.72, 0.006), color=color.rgba32(196, 190, 158, 9), unlit=True)
decoracion_cinta.extend((
    Entity(parent=camera.ui, model="quad", position=(0, 0.485, -0.74),
           scale=(1.72, 0.025), color=color.rgba32(0, 0, 0, 28), unlit=True),
    Entity(parent=camera.ui, model="quad", position=(0, -0.485, -0.74),
           scale=(1.72, 0.025), color=color.rgba32(0, 0, 0, 35), unlit=True),
))

# Velo negro para los apagones (esta DETRAS del REC, asi la camara "sigue grabando").
velo = Entity(parent=camera.ui, model="quad", scale=(2, 1), z=-0.6,
              color=color.rgba32(0, 0, 0, 0), unlit=True, enabled=False)

# Agrupa la interfaz de partida para ocultarla por completo bajo el menú.
hud_raiz = Entity(parent=camera.ui)
for elemento in (
    hud, cord_texto, cord_fondo, cord_barra, objetivo, centro, mensaje,
    energia_texto, energia_fondo, energia_barra, zoom_texto, inventario_texto,
    amenaza_texto, alerta, fin_texto, fin_sub, rec_dot, rec_texto, cam_texto,
    reloj_cinta, banda_cinta, velo, *decoracion_cinta,
):
    elemento.parent = hud_raiz
hud_raiz.enabled = False


# ----------------------------------------------------------------------------
# MENÚ PRINCIPAL Y RECORRIDO CINEMATOGRÁFICO
# ----------------------------------------------------------------------------
class BotonMenu(Entity):
    """Botón UI propio, dibujado con una quad para no depender de texturas externas."""
    def __init__(self, texto, posicion, accion, ancho=0.43):
        super().__init__(parent=camera.ui, model="quad", collider="box",
                         position=(posicion[0], posicion[1], -0.82),
                         scale=(ancho, 0.064), color=color.rgb32(34, 36, 28), unlit=True)
        self.accion = accion
        self.color_base = color.rgb32(34, 36, 28)
        self.color_activo = color.rgb32(91, 79, 43)
        self.etiqueta = Text(parent=camera.ui, text=texto,
                             position=(posicion[0], posicion[1] - 0.012, -0.92),
                             origin=(0, 0), scale=0.78,
                             color=color.rgb32(218, 213, 184))

    def mostrar(self, visible):
        self.enabled = visible
        self.etiqueta.enabled = visible


class MenuPrincipal:
    """Menú sobre una toma lenta del laberinto; la simulación queda detenida."""
    def __init__(self):
        self.activo = False
        self.pantalla = "principal"
        self.indice = 0
        self.partida_iniciada = False
        self.reloj = 0.0
        self.progreso = 0.0
        self.direccion = 1
        self.velocidad_camara = 0.18       # celdas por segundo
        self.t_sombra = 0.0
        self.t_siguiente_sombra = 17.0
        self.recorrido = [laberinto.a_mundo(*celda) for celda in laberinto.camino]
        if len(self.recorrido) < 2:
            self.recorrido = [laberinto.a_mundo(1, 1), laberinto.a_mundo(2, 1)]

        self.velo = Entity(parent=camera.ui, model="quad", scale=(2, 1), z=-0.70,
                           color=color.rgba32(0, 0, 0, 90), unlit=True)
        self.panel = Entity(parent=camera.ui, model="quad", position=(-0.52, 0, -0.76),
                            scale=(0.86, 0.94), color=color.rgba32(10, 12, 9, 224), unlit=True)
        self.acento = Entity(parent=camera.ui, model="quad", position=(-0.91, 0, -0.80),
                             scale=(0.008, 0.94), color=color.rgb32(153, 129, 59), unlit=True)
        self.sello = Text(parent=camera.ui, text="CINTA 01   /   NIVEL 0",
                          position=(-0.52, 0.365, -0.94), origin=(0, 0), scale=0.62,
                          color=color.rgb32(173, 166, 129))
        self.titulo = Text(parent=camera.ui, text="BACKROOM: ENTITY",
                           position=(-0.52, 0.27, -0.94), origin=(0, 0), scale=1.45,
                           color=color.rgb32(222, 211, 160))
        self.subtitulo = Text(parent=camera.ui,
                              text="NO RECUERDAS HABER ENTRADO.",
                              position=(-0.52, 0.205, -0.94), origin=(0, 0), scale=0.70,
                              color=color.rgb32(161, 157, 132))
        self.descripcion = Text(parent=camera.ui,
                                text="La habitación intenta parecer real.\nCruza un umbral y el lugar será distinto al otro lado.",
                                position=(-0.52, 0.145, -0.94), origin=(0, 0), scale=0.60,
                                color=color.rgb32(143, 141, 122))
        self.volumen_texto = Text(parent=camera.ui, text="VOLUMEN GENERAL  65%",
                                  position=(-0.52, 0.10, -0.94), origin=(0, 0), scale=0.70,
                                  color=color.rgb32(204, 198, 165), enabled=False)
        self.ayuda = Text(parent=camera.ui,
                          text="FLECHAS / ENTER  |  RATÓN PARA ELEGIR  |  ESC PARA VOLVER",
                          position=(-0.52, -0.335, -0.94), origin=(0, 0), scale=0.48,
                          color=color.rgb32(126, 127, 111))
        self.pie = Text(parent=camera.ui, text="GRABACIÓN LOCAL  —  SEÑAL INESTABLE",
                        position=(-0.52, -0.405, -0.94), origin=(0, 0), scale=0.46,
                        color=color.rgb32(113, 111, 91))

        self.botones_principales = [
            BotonMenu("JUGAR", (-0.52, 0.035), self.iniciar_partida),
            BotonMenu("OPCIONES", (-0.52, -0.065), self.abrir_opciones),
            BotonMenu("SALIR", (-0.52, -0.165), application.quit),
        ]
        self.botones_opciones = [
            BotonMenu("−", (-0.69, 0.015), lambda: self.ajustar_volumen(-0.05), ancho=0.11),
            BotonMenu("+", (-0.35, 0.015), lambda: self.ajustar_volumen(0.05), ancho=0.11),
            BotonMenu("EFECTOS VHS: ACTIVADOS", (-0.52, -0.10), self.alternar_shader, ancho=0.46),
            BotonMenu("VOLVER", (-0.52, -0.205), self.volver_principal),
        ]
        self.actualizar_textos_opciones()
        self.abrir()

    def _botones_actuales(self):
        return self.botones_opciones if self.pantalla == "opciones" else self.botones_principales

    def _mostrar_pantalla(self):
        opciones = self.pantalla == "opciones"
        self.volumen_texto.enabled = opciones
        self.sello.text = "AJUSTES DE LA GRABACIÓN" if opciones else "CINTA 01   /   NIVEL 0"
        self.titulo.text = "OPCIONES" if opciones else "BACKROOM: ENTITY"
        self.subtitulo.text = "AJUSTA LA SEÑAL ANTES DE ENTRAR." if opciones else "NO RECUERDAS HABER ENTRADO."
        self.descripcion.text = ("← / → ajusta el volumen general.\nLos efectos VHS se pueden desactivar si afectan el rendimiento."
                                 if opciones else
                                 "La habitación intenta parecer real.\nCruza un umbral y el lugar será distinto al otro lado.")
        for boton in self.botones_principales:
            boton.mostrar(not opciones)
        for boton in self.botones_opciones:
            boton.mostrar(opciones)
        self.indice = 0

    def actualizar_textos_opciones(self):
        self.volumen_texto.text = f"VOLUMEN GENERAL  {int(E.volumen * 100)}%"
        shader_activo = "ACTIVADOS" if USAR_SHADER else "DESACTIVADOS"
        self.botones_opciones[2].etiqueta.text = f"EFECTOS VHS: {shader_activo}"

    def _aplicar_volumen(self):
        if zumbido_ambiente:
            base = max(0.32, 0.50 - min(E.nivel_actual, 3) * 0.045)
            if laberinto.tiempo_aviso <= 5:
                base += 0.16
            zumbido_ambiente.volume = base * E.volumen

    def ajustar_volumen(self, cambio):
        E.volumen = max(0.0, min(1.0, round(E.volumen + cambio, 2)))
        self.actualizar_textos_opciones()
        self._aplicar_volumen()

    def alternar_shader(self):
        global USAR_SHADER
        USAR_SHADER = not USAR_SHADER
        camera.shader = shader_camara if USAR_SHADER else None
        self.actualizar_textos_opciones()

    def abrir_opciones(self):
        self.pantalla = "opciones"
        E.fase = "opciones"
        self._mostrar_pantalla()

    def volver_principal(self):
        self.pantalla = "principal"
        E.fase = "menu"
        self._mostrar_pantalla()

    def iniciar_partida(self):
        reconstruir_mapa = self.partida_iniciada
        self.partida_iniciada = True
        self.activo = False
        self.velo.enabled = False
        self.panel.enabled = False
        self.acento.enabled = False
        for texto in (self.sello, self.titulo, self.subtitulo, self.descripcion,
                      self.volumen_texto, self.ayuda, self.pie):
            texto.enabled = False
        for boton in self.botones_principales + self.botones_opciones:
            boton.mostrar(False)
        self.t_sombra = 0.0
        entidad_ciega.activa = False
        entidad_ciega.enabled = False
        hud_raiz.enabled = True
        reiniciar(reconstruir_mapa=reconstruir_mapa)

    def abrir(self):
        self.activo = True
        self.pantalla = "principal"
        self.progreso = 0.0
        self.direccion = 1
        self.reloj = 0.0
        self.t_sombra = 0.0
        self.t_siguiente_sombra = random.uniform(16.0, 28.0)
        self._mostrar_pantalla()
        self.velo.enabled = True
        self.panel.enabled = True
        self.acento.enabled = True
        self.sello.enabled = True
        self.titulo.enabled = True
        self.subtitulo.enabled = True
        self.descripcion.enabled = True
        self.ayuda.enabled = True
        self.pie.enabled = True
        hud_raiz.enabled = False
        E.fase = "menu"
        jugador.speed = 0
        jugador.gravity = 0
        jugador.jump_height = 0
        jugador.mouse_sensitivity = Vec2(0, 0)
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation = Vec3(0, 0, 0)
        if self.recorrido:
            inicio_x, inicio_z = self.recorrido[0]
            jugador.position = (inicio_x, 0.2, inicio_z)
        mouse.locked = False
        mouse.visible = True
        entidad_ciega.activa = False
        entidad_ciega.enabled = False
        self._aplicar_volumen()

    def _punto_recorrido(self, progreso):
        progreso = max(0.0, min(float(len(self.recorrido) - 1), progreso))
        i = min(len(self.recorrido) - 2, int(progreso))
        mezcla = progreso - i
        a, b = self.recorrido[i], self.recorrido[i + 1]
        return (a[0] + (b[0] - a[0]) * mezcla,
                a[1] + (b[1] - a[1]) * mezcla)

    def _actualizar_camara(self, dt):
        maximo = len(self.recorrido) - 1
        self.progreso += self.direccion * self.velocidad_camara * dt
        if self.progreso >= maximo:
            self.progreso = float(maximo)
            self.direccion = -1
        elif self.progreso <= 0:
            self.progreso = 0.0
            self.direccion = 1
        x, z = self._punto_recorrido(self.progreso)
        antes = self._punto_recorrido(self.progreso - self.direccion * 0.20)
        despues = self._punto_recorrido(self.progreso + self.direccion * 0.20)
        dx, dz = despues[0] - antes[0], despues[1] - antes[1]
        if abs(dx) + abs(dz) > 0.001:
            jugador.rotation_y = math.degrees(math.atan2(dx, dz))
        jugador.position = (x, 0.2, z)
        jugador.camera_pivot.y = 1.65
        jugador.camera_pivot.rotation_x = math.sin(self.reloj * 0.43) * 2.0 - 1.0
        jugador.camera_pivot.rotation_z = math.sin(self.reloj * 0.31) * 0.35
        camera.position = (math.sin(self.reloj * 0.7) * 0.008,
                           math.sin(self.reloj * 0.5) * 0.006, 0)

    def _actualizar_sombra(self, dt):
        if self.t_sombra > 0:
            self.t_sombra -= dt
            if self.t_sombra <= 0:
                entidad_ciega.enabled = False
            return
        self.t_siguiente_sombra -= dt
        if self.t_siguiente_sombra > 0 or len(self.recorrido) < 5:
            return
        adelante = random.randint(3, 6) * self.direccion
        indice = int(max(0, min(len(self.recorrido) - 1, self.progreso + adelante)))
        sx, sz = self.recorrido[indice]
        entidad_ciega.position = (sx, 0.02, sz)
        dx, dz = jugador.x - sx, jugador.z - sz
        entidad_ciega.rotation_y = math.degrees(math.atan2(dx, dz))
        entidad_ciega.scale = (0.78, 0.92, 0.78)
        entidad_ciega.enabled = True
        self.t_sombra = random.uniform(1.0, 2.0)
        self.t_siguiente_sombra = random.uniform(20.0, 34.0)

    def actualizar(self, dt):
        if not self.activo:
            return
        self.reloj += dt
        self._actualizar_camara(dt)
        self._actualizar_sombra(dt)
        botones = self._botones_actuales()
        hovered = mouse.hovered_entity
        for i, boton in enumerate(botones):
            if hovered is boton:
                boton.color = boton.color_activo
            else:
                boton.color = boton.color_activo if i == self.indice else boton.color_base
        if USAR_SHADER:
            camera.set_shader_input("tiempo", self.reloj)
            camera.set_shader_input("glitch", 0.025 + 0.025 * (0.5 + 0.5 * math.sin(self.reloj * 0.37)))
            camera.set_shader_input("locura", 0.08 + 0.025 * math.sin(self.reloj * 0.19))

    def procesar_input(self, key):
        botones = self._botones_actuales()
        if key == "escape":
            if self.pantalla == "opciones":
                self.volver_principal()
            else:
                application.quit()
            return
        if key in ("up arrow", "w"):
            self.indice = (self.indice - 1) % len(botones)
        elif key in ("down arrow", "s"):
            self.indice = (self.indice + 1) % len(botones)
        elif self.pantalla == "opciones" and key == "left arrow":
            self.ajustar_volumen(-0.05)
        elif self.pantalla == "opciones" and key == "right arrow":
            self.ajustar_volumen(0.05)
        elif key in ("enter", "space"):
            botones[self.indice].accion()
        elif key == "left mouse down":
            hovered = mouse.hovered_entity
            for boton in botones:
                if hovered is boton:
                    boton.accion()
                    break


main_menu = MenuPrincipal()

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
        audio.volume = volumen * E.volumen
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
                mostrar_alerta("AGUA DE ALMENDRA | PULSA 1 PARA USAR", 2.2)
            else:
                E.refresco_inventario += 1
                mostrar_alerta("REFRESCO | PULSA 2 PARA USAR", 2.2)
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
    mostrar_alerta("REFRESCO | MAS RAPIDO Y RECUPERAS AIRE", 2.2)


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
    fin_sub.text = "R REINICIAR   |   ESC MENÚ PRINCIPAL"
    alerta.enabled = False
    amenaza_texto.enabled = False
    silueta.ocultar()


def cruzar_umbral():
    """Continúa la grabación en otra zona cuando el jugador llega a la falsa salida."""
    if laberinto.reconstruccion_en_curso:
        return
    siguiente = E.nivel_actual + 1
    if not laberinto.iniciar_nueva_zona(jugador, siguiente):
        return
    E.nivel_actual = siguiente
    E.fundido = 1.8
    E.glitch = max(E.glitch, 1.4)
    E.cordura = max(0.0, E.cordura - 4.0)
    E.techo = max(35.0, E.techo - 3.0)
    E.t_evento_mental = max(E.t_evento_mental, 8.0)
    E.t_silueta = random.uniform(12.0, 20.0)
    E.t_mensaje = random.uniform(18.0, 30.0)
    E.t_consumible = 7.0
    E.ecos.clear()
    limpiar_consumibles()
    silueta.ocultar()
    entidad_ciega.activa = False
    entidad_ciega.enabled = False
    entidad_ciega.estado = "acecho"
    entidad_ciega.confianza = 0.0
    entidad_ciega.ruta = []
    entidad_ciega.objetivo = None
    entidad_ciega.ultima_posicion = None
    entidad_ciega.t_reintento_activacion = 8.0
    amenaza_texto.enabled = False
    mostrar_alerta("NO ERA LA SALIDA. SIGUE GRABANDO.", 3.2)


def reiniciar(reconstruir_mapa=True):
    global zoom_fov, intro_activo, intro_reloj
    E.t = 0.0
    E.ultimo_seg = -1
    E.ultima_cordura = -1
    E.cordura = 100.0
    E.techo = 100.0
    E.cambios = 0
    E.nivel_actual = 0
    E.energia_sprint = ENERGIA_SPRINT_MAX
    E.t_corrida = 0.0
    E.t_consumible = 9.0
    E.agua_inventario = 0
    E.refresco_inventario = 0
    E.refresco_t = 0.0
    E.zoom_ui_t = 0.0
    E.fallo_linterna = 0.0
    E.linterna = True
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
    E.t_evento_mental = 0.0
    E.t_glitch = random.uniform(8.0, 14.0)
    E.ultima_fase_cordura = None
    E.mov_antes = False
    limpiar_consumibles()
    entidad_ciega.activa = False
    entidad_ciega.enabled = False
    entidad_ciega.estado = "acecho"
    entidad_ciega.confianza = 0.0
    entidad_ciega.ruta = []
    entidad_ciega.objetivo = None
    entidad_ciega.ultima_posicion = None
    E.corrida_ruido_t = 0.0
    entidad_ciega.t_reintento_activacion = 0.0
    amenaza_texto.enabled = False
    if reconstruir_mapa:
        laberinto.nivel = 0
        laberinto.perfil = perfil_de_zona(0)
        laberinto.reconstruir(None)
    x, z = laberinto.a_mundo(1, 1)
    jugador.position = (x, 0.2, z)
    jugador.rotation_y = rumbo_inicial - 5
    jugador.camera_pivot.y = 0.34
    jugador.camera_pivot.rotation = Vec3(68, 0, -4)
    jugador.mouse_sensitivity = Vec2(0, 0)
    jugador.gravity = 0
    jugador.jump_height = 0
    jugador.speed = 0
    jugador.grounded = False
    intro_activo = True
    intro_reloj = 0.0
    mouse.locked = True
    mouse.visible = False
    zoom_fov = FOV_NORMAL
    zoom_texto.enabled = False
    fin_texto.enabled = False
    fin_sub.enabled = False
    silueta.ocultar()


def input(key):
    global zoom_fov
    if main_menu.activo:
        main_menu.procesar_input(key)
        return
    if laberinto.reconstruccion_en_curso and key != "escape":
        return
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
        zoom_texto.text = f"ZOOM {int(FOV_NORMAL * 100 / zoom_fov)}%  |  V RESTABLECER"
        zoom_texto.enabled = True
        E.zoom_ui_t = 2.0
    elif key == "v" and E.fase == "juego":
        zoom_fov = FOV_NORMAL
        zoom_texto.text = "ZOOM 100%"
        zoom_texto.enabled = True
        E.zoom_ui_t = 1.2
    elif key == "r" and E.fase == "fin" and E.fin_t > 2.0:
        reiniciar()
    elif key == "escape" and E.fase == "fin":
        main_menu.abrir()
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


def nivel_cordura(valor):
    """Nombre y color del estado mental para comunicar la escalada en el HUD."""
    if valor >= 75:
        return "ESTABLE", color.rgb32(160, 181, 139)
    if valor >= 50:
        return "INQUIETA", color.rgb32(198, 183, 105)
    if valor >= 25:
        return "ALTERADA", color.rgb32(207, 132, 76)
    return "CRITICA", color.rgb32(204, 79, 70)


def agregar_eco_fantasma(cantidad=1):
    """Agenda pasos falsos con un limite para evitar acumulaciones y saturacion."""
    espacio = max(0, 5 - len(E.ecos))
    for _ in range(min(cantidad, espacio)):
        E.ecos.append(random.uniform(0.45, 1.2))


def posponer_otros_eventos(excepto):
    """Evita que temporizadores vencidos se disparen en cadena tras un susto."""
    pausa = E.t_evento_mental + random.uniform(3.0, 7.0)
    if excepto != "silueta":
        E.t_silueta = max(E.t_silueta, pausa)
    if excepto != "reloj":
        E.t_reloj = max(E.t_reloj, pausa)
    if excepto != "mensaje":
        E.t_mensaje = max(E.t_mensaje, pausa)


def actualizar_alucinaciones(dt, moviendo, corriendo=False):
    c = E.cordura
    E.t_evento_mental = max(0.0, E.t_evento_mental - dt)
    E.t_glitch = max(0.0, E.t_glitch - dt)

    # La cinta se degrada a intervalos; la frecuencia e intensidad escalan con
    # la cordura, pero nunca dependen de una tirada aleatoria cada frame.
    if c < 65 and E.t_glitch <= 0:
        escala = (65.0 - c) / 65.0
        if random.random() < 0.48 + escala * 0.42:
            E.glitch = max(E.glitch, random.uniform(0.16, 0.30 + escala * 0.38))
        E.t_glitch = random.uniform(17.0, 27.0) * (0.34 + 0.66 * c / 100.0)

    # 1) Siluetas que se asoman junto a esquinas (menos de 82).
    if c < 82:
        E.t_silueta -= dt * (1.45 if corriendo else 1.0)
        if (not silueta.enabled and E.t_silueta <= 0
                and E.t_evento_mental <= 0):
            if silueta.intentar_aparecer():
                E.t_evento_mental = random.uniform(8.0, 12.0)
                posponer_otros_eventos("silueta")
                # El susto se vuelve mas probable al entrar en estado critico,
                # pero no acompaña todas las apariciones de la figura.
                probabilidad_susto = min(0.82, 0.28 + max(0.0, 55 - c) * 0.018)
                if c < 55 and random.random() < probabilidad_susto:
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
        agregar_eco_fantasma(random.randint(2, 4))
    E.mov_antes = moviendo

    # 3) El reloj de la cinta salta hacia atras (menos de 55).
    if c < 50:
        E.t_reloj -= dt
        if E.t_reloj <= 0 and E.t_evento_mental <= 0:
            E.desfase_reloj = max(-E.t + 1.0, E.desfase_reloj - random.uniform(20, 160))
            E.t_reloj = random.uniform(18, 34) * (0.55 + 0.45 * c / 100.0)
            E.glitch = max(E.glitch, 0.35)
            E.t_evento_mental = random.uniform(8.0, 12.0)
            posponer_otros_eventos("reloj")

    # 4) Mensajes que parpadean en pantalla (menos de 45).
    if c < 40:
        E.t_mensaje -= dt
        if E.t_mensaje <= 0 and E.t_evento_mental <= 0:
            mostrar_alerta(random.choice(FRASES_LOCURA), 0.3)
            E.glitch = max(E.glitch, 0.7)
            E.t_mensaje = random.uniform(22, 42) * (0.60 + 0.40 * c / 100.0)
            E.t_evento_mental = random.uniform(7.0, 11.0)
            posponer_otros_eventos("mensaje")


def update():
    dt = min(time.dt, 1 / 20)
    if main_menu.activo:
        main_menu.actualizar(dt)
        return
    E.t += dt
    actualizar_intro(dt)

    # --- reloj de la cinta (solo se reescribe el texto cuando cambia el segundo) ---
    seg_total = max(0, int(E.t + E.desfase_reloj))
    if seg_total != E.ultimo_seg:
        E.ultimo_seg = seg_total
        m, s = divmod(seg_total, 60)
        h, m = divmod(m, 60)
        reloj_cinta.text = f"{h:02d}:{m:02d}:{s:02d}"
    etiqueta_zona = f"CAM-01   /   NIVEL {E.nivel_actual:02d}"
    if cam_texto.text != etiqueta_zona:
        cam_texto.text = etiqueta_zona
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

    cambio = False
    cambio_nivel = False
    if laberinto.reconstruccion_en_curso:
        cambio = laberinto.avanzar_reconstruccion()
        if cambio:
            cambio_nivel = laberinto.nivel_acaba_de_cambiar
            laberinto.nivel_acaba_de_cambiar = False
        if not cambio:
            # El fundido que anuncia el cambio cubre la construcción progresiva.
            jugador.speed = 0
            E.fundido = 1.0
            aplicar_velo(1.0)
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
    if not cambio:
        laberinto.actualizar(dt, jugador)
        if laberinto.reconstruccion_en_curso:
            cambio = laberinto.avanzar_reconstruccion()
            if cambio:
                cambio_nivel = laberinto.nivel_acaba_de_cambiar
                laberinto.nivel_acaba_de_cambiar = False
            if not cambio:
                jugador.speed = 0
                E.fundido = 1.0
                aplicar_velo(1.0)
                aplicar_shader(dt)
                return
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
                agregar_eco_fantasma()
    else:
        distancia_paso = min(distancia_paso, 0.35)

    # --- eventos ---
    if cambio and cambio_nivel:
        limpiar_consumibles()
        E.t_consumible = 7.0
        entidad_ciega.ruta = []
        entidad_ciega.t_ruta = 0.0
        E.t_evento_mental = max(E.t_evento_mental, 8.0)
        posponer_otros_eventos("cambio")
        E.fundido = 1.15
        E.glitch = max(E.glitch, 0.85)
        silueta.ocultar()
        mostrar_alerta(f"{laberinto.perfil['nombre']}\nNO RECUERDAS HABER LLEGADO", 3.5)
    elif cambio:
        limpiar_consumibles()
        E.t_consumible = 5.0
        entidad_ciega.ruta = []
        entidad_ciega.t_ruta = 0.0
        E.cambios += 1
        E.techo = max(35.0, 100.0 - 8.0 * E.cambios)
        E.cordura = max(0.0, E.cordura - 8.0)
        E.t_evento_mental = max(E.t_evento_mental, 10.0)
        posponer_otros_eventos("cambio")
        E.fundido = 1.7
        E.glitch = 1.25
        silueta.ocultar()
        entidad_ciega.t_reintento_activacion = 0.0
        mostrar_alerta("LAS PAREDES SE HAN MOVIDO", 3.0)
    if laberinto.observar_imitacion(jugador, dt):
        E.cordura = max(0.0, E.cordura - 12.0)
        E.glitch = 2.0
        E.t_evento_mental = max(E.t_evento_mental, 10.0)
        posponer_otros_eventos("puerta")
        mostrar_alerta("LA PUERTA NUNCA ESTUVO AHI", 3.0)

    # --- cordura y alucinaciones ---
    if not intro_activo:
        E.t_corrida += dt
        actualizar_cordura(dt)
        actualizar_alucinaciones(dt, moviendo, corriendo)
        actualizar_susto(dt)

        # Segunda amenaza: no ve al jugador; necesita reunir suficientes señales.
        entidad_ciega.t_reintento_activacion = max(
            0.0, entidad_ciega.t_reintento_activacion - dt)
        if (not entidad_ciega.activa and entidad_ciega.t_reintento_activacion <= 0
                and E.fase == "juego"
                and (E.t_corrida >= T_ENTIDAD_CIEGA or E.cordura <= 48)):
            if entidad_ciega.activar():
                E.glitch = max(E.glitch, 0.38)
                mostrar_alerta("NO HAGAS RUIDO", 2.4)
            else:
                # Si no hay un punto válido en este mapa, repetir la búsqueda cada
                # frame puede causar tirones. El siguiente intento será tras 2 s.
                entidad_ciega.t_reintento_activacion = 2.0
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
            cruzar_umbral()
            return
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
    contador = f"1 AGUA {E.agua_inventario}   |   2 REFRESCO {E.refresco_inventario}"
    if E.refresco_t > 0:
        contador += f"   |   TURBO {E.refresco_t:0.0f}s"
    if contador != inventario_texto.text:
        inventario_texto.text = contador
    cint = int(E.cordura)
    if cint != E.ultima_cordura:
        E.ultima_cordura = cint
        cord_barra.scale_x = 0.25 * E.cordura / 100.0
        l = 1.0 - E.cordura / 100.0
        cord_barra.color = color.rgb32(int(170 + 60 * l), int(176 - 120 * l), int(150 - 110 * l))
        fase, tono_fase = nivel_cordura(E.cordura)
        if fase != E.ultima_fase_cordura:
            E.ultima_fase_cordura = fase
            cord_texto.text = f"CORDURA | {fase}"
            cord_texto.color = tono_fase

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
        base_ambiente = max(0.32, 0.50 - min(E.nivel_actual, 3) * 0.045)
        if laberinto.tiempo_aviso <= 5:
            base_ambiente += 0.16
        objetivo_vol = base_ambiente * E.volumen
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
