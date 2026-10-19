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
import math
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
    """Guarda la comida en casillas para buscarla rápido sin recorrer las 2800 piezas."""

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
        self.x = limitar(self.x + self.dx * v * dt, 0, MUNDO)
        self.y = limitar(self.y + self.dy * v * dt, 0, MUNDO)
        # Las células grandes pierden masa poco a poco, así el mundo se equilibra
        if self.masa > 150:
            self.masa -= self.masa * 0.0015 * dt


class Juego:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Agar 2D")
        pygame.display.set_mode((1000, 600), pygame.RESIZABLE)
        self.reloj = pygame.time.Clock()
        self.f_peq = pygame.font.SysFont("consolas", 16)
        self.f_media = pygame.font.SysFont("consolas", 22, bold=True)
        self.f_grande = pygame.font.SysFont("consolas", 54, bold=True)
        self.cache_texto = {}
        self.config = {
            "cantidad_npc": N_NPC,
            "velocidad_jugador": 1.0,
            "masa_comida": MASA_COMIDA,
            "intervalo_poder": INTERVALO_PODER,
            "duracion_poder": DURACION_PODER,
            "max_celulas": MAX_CELULAS_JUGADOR,
        }
        self.opciones_admin = [
            ("NPC en el mundo", "cantidad_npc", 5, 200, 5, ""),
            ("Velocidad del jugador", "velocidad_jugador", 0.5, None, 0.1, "x"),
            ("Masa por comida", "masa_comida", 1, None, 5, ""),
            ("Intervalo entre poderes", "intervalo_poder", 1, 30, 1, " s"),
            ("Duración de poderes", "duracion_poder", 2, 30, 1, " s"),
            ("Máximo de células", "max_celulas", 2, 32, 1, ""),
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
                              MASA_INICIAL, (255, 215, 90), "TÚ", es_jugador=True)
        self.jugadores = [self.jugador]
        self.jugador.factor_velocidad_admin = self.config["velocidad_jugador"]
        self.celulas = [self.jugador]
        for _ in range(self.config["cantidad_npc"]):
            self.celulas.append(self.crear_npc(lejos_de=self.jugador))
        self.cola_respawn = []
        self.estado = "jugando"      # jugando | muerto
        self.pausado = False
        self.cam_x, self.cam_y = self.jugador.x, self.jugador.y
        self.escala = 1.0
        self.tiempo = 0.0
        self.masa_max = MASA_INICIAL
        self.comidos_ronda = 0
        self.asesino = ""
        self.poderes = []
        self.tiempo_proximo_poder = self.config["intervalo_poder"]
        self.mensaje_poder = ""
        self.t_mensaje_poder = 0.0
        self.cursor_mundo = None
        self.estado = "menu"

    def nueva_comida(self):
        return Comida(random.uniform(0, MUNDO), random.uniform(0, MUNDO), color_aleatorio(0.8))

    def masa_total_jugador(self):
        return sum(c.masa for c in self.jugadores if c.viva)

    def actualizar_jugador_principal(self):
        self.jugadores = [c for c in self.celulas if c.es_jugador and c.viva]
        if self.jugadores:
            self.jugador = max(self.jugadores, key=lambda c: c.masa)

    def empezar(self):
        self.estado = "jugando"
        self.pausado = False

    def mitosis(self, celula=None):
        vivos = [c for c in self.jugadores if c.viva]
        if len(vivos) >= self.config["max_celulas"]:
            self.aviso_poder("LÍMITE DE CÉLULAS")
            return False
        candidata = celula or max(vivos, key=lambda c: c.masa, default=None)
        if candidata is None or candidata.masa < 100:
            self.aviso_poder("NECESITAS 100 DE MASA PARA LA MITOSIS")
            return False

        masa_nueva = candidata.masa / 2
        candidata.masa = masa_nueva
        angulo = random.random() * math.tau
        distancia = candidata.r * 0.85
        clon = Celula(limitar(candidata.x + math.cos(angulo) * distancia, 0, MUNDO),
                      limitar(candidata.y + math.sin(angulo) * distancia, 0, MUNDO),
                      masa_nueva, candidata.color, candidata.nombre, es_jugador=True)
        clon.dx, clon.dy = candidata.dx, candidata.dy
        clon.tx, clon.ty = candidata.tx, candidata.ty
        clon.factor_velocidad_admin = self.config["velocidad_jugador"]
        clon.fusion_tiempo = candidata.fusion_tiempo = 10.0
        clon.boost_tiempo = candidata.boost_tiempo
        clon.escudo_tiempo = candidata.escudo_tiempo
        clon.iman_tiempo = candidata.iman_tiempo
        self.celulas.append(clon)
        self.jugadores.append(clon)
        self.actualizar_jugador_principal()
        self.aviso_poder("¡MITOSIS!")
        return True

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
            objetivo.masa *= 1.3
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
                    npc.x = limitar(npc.x + nx * empuje, npc.r, MUNDO - npc.r)
                    npc.y = limitar(npc.y + ny * empuje, npc.r, MUNDO - npc.r)
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
        for o in self.celulas:
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
        elif presa and d_pr < percep * c.agresividad:
            # CAZAR (apuntando un poco adelante de donde va la presa)
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
        c.tx, c.ty = normalizar(vx, vy)

    # ---------- Actualización ----------
    def actualizar(self, dt):
        if self.pausado or self.estado == "menu" or self.admin_abierto:
            return
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
                j.sprint = sprint and j.masa > MASA_MIN_SPRINT
                j.factor_velocidad_admin = self.config["velocidad_jugador"]
            self.tiempo_proximo_poder -= dt
            if self.tiempo_proximo_poder <= 0:
                self.crear_poder()
                self.tiempo_proximo_poder = self.config["intervalo_poder"]
            if self.t_mensaje_poder > 0:
                self.t_mensaje_poder = max(0, self.t_mensaje_poder - dt)

        for c in tuple(self.celulas):
            if not c.es_jugador:
                c.t_pensar -= dt
                if c.t_pensar <= 0:
                    self.pensar(c)
                    c.t_pensar = random.uniform(0.2, 0.3)
            c.mover(dt)
            radio_comida = c.r * (1.6 if c.es_jugador and c.iman_tiempo > 0 else 0.9)
            n = self.comida.comer(c.x, c.y, radio_comida)
            if n:
                c.masa += n * self.config["masa_comida"]
                for _ in range(n):
                    self.comida.agregar(self.nueva_comida())
            if c.es_jugador and self.estado == "jugando":
                poder = next((p for p in self.poderes
                              if math.hypot(p.x - c.x, p.y - c.y) < c.r + 22), None)
                if poder:
                    self.poderes.remove(poder)
                    self.aplicar_poder(poder, c)
            if not c.es_jugador:
                c.masa = min(c.masa, MASA_MAX_NPC)

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
            self.cam_x += (self.jugador.x - self.cam_x) * min(1.0, 8 * dt)
            self.cam_y += (self.jugador.y - self.cam_y) * min(1.0, 8 * dt)
            self.masa_max = max(self.masa_max, self.masa_total_jugador())
            objetivo = limitar((14 / self.jugador.r) ** 0.35, 0.22, 1.1)
            self.escala += (objetivo - self.escala) * min(1.0, 3 * dt)

    def resolver_comidas(self):
        celulas = self.celulas
        for a in celulas:
            if not a.viva:
                continue
            for b in celulas:
                if a is b or not b.viva:
                    continue
                if a.es_jugador and b.es_jugador:
                    continue
                if b.es_jugador and self.tiempo < INMUNIDAD_INICIAL:
                    continue
                if b.es_jugador and b.escudo_tiempo > 0:
                    continue
                if a.masa > b.masa * VENTAJA:
                    limite = a.r - b.r * 0.4
                    if (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < limite * limite:
                        a.masa += b.masa
                        a.comidos += 1
                        if a.es_jugador and not b.es_jugador:
                            self.comidos_ronda += 1
                        b.viva = False
                        if b.es_jugador:
                            self.asesino = a.nombre
                        else:
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
        oscurecedor = pygame.Surface((w, h), pygame.SRCALPHA)
        oscurecedor.fill((7, 9, 20, 195))
        pantalla.blit(oscurecedor, (0, 0))
        centro_x, centro_y = w // 2, h // 2
        panel = pygame.Rect(centro_x - 330, centro_y - 255, 660, 510)
        pygame.draw.rect(pantalla, (17, 23, 43), panel, border_radius=24)
        pygame.draw.rect(pantalla, (70, 94, 145), panel, width=2, border_radius=24)

        # Motas decorativas alrededor del panel principal.
        animacion = pygame.time.get_ticks() * 0.00008
        for i in range(22):
            angulo = i * math.tau / 22 + animacion
            x = int(centro_x + math.cos(angulo) * (360 + 12 * math.sin(animacion * 10 + i)))
            y = int(centro_y + math.sin(angulo) * 270)
            pygame.draw.circle(pantalla, (75, 115, 180), (x, y), 2 + i % 3)

        titulo = self.f_grande.render("AGARIO", True, (255, 220, 100))
        pantalla.blit(titulo, titulo.get_rect(center=(centro_x, centro_y - 174)))
        subtitulo = self.f_media.render("CRECE · DIVÍDETE · SOBREVIVE", True, (170, 194, 235))
        pantalla.blit(subtitulo, subtitulo.get_rect(center=(centro_x, centro_y - 123)))
        descripcion = self.f_peq.render("Un mundo vivo lleno de rivales y poderes inesperados", True, GRIS)
        pantalla.blit(descripcion, descripcion.get_rect(center=(centro_x, centro_y - 91)))

        self.menu_rect_jugar = pygame.Rect(centro_x - 145, centro_y - 42, 290, 62)
        hover = self.menu_rect_jugar.collidepoint(pygame.mouse.get_pos())
        boton = (255, 197, 75) if hover else (235, 163, 55)
        pygame.draw.rect(pantalla, boton, self.menu_rect_jugar, border_radius=15)
        pygame.draw.rect(pantalla, (255, 230, 160), self.menu_rect_jugar, width=2, border_radius=15)
        texto_jugar = self.f_media.render("JUGAR", True, (35, 28, 24))
        pantalla.blit(texto_jugar, texto_jugar.get_rect(center=self.menu_rect_jugar.center))

        self.menu_rect_controles = pygame.Rect(centro_x - 145, centro_y + 37, 290, 46)
        pygame.draw.rect(pantalla, (37, 49, 76), self.menu_rect_controles, border_radius=12)
        pygame.draw.rect(pantalla, (75, 95, 135), self.menu_rect_controles, width=1, border_radius=12)
        etiqueta = "OCULTAR CONTROLES" if self.menu_mostrar_controles else "VER CONTROLES"
        texto_controles = self.f_peq.render(etiqueta, True, BLANCO)
        pantalla.blit(texto_controles, texto_controles.get_rect(center=self.menu_rect_controles.center))

        if self.menu_mostrar_controles:
            controles = ["Mouse o WASD / flechas: mover", "ESPACIO: sprint   ·   Q: mitosis",
                         "P: pausa   ·   F1: menú admin"]
            for i, linea in enumerate(controles):
                img = self.f_peq.render(linea, True, (195, 205, 225))
                pantalla.blit(img, img.get_rect(center=(centro_x, centro_y + 112 + i * 23)))
        else:
            nota = self.f_peq.render("Recoge orbes de poder y cambia el rumbo de la partida", True, (195, 205, 225))
            pantalla.blit(nota, nota.get_rect(center=(centro_x, centro_y + 116)))
        pie = self.f_peq.render("Pulsa ENTER para comenzar   ·   F1 abre administración", True, GRIS)
        pantalla.blit(pie, pie.get_rect(center=(centro_x, centro_y + 218)))

    def dibujar_admin(self, pantalla, w, h):
        oscurecedor = pygame.Surface((w, h), pygame.SRCALPHA)
        oscurecedor.fill((4, 7, 15, 205))
        pantalla.blit(oscurecedor, (0, 0))
        panel = pygame.Rect(w // 2 - 300, h // 2 - 245, 600, 490)
        pygame.draw.rect(pantalla, (17, 23, 43), panel, border_radius=20)
        pygame.draw.rect(pantalla, (87, 119, 176), panel, width=2, border_radius=20)
        titulo = self.f_media.render("ADMINISTRACIÓN DEL MUNDO", True, (255, 220, 100))
        pantalla.blit(titulo, titulo.get_rect(center=(w // 2, panel.y + 48)))
        detalle = self.f_peq.render("Los cambios se aplican al instante", True, GRIS)
        pantalla.blit(detalle, detalle.get_rect(center=(w // 2, panel.y + 80)))
        for i, linea in enumerate(self.admin_lineas):
            tono = (125, 220, 255) if i == self.admin_seleccion else BLANCO
            img = self.f_media.render(linea, True, tono)
            pantalla.blit(img, (panel.x + 62, panel.y + 122 + i * 43))
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

    def dibujar_minimapa(self, pantalla, w, h):
        lado = 150
        mini = pygame.Surface((lado, lado), pygame.SRCALPHA)
        mini.fill((0, 0, 0, 140))
        f = lado / MUNDO
        for c in self.celulas:
            if c.es_jugador:
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
        panel = pygame.Surface((190, 150), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
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
                                 "Mouse: mover  |  ESPACIO: sprint  |  Q: mitosis  |  P: pausa",
                                 GRIS, (w // 2, h - 18), centrado=True)
            if self.t_mensaje_poder > 0:
                self.poner_texto(pantalla, self.f_media, self.mensaje_poder,
                                 (255, 225, 110), (w // 2, 34), centrado=True)

    def dibujar_muerte(self, pantalla, w, h):
        velo = pygame.Surface((w, h), pygame.SRCALPHA)
        velo.fill((0, 0, 0, 170))
        pantalla.blit(velo, (0, 0))
        self.poner_texto(pantalla, self.f_grande, "TE COMIERON", (255, 110, 110), (w // 2, h // 2 - 90), centrado=True)
        self.poner_texto(pantalla, self.f_media, f"Te comió {self.asesino}", BLANCO, (w // 2, h // 2 - 40), centrado=True)
        datos = [f"Masa máxima: {int(self.masa_max)}",
                 f"Células que comiste: {self.comidos_ronda}",
                 f"Tiempo: {int(self.tiempo // 60)}:{int(self.tiempo % 60):02d}"]
        for i, d in enumerate(datos):
            self.poner_texto(pantalla, self.f_media, d, BLANCO, (w // 2, h // 2 + 10 + i * 32), centrado=True)
        self.poner_texto(pantalla, self.f_peq, "ENTER: jugar de nuevo   |   ESC: salir", GRIS,
                         (w // 2, h // 2 + 135), centrado=True)

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
                        self.empezar()
                    elif e.key == pygame.K_c:
                        self.menu_mostrar_controles = not self.menu_mostrar_controles
                elif e.key == pygame.K_p and self.estado == "jugando":
                    self.pausado = not self.pausado
                elif e.key == pygame.K_q and self.estado == "jugando" and not self.pausado:
                    self.mitosis()
                elif e.key == pygame.K_RETURN and self.estado == "muerto":
                    self.nuevo_juego()
                    self.empezar()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.estado == "menu":
                if self.menu_rect_jugar.collidepoint(e.pos):
                    self.empezar()
                elif self.menu_rect_controles.collidepoint(e.pos):
                    self.menu_mostrar_controles = not self.menu_mostrar_controles
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
