"""
Agar 2D - juego estilo agar.io

Controles:
  Mouse            -> la célula se mueve hacia el cursor
  W A S D / flechas-> alternativa con teclado
  ESPACIO          -> sprint (gasta masa mientras lo mantienes)
  Q                -> mitosis (divide una célula grande)
  P                -> pausa
  ENTER            -> empezar / volver a jugar (cuando te comen)
  F1               -> menú de administración
  ESC              -> salir

Reglas:
  - Recoge puntos de comida para crecer.
  - Puedes comerte a una célula si tienes al menos 15% más de masa y la cubres.
  - Las células más grandes te comen a ti.
  - Cuanto más grande eres, más lento vas y más se aleja la cámara.

Requiere: pygame  (pip install pygame   o   pip install pygame-ce)
"""
import colorsys
import array
import json
import math
import os
import random
import sys

import pygame

# ---------- Configuración del mundo ----------
MUNDO = 7000              # el mundo es un cuadrado de MUNDO x MUNDO
N_COMIDA = 4500
N_NPC = 60
TAM_GRILLA = 200          # tamaño de cada casilla de la rejilla espacial de comida

# ---------- Células ----------
MASA_INICIAL = 20
MASA_COMIDA = 10
RADIO_K = 3.2             # radio = RADIO_K * raiz(masa)
VENTAJA = 1.15            # hace falta tener 15% más de masa para comerse a otra
MASA_MIN_SPRINT = 25
COSTO_SPRINT = 0.04       # fracción de masa por segundo que cuesta el sprint
MASA_MAX_NPC = 12000
INMUNIDAD_INICIAL = 6.0   # segundos sin poder ser comido al empezar
SPRINT_NPC_MAX = 1.5      # un NPC solo puede hacer sprint 1.5 s seguidos...
SPRINT_NPC_ESPERA = 5.0   # ...y luego debe descansar 5 s
RADIO_COMIDA = 6
INTERVALO_PODER = 8.0
DURACION_PODER = 7.0
MAX_CELULAS_JUGADOR = 8

FPS = 60
TITULO_JUEGO = "Masa Viva"

# ---------- Colores ----------
FONDO = (22, 24, 38)
FUERA = (8, 8, 14)
LINEA_GRILLA = (34, 38, 58)
BORDE_MUNDO = (200, 70, 70)
BLANCO = (240, 240, 250)
GRIS = (140, 145, 170)

NOMBRES = ["Blob", "Pelusa", "Gordo", "Sombra", "Chispa", "Nube", "Pixel", "Bola", "Tito", "Lola",
           "Rayo", "Mochi", "Pulga", "Gelatina", "Turbo", "Nacho", "Pepa", "Zeta", "Burbuja", "Koko",
           "Duende", "Fantasma", "Luna", "Trueno", "Coco", "Manchas", "Vortex", "Panda", "Cometa", "Ñoño"]


def color_aleatorio(saturacion=0.65):
    r, g, b = colorsys.hsv_to_rgb(random.random(), saturacion, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def oscurecer(color, f=0.6):
    return int(color[0] * f), int(color[1] * f), int(color[2] * f)


def limitar(v, a, b):
    return max(a, min(b, v))


def normalizar(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-6 else (0.0, 0.0)


class Comida:
    __slots__ = ("x", "y", "color")

    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color


class RejillaComida:
    """Guarda la comida en casillas para buscarla rápido sin recorrer las 4500 piezas."""

    def __init__(self):
        self.casillas = {}

    def agregar(self, f):
        self.casillas.setdefault((int(f.x // TAM_GRILLA), int(f.y // TAM_GRILLA)), []).append(f)

    def comer(self, x, y, r):
        """Quita la comida dentro del círculo y devuelve cuántas piezas eran."""
        cantidad = 0
        r2 = r * r
        for gx in range(int((x - r) // TAM_GRILLA), int((x + r) // TAM_GRILLA) + 1):
            for gy in range(int((y - r) // TAM_GRILLA), int((y + r) // TAM_GRILLA) + 1):
                lista = self.casillas.get((gx, gy))
                if not lista:
                    continue
                restantes = [f for f in lista if (f.x - x) ** 2 + (f.y - y) ** 2 > r2]
                if len(restantes) != len(lista):
                    cantidad += len(lista) - len(restantes)
                    self.casillas[(gx, gy)] = restantes
        return cantidad

    def mas_cercana(self, x, y, rango):
        mejor, mejor_d2 = None, rango * rango
        for gx in range(int((x - rango) // TAM_GRILLA), int((x + rango) // TAM_GRILLA) + 1):
            for gy in range(int((y - rango) // TAM_GRILLA), int((y + rango) // TAM_GRILLA) + 1):
                for f in self.casillas.get((gx, gy), ()):
                    d2 = (f.x - x) ** 2 + (f.y - y) ** 2
                    if d2 < mejor_d2:
                        mejor, mejor_d2 = f, d2
        return mejor

    def en_rectangulo(self, x0, y0, x1, y1):
        for gx in range(int(x0 // TAM_GRILLA), int(x1 // TAM_GRILLA) + 1):
            for gy in range(int(y0 // TAM_GRILLA), int(y1 // TAM_GRILLA) + 1):
                for f in self.casillas.get((gx, gy), ()):
                    yield f


class RejillaCelulas:
    """Índice espacial de células para consultas locales de colisión y percepción."""

    TAM_CASILLA = 300

    def __init__(self):
        self.casillas = {}
        self.posiciones = {}
        self.orden = {}
        self.radio_maximo = 0.0

    def _clave(self, x, y):
        return int(x // self.TAM_CASILLA), int(y // self.TAM_CASILLA)

    def agregar(self, celula):
        clave = self._clave(celula.x, celula.y)
        self.casillas.setdefault(clave, []).append(celula)
        self.posiciones[celula] = clave
        self.radio_maximo = max(self.radio_maximo, celula.r)

    def reconstruir(self, celulas):
        self.casillas.clear()
        self.posiciones.clear()
        self.orden.clear()
        self.radio_maximo = 0.0
        for indice, celula in enumerate(celulas):
            self.orden[celula] = indice
            if celula.viva:
                self.agregar(celula)

    def mover(self, celula, x_anterior, y_anterior):
        clave_anterior = self.posiciones.get(celula)
        clave_nueva = self._clave(celula.x, celula.y)
        if clave_anterior != clave_nueva:
            if clave_anterior is not None:
                lista = self.casillas.get(clave_anterior, [])
                if celula in lista:
                    lista.remove(celula)
                    if not lista:
                        self.casillas.pop(clave_anterior, None)
            self.casillas.setdefault(clave_nueva, []).append(celula)
            self.posiciones[celula] = clave_nueva
        self.radio_maximo = max(self.radio_maximo, celula.r)

    def cercanas(self, x, y, rango):
        if rango < 0:
            return ()
        paso = self.TAM_CASILLA
        salida = []
        x0, x1 = int((x - rango) // paso), int((x + rango) // paso)
        y0, y1 = int((y - rango) // paso), int((y + rango) // paso)
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                for celula in self.casillas.get((gx, gy), ()):
                    if (celula.x - x) ** 2 + (celula.y - y) ** 2 <= rango * rango:
                        salida.append(celula)
        salida.sort(key=self.orden.get)
        return salida


PODERES = {
    "mitosis": ("MITOSIS", (110, 220, 255)),
    "turbo": ("TURBO", (255, 170, 70)),
    "escudo": ("ESCUDO", (120, 255, 190)),
    "iman": ("IMÁN", (255, 100, 210)),
    "masa": ("MASA +", (255, 225, 90)),
    "portal": ("PORTAL", (170, 130, 255)),
    "onda": ("ONDA", (255, 100, 110)),
}


class Potenciador:
    __slots__ = ("x", "y", "tipo", "fase")

    def __init__(self, x, y, tipo):
        self.x, self.y, self.tipo = x, y, tipo
        self.fase = random.random() * math.tau


class Virus:
    """Pincho estático que puede explotar células grandes y dividirse con masa."""

    __slots__ = ("x", "y", "r", "bolitas")

    def __init__(self, x, y, radio=58):
        self.x, self.y, self.r = x, y, radio
        self.bolitas = 0


class MasaEyectada:
    __slots__ = ("x", "y", "dx", "dy", "masa", "propietario", "vida")

    def __init__(self, x, y, dx, dy, masa, propietario):
        self.x, self.y, self.dx, self.dy = x, y, dx, dy
        self.masa, self.propietario = masa, propietario
        self.vida = 3.0


class Celula:
    def __init__(self, x, y, masa, color, nombre, es_jugador=False):
        self.x, self.y = x, y
        self.masa = masa
        self.color = color
        self.nombre = nombre
        self.es_jugador = es_jugador
        self.viva = True
        self.dx = self.dy = 0.0        # dirección actual (suavizada)
        self.tx = self.ty = 0.0        # dirección deseada
        self.sprint = False
        self.comidos = 0
        # Solo para la IA
        self.t_pensar = random.uniform(0, 0.3)
        self.t_vagar = 0.0
        self.obj_x = self.obj_y = None
        self.agresividad = random.uniform(0.35, 1.0)
        self.t_sprint = 0.0            # tiempo seguido haciendo sprint
        self.t_descanso = 0.0          # tiempo que le falta para poder volver a correr
        self.factor_vel = random.uniform(0.92, 1.05)
        self.boost_tiempo = 0.0
        self.escudo_tiempo = 0.0
        self.iman_tiempo = 0.0
        self.fusion_tiempo = 0.0
        self.factor_velocidad_admin = 1.0
        self.factor_decaimiento_grande = 0.5
        self.impulso_x = self.impulso_y = 0.0
        self.tiempo_mitosis_npc = 0.0

    @property
    def r(self):
        return RADIO_K * math.sqrt(self.masa)

    def velocidad(self):
        v = 230 * self.masa ** -0.08
        if self.sprint:
            v *= 1.6
        if self.boost_tiempo > 0:
            v *= 1.8
        if self.es_jugador:
            v *= self.factor_velocidad_admin
        return v if self.es_jugador else v * self.factor_vel

    def mover(self, dt):
        self.boost_tiempo = max(0.0, self.boost_tiempo - dt)
        self.escudo_tiempo = max(0.0, self.escudo_tiempo - dt)
        self.iman_tiempo = max(0.0, self.iman_tiempo - dt)
        self.fusion_tiempo = max(0.0, self.fusion_tiempo - dt)
        self.tiempo_mitosis_npc = max(0.0, self.tiempo_mitosis_npc - dt)
        if not self.es_jugador:
            # Los NPC se cansan: sprint limitado y luego descanso
            self.t_descanso = max(0.0, self.t_descanso - dt)
            if self.sprint and self.t_descanso <= 0:
                self.t_sprint += dt
                if self.t_sprint > SPRINT_NPC_MAX:
                    self.sprint = False
                    self.t_sprint = 0.0
                    self.t_descanso = SPRINT_NPC_ESPERA
            else:
                self.sprint = False
                self.t_sprint = 0.0
        if self.sprint and self.masa > MASA_MIN_SPRINT:
            self.masa -= self.masa * COSTO_SPRINT * dt
        else:
            self.sprint = False
        # Suaviza el cambio de dirección
        k = min(1.0, 6 * dt)
        self.dx += (self.tx - self.dx) * k
        self.dy += (self.ty - self.dy) * k
        v = self.velocidad()
        self.x = limitar(self.x + (self.dx * v + self.impulso_x) * dt, 0, MUNDO)
        self.y = limitar(self.y + (self.dy * v + self.impulso_y) * dt, 0, MUNDO)
        amortiguacion = math.exp(-4.0 * dt)
        self.impulso_x *= amortiguacion
        self.impulso_y *= amortiguacion
        # Las células grandes pierden masa poco a poco, así el mundo se equilibra
        if self.masa > 150:
            factor = (self.masa / 150) ** self.factor_decaimiento_grande
            self.masa -= self.masa * 0.0015 * factor * dt


class Juego:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITULO_JUEGO)
        pygame.display.set_mode((1000, 600), pygame.RESIZABLE)
        self.reloj = pygame.time.Clock()
        self.superficies = {}
        self.rejilla_celulas = RejillaCelulas()
        self.nombre_jugador = "Jugador"
        self.colores_jugador = [(255, 215, 90), (105, 210, 255), (255, 125, 170),
                                (135, 235, 145), (195, 145, 255)]
        self.color_jugador_indice = 0
        self.menu_nombre_activo = False
        self.menu_rect_nombre = pygame.Rect(0, 0, 0, 0)
        self.menu_rect_color_menos = pygame.Rect(0, 0, 0, 0)
        self.menu_rect_color_mas = pygame.Rect(0, 0, 0, 0)
        self.sonido_silenciado = False
        self.sonidos = {}
        self.crear_sonidos()
        self.archivo_record = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agario_record.json")
        self.record = self.cargar_record()
        self.nuevo_record = False
        self.record_guardado = False
        self.animaciones_comida = []
        self.animaciones_masa = []
        self.particulas = []
        self.f_peq = pygame.font.SysFont("consolas", 16)
        self.f_media = pygame.font.SysFont("consolas", 22, bold=True)
        self.f_grande = pygame.font.SysFont("consolas", 54, bold=True)
        self.cache_texto = {}
        self.config = {
            "cantidad_npc": N_NPC,
            "velocidad_jugador": 1.0,
            "masa_comida": MASA_COMIDA,
            "decaimiento_grande": 0.5,
            "intervalo_poder": INTERVALO_PODER,
            "duracion_poder": DURACION_PODER,
            "max_celulas": MAX_CELULAS_JUGADOR,
            "cantidad_virus": 35,
            "masa_min_virus": 150,
            "radio_virus": 58,
            "bolitas_virus": 8,
            "bono_virus": 0.05,
            "fragmentos_virus": 8,
            "limite_npc_virus": 2.0,
            "coste_eyectar": 15,
            "masa_bolita": 10,
            "masa_min_eyectar": 50,
            "radio_minimapa": 1500,
            "masa_min_mitosis_npc": 700,
        }
        self.opciones_admin = [
            ("NPC en el mundo", "cantidad_npc", 5, 200, 5, ""),
            ("Velocidad del jugador", "velocidad_jugador", 0.5, None, 0.1, "x"),
            ("Masa por comida", "masa_comida", 5, None, 5, ""),
            ("Decaimiento de células grandes", "decaimiento_grande", 0.0, 1.0, 0.05, ""),
            ("Intervalo entre poderes", "intervalo_poder", 1, 30, 1, " s"),
            ("Duración de poderes", "duracion_poder", 2, 30, 1, " s"),
            ("Máximo de células", "max_celulas", 2, 32, 1, ""),
            ("Virus en el mundo", "cantidad_virus", 0, 100, 5, ""),
            ("Masa mínima para virus", "masa_min_virus", 50, 500, 25, ""),
            ("Radio de virus", "radio_virus", 30, 100, 5, ""),
            ("Bolitas para dividir virus", "bolitas_virus", 3, 20, 1, ""),
            ("Bono de masa del virus", "bono_virus", 0.0, 0.5, 0.05, ""),
            ("Fragmentos máximos por virus", "fragmentos_virus", 2, 16, 1, ""),
            ("Límite NPC por virus (x cantidad)", "limite_npc_virus", 1.0, 4.0, 0.5, "x"),
            ("Coste de eyectar masa", "coste_eyectar", 5, 100, 5, ""),
            ("Masa de cada bolita", "masa_bolita", 1, 50, 1, ""),
            ("Masa mínima para eyectar", "masa_min_eyectar", 20, 300, 10, ""),
            ("Radio de detección del minimapa", "radio_minimapa", 300, 4000, 100, ""),
            ("Masa mínima de mitosis NPC", "masa_min_mitosis_npc", 300, 3000, 100, ""),
        ]
        self.admin_abierto = False
        self.admin_seleccion = 0
        self.admin_lineas = []
        self.menu_mostrar_controles = False
        self.menu_rect_jugar = pygame.Rect(0, 0, 0, 0)
        self.menu_rect_controles = pygame.Rect(0, 0, 0, 0)
        self.mensaje_poder = ""
        self.t_mensaje_poder = 0.0
        self.cursor_mundo = None
        self.actualizar_texto_admin()
        self.nuevo_juego()

    def crear_sonidos(self):
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            frecuencia = pygame.mixer.get_init()[0]
            for nombre, tonos in (("comer", (620, 900)), ("mitosis", (330, 660)),
                                  ("poder", (520, 780, 1040)), ("muerte", (440, 330, 220))):
                duracion = 0.16 if nombre != "muerte" else 0.35
                muestras = array.array("h")
                for i in range(int(frecuencia * duracion)):
                    t = i / frecuencia
                    tono = tonos[min(len(tonos) - 1, int(t / duracion * len(tonos)))]
                    envolvente = min(1.0, t * 35) * max(0.0, 1.0 - t / duracion)
                    muestras.append(int(12000 * envolvente * math.sin(math.tau * tono * t)))
                self.sonidos[nombre] = pygame.mixer.Sound(buffer=muestras)
        except pygame.error:
            self.sonidos = {}

    def reproducir_sonido(self, nombre):
        sonido = self.sonidos.get(nombre)
        if sonido and not self.sonido_silenciado:
            sonido.play()

    def cargar_record(self):
        try:
            with open(self.archivo_record, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            return {"masa_maxima": float(datos.get("masa_maxima", 0)),
                    "comidos": int(datos.get("comidos", 0)),
                    "tiempo": float(datos.get("tiempo", 0))}
        except (OSError, ValueError, TypeError):
            return {"masa_maxima": 0.0, "comidos": 0, "tiempo": 0.0}

    def guardar_record(self):
        if self.record_guardado:
            return
        self.record_guardado = True
        actuales = {"masa_maxima": self.masa_max,
                    "comidos": self.comidos_ronda,
                    "tiempo": self.tiempo}
        for llave, valor in actuales.items():
            if valor > self.record.get(llave, 0):
                self.record[llave] = valor
                self.nuevo_record = True
        if self.nuevo_record:
            try:
                with open(self.archivo_record, "w", encoding="utf-8") as archivo:
                    json.dump(self.record, archivo, ensure_ascii=False, indent=2)
            except OSError:
                pass

    def actualizar_animaciones(self, dt):
        activas = []
        for celula, comedor, restante, duracion, masa_inicial in self.animaciones_comida:
            restante -= dt
            if restante > 0:
                if comedor.viva:
                    k = min(1.0, 12 * dt)
                    celula.x += (comedor.x - celula.x) * k
                    celula.y += (comedor.y - celula.y) * k
                celula.masa = masa_inicial * (restante / duracion) ** 2
                activas.append((celula, comedor, restante, duracion, masa_inicial))
        self.animaciones_comida = activas

        activas = []
        for animacion in self.animaciones_masa:
            celula = animacion["celula"]
            if not celula.viva:
                continue
            animacion["tiempo"] += dt
            progreso = min(1.0, animacion["tiempo"] / animacion["duracion"])
            celula.masa = animacion["inicio"] + (animacion["fin"] - animacion["inicio"]) * progreso
            if progreso < 1:
                activas.append(animacion)
        self.animaciones_masa = activas

        activas = []
        for particula in self.particulas:
            particula["vida"] -= dt
            if particula["vida"] <= 0:
                continue
            particula["x"] += particula["dx"] * dt
            particula["y"] += particula["dy"] * dt
            particula["dx"] *= math.exp(-3 * dt)
            particula["dy"] *= math.exp(-3 * dt)
            activas.append(particula)
        self.particulas = activas

    def crear_particulas_comida(self, celula, cantidad):
        for _ in range(min(12, cantidad * 2)):
            angulo = random.random() * math.tau
            velocidad = random.uniform(70, 200)
            self.particulas.append({"x": celula.x, "y": celula.y,
                                    "dx": math.cos(angulo) * velocidad,
                                    "dy": math.sin(angulo) * velocidad,
                                    "color": color_aleatorio(0.8),
                                    "vida": random.uniform(0.18, 0.38),
                                    "vida_max": 0.38})

    # ---------- Creación del mundo ----------
    def masa_aleatoria(self):
        t = random.random()
        if t < 0.55:
            return random.uniform(8, 30)
        if t < 0.83:
            return random.uniform(60, 200)
        if t < 0.97:
            return random.uniform(300, 700)
        return random.uniform(900, 1800)

    def crear_npc(self, lejos_de=None):
        for _ in range(40):
            x, y = random.uniform(80, MUNDO - 80), random.uniform(80, MUNDO - 80)
            if lejos_de is None or math.hypot(x - lejos_de.x, y - lejos_de.y) > 1100:
                break
        return Celula(x, y, self.masa_aleatoria(), color_aleatorio(), random.choice(NOMBRES))

    def nuevo_juego(self):
        self.comida = RejillaComida()
        for _ in range(N_COMIDA):
            self.comida.agregar(self.nueva_comida())
        self.jugador = Celula(random.uniform(1500, MUNDO - 1500), random.uniform(1500, MUNDO - 1500),
                              MASA_INICIAL, self.colores_jugador[self.color_jugador_indice],
                              self.nombre_jugador.strip()[:16] or "Jugador", es_jugador=True)
        self.jugadores = [self.jugador]
        self.jugador.factor_velocidad_admin = self.config["velocidad_jugador"]
        self.celulas = [self.jugador]
        for _ in range(self.config["cantidad_npc"]):
            self.celulas.append(self.crear_npc(lejos_de=self.jugador))
        self.cola_respawn = []
        self.pausado = False
        self.cam_x, self.cam_y = self.jugador.x, self.jugador.y
        self.escala = 1.0
        self.tiempo = 0.0
        self.masa_max = MASA_INICIAL
        self.comidos_ronda = 0
        self.asesino = ""
        self.poderes = []
        self.virus = [self.crear_virus(lejos_de=self.jugador)
                      for _ in range(self.config["cantidad_virus"])]
        self.masa_eyectada = []
        self.animaciones_comida = []
        self.animaciones_masa = []
        self.particulas = []
        self.nuevo_record = False
        self.record_guardado = False
        self.tiempo_proximo_poder = self.config["intervalo_poder"]
        self.mensaje_poder = ""
        self.t_mensaje_poder = 0.0
        self.cursor_mundo = None
        self.estado = "menu"

    def nueva_comida(self):
        return Comida(random.uniform(0, MUNDO), random.uniform(0, MUNDO), color_aleatorio(0.8))

    def crear_virus(self, lejos_de=None):
        for _ in range(40):
            x, y = random.uniform(500, MUNDO - 500), random.uniform(500, MUNDO - 500)
            if lejos_de is None or math.hypot(x - lejos_de.x, y - lejos_de.y) > 700:
                break
        return Virus(x, y, self.config["radio_virus"])

    def masa_total_jugador(self):
        return sum(c.masa for c in self.jugadores if c.viva)

    def actualizar_jugador_principal(self):
        self.jugadores = [c for c in self.celulas if c.es_jugador and c.viva]
        if self.jugadores:
            self.jugador = max(self.jugadores, key=lambda c: c.masa)

    def empezar(self):
        self.estado = "jugando"
        self.pausado = False

    def direccion_hacia_cursor(self, celula):
        if self.cursor_mundo is not None:
            objetivo_x, objetivo_y = self.cursor_mundo
        else:
            w, h = pygame.display.get_surface().get_size()
            mx, my = pygame.mouse.get_pos()
            objetivo_x = self.cam_x + (mx - w / 2) / self.escala
            objetivo_y = self.cam_y + (my - h / 2) / self.escala
        dx, dy = normalizar(objetivo_x - celula.x, objetivo_y - celula.y)
        if dx == 0 and dy == 0:
            dx, dy = normalizar(celula.tx, celula.ty)
        return (dx, dy) if dx or dy else (1.0, 0.0)

    def mitosis(self, celula=None):
        vivos = [c for c in self.jugadores if c.viva]
        if len(vivos) >= self.config["max_celulas"]:
            self.aviso_poder("LÍMITE DE CÉLULAS")
            return False
        candidata = celula or max(vivos, key=lambda c: c.masa, default=None)
        if candidata is None or candidata.masa < 100:
            self.aviso_poder("NECESITAS 100 DE MASA PARA LA MITOSIS")
            return False

        masa_original = candidata.masa
        masa_nueva = masa_original / 2
        candidata.masa = masa_nueva
        dx, dy = self.direccion_hacia_cursor(candidata)
        distancia = candidata.r * 0.85
        clon = Celula(limitar(candidata.x + dx * distancia, 0, MUNDO),
                      limitar(candidata.y + dy * distancia, 0, MUNDO),
                      masa_nueva, candidata.color, candidata.nombre, es_jugador=True)
        clon.dx, clon.dy = candidata.dx, candidata.dy
        clon.tx, clon.ty = candidata.tx, candidata.ty
        clon.factor_velocidad_admin = self.config["velocidad_jugador"]
        fusion = min(18.0, 4.0 + masa_original * 0.02)
        clon.fusion_tiempo = candidata.fusion_tiempo = fusion
        clon.impulso_x, clon.impulso_y = dx * 850, dy * 850
        clon.boost_tiempo = candidata.boost_tiempo
        clon.escudo_tiempo = candidata.escudo_tiempo
        clon.iman_tiempo = candidata.iman_tiempo
        self.celulas.append(clon)
        self.jugadores.append(clon)
        if self.rejilla_celulas.casillas:
            self.rejilla_celulas.orden[clon] = len(self.rejilla_celulas.orden)
            self.rejilla_celulas.agregar(clon)
        self.actualizar_jugador_principal()
        self.aviso_poder("¡MITOSIS!")
        self.reproducir_sonido("mitosis")
        return True

    def mitosis_npc(self, celula, presa):
        npc_vivos = sum(not c.es_jugador and c.viva for c in self.celulas)
        if (npc_vivos >= self.config["cantidad_npc"] or
                celula.masa < self.config["masa_min_mitosis_npc"] or
                celula.tiempo_mitosis_npc > 0):
            return False
        dx, dy = normalizar(presa.x - celula.x, presa.y - celula.y)
        if dx == 0 and dy == 0:
            return False
        masa = celula.masa / 2
        celula.masa = masa
        clon = Celula(limitar(celula.x + dx * celula.r * 0.9, 0, MUNDO),
                      limitar(celula.y + dy * celula.r * 0.9, 0, MUNDO),
                      masa, celula.color, celula.nombre)
        clon.dx, clon.dy = celula.dx, celula.dy
        clon.tx, clon.ty = dx, dy
        clon.impulso_x, clon.impulso_y = dx * 720, dy * 720
        clon.agresividad = celula.agresividad
        celula.tiempo_mitosis_npc = 10.0
        self.celulas.append(clon)
        if self.rejilla_celulas.casillas:
            self.rejilla_celulas.orden[clon] = len(self.rejilla_celulas.orden)
            self.rejilla_celulas.agregar(clon)
        return True

    def eyectar_masa(self):
        vivos = [c for c in self.jugadores if c.viva]
        celula = max(vivos, key=lambda c: c.masa, default=None)
        if celula is None or celula.masa < self.config["masa_min_eyectar"]:
            return False
        coste = self.config["coste_eyectar"]
        if celula.masa - coste < 10:
            return False
        dx, dy = self.direccion_hacia_cursor(celula)
        celula.masa -= coste
        self.masa_eyectada.append(MasaEyectada(
            celula.x + dx * (celula.r + 8), celula.y + dy * (celula.r + 8),
            dx * 650, dy * 650, self.config["masa_bolita"], celula))
        return True

    def dividir_virus(self, virus, dx=1.0, dy=0.0):
        if len(self.virus) >= 100:
            virus.bolitas = 0
            return
        dx, dy = normalizar(dx, dy)
        if dx == 0 and dy == 0:
            dx, dy = 1.0, 0.0
        x = limitar(virus.x + dx * virus.r * 1.8, virus.r, MUNDO - virus.r)
        y = limitar(virus.y + dy * virus.r * 1.8, virus.r, MUNDO - virus.r)
        nuevo = Virus(x, y, virus.r)
        self.virus.append(nuevo)
        virus.bolitas = 0
        for celula in self.celulas:
            if math.hypot(celula.x - x, celula.y - y) < celula.r + nuevo.r + 35:
                ex, ey = normalizar(celula.x - x, celula.y - y)
                celula.impulso_x += ex * 500
                celula.impulso_y += ey * 500

    def actualizar_masa_eyectada(self, dt):
        restantes = []
        for bolita in self.masa_eyectada:
            bolita.vida -= dt
            bolita.x = limitar(bolita.x + bolita.dx * dt, 0, MUNDO)
            bolita.y = limitar(bolita.y + bolita.dy * dt, 0, MUNDO)
            bolita.dx *= math.exp(-1.8 * dt)
            bolita.dy *= math.exp(-1.8 * dt)
            if bolita.vida <= 0:
                continue
            virus_objetivo = next((v for v in self.virus
                                   if math.hypot(v.x - bolita.x, v.y - bolita.y) < v.r + 7), None)
            if virus_objetivo:
                virus_objetivo.bolitas += 1
                if virus_objetivo.bolitas >= self.config["bolitas_virus"]:
                    self.dividir_virus(virus_objetivo, bolita.dx, bolita.dy)
                continue
            comida_por = next((c for c in self.celulas if c is not bolita.propietario and c.viva
                               and math.hypot(c.x - bolita.x, c.y - bolita.y) < c.r + 7), None)
            if comida_por:
                comida_por.masa += bolita.masa
                continue
            restantes.append(bolita)
        self.masa_eyectada = restantes

    def explotar_celula(self, celula, virus):
        masa = celula.masa * (1 + self.config["bono_virus"])
        celula.viva = False
        if celula.es_jugador:
            vivos = [c for c in self.jugadores if c.viva]
            max_fragmentos = max(1, self.config["max_celulas"] - len(vivos))
        else:
            npc_vivos = sum(not c.es_jugador and c.viva for c in self.celulas)
            limite_npc = max(1, int(self.config["cantidad_npc"] * self.config["limite_npc_virus"]))
            max_fragmentos = max(1, limite_npc - npc_vivos)
        cantidad = min(max_fragmentos, self.config["fragmentos_virus"],
                       max(2, int(math.sqrt(celula.masa / 150) + 2)))
        masa_fragmento = masa / cantidad
        for i in range(cantidad):
            angulo = math.tau * i / cantidad + random.uniform(-0.12, 0.12)
            dx, dy = math.cos(angulo), math.sin(angulo)
            distancia_salida = virus.r + RADIO_K * math.sqrt(masa_fragmento) + 12
            fragmento = Celula(
                limitar(virus.x + dx * distancia_salida, 0, MUNDO),
                limitar(virus.y + dy * distancia_salida, 0, MUNDO),
                masa_fragmento, celula.color, celula.nombre, es_jugador=celula.es_jugador)
            fragmento.impulso_x, fragmento.impulso_y = dx * 620, dy * 620
            if celula.es_jugador:
                fragmento.factor_velocidad_admin = self.config["velocidad_jugador"]
                fragmento.fusion_tiempo = min(18.0, 4.0 + celula.masa * 0.02)
                self.jugadores.append(fragmento)
            self.celulas.append(fragmento)
        if celula.es_jugador:
            self.actualizar_jugador_principal()

    def resolver_virus(self):
        for celula in tuple(self.celulas):
            if not celula.viva or celula.masa <= self.config["masa_min_virus"]:
                continue
            virus = next((v for v in self.virus
                          if math.hypot(celula.x - v.x, celula.y - v.y) < celula.r + v.r), None)
            if virus:
                self.explotar_celula(celula, virus)

    def esta_refugiada(self, celula):
        return any(celula.r < v.r and math.hypot(celula.x - v.x, celula.y - v.y) < v.r - celula.r * 0.35
                   for v in self.virus)

    def aviso_poder(self, mensaje):
        self.mensaje_poder = mensaje
        self.t_mensaje_poder = 2.0

    def crear_poder(self):
        if len(self.poderes) >= 12:
            return
        tipo = random.choice(tuple(PODERES))
        x = limitar(self.jugador.x + random.uniform(-800, 800), 30, MUNDO - 30)
        y = limitar(self.jugador.y + random.uniform(-800, 800), 30, MUNDO - 30)
        self.poderes.append(Potenciador(x, y, tipo))

    def aplicar_poder(self, poder, celula):
        duracion = self.config["duracion_poder"]
        jugadores = [c for c in self.jugadores if c.viva]
        if poder.tipo == "mitosis":
            self.mitosis(celula)
        elif poder.tipo == "turbo":
            for c in jugadores:
                c.boost_tiempo = duracion
            self.aviso_poder("TURBO: velocidad aumentada")
        elif poder.tipo == "escudo":
            for c in jugadores:
                c.escudo_tiempo = duracion
            self.aviso_poder("ESCUDO: protección temporal")
        elif poder.tipo == "iman":
            for c in jugadores:
                c.iman_tiempo = duracion
            self.aviso_poder("IMÁN: atraes más comida")
        elif poder.tipo == "masa":
            objetivo = max(jugadores, key=lambda c: c.masa)
            self.animaciones_masa = [a for a in self.animaciones_masa if a["celula"] is not objetivo]
            self.animaciones_masa.append({"celula": objetivo, "inicio": objetivo.masa,
                                          "fin": objetivo.masa * 1.3, "tiempo": 0.0,
                                          "duracion": 0.5})
            self.aviso_poder("MASA: +30% para tu célula mayor")
        elif poder.tipo == "portal":
            cx, cy = self.jugador.x, self.jugador.y
            nx, ny = random.uniform(300, MUNDO - 300), random.uniform(300, MUNDO - 300)
            for c in jugadores:
                c.x = limitar(nx + c.x - cx, c.r, MUNDO - c.r)
                c.y = limitar(ny + c.y - cy, c.r, MUNDO - c.r)
            self.aviso_poder("PORTAL: ¡te has teletransportado!")
        elif poder.tipo == "onda":
            movidos = 0
            for npc in self.celulas:
                if npc.es_jugador:
                    continue
                dx, dy = npc.x - celula.x, npc.y - celula.y
                d = math.hypot(dx, dy)
                if d < 900:
                    nx, ny = normalizar(dx, dy)
                    empuje = 900 - d
                    npc.impulso_x += nx * empuje * 3
                    npc.impulso_y += ny * empuje * 3
                    movidos += 1
            self.aviso_poder(f"ONDA: apartaste {movidos} rivales")

    def ajustar_opcion_admin(self, direccion):
        etiqueta, llave, minimo, maximo, paso, unidad = self.opciones_admin[self.admin_seleccion]
        anterior = self.config[llave]
        nuevo = max(minimo, anterior + direccion * paso)
        if maximo is not None:
            nuevo = min(maximo, nuevo)
        nuevo = round(nuevo, 1) if isinstance(paso, float) or paso < 1 else int(nuevo)
        if nuevo == anterior:
            return
        self.config[llave] = nuevo

        if llave == "cantidad_npc":
            npc = [c for c in self.celulas if not c.es_jugador]
            if nuevo > len(npc):
                self.celulas.extend(self.crear_npc(lejos_de=self.jugador) for _ in range(nuevo - len(npc)))
            elif nuevo < len(npc):
                quitar = set(random.sample(npc, len(npc) - nuevo))
                self.celulas = [c for c in self.celulas if c not in quitar]
        elif llave == "cantidad_virus":
            if nuevo > len(self.virus):
                self.virus.extend(self.crear_virus(lejos_de=self.jugador)
                                  for _ in range(nuevo - len(self.virus)))
            elif nuevo < len(self.virus):
                self.virus = self.virus[:nuevo]
        elif llave == "radio_virus":
            for virus in self.virus:
                virus.r = nuevo
        elif llave == "velocidad_jugador":
            for c in self.jugadores:
                c.factor_velocidad_admin = nuevo
        elif llave == "intervalo_poder":
            self.tiempo_proximo_poder = min(self.tiempo_proximo_poder, nuevo)
        elif llave == "duracion_poder":
            factor = nuevo / anterior
            for c in self.jugadores:
                c.boost_tiempo *= factor
                c.escudo_tiempo *= factor
                c.iman_tiempo *= factor
        self.actualizar_texto_admin()

    def actualizar_texto_admin(self):
        self.admin_lineas = []
        for i, (etiqueta, llave, minimo, maximo, paso, unidad) in enumerate(self.opciones_admin):
            valor = self.config[llave]
            formato = f"{valor:.1f}" if paso < 1 else f"{valor:.0f}"
            marca = "▶" if i == self.admin_seleccion else " "
            self.admin_lineas.append(f"{marca}  {etiqueta}: {formato}{unidad}")

    def superficie(self, nombre, tamano, relleno):
        """Reutiliza superficies transparentes y solo las reemplaza si cambia su tamaño."""
        superficie = self.superficies.get(nombre)
        if superficie is None or superficie.get_size() != tamano:
            superficie = pygame.Surface(tamano, pygame.SRCALPHA)
            self.superficies[nombre] = superficie
        superficie.fill(relleno)
        return superficie

    # ---------- Entrada del jugador ----------
    def leer_entrada(self):
        """Devuelve (dir_x, dir_y, sprint). Separado para poder probarlo."""
        teclas = pygame.key.get_pressed()
        kx = (teclas[pygame.K_d] or teclas[pygame.K_RIGHT]) - (teclas[pygame.K_a] or teclas[pygame.K_LEFT])
        ky = (teclas[pygame.K_s] or teclas[pygame.K_DOWN]) - (teclas[pygame.K_w] or teclas[pygame.K_UP])
        sprint = bool(teclas[pygame.K_SPACE])
        if kx or ky:
            self.cursor_mundo = None
            dx, dy = normalizar(kx, ky)
            return dx, dy, sprint
        w, h = pygame.display.get_surface().get_size()
        mx, my = pygame.mouse.get_pos()
        vx, vy = mx - w / 2, my - h / 2
        dist = math.hypot(vx, vy)
        if dist < 6:
            self.cursor_mundo = (self.cam_x, self.cam_y)
            return 0.0, 0.0, sprint
        zona = max(40, self.jugador.r * self.escala)   # cerca del centro va más despacio
        fuerza = min(1.0, dist / zona)
        dx, dy = normalizar(vx, vy)
        self.cursor_mundo = (self.cam_x + vx / self.escala, self.cam_y + vy / self.escala)
        return dx * fuerza, dy * fuerza, sprint

    # ---------- IA de los NPC ----------
    def empuje_borde(self, c):
        """Vector que aleja al NPC de los bordes del mundo, para que no se atasque en las esquinas."""
        margen = 350
        ex = ey = 0.0
        if c.x < margen:
            ex += (margen - c.x) / margen
        if c.x > MUNDO - margen:
            ex -= (c.x - (MUNDO - margen)) / margen
        if c.y < margen:
            ey += (margen - c.y) / margen
        if c.y > MUNDO - margen:
            ey -= (c.y - (MUNDO - margen)) / margen
        return ex, ey

    def pensar(self, c):
        percep = 200 + c.r * 2
        amenaza = presa = None
        d_am = d_pr = 1e9
        rango = percep + c.r + self.rejilla_celulas.radio_maximo
        for o in self.rejilla_celulas.cercanas(c.x, c.y, rango):
            if o is c:
                continue
            d = math.hypot(o.x - c.x, o.y - c.y) - o.r - c.r   # distancia entre bordes
            if d > percep:
                continue
            if o.masa > c.masa * VENTAJA:
                if d < d_am:
                    amenaza, d_am = o, d
            elif c.masa > o.masa * VENTAJA and o.masa > c.masa * 0.06:
                if d < d_pr:
                    presa, d_pr = o, d

        c.sprint = False
        ex, ey = self.empuje_borde(c)

        if amenaza and d_am < 140 + amenaza.r * 0.8:
            # HUIR
            vx, vy = normalizar(c.x - amenaza.x, c.y - amenaza.y)
            vx, vy = vx + ex * 1.3, vy + ey * 1.3
            c.sprint = d_am < 90 and c.masa > 60 and c.t_descanso <= 0
        elif presa and c.agresividad > 0.78 and d_pr < percep * c.agresividad:
            # CAZAR (apuntando un poco adelante de donde va la presa)
            if c.agresividad > 0.92 and d_pr > c.r * 2.5:
                self.mitosis_npc(c, presa)
            t = max(0.0, d_pr) / max(c.velocidad(), 1)
            px = presa.x + presa.dx * presa.velocidad() * t * 0.6
            py = presa.y + presa.dy * presa.velocidad() * t * 0.6
            vx, vy = normalizar(px - c.x, py - c.y)
            vx, vy = vx + ex * 0.5, vy + ey * 0.5
            c.sprint = d_pr < c.r * 2.5 and c.masa > 60 and presa.masa * 1.3 < c.masa and c.t_descanso <= 0
        else:
            comida = self.comida.mas_cercana(c.x, c.y, percep)
            if comida:
                vx, vy = normalizar(comida.x - c.x, comida.y - c.y)
            else:
                # VAGAR hacia un punto al azar
                c.t_vagar -= 0.25
                if c.obj_x is None or c.t_vagar <= 0 or math.hypot(c.obj_x - c.x, c.obj_y - c.y) < 80:
                    c.obj_x = limitar(c.x + random.uniform(-1500, 1500), 100, MUNDO - 100)
                    c.obj_y = limitar(c.y + random.uniform(-1500, 1500), 100, MUNDO - 100)
                    c.t_vagar = random.uniform(4, 8)
                vx, vy = normalizar(c.obj_x - c.x, c.obj_y - c.y)
            vx, vy = vx + ex * 0.5, vy + ey * 0.5
        if c.masa > self.config["masa_min_virus"]:
            for virus in self.virus:
                dx, dy = c.x - virus.x, c.y - virus.y
                distancia = math.hypot(dx, dy)
                margen = c.r + virus.r + 180
                if 1e-6 < distancia < margen:
                    nx, ny = dx / distancia, dy / distancia
                    fuerza = (margen - distancia) / margen * 1.8
                    vx += nx * fuerza
                    vy += ny * fuerza
        c.tx, c.ty = normalizar(vx, vy)

    # ---------- Actualización ----------
    def actualizar(self, dt):
        if self.pausado or self.estado == "menu" or self.admin_abierto:
            return
        self.actualizar_animaciones(dt)
        if self.estado == "jugando":
            self.tiempo += dt
            dx, dy, sprint = self.leer_entrada()
            for j in self.jugadores:
                if self.cursor_mundo is not None:
                    mx, my = self.cursor_mundo
                    vx, vy = mx - j.x, my - j.y
                    distancia = math.hypot(vx, vy)
                    zona = max(40, j.r * self.escala)
                    fuerza = min(1.0, distancia / zona)
                    ix, iy = normalizar(vx, vy)
                    j.tx, j.ty = ix * fuerza, iy * fuerza
                else:
                    j.tx, j.ty = dx, dy
                if j is not self.jugador and j.fusion_tiempo <= 0:
                    fx, fy = normalizar(self.jugador.x - j.x, self.jugador.y - j.y)
                    j.tx, j.ty = normalizar(j.tx + fx * 0.65, j.ty + fy * 0.65)
                if j.fusion_tiempo > 0:
                    rx = ry = 0.0
                    for otra in self.jugadores:
                        if otra is j or not otra.viva:
                            continue
                        vx, vy = j.x - otra.x, j.y - otra.y
                        distancia = math.hypot(vx, vy)
                        minimo = j.r + otra.r + 25
                        if 1e-6 < distancia < minimo:
                            fuerza = (minimo - distancia) / minimo
                            rx += vx / distancia * fuerza
                            ry += vy / distancia * fuerza
                    j.tx, j.ty = normalizar(j.tx + rx * 0.8, j.ty + ry * 0.8)
                j.sprint = sprint and j.masa > MASA_MIN_SPRINT
                j.factor_velocidad_admin = self.config["velocidad_jugador"]
            self.tiempo_proximo_poder -= dt
            if self.tiempo_proximo_poder <= 0:
                self.crear_poder()
                self.tiempo_proximo_poder = self.config["intervalo_poder"]
            if self.t_mensaje_poder > 0:
                self.t_mensaje_poder = max(0, self.t_mensaje_poder - dt)

        self.rejilla_celulas.reconstruir(self.celulas)
        for c in tuple(self.celulas):
            c.factor_decaimiento_grande = self.config["decaimiento_grande"]
            if not c.es_jugador:
                c.t_pensar -= dt
                if c.t_pensar <= 0:
                    self.pensar(c)
                    c.t_pensar = random.uniform(0.2, 0.3)
            x_anterior, y_anterior = c.x, c.y
            c.mover(dt)
            self.rejilla_celulas.mover(c, x_anterior, y_anterior)
            radio_comida = c.r * (1.6 if c.es_jugador and c.iman_tiempo > 0 else 0.9)
            n = self.comida.comer(c.x, c.y, radio_comida)
            if n:
                c.masa += n * self.config["masa_comida"]
                self.rejilla_celulas.radio_maximo = max(self.rejilla_celulas.radio_maximo, c.r)
                for _ in range(n):
                    self.comida.agregar(self.nueva_comida())
                if c.es_jugador:
                    self.crear_particulas_comida(c, n)
                    self.reproducir_sonido("comer")
            if c.es_jugador and self.estado == "jugando":
                poder = next((p for p in self.poderes
                              if math.hypot(p.x - c.x, p.y - c.y) < c.r + 22), None)
                if poder:
                    self.poderes.remove(poder)
                    self.aplicar_poder(poder, c)
                    self.reproducir_sonido("poder")
            if not c.es_jugador:
                c.masa = min(c.masa, MASA_MAX_NPC)

        self.actualizar_masa_eyectada(dt)
        self.resolver_virus()
        self.resolver_comidas()

        # Reaparición de NPC comidos, para mantener siempre el mismo número
        for i in range(len(self.cola_respawn)):
            self.cola_respawn[i] -= dt
        pendientes = [t for t in self.cola_respawn if t > 0]
        faltan_respawns = len(self.cola_respawn) - len(pendientes)
        npc_actuales = sum(not c.es_jugador for c in self.celulas)
        for _ in range(min(faltan_respawns, max(0, self.config["cantidad_npc"] - npc_actuales))):
            self.celulas.append(self.crear_npc(lejos_de=self.jugador))
        self.cola_respawn = pendientes

        # Cámara y zoom: al crecer, la cámara se aleja
        if self.estado == "jugando" and self.jugadores:
            self.actualizar_jugador_principal()
            total = self.masa_total_jugador()
            self.cam_x = sum(c.x * c.masa for c in self.jugadores) / max(total, 1e-6)
            self.cam_y = sum(c.y * c.masa for c in self.jugadores) / max(total, 1e-6)
            self.masa_max = max(self.masa_max, self.masa_total_jugador())
            ancho, alto = pygame.display.get_surface().get_size()
            extension = max((math.hypot(c.x - self.cam_x, c.y - self.cam_y) + c.r
                             for c in self.jugadores), default=self.jugador.r) + 100
            objetivo = limitar(min(ancho, alto) / (2 * extension), 0.18, 1.1)
            self.escala += (objetivo - self.escala) * min(1.0, 3 * dt)

    def resolver_comidas(self):
        celulas = self.celulas
        self.rejilla_celulas.reconstruir(celulas)
        for a in celulas:
            if not a.viva:
                continue
            for b in self.rejilla_celulas.cercanas(a.x, a.y, a.r):
                if a is b or not b.viva:
                    continue
                if a.es_jugador and b.es_jugador:
                    continue
                if b.es_jugador and self.tiempo < INMUNIDAD_INICIAL:
                    continue
                if b.es_jugador and b.escudo_tiempo > 0:
                    continue
                if self.esta_refugiada(b) and not any(
                        math.hypot(a.x - v.x, a.y - v.y) <= a.r + v.r
                        for v in self.virus
                        if b.r < v.r and math.hypot(b.x - v.x, b.y - v.y) < v.r - b.r * 0.35):
                    continue
                if a.masa > b.masa * VENTAJA:
                    limite = a.r - b.r * 0.4
                    if (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < limite * limite:
                        a.masa += b.masa
                        a.comidos += 1
                        if a.es_jugador and not b.es_jugador:
                            self.comidos_ronda += 1
                        b.viva = False
                        self.animaciones_comida.append((b, a, 0.2, 0.2, b.masa))
                        if b.es_jugador:
                            self.asesino = a.nombre
                            self.reproducir_sonido("muerte")
                        else:
                            if a.es_jugador:
                                self.reproducir_sonido("comer")
                            self.cola_respawn.append(random.uniform(2, 6))

        # Las células creadas por mitosis vuelven a fusionarse tras su espera.
        jugadores = [c for c in celulas if c.es_jugador and c.viva]
        for i, a in enumerate(jugadores):
            if not a.viva or a.fusion_tiempo > 0:
                continue
            for b in jugadores[i + 1:]:
                if not b.viva or b.fusion_tiempo > 0:
                    continue
                distancia = math.hypot(a.x - b.x, a.y - b.y)
                if distancia < min(a.r, b.r) * 0.55:
                    a.masa += b.masa
                    a.comidos += b.comidos
                    b.viva = False
                    break
        self.celulas = [c for c in celulas if c.viva]
        self.actualizar_jugador_principal()
        if not self.jugadores and self.estado == "jugando":
            self.estado = "muerto"
            self.guardar_record()

    # ---------- Dibujo ----------
    def texto(self, fuente, contenido, color):
        clave = (id(fuente), contenido, color)
        img = self.cache_texto.get(clave)
        if img is None:
            if len(self.cache_texto) > 600:
                self.cache_texto.clear()
            img = fuente.render(contenido, True, color)
            self.cache_texto[clave] = img
        return img

    def poner_texto(self, pantalla, fuente, contenido, color, pos, centrado=False, derecha=False):
        img = self.texto(fuente, contenido, color)
        rect = img.get_rect()
        if centrado:
            rect.center = pos
        elif derecha:
            rect.topright = pos
        else:
            rect.topleft = pos
        pantalla.blit(img, rect)

    def nombre_con_sombra(self, pantalla, fuente, contenido, centro):
        """Texto blanco con sombra oscura, para que se lea sobre cualquier color."""
        sombra = self.texto(fuente, contenido, (20, 20, 30))
        img = self.texto(fuente, contenido, BLANCO)
        pantalla.blit(sombra, sombra.get_rect(center=(centro[0] + 1, centro[1] + 1)))
        pantalla.blit(img, img.get_rect(center=centro))

    def dibujar_menu_inicio(self, pantalla, w, h):
        oscurecedor = self.superficie("velo_menu", (w, h), (7, 9, 20, 195))
        pantalla.blit(oscurecedor, (0, 0))
        centro_x, centro_y = w // 2, h // 2
        panel = pygame.Rect(centro_x - 330, centro_y - 280, 660, 560)
        pygame.draw.rect(pantalla, (17, 23, 43), panel, border_radius=24)
        pygame.draw.rect(pantalla, (70, 94, 145), panel, width=2, border_radius=24)

        # Motas decorativas alrededor del panel principal.
        animacion = pygame.time.get_ticks() * 0.00008
        for i in range(22):
            angulo = i * math.tau / 22 + animacion
            x = int(centro_x + math.cos(angulo) * (360 + 12 * math.sin(animacion * 10 + i)))
            y = int(centro_y + math.sin(angulo) * 270)
            pygame.draw.circle(pantalla, (75, 115, 180), (x, y), 2 + i % 3)

        titulo = self.f_grande.render(TITULO_JUEGO.upper(), True, (255, 220, 100))
        pantalla.blit(titulo, titulo.get_rect(center=(centro_x, centro_y - 220)))
        subtitulo = self.f_media.render("CRECE · DIVÍDETE · SOBREVIVE", True, (170, 194, 235))
        pantalla.blit(subtitulo, subtitulo.get_rect(center=(centro_x, centro_y - 175)))
        descripcion = self.f_peq.render("Un mundo vivo lleno de rivales y poderes inesperados", True, GRIS)
        pantalla.blit(descripcion, descripcion.get_rect(center=(centro_x, centro_y - 146)))

        self.poner_texto(pantalla, self.f_peq, "NOMBRE", GRIS,
                         (centro_x - 145, centro_y - 128))
        self.menu_rect_nombre = pygame.Rect(centro_x - 145, centro_y - 110, 290, 34)
        tono_nombre = (60, 77, 112) if self.menu_nombre_activo else (37, 49, 76)
        pygame.draw.rect(pantalla, tono_nombre, self.menu_rect_nombre, border_radius=9)
        pygame.draw.rect(pantalla, (105, 140, 190), self.menu_rect_nombre, 1, border_radius=9)
        nombre = self.nombre_jugador + ("|" if self.menu_nombre_activo else "")
        self.poner_texto(pantalla, self.f_peq, nombre[:17], BLANCO,
                         (self.menu_rect_nombre.x + 12, self.menu_rect_nombre.y + 9))

        self.menu_rect_color_menos = pygame.Rect(centro_x - 72, centro_y - 65, 38, 30)
        self.menu_rect_color_mas = pygame.Rect(centro_x + 34, centro_y - 65, 38, 30)
        pygame.draw.rect(pantalla, (37, 49, 76), self.menu_rect_color_menos, border_radius=8)
        pygame.draw.rect(pantalla, (37, 49, 76), self.menu_rect_color_mas, border_radius=8)
        self.poner_texto(pantalla, self.f_peq, "<", BLANCO, self.menu_rect_color_menos.center, centrado=True)
        self.poner_texto(pantalla, self.f_peq, ">", BLANCO, self.menu_rect_color_mas.center, centrado=True)
        pygame.draw.circle(pantalla, self.colores_jugador[self.color_jugador_indice],
                           (centro_x, centro_y - 50), 12)
        self.poner_texto(pantalla, self.f_peq, "COLOR", GRIS,
                         (centro_x - 145, centro_y - 58))

        self.menu_rect_jugar = pygame.Rect(centro_x - 145, centro_y - 28, 290, 52)
        hover = self.menu_rect_jugar.collidepoint(pygame.mouse.get_pos())
        boton = (255, 197, 75) if hover else (235, 163, 55)
        pygame.draw.rect(pantalla, boton, self.menu_rect_jugar, border_radius=15)
        pygame.draw.rect(pantalla, (255, 230, 160), self.menu_rect_jugar, width=2, border_radius=15)
        texto_jugar = self.f_media.render("JUGAR", True, (35, 28, 24))
        pantalla.blit(texto_jugar, texto_jugar.get_rect(center=self.menu_rect_jugar.center))

        self.menu_rect_controles = pygame.Rect(centro_x - 145, centro_y + 34, 290, 42)
        pygame.draw.rect(pantalla, (37, 49, 76), self.menu_rect_controles, border_radius=12)
        pygame.draw.rect(pantalla, (75, 95, 135), self.menu_rect_controles, width=1, border_radius=12)
        etiqueta = "OCULTAR CONTROLES" if self.menu_mostrar_controles else "VER CONTROLES"
        texto_controles = self.f_peq.render(etiqueta, True, BLANCO)
        pantalla.blit(texto_controles, texto_controles.get_rect(center=self.menu_rect_controles.center))

        if self.menu_mostrar_controles:
            controles = ["Mouse o WASD / flechas: mover", "ESPACIO: sprint · Q: mitosis · W: masa",
                         "P: pausa · F1: admin · M: sonido"]
            for i, linea in enumerate(controles):
                img = self.f_peq.render(linea, True, (195, 205, 225))
                pantalla.blit(img, img.get_rect(center=(centro_x, centro_y + 113 + i * 23)))
        else:
            nota = self.f_peq.render("Recoge orbes de poder y cambia el rumbo de la partida", True, (195, 205, 225))
            pantalla.blit(nota, nota.get_rect(center=(centro_x, centro_y + 120)))
        pie = self.f_peq.render("ENTER: comenzar · F1: administración", True, GRIS)
        pantalla.blit(pie, pie.get_rect(center=(centro_x, centro_y + 250)))

    def dibujar_admin(self, pantalla, w, h):
        oscurecedor = self.superficie("velo_admin", (w, h), (4, 7, 15, 205))
        pantalla.blit(oscurecedor, (0, 0))
        panel_alto = min(h - 20, 160 + len(self.admin_lineas) * 22)
        panel = pygame.Rect(w // 2 - 350, h // 2 - panel_alto // 2, 700, panel_alto)
        pygame.draw.rect(pantalla, (17, 23, 43), panel, border_radius=20)
        pygame.draw.rect(pantalla, (87, 119, 176), panel, width=2, border_radius=20)
        titulo = self.f_media.render("ADMINISTRACIÓN DEL MUNDO", True, (255, 220, 100))
        pantalla.blit(titulo, titulo.get_rect(center=(w // 2, panel.y + 48)))
        detalle = self.f_peq.render("Los cambios se aplican al instante", True, GRIS)
        pantalla.blit(detalle, detalle.get_rect(center=(w // 2, panel.y + 80)))
        for i, linea in enumerate(self.admin_lineas):
            tono = (125, 220, 255) if i == self.admin_seleccion else BLANCO
            img = self.f_peq.render(linea, True, tono)
            pantalla.blit(img, (panel.x + 42, panel.y + 96 + i * 22))
        ayuda = self.f_peq.render("↑ / ↓ elegir   ·   ← / → cambiar   ·   F1 o ESC cerrar", True, (190, 202, 224))
        pantalla.blit(ayuda, ayuda.get_rect(center=(w // 2, panel.bottom - 35)))

    def dibujar_mundo(self, pantalla, w, h):
        s = self.escala
        cx, cy = self.cam_x, self.cam_y
        mitad_x, mitad_y = w / (2 * s), h / (2 * s)
        x_ini, x_fin = cx - mitad_x, cx + mitad_x
        y_ini, y_fin = cy - mitad_y, cy + mitad_y

        def px(x):
            return (x - cx) * s + w / 2

        def py(y):
            return (y - cy) * s + h / 2

        pantalla.fill(FUERA)
        rect_mundo = pygame.Rect(int(px(0)), int(py(0)), int(MUNDO * s), int(MUNDO * s))
        pygame.draw.rect(pantalla, FONDO, rect_mundo)

        # Cuadrícula
        paso = 100
        while paso * s < 18:
            paso *= 2
        k = max(0, int(x_ini // paso))
        while k * paso <= min(MUNDO, x_fin):
            x = int(px(k * paso))
            pygame.draw.line(pantalla, LINEA_GRILLA, (x, max(0, int(py(0)))), (x, min(h, int(py(MUNDO)))))
            k += 1
        k = max(0, int(y_ini // paso))
        while k * paso <= min(MUNDO, y_fin):
            y = int(py(k * paso))
            pygame.draw.line(pantalla, LINEA_GRILLA, (max(0, int(px(0))), y), (min(w, int(px(MUNDO))), y))
            k += 1
        pygame.draw.rect(pantalla, BORDE_MUNDO, rect_mundo, 4)

        # Comida
        rc = max(2, int(RADIO_COMIDA * s))
        for f in self.comida.en_rectangulo(x_ini - 20, y_ini - 20, x_fin + 20, y_fin + 20):
            pygame.draw.circle(pantalla, f.color, (int(px(f.x)), int(py(f.y))), rc)

        # Potenciadores del mundo
        for poder in self.poderes:
            sx, sy = int(px(poder.x)), int(py(poder.y))
            if not (-30 <= sx <= w + 30 and -30 <= sy <= h + 30):
                continue
            etiqueta, tono = PODERES[poder.tipo]
            pulso = int(3 * math.sin(pygame.time.get_ticks() * 0.006 + poder.fase))
            radio = max(8, int((18 + pulso) * s))
            pygame.draw.circle(pantalla, tono, (sx, sy), radio + 4, max(1, int(2 * s)))
            pygame.draw.circle(pantalla, tono, (sx, sy), max(4, radio // 2))
            self.poner_texto(pantalla, self.f_peq, etiqueta, BLANCO, (sx, sy - radio - 10), centrado=True)

        for virus in self.virus:
            sx, sy = int(px(virus.x)), int(py(virus.y))
            radio = max(5, int(virus.r * s))
            if not (-radio <= sx <= w + radio and -radio <= sy <= h + radio):
                continue
            pygame.draw.circle(pantalla, (74, 175, 92), (sx, sy), radio)
            for punta in range(12):
                angulo = math.tau * punta / 12
                x2 = int(sx + math.cos(angulo) * radio * 1.35)
                y2 = int(sy + math.sin(angulo) * radio * 1.35)
                pygame.draw.line(pantalla, (135, 225, 125), (sx, sy), (x2, y2), max(2, int(5 * s)))
            pygame.draw.circle(pantalla, (35, 105, 58), (sx, sy), max(2, int(radio * 0.58)))

        for bolita in self.masa_eyectada:
            sx, sy = int(px(bolita.x)), int(py(bolita.y))
            pygame.draw.circle(pantalla, (255, 224, 125), (sx, sy), max(2, int(7 * s)))

        # Células (las más grandes encima)
        for c in sorted(self.celulas, key=lambda c: c.masa):
            rr = c.r * s
            sx, sy = px(c.x), py(c.y)
            if sx + rr < 0 or sx - rr > w or sy + rr < 0 or sy - rr > h:
                continue
            borde = BLANCO if c.es_jugador else oscurecer(c.color)
            pygame.draw.circle(pantalla, borde, (int(sx), int(sy)), max(2, int(rr)))
            grosor = max(2, int(rr * 0.07))
            pygame.draw.circle(pantalla, c.color, (int(sx), int(sy)), max(1, int(rr - grosor)))
            if c.es_jugador and self.tiempo < INMUNIDAD_INICIAL and self.estado == "jugando":
                pulso = 4 + int(3 * math.sin(self.tiempo * 8))
                pygame.draw.circle(pantalla, (120, 220, 255), (int(sx), int(sy)), max(2, int(rr)) + pulso, 2)
            if c.es_jugador and c.escudo_tiempo > 0:
                pygame.draw.circle(pantalla, (120, 255, 190), (int(sx), int(sy)), max(2, int(rr)) + 7, 3)
            if rr > 22:
                fuente = self.f_media if rr > 45 else self.f_peq
                self.nombre_con_sombra(pantalla, fuente, c.nombre, (sx, sy))
                if rr > 45:
                    self.nombre_con_sombra(pantalla, self.f_peq, str(int(c.masa)), (sx, sy + 20))

        for celula, _, _, _, _ in self.animaciones_comida:
            sx, sy = int(px(celula.x)), int(py(celula.y))
            rr = max(2, int(celula.r * s))
            pygame.draw.circle(pantalla, oscurecer(celula.color), (sx, sy), rr)
            pygame.draw.circle(pantalla, celula.color, (sx, sy), max(1, int(rr * 0.88)))
        for particula in self.particulas:
            sx, sy = int(px(particula["x"])), int(py(particula["y"]))
            radio = max(1, int(3 * s * particula["vida"] / particula["vida_max"]))
            pygame.draw.circle(pantalla, particula["color"], (sx, sy), radio)

    def dibujar_minimapa(self, pantalla, w, h):
        lado = 150
        mini = self.superficie("minimapa", (lado, lado), (0, 0, 0, 140))
        f = lado / MUNDO
        for c in self.celulas:
            if c.es_jugador:
                continue
            if math.hypot(c.x - self.jugador.x, c.y - self.jugador.y) > self.config["radio_minimapa"]:
                continue
            pygame.draw.circle(mini, c.color, (int(c.x * f), int(c.y * f)), max(2, int(c.r * f * 1.5)))
        if self.estado == "jugando":
            pygame.draw.circle(mini, BLANCO, (int(self.jugador.x * f), int(self.jugador.y * f)), 4)
            vista = pygame.Rect(int((self.cam_x - w / (2 * self.escala)) * f),
                                int((self.cam_y - h / (2 * self.escala)) * f),
                                int(w / self.escala * f), int(h / self.escala * f))
            pygame.draw.rect(mini, (255, 255, 255, 120), vista, 1)
        pygame.draw.rect(mini, GRIS, mini.get_rect(), 1)
        pantalla.blit(mini, (w - lado - 12, h - lado - 12))

    def dibujar_interfaz(self, pantalla, w, h):
        j = self.jugador
        orden = sorted(self.celulas, key=lambda c: -c.masa)

        # Ranking
        panel = self.superficie("panel_ranking", (190, 150), (0, 0, 0, 120))
        pantalla.blit(panel, (w - 202, 12))
        self.poner_texto(pantalla, self.f_media, "Ranking", BLANCO, (w - 107, 24), centrado=True)
        for i, c in enumerate(orden[:5]):
            color = (255, 215, 90) if c.es_jugador else BLANCO
            self.poner_texto(pantalla, self.f_peq, f"{i + 1}. {c.nombre}", color, (w - 195, 44 + i * 22))
            self.poner_texto(pantalla, self.f_peq, str(int(c.masa)), color, (w - 18, 44 + i * 22), derecha=True)

        # Datos del jugador
        if self.estado == "jugando":
            puesto = orden.index(j) + 1
            self.poner_texto(pantalla, self.f_media, f"Masa: {int(self.masa_total_jugador())}", BLANCO, (14, 12))
            self.poner_texto(pantalla, self.f_peq, f"Puesto: {puesto} de {len(orden)}", GRIS, (14, 42))
            self.poner_texto(pantalla, self.f_peq,
                             f"Comidos: {self.comidos_ronda}  ·  Células: {len(self.jugadores)}", GRIS, (14, 62))
            if j.sprint:
                self.poner_texto(pantalla, self.f_peq, "¡SPRINT!", (255, 160, 80), (14, 82))
            if self.tiempo < INMUNIDAD_INICIAL:
                resto = INMUNIDAD_INICIAL - self.tiempo
                self.poner_texto(pantalla, self.f_peq, f"Protegido: {resto:.0f} s", (120, 220, 255), (14, 102))
            activos = []
            for nombre, atributo in (("TURBO", "boost_tiempo"), ("ESCUDO", "escudo_tiempo"),
                                     ("IMÁN", "iman_tiempo")):
                restante = max((getattr(c, atributo) for c in self.jugadores), default=0)
                if restante > 0:
                    activos.append(f"{nombre} {restante:.0f}s")
            if activos:
                self.poner_texto(pantalla, self.f_peq, "  ·  ".join(activos), (255, 220, 120), (14, 126))
            if self.tiempo < 10:
                self.poner_texto(pantalla, self.f_peq,
                                 "Mouse: mover | ESPACIO: sprint | Q: mitosis | W: masa | P: pausa | M: sonido",
                                 GRIS, (w // 2, h - 18), centrado=True)
            self.poner_texto(pantalla, self.f_peq,
                             "SONIDO: SILENCIADO" if self.sonido_silenciado else "SONIDO: ACTIVO",
                             GRIS, (14, h - 24))
            if self.t_mensaje_poder > 0:
                self.poner_texto(pantalla, self.f_media, self.mensaje_poder,
                                 (255, 225, 110), (w // 2, 34), centrado=True)

    def dibujar_muerte(self, pantalla, w, h):
        velo = self.superficie("velo_muerte", (w, h), (0, 0, 0, 170))
        pantalla.blit(velo, (0, 0))
        self.poner_texto(pantalla, self.f_grande, "TE COMIERON", (255, 110, 110), (w // 2, h // 2 - 130), centrado=True)
        self.poner_texto(pantalla, self.f_media, f"Te comió {self.asesino}", BLANCO, (w // 2, h // 2 - 82), centrado=True)
        datos = [f"Masa máxima: {int(self.masa_max)}",
                 f"Células que comiste: {self.comidos_ronda}",
                 f"Tiempo: {int(self.tiempo // 60)}:{int(self.tiempo % 60):02d}"]
        for i, d in enumerate(datos):
            self.poner_texto(pantalla, self.f_media, d, BLANCO, (w // 2, h // 2 - 38 + i * 27), centrado=True)
        mejores = [f"Récord de masa: {int(self.record['masa_maxima'])}",
                   f"Récord de células: {self.record['comidos']}",
                   f"Récord de tiempo: {int(self.record['tiempo'] // 60)}:{int(self.record['tiempo'] % 60):02d}"]
        for i, linea in enumerate(mejores):
            self.poner_texto(pantalla, self.f_peq, linea, GRIS,
                             (w // 2, h // 2 + 65 + i * 20), centrado=True)
        if self.nuevo_record:
            self.poner_texto(pantalla, self.f_media, "¡NUEVO RÉCORD!", (255, 220, 90),
                             (w // 2, h // 2 + 135), centrado=True)
        self.poner_texto(pantalla, self.f_peq, "ENTER: jugar de nuevo   |   ESC: salir", GRIS,
                         (w // 2, h // 2 + 180), centrado=True)

    def dibujar(self):
        pantalla = pygame.display.get_surface()
        w, h = pantalla.get_size()
        self.dibujar_mundo(pantalla, w, h)
        self.dibujar_interfaz(pantalla, w, h)
        self.dibujar_minimapa(pantalla, w, h)
        if self.estado == "menu":
            self.dibujar_menu_inicio(pantalla, w, h)
        if self.pausado:
            self.poner_texto(pantalla, self.f_grande, "PAUSA", BLANCO, (w // 2, h // 2), centrado=True)
        if self.estado == "muerto":
            self.dibujar_muerte(pantalla, w, h)
        if self.admin_abierto:
            self.dibujar_admin(pantalla, w, h)

    # ---------- Bucle principal ----------
    def manejar_eventos(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if self.admin_abierto:
                        self.admin_abierto = False
                        continue
                    return False
                if e.key == pygame.K_F1:
                    self.admin_abierto = not self.admin_abierto
                    continue
                if self.admin_abierto:
                    if e.key in (pygame.K_UP, pygame.K_w):
                        self.admin_seleccion = (self.admin_seleccion - 1) % len(self.opciones_admin)
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        self.admin_seleccion = (self.admin_seleccion + 1) % len(self.opciones_admin)
                    elif e.key in (pygame.K_LEFT, pygame.K_a):
                        self.ajustar_opcion_admin(-1)
                    elif e.key in (pygame.K_RIGHT, pygame.K_d):
                        self.ajustar_opcion_admin(1)
                    self.actualizar_texto_admin()
                    continue
                if self.estado == "menu":
                    if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.nombre_jugador = self.nombre_jugador.strip()[:16] or "Jugador"
                        self.jugador.nombre = self.nombre_jugador
                        self.menu_nombre_activo = False
                        pygame.key.stop_text_input()
                        self.empezar()
                    elif e.key == pygame.K_c:
                        self.menu_mostrar_controles = not self.menu_mostrar_controles
                    elif e.key == pygame.K_BACKSPACE and self.menu_nombre_activo:
                        self.nombre_jugador = self.nombre_jugador[:-1]
                        self.jugador.nombre = self.nombre_jugador or "Jugador"
                elif e.key == pygame.K_p and self.estado == "jugando":
                    self.pausado = not self.pausado
                elif e.key == pygame.K_m and self.estado == "jugando":
                    self.sonido_silenciado = not self.sonido_silenciado
                elif e.key == pygame.K_w and self.estado == "jugando" and not self.pausado:
                    self.eyectar_masa()
                elif e.key == pygame.K_q and self.estado == "jugando" and not self.pausado:
                    self.mitosis()
                elif e.key == pygame.K_RETURN and self.estado == "muerto":
                    self.nuevo_juego()
                    self.empezar()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.estado == "menu":
                if self.menu_rect_jugar.collidepoint(e.pos):
                    self.nombre_jugador = self.nombre_jugador.strip()[:16] or "Jugador"
                    self.jugador.nombre = self.nombre_jugador
                    self.menu_nombre_activo = False
                    pygame.key.stop_text_input()
                    self.empezar()
                elif self.menu_rect_controles.collidepoint(e.pos):
                    self.menu_mostrar_controles = not self.menu_mostrar_controles
                elif self.menu_rect_nombre.collidepoint(e.pos):
                    self.menu_nombre_activo = True
                    pygame.key.start_text_input()
                elif self.menu_rect_color_menos.collidepoint(e.pos):
                    self.color_jugador_indice = (self.color_jugador_indice - 1) % len(self.colores_jugador)
                    self.jugador.color = self.colores_jugador[self.color_jugador_indice]
                elif self.menu_rect_color_mas.collidepoint(e.pos):
                    self.color_jugador_indice = (self.color_jugador_indice + 1) % len(self.colores_jugador)
                    self.jugador.color = self.colores_jugador[self.color_jugador_indice]
                else:
                    self.menu_nombre_activo = False
                    pygame.key.stop_text_input()
            elif e.type == pygame.TEXTINPUT and self.estado == "menu" and self.menu_nombre_activo:
                self.nombre_jugador = (self.nombre_jugador + e.text)[:16]
                self.jugador.nombre = self.nombre_jugador or "Jugador"
        return True

    def ejecutar(self):
        corriendo = True
        while corriendo:
            dt = min(self.reloj.tick(FPS) / 1000, 0.05)
            corriendo = self.manejar_eventos()
            self.actualizar(dt)
            self.dibujar()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Juego().ejecutar()
