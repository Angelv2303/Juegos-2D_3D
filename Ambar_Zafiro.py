"""
ÁMBAR Y ZAFIRO - juego cooperativo de plataformas y puzzles

Dos personajes, dos habilidades. Para salir de cada habitación hay que trabajar en equipo.
Puedes jugar con un amigo en el mismo teclado, o solo con una IA como compañera.

  ÁMBAR  (naranja): fuerte. Empuja cajas y resiste la LAVA, pero salta poco.
  ZAFIRO (azul)   : ágil.   Salta alto y resiste el AGUA, pero no puede mover cajas.
  El ÁCIDO (verde) mata a los dos.

  Un BOTÓN abre las puertas de su mismo color mientras alguien (o una caja) lo pisa.
  Hay que llevar a cada personaje a su puerta de salida. Los dos a la vez.

Controles:
  Dos jugadores:  Ámbar = A D (mover) W (saltar)    Zafiro = flechas
  Un jugador:     A D / flechas para mover, W / flecha arriba / ESPACIO para saltar
  Órdenes a la IA (un jugador):
      Q = "sígueme"      E = "espera aquí"      R = "ve al botón más cercano"
      TAB = cambiar de personaje (la IA pasa a controlar al que dejas)
  Otros:  Retroceso = reiniciar nivel   P = pausa   ESC = menú

Requiere: pygame  (pip install pygame   o   pip install pygame-ce)
"""
import heapq
import math
import array
import random
import sys

import pygame

# ---------- Constantes del mundo ----------
TILE = 40
COLS, ROWS = 24, 15
ANCHO, ALTO = COLS * TILE, ROWS * TILE        # 960 x 600
FPS = 60
GRAVEDAD = 0.42
CAIDA_MAX = 11.0

PERFILES = {
    "ambar": {"nombre": "Ámbar", "w": 32, "h": 38, "vel": 2.8, "salto": 8.0,
              "color": (255, 150, 50), "inmune": "L", "empuja": True},
    "zafiro": {"nombre": "Zafiro", "w": 26, "h": 34, "vel": 3.3, "salto": 9.6,
               "color": (80, 180, 255), "inmune": "W", "empuja": False},
}
OTRO = {"ambar": "zafiro", "zafiro": "ambar"}

COLOR_FONDO_A = (16, 18, 34)
COLOR_FONDO_B = (32, 36, 62)
COLOR_PARED = (62, 68, 104)
COLOR_PARED_CLARA = (100, 108, 152)
COLOR_PARED_OSCURA = (44, 48, 78)
COLORES_PELIGRO = {"L": (235, 85, 40), "W": (55, 140, 255), "X": (120, 230, 70)}
NOMBRES_PELIGRO = {"L": "lava", "W": "agua", "X": "ácido"}
COLORES_LETRA = {"A": (240, 200, 60), "B": (180, 110, 240), "C": (235, 235, 235)}
BLANCO = (240, 240, 250)
GRIS = (150, 155, 180)


class SonidoJuego:
    """Audio sintetizado localmente: no requiere paquetes ni archivos de sonido."""

    def __init__(self):
        self.disponible = False
        self.efectos = {}
        self.ambiente = None
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.disponible = True
            self.efectos = {
                "saltar": self._tono([520, 760], 0.11, 0.10),
                "boton": self._tono([350, 520, 690], 0.20, 0.13),
                "puerta": self._tono([220, 330, 440], 0.30, 0.12),
                "muerte": self._tono([420, 300, 180, 90], 0.58, 0.20),
                "victoria": self._tono([440, 554, 659, 880], 0.48, 0.13),
                "inicio": self._tono([392, 523, 659], 0.30, 0.11),
            }
            self.ambiente = self._ambiente()
            self.ambiente.set_volume(0.10)
            pygame.mixer.Channel(0).play(self.ambiente, loops=-1)
        except (pygame.error, RuntimeError):
            self.disponible = False

    @staticmethod
    def _tono(frecuencias, duracion, volumen):
        frecuencia_muestra = 22050
        total = int(frecuencia_muestra * duracion)
        datos = array.array("h")
        tramo = total / len(frecuencias)
        for i in range(total):
            local = i % tramo
            envolvente = min(1.0, local / 250, (tramo - local) / 450)
            nota = frecuencias[min(len(frecuencias) - 1, int(i / tramo))]
            onda = math.sin(2 * math.pi * nota * i / frecuencia_muestra)
            datos.append(int(32767 * volumen * max(0, envolvente) * onda))
        return pygame.mixer.Sound(buffer=datos.tobytes())

    @staticmethod
    def _ambiente():
        frecuencia_muestra = 22050
        total = frecuencia_muestra * 4
        datos = array.array("h")
        for i in range(total):
            t = i / frecuencia_muestra
            fade = min(1.0, t * 3, (4 - t) * 3)
            onda = (math.sin(2 * math.pi * 110 * t)
                    + 0.55 * math.sin(2 * math.pi * 164.8 * t)
                    + 0.25 * math.sin(2 * math.pi * (55 + 2 * math.sin(t * 1.57)) * t))
            datos.append(int(32767 * 0.18 * fade * onda / 1.8))
        return pygame.mixer.Sound(buffer=datos.tobytes())

    def reproducir(self, nombre):
        if not self.disponible:
            return
        try:
            sonido = self.efectos.get(nombre)
            if sonido:
                canal = pygame.mixer.find_channel(True)
                if canal:
                    canal.play(sonido)
        except pygame.error:
            self.disponible = False


sonidos = None

# ---------- Niveles ----------
# #  pared          .  vacío
# L  lava (mata a Zafiro)   W  agua (mata a Ámbar)   X  ácido (mata a ambos)
# A B C  botones    a b c  puertas (se abren con el botón de su letra)
# o  caja           M  inicio de Ámbar     Z  inicio de Zafiro
# E  salida de Ámbar        F  salida de Zafiro
NIVELES_ASCII = [
    ("Cada uno en su color",
     "Ámbar resiste la lava (roja) y Zafiro el agua (azul). El ácido verde mata a los dos.",
     ["########################"]
     + ["#......................#"] * 12
     + ["#.MZ" + "." * 16 + "EF.#",
        "#####WWW####LLL#########"]),

    ("Botón y puerta",
     "Un botón abre la puerta de su color mientras lo pisan. Turnaos: uno la abre, el otro pasa.",
     ["########################"]
     + ["#" + "." * 10 + "#" + "." * 11 + "#"] * 11
     + ["#" + "." * 10 + "a" + "." * 11 + "#",
        "#.MZ...A...a...A.....EF#",
        "#" * 17 + "XX" + "#" * 5]),

    ("Cajas y alturas",
     "Solo Ámbar empuja cajas. Solo Zafiro salta a las plataformas altas. Una caja también pisa botones.",
     ["########################"]
     + ["#" + "." * 9 + "#" + "." * 7 + "#" + "." * 4 + "#"] * 10
     + ["#.........#.C..F..#....#",
        "#.........b.####..c....#",
        "#.MZo....Bb.......c...E#",
        "#" * 19 + "XX" + "###"]),

    ("Equipo completo",
     "Usa la caja como escalera. Después, turnaos en los botones y cuidado con cada charco.",
     ["########################"]
     + ["#" + "." * 15 + "#" + "." * 6 + "#"] * 11
     + ["#........##.....a......#",
        "#.MZ..o..##..A..a.A..EF#",
        "#" * 14 + "WW" + "###" + "LL" + "###"]),
]

# La campaña suma salas con más cambios de altura y peligros alternados.
# Cada habitación conserva el formato 24 x 15 del editor ASCII.
NIVELES_ASCII += [
    ("Pasarela volcánica",
     "Los fosos tienen piedras de apoyo. Saltad sobre cada una para cruzar el líquido.",
     ["########################"]
     + ["#......................#"] * 10
     + ["#......................#",
        "#......................#",
        "#.MZ..#........#....EF.#",
        "######L########W#######"]),
    ("El botón elevado",
     "Zafiro alcanza la repisa. Ámbar puede esperar junto a la salida hasta abrir la puerta.",
     ["########################"]
     + ["#...........#..........#"] * 8
     + ["#...........#..........#",
        "#.....B.....b..........#",
        "#.MZ........b......EF..#",
        "########################",
        "#......................#",
        "########################"]),
    ("Tres saltos coordinados",
     "Tres fosos estrechos y piedras de apoyo. Cada héroe resiste un elemento distinto.",
     ["########################"]
     + ["#......................#"] * 11
     + ["#......................#",
        "#.MZ..#.....#.....#.EF.#",
        "######L#####W#####L#####"]),
    ("La última cámara",
     "Cruzad los huecos de lava y agua con un salto. Cada héroe tiene una resistencia distinta.",
     ["########################"]
     + ["#....#.................#"] * 5
     + ["#......................#"] * 5
     + ["#.......###..###.......#",
        "#......................#",
        "#.MZ...............EF..#",
        "######L########W#######"]),
]


def ajustar_nuevo_mapa(titulo, pista, filas):
    """Rellena con aire las habitaciones nuevas y mantiene el suelo en su fila final."""
    if len(filas) > ROWS:
        raise ValueError(f"El nivel {titulo!r} tiene más de {ROWS} filas")
    suelo = filas[-1].ljust(COLS, "#")
    intermedias = filas[1:-1]
    while len(intermedias) < ROWS - 2:
        intermedias.append("#" + "." * (COLS - 2) + "#")
    filas = [filas[0].ljust(COLS, "#")] + [f.ljust(COLS, "#") for f in intermedias] + [suelo]
    if any(len(f) != COLS for f in filas):
        raise ValueError(f"Una fila del nivel {titulo!r} supera {COLS} columnas")
    return titulo, pista, filas


NIVELES_ASCII[-4:] = [ajustar_nuevo_mapa(*nivel) for nivel in NIVELES_ASCII[-4:]]


class Nivel:
    def __init__(self, titulo, pista, filas):
        assert len(filas) == ROWS, (titulo, len(filas))
        self.titulo, self.pista = titulo, pista
        self.solido = [[False] * COLS for _ in range(ROWS)]
        self.peligro = [[None] * COLS for _ in range(ROWS)]
        self.puertas, self.placas, self.cajas = [], [], []
        self.inicio, self.salida = {}, {}
        for cy, fila in enumerate(filas):
            assert len(fila) == COLS, (titulo, cy, len(fila))
            for cx, ch in enumerate(fila):
                if ch == "#":
                    self.solido[cy][cx] = True
                elif ch in "LWX":
                    self.peligro[cy][cx] = ch
                elif ch in "abc":
                    self.puertas.append((ch.upper(), cx, cy))
                elif ch in "ABC":
                    self.placas.append((ch, cx, cy))
                elif ch == "o":
                    self.cajas.append((cx, cy))
                elif ch == "M":
                    self.inicio["ambar"] = (cx, cy)
                elif ch == "Z":
                    self.inicio["zafiro"] = (cx, cy)
                elif ch == "E":
                    self.salida["ambar"] = (cx, cy)
                elif ch == "F":
                    self.salida["zafiro"] = (cx, cy)
                elif ch != ".":
                    raise ValueError(f"Símbolo desconocido {ch!r} en {titulo}")
        assert set(self.inicio) == set(self.salida) == {"ambar", "zafiro"}, titulo

    def es_solido(self, cx, cy):
        if cx < 0 or cx >= COLS or cy < 0 or cy >= ROWS:
            return True
        return self.solido[cy][cx]

    def peligro_en(self, cx, cy):
        if 0 <= cx < COLS and 0 <= cy < ROWS:
            return self.peligro[cy][cx]
        return None


NIVELES = [Nivel(*n) for n in NIVELES_ASCII]


def casillas(l, t, r, b):
    """Rango de casillas cubiertas por un rectángulo."""
    return (int(math.floor(l / TILE)), int(math.floor((r - 1e-9) / TILE)),
            int(math.floor(t / TILE)), int(math.floor((b - 1e-9) / TILE)))


def solapan(al, at, ar, ab, bl, bt, br, bb):
    return al < br and ar > bl and at < bb and ab > bt


def toca_peligro(nivel, c, inmune):
    """True si el cuerpo toca un líquido que lo mata."""
    x0, x1, y0, y1 = casillas(c.x + 5, c.y + 4, c.x + c.w - 5, c.y + c.h - 2)
    for cy in range(y0, y1 + 1):
        for cx in range(x0, x1 + 1):
            p = nivel.peligro_en(cx, cy)
            if p and (p == "X" or p != inmune):
                return p
    return None


# ---------- Física ----------
class Cuerpo:
    es_caja = False

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.vy = 0.0
        self.suelo = False

    def rect(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def mover_x(self, dx, mundo, empuja=False):
        """Mueve en X. Devuelve True si empujó una caja."""
        if dx == 0:
            return False
        self.x += dx
        empujo = False
        for (l, t, r, b, obj) in mundo.solidos(self.x, self.y, self.x + self.w, self.y + self.h, self):
            if not solapan(self.x, self.y, self.x + self.w, self.y + self.h, l, t, r, b):
                continue
            if obj is not None and empuja and obj.es_caja and mundo.empujar(obj, dx):
                empujo = True
                continue
            self.x = l - self.w if dx > 0 else r
        return empujo

    def mover_y(self, dy, mundo):
        self.y += dy
        self.suelo = False
        for (l, t, r, b, obj) in mundo.solidos(self.x, self.y, self.x + self.w, self.y + self.h, self):
            if not solapan(self.x, self.y, self.x + self.w, self.y + self.h, l, t, r, b):
                continue
            if dy > 0:
                self.y = t - self.h
                self.suelo = True
            else:
                self.y = b
            self.vy = 0.0


class Personaje(Cuerpo):
    def __init__(self, clave, cx, cy):
        p = PERFILES[clave]
        super().__init__(cx * TILE + (TILE - p["w"]) / 2, (cy + 1) * TILE - p["h"], p["w"], p["h"])
        self.clave, self.perfil = clave, p
        self.mirando = 1
        self.empujando = False
        self.empuja_activo = True        # la IA lo desactiva: nunca empuja cajas por accidente
        self.dentro = False
        self.celda_suelo = (cx, cy)

    def paso(self, dir_x, salto, mundo):
        p = self.perfil
        dx = dir_x * p["vel"]
        if self.empujando:
            dx *= 0.55
        if salto and self.suelo:
            self.vy = -p["salto"]
        self.vy = min(self.vy + GRAVEDAD, CAIDA_MAX)
        if dir_x:
            self.mirando = 1 if dir_x > 0 else -1
        self.empujando = self.mover_x(dx, mundo, p["empuja"] and self.empuja_activo)
        self.mover_y(self.vy, mundo)

    def celda(self):
        return (int((self.x + self.w / 2) // TILE), int((self.y + self.h - 0.5) // TILE))


class Caja(Cuerpo):
    es_caja = True

    def __init__(self, cx, cy):
        super().__init__(cx * TILE + 2, (cy + 1) * TILE - 36, 36, 36)

    def paso(self, mundo):
        self.vy = min(self.vy + GRAVEDAD, CAIDA_MAX)
        self.mover_y(self.vy, mundo)


class Placa:
    def __init__(self, letra, cx, cy):
        self.letra, self.cx, self.cy = letra, cx, cy
        self.rect = (cx * TILE + 4, (cy + 1) * TILE - 8, cx * TILE + TILE - 4, (cy + 1) * TILE)
        self.pulsada = False


class Puerta:
    def __init__(self, letra, cx, cy):
        self.letra, self.cx, self.cy = letra, cx, cy
        self.rect = (cx * TILE, cy * TILE, cx * TILE + TILE, cy * TILE + TILE)
        self.abierta = False
        self.visual = 0.0


class MundoEstatico:
    """Solo paredes. Lo usa la IA para planear rutas y comprobar saltos."""

    def __init__(self, nivel):
        self.nivel = nivel

    def solidos(self, l, t, r, b, ignorar=None):
        x0, x1, y0, y1 = casillas(l, t, r, b)
        res = []
        es_solido = self.nivel.es_solido
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                if es_solido(cx, cy):
                    res.append((cx * TILE, cy * TILE, cx * TILE + TILE, cy * TILE + TILE, None))
        return res


class Mundo(MundoEstatico):
    """El mundo real: paredes + puertas cerradas + cajas, con botones que abren puertas."""

    def __init__(self, nivel):
        super().__init__(nivel)
        self.cajas = [Caja(cx, cy) for cx, cy in nivel.cajas]
        self.puertas = [Puerta(*p) for p in nivel.puertas]
        self.placas = [Placa(*p) for p in nivel.placas]
        self.personajes = {}

    def solidos(self, l, t, r, b, ignorar=None):
        res = super().solidos(l, t, r, b)
        for pu in self.puertas:
            if not pu.abierta and solapan(l, t, r, b, *pu.rect):
                res.append((*pu.rect, None))
        for c in self.cajas:
            if c is not ignorar and solapan(l, t, r, b, c.x, c.y, c.x + c.w, c.y + c.h):
                res.append((c.x, c.y, c.x + c.w, c.y + c.h, c))
        return res

    def empujar(self, caja, dx):
        x0 = caja.x
        caja.mover_x(dx, self, False)
        return abs(caja.x - (x0 + dx)) < 1e-6

    def cuerpos(self):
        return list(self.personajes.values()) + self.cajas

    def actualizar(self):
        for c in self.cajas:
            c.paso(self)
        cuerpos = self.cuerpos()
        for pl in self.placas:
            pl.pulsada = any(solapan(*pl.rect, *c.rect()) for c in cuerpos)
        activas = {pl.letra for pl in self.placas if pl.pulsada}
        for pu in self.puertas:
            if pu.letra in activas:
                pu.abierta = True
            elif pu.abierta and not any(solapan(*pu.rect, *c.rect()) for c in cuerpos):
                pu.abierta = False      # no se cierra encima de nadie
            pu.visual += ((1.0 if pu.abierta else 0.0) - pu.visual) * 0.2


# ---------- Inteligencia artificial del compañero ----------
MAX_SIM = 220
CAIDA_MAX_NODOS = 14


def soporte(mundo, x, y):
    return bool(mundo.solidos(x - 0.01, y - 0.5, x + 0.01, y + 0.5))


class Ejecutor:
    """Ejecuta UNA maniobra entre dos casillas. Se usa tanto para comprobar si la maniobra
    funciona (simulación) como para hacerla de verdad, así que siempre coinciden."""

    def __init__(self, pol, origen, destino, perfil):
        self.pol, self.S, self.T, self.perfil = pol, origen, destino, perfil
        self.sx = (origen[0] + 0.5) * TILE
        self.tx = (destino[0] + 0.5) * TILE
        self.fase = "alinear" if pol == "centro" else "ir"
        self.n = 0
        self.aire = 0
        self.ult_x = None

    def en_destino(self, c):
        return (c.suelo and int((c.x + c.w / 2) // TILE) == self.T[0]
                and int((c.y + c.h - 0.5) // TILE) == self.T[1])

    def paso(self, c, mundo):
        """Devuelve (dirección, salto, estado) con estado None | 'fin' | 'fallo'."""
        self.n += 1
        if self.n > 300:
            return 0.0, False, "fallo"
        vel = self.perfil["vel"]
        cx = c.x + c.w / 2
        if self.n > 1 and self.en_destino(c):
            return 0.0, False, "fin"

        def hacia(x):
            return max(-1.0, min(1.0, (x - cx) / vel))

        if self.pol == "caminar":
            return hacia(self.tx), False, None

        if self.fase == "alinear":                       # 'centro': salta desde el centro de la casilla
            if not c.suelo:
                return 0.0, False, None
            if abs(self.sx - cx) > 1.0:
                return hacia(self.sx), False, None
            self.fase = "saltar"
        if self.fase == "saltar":
            self.fase, self.aire = "aire", 0
            return hacia(self.tx), True, None
        if self.fase == "ir":                            # 'borde': corre y salta en el último momento
            if not c.suelo:
                return hacia(self.tx), False, None
            d = 1.0 if self.tx > cx else -1.0
            trasera = c.x if d > 0 else c.x + c.w
            sin_suelo = not soporte(mundo, trasera + d * vel, c.y + c.h + 1)
            bloqueado = self.ult_x is not None and abs(c.x - self.ult_x) < 0.01 and self.n > 3
            self.ult_x = c.x
            if sin_suelo or bloqueado:
                self.fase, self.aire = "aire", 0
                return d, True, None
            return d, False, None
        self.aire += 1                                   # en el aire
        if c.suelo and self.aire > 3:
            return 0.0, False, "fallo"
        return hacia(self.tx), False, None


class Grafo:
    """Mapa de casillas donde un personaje puede estar de pie y de maniobras entre ellas.
    Las maniobras se calculan al hacer falta y se guardan."""

    def __init__(self, nivel, clave):
        self.nivel, self.clave = nivel, clave
        self.perfil = PERFILES[clave]
        self.mundo = MundoEstatico(nivel)
        inmune = self.perfil["inmune"]
        self.nodos = set()
        for cy in range(ROWS):
            for cx in range(COLS):
                if nivel.es_solido(cx, cy) or not nivel.es_solido(cx, cy + 1):
                    continue
                p = nivel.peligro[cy][cx]
                if p and (p == "X" or p != inmune):
                    continue
                self.nodos.add((cx, cy))
        g = GRAVEDAD
        apice = self.perfil["salto"] ** 2 / (2 * g)
        alcance = self.perfil["vel"] * 2 * self.perfil["salto"] / g
        self.subida_max = int((apice - 4) // TILE)
        self.dx_max = int(math.ceil((alcance + self.perfil["w"]) / TILE))
        self.aristas = {}
        self.bloqueadas = {}
        self.reloj = 0

    # -- simulación de una maniobra
    def simular(self, S, T, pol):
        c = Personaje(self.clave, S[0], S[1])
        c.suelo = True
        ej = Ejecutor(pol, S, T, self.perfil)
        for n in range(MAX_SIM):
            d, s, est = ej.paso(c, self.mundo)
            if est == "fin":
                return n
            if est == "fallo":
                return None
            c.paso(d, s, self.mundo)
            if toca_peligro(self.nivel, c, self.perfil["inmune"]) or c.y > ALTO + 80:
                return None
        return None

    def aristas_de(self, S):
        if S in self.aristas:
            return self.aristas[S]
        lista = []
        for dy in range(-self.subida_max, min(5, CAIDA_MAX_NODOS) + 10):
            for dx in range(-self.dx_max, self.dx_max + 1):
                T = (S[0] + dx, S[1] + dy)
                if T == S or T not in self.nodos:
                    continue
                pols = []
                if dy >= 0 and ((dy == 0 and abs(dx) == 1) or (dy > 0 and abs(dx) <= 3)):
                    pols.append("caminar")
                if dy <= 4 and not (dy == 0 and abs(dx) == 1):
                    pols.append("centro")
                    if dx != 0:
                        pols.append("borde")
                for pol in pols:
                    n = self.simular(S, T, pol)
                    if n is not None:
                        lista.append((T, pol, n + (0 if pol == "caminar" else 8)))
        self.aristas[S] = lista
        return lista

    def preparar_todo(self):
        for n in self.nodos:
            self.aristas_de(n)

    def bloquear(self, S, T, pol, frames=480):
        self.bloqueadas[(S, T, pol)] = self.reloj + frames

    def esta_bloqueada(self, S, T, pol):
        hasta = self.bloqueadas.get((S, T, pol))
        return hasta is not None and hasta > self.reloj

    def mas_cercano(self, celda):
        mejor, md = None, 1e9
        for n in self.nodos:
            d = abs(n[0] - celda[0]) + 2 * abs(n[1] - celda[1])
            if d < md:
                mejor, md = n, d
        return mejor

    def camino(self, inicio, objetivos):
        """Lista de maniobras (S, T, pol) hasta el objetivo más cercano, o None."""
        dist = {inicio: 0}
        previo = {}
        cola = [(0, inicio)]
        while cola:
            d, n = heapq.heappop(cola)
            if d > dist.get(n, 1e18):
                continue
            if n in objetivos:
                ruta = []
                while n != inicio:
                    p, pol = previo[n]
                    ruta.append((p, n, pol))
                    n = p
                ruta.reverse()
                return ruta
            for (T, pol, costo) in self.aristas_de(n):
                if self.esta_bloqueada(n, T, pol):
                    continue
                nd = d + costo
                if nd < dist.get(T, 1e18):
                    dist[T] = nd
                    previo[T] = (n, pol)
                    heapq.heappush(cola, (nd, T))
        return None


class IA:
    """Controla a un personaje. Modos: 'esperar', 'seguir', 'boton' y 'ir' (a una casilla)."""

    def __init__(self, juego, clave):
        self.juego, self.clave = juego, clave
        self.grafo = Grafo(juego.nivel, clave)
        self.modo = "esperar"
        self.meta = None
        self.ejecutor = None
        self.arista = None
        self.pausa = 0
        self.sin_avance = 0
        self.x_prev = None
        self.mensaje, self.t_mensaje = "", 0
        self.avisado_sin_ruta = False

    def decir(self, texto, frames=110):
        self.mensaje, self.t_mensaje = texto, frames

    def ordenar(self, modo, meta=None):
        self.modo, self.meta = modo, meta
        self.ejecutor = None
        self.pausa = 0
        self.avisado_sin_ruta = False
        textos = {"seguir": "¡Te sigo!", "esperar": "Aquí espero", "boton": "¡Voy a un botón!",
                  "auto": "¡Busco una ruta!"}
        if modo in textos:
            self.decir(textos[modo])

    def nodo_actual(self, yo):
        n = yo.celda()
        if n in self.grafo.nodos:
            return n
        mejor, md = None, 99
        for dx in range(-2, 3):
            for dy in range(0, 3):
                m = (n[0] + dx, n[1] + dy)
                if m in self.grafo.nodos and abs(dx) + abs(dy) < md:
                    mejor, md = m, abs(dx) + abs(dy)
        return mejor

    def objetivos(self, otro):
        if self.modo == "auto":
            exit_x = (self.juego.nivel.salida[self.clave][0] + 0.5) * TILE
            otro_x = otro.x + otro.w / 2
            pendientes = set()
            for puerta in self.juego.mundo.puertas:
                letra = puerta.letra
                puerta_x = (puerta.cx + 0.5) * TILE
                ya_cruzo = (otro_x - puerta_x) * (exit_x - puerta_x) > 0
                if ya_cruzo:
                    continue
                for letra_pl, cx, cy in self.juego.nivel.placas:
                    if letra_pl == letra and (cx, cy) in self.grafo.nodos:
                        pendientes.add((cx, cy))
            if pendientes:
                return pendientes
            salida = self.juego.nivel.salida[self.clave]
            return {salida} if salida in self.grafo.nodos else set()
        if self.modo == "seguir":
            n = self.grafo.mas_cercano(otro.celda_suelo)
            return {n} if n else set()
        if self.modo == "boton":
            return {(cx, cy) for (_, cx, cy) in self.juego.nivel.placas if (cx, cy) in self.grafo.nodos}
        if self.modo == "ir" and self.meta in self.grafo.nodos:
            return {self.meta}
        return set()

    def fallar(self):
        if self.arista:
            self.grafo.bloquear(*self.arista)
        self.ejecutor = None
        self.arista = None
        self.pausa = 12

    def control(self, yo, otro, mundo):
        """Devuelve (dirección, salto) para este fotograma."""
        self.grafo.reloj += 1
        if self.t_mensaje > 0:
            self.t_mensaje -= 1
        if self.modo == "esperar":
            return 0.0, False
        if self.pausa > 0:
            self.pausa -= 1
            return 0.0, False

        if self.ejecutor:
            d, s, est = self.ejecutor.paso(yo, mundo)
            if est == "fallo":
                self.fallar()
                return 0.0, False
            if est is None:
                # ¿Atascado contra algo (una caja, una puerta cerrada)?
                if yo.suelo and d != 0 and self.x_prev is not None and abs(yo.x - self.x_prev) < 0.01:
                    self.sin_avance += 1
                else:
                    self.sin_avance = 0
                self.x_prev = yo.x
                if self.sin_avance > 25:
                    self.sin_avance = 0
                    self.fallar()
                    return 0.0, False
                return d, s
            self.ejecutor = None                         # llegó a su casilla: elige la siguiente

        if not yo.suelo:
            return 0.0, False
        nodo = self.nodo_actual(yo)
        if nodo is None:
            return 0.0, False
        metas = self.objetivos(otro)
        if not metas:
            return 0.0, False

        # ¿Ya llegó?
        cx = yo.x + yo.w / 2
        if self.modo == "seguir":
            ox, oy = otro.x + otro.w / 2, otro.y + otro.h / 2
            if abs(cx - ox) < 70 and abs((yo.y + yo.h / 2) - oy) < 46:
                return 0.0, False
        elif nodo in metas:
            if self.modo in ("boton", "auto"):
                centro = (nodo[0] + 0.5) * TILE
                if abs(centro - cx) > 3:
                    return max(-1.0, min(1.0, (centro - cx) / yo.perfil["vel"])), False
                if self.modo == "boton":
                    self.modo = "esperar"
                    self.decir("Listo, aquí me quedo")
            return 0.0, False

        ruta = self.grafo.camino(nodo, metas)
        if not ruta:
            if not self.avisado_sin_ruta:
                self.decir("No llego hasta allí")
                self.avisado_sin_ruta = True
            self.pausa = 30
            return 0.0, False
        self.avisado_sin_ruta = False
        self.arista = ruta[0]
        self.ejecutor = Ejecutor(self.arista[2], self.arista[0], self.arista[1], yo.perfil)
        self.x_prev = None
        self.sin_avance = 0
        d, s, est = self.ejecutor.paso(yo, mundo)
        return d, s


# ---------- Juego ----------
def oscurecer(color, f=0.6):
    return int(color[0] * f), int(color[1] * f), int(color[2] * f)


def aclarar(color, f=0.35):
    return (int(color[0] + (255 - color[0]) * f), int(color[1] + (255 - color[1]) * f),
            int(color[2] + (255 - color[2]) * f))


class Juego:
    MODOS = {"ambar": "Jugar con Ámbar  (la IA controla a Zafiro)",
             "zafiro": "Jugar con Zafiro  (la IA controla a Ámbar)",
             "dos": "Dos jugadores  (mismo teclado)"}

    def __init__(self, nivel_inicio=0, modo_demo=None):
        global sonidos
        pygame.init()
        pygame.display.set_caption("Ámbar y Zafiro")
        pygame.display.set_mode((ANCHO, ALTO), pygame.RESIZABLE)
        sonidos = SonidoJuego()
        self.lienzo = pygame.Surface((ANCHO, ALTO))
        self.reloj = pygame.time.Clock()
        self.f_peq = pygame.font.SysFont("consolas", 14)
        self.f_med = pygame.font.SysFont("consolas", 20, bold=True)
        self.f_gde = pygame.font.SysFont("consolas", 46, bold=True)
        self.cache_texto = {}
        self.fondo = self.crear_fondo()
        self.nivel_inicio = nivel_inicio
        self.estado = "menu"
        self.pausado = False
        self.ias, self.cache_ias = {}, {}
        self.humano = None
        self.modo_juego = None
        self.tiempo_total = 0
        self.t_anim = 0.0
        self.causa = ""
        self.menu_rects = []
        self.mouse_pos = (-1, -1)
        self.forzados = {}                   # controles impuestos (solo para pruebas)
        self.nivel = NIVELES[0]
        self.mundo = None
        self.pers = {}
        if modo_demo:
            self.empezar(modo_demo)

    # ---------- Carga ----------
    def crear_fondo(self):
        s = pygame.Surface((ANCHO, ALTO))
        for y in range(ALTO):
            f = y / ALTO
            col = tuple(int(COLOR_FONDO_A[i] + (COLOR_FONDO_B[i] - COLOR_FONDO_A[i]) * f) for i in range(3))
            pygame.draw.line(s, col, (0, y), (ANCHO, y))
        # Textura tenue de piedra y polvo luminoso en el fondo de cada sala.
        for y in range(28, ALTO, 48):
            pygame.draw.line(s, (35, 41, 68), (0, y), (ANCHO, y), 1)
        for i in range(72):
            x = (i * 193 + 41) % ANCHO
            y = (i * 127 + 17) % ALTO
            brillo = 48 + (i * 19) % 54
            pygame.draw.circle(s, (brillo // 2, brillo, min(150, brillo + 35)), (x, y), 1 + i % 2)
        pygame.draw.ellipse(s, (25, 33, 60), (ANCHO // 2 - 310, 120, 620, 380), 1)
        return s

    def empezar(self, modo):
        sonidos.reproducir("inicio")
        self.modo_juego = modo
        self.cache_ias = {}
        self.cargar_nivel(self.nivel_inicio)

    def cargar_nivel(self, idx):
        self.idx = idx
        self.nivel = NIVELES[idx]
        self.mundo = Mundo(self.nivel)
        self.pers = {k: Personaje(k, *self.nivel.inicio[k]) for k in ("ambar", "zafiro")}
        self.mundo.personajes = self.pers
        self.ias = {}
        self.cache_ias = {}
        if self.modo_juego in ("ambar", "zafiro"):
            self.humano = self.modo_juego
            ia = self.obtener_ia(OTRO[self.humano])
            ia.ordenar("auto")
            ia.mensaje = ""
        elif self.modo_juego == "auto":          # solo para pruebas: dos IA
            self.humano = None
            for k in self.pers:
                self.obtener_ia(k)
        else:
            self.humano = None
        self.tiempo = 0.0
        self.t_anim = 0.0
        self.estado = "jugando"
        self.pausado = False
        self.fondo_nivel = self.crear_capa_estatica()

    def obtener_ia(self, clave):
        if clave not in self.cache_ias:
            self.cache_ias[clave] = IA(self, clave)
        ia = self.cache_ias[clave]
        self.ias[clave] = ia
        return ia

    # ---------- Entrada ----------
    def leer_humanos(self):
        t = pygame.key.get_pressed()
        izq_wasd, der_wasd = t[pygame.K_a], t[pygame.K_d]
        izq_fl, der_fl = t[pygame.K_LEFT], t[pygame.K_RIGHT]
        saltar_wasd, saltar_fl = t[pygame.K_w], t[pygame.K_UP]
        if self.modo_juego == "dos":
            return {"ambar": (float(der_wasd - izq_wasd), bool(saltar_wasd)),
                    "zafiro": (float(der_fl - izq_fl), bool(saltar_fl))}
        d = float((der_wasd or der_fl) - (izq_wasd or izq_fl))
        return {self.humano: (d, bool(saltar_wasd or saltar_fl or t[pygame.K_SPACE]))}

    def cambiar_personaje(self):
        if self.modo_juego not in ("ambar", "zafiro"):
            return
        viejo, nuevo = self.humano, OTRO[self.humano]
        self.ias.pop(nuevo, None)
        self.humano = nuevo
        ia = self.obtener_ia(viejo)
        ia.ordenar("esperar")

    def orden_ia(self, modo):
        if self.humano is None or self.modo_juego == "dos":
            return
        self.ias[OTRO[self.humano]].ordenar(modo)

    # ---------- Lógica ----------
    def paso(self):
        """Un fotograma de física (1/60 s). Se puede llamar sin pantalla, para pruebas."""
        if self.estado != "jugando" or self.pausado:
            return
        self.tiempo += 1 / FPS
        controles = self.leer_humanos() if self.modo_juego != "auto" else {}
        for clave, c in self.pers.items():
            c.empuja_activo = clave not in self.ias
            if clave in self.ias:
                otro = self.pers[OTRO[clave]]
                controles[clave] = self.ias[clave].control(c, otro, self.mundo)
        controles.update(self.forzados)
        for clave, c in self.pers.items():
            direccion, saltar = controles.get(clave, (0.0, False))
            if saltar and c.suelo:
                sonidos.reproducir("saltar")
            c.paso(direccion, saltar, self.mundo)
            if c.suelo:
                c.celda_suelo = c.celda()
        botones_antes = tuple(pl.pulsada for pl in self.mundo.placas)
        puertas_antes = tuple(pu.abierta for pu in self.mundo.puertas)
        self.mundo.actualizar()
        if botones_antes != tuple(pl.pulsada for pl in self.mundo.placas):
            sonidos.reproducir("boton")
        if any(not antes and pu.abierta for antes, pu in zip(puertas_antes, self.mundo.puertas)):
            sonidos.reproducir("puerta")
        self.revisar()

    def revisar(self):
        for clave, c in self.pers.items():
            p = toca_peligro(self.nivel, c, c.perfil["inmune"])
            if p:
                self.causa = f"{c.perfil['nombre']} cayó en {NOMBRES_PELIGRO[p]}"
                self.estado = "muerto"
                sonidos.reproducir("muerte")
                return
            ex, ey = self.nivel.salida[clave]
            cx, cy = c.x + c.w / 2, c.y + c.h / 2
            c.dentro = ex * TILE <= cx < (ex + 1) * TILE and ey * TILE <= cy < (ey + 1) * TILE
        if all(c.dentro for c in self.pers.values()):
            self.estado = "nivel_ok"
            sonidos.reproducir("victoria")

    # ---------- Dibujo ----------
    def texto(self, fuente, contenido, color):
        clave = (id(fuente), contenido, color)
        img = self.cache_texto.get(clave)
        if img is None:
            if len(self.cache_texto) > 400:
                self.cache_texto.clear()
            img = fuente.render(contenido, True, color)
            self.cache_texto[clave] = img
        return img

    def poner(self, s, fuente, contenido, color, pos, modo="izq"):
        img = self.texto(fuente, contenido, color)
        r = img.get_rect()
        if modo == "centro":
            r.center = pos
        elif modo == "der":
            r.topright = pos
        else:
            r.topleft = pos
        s.blit(img, r)

    def crear_capa_estatica(self):
        s = self.fondo.copy()
        n = self.nivel
        for cy in range(ROWS):
            for cx in range(COLS):
                if not n.solido[cy][cx]:
                    continue
                r = pygame.Rect(cx * TILE, cy * TILE, TILE, TILE)
                variacion = ((cx * 13 + cy * 7) % 9) - 4
                base = tuple(max(0, min(255, c + variacion)) for c in COLOR_PARED)
                pygame.draw.rect(s, base, r)
                pygame.draw.rect(s, COLOR_PARED_OSCURA, r, 1)
                interior = r.inflate(-5, -5)
                pygame.draw.rect(s, aclarar(base, 0.10), interior, border_radius=4)
                pygame.draw.line(s, aclarar(base, 0.3), (r.x + 4, r.y + 4), (r.right - 5, r.y + 4), 2)
                pygame.draw.line(s, COLOR_PARED_OSCURA, (r.x + 4, r.bottom - 4), (r.right - 5, r.bottom - 4), 2)
                if (cx + cy) % 3 == 0:
                    pygame.draw.circle(s, (125, 143, 184), (r.x + 9, r.y + 12), 2)
                    pygame.draw.circle(s, (46, 53, 86), (r.right - 9, r.bottom - 11), 2)
                if not n.es_solido(cx, cy - 1):
                    pygame.draw.rect(s, (105, 190, 171), (r.x, r.y, TILE, 4))
                    pygame.draw.line(s, (164, 224, 191), (r.x + 4, r.y + 2), (r.right - 5, r.y + 2), 1)
                if cy + 1 < ROWS and not n.es_solido(cx, cy + 1):
                    pygame.draw.rect(s, COLOR_PARED_OSCURA, (r.x, r.bottom - 5, TILE, 5))
        return s

    def dibujar_peligros(self, s):
        for cy in range(ROWS):
            for cx in range(COLS):
                p = self.nivel.peligro[cy][cx]
                if not p:
                    continue
                col = COLORES_PELIGRO[p]
                r = pygame.Rect(cx * TILE, cy * TILE, TILE, TILE)
                pygame.draw.rect(s, oscurecer(col, 0.78), r)
                puntos = [(r.x, r.bottom), (r.x, r.y + 4)]
                for x in range(0, TILE + 1, 4):
                    if p == "L":
                        ola = math.sin((cx * TILE + x) * 0.23 + self.t_anim * 5) * 3
                    elif p == "W":
                        ola = math.sin((cx * TILE + x) * 0.15 + self.t_anim * 2.8) * 2
                    else:
                        ola = math.sin((cx * TILE + x) * 0.3 + self.t_anim * 3.5) * 4
                    puntos.append((r.x + x, r.y + 4 + ola))
                puntos.append((r.right, r.bottom))
                pygame.draw.polygon(s, col, puntos)
                pygame.draw.lines(s, aclarar(col), False, puntos[1:-1], 2)
                if p == "L":
                    # Brasas que titilan sobre la lava.
                    for i in range(3):
                        bx = r.x + 7 + (i * 13 + int(self.t_anim * (8 + i))) % 28
                        by = r.y + 12 + int(math.sin(self.t_anim * 4 + i + cx) * 3)
                        pygame.draw.circle(s, (255, 218, 115), (bx, by), 2)
                elif p == "W":
                    for i in range(2):
                        bx = r.x + 10 + (i * 17 + int(self.t_anim * 5)) % 25
                        by = r.y + 16 + int(math.sin(self.t_anim * 2 + i + cy) * 5)
                        pygame.draw.circle(s, (133, 215, 255), (bx, by), 2, 1)
                else:
                    pulso = 2 + int((math.sin(self.t_anim * 3 + cx + cy) + 1) * 1.5)
                    pygame.draw.circle(s, (202, 255, 135), (r.centerx, r.y + 17), pulso, 1)

    def dibujar_objetos(self, s):
        # Salidas
        for clave, (cx, cy) in self.nivel.salida.items():
            col = PERFILES[clave]["color"]
            r = pygame.Rect(cx * TILE + 3, cy * TILE + 2, TILE - 6, TILE - 2)
            dentro = self.pers[clave].dentro
            pygame.draw.rect(s, oscurecer(col, 0.35), r, border_top_left_radius=16, border_top_right_radius=16)
            pygame.draw.rect(s, aclarar(col, 0.4) if dentro else col, r, 3,
                             border_top_left_radius=16, border_top_right_radius=16)
            if dentro:
                pygame.draw.rect(s, col, r.inflate(-10, -8), border_top_left_radius=12, border_top_right_radius=12)
        # Botones
        for pl in self.mundo.placas:
            col = COLORES_LETRA[pl.letra]
            alto = 4 if pl.pulsada else 8
            pygame.draw.rect(s, oscurecer(col, 0.5), (pl.cx * TILE + 2, (pl.cy + 1) * TILE - 3, TILE - 4, 3))
            pygame.draw.rect(s, col, (pl.cx * TILE + 5, (pl.cy + 1) * TILE - 3 - alto, TILE - 10, alto), border_radius=3)
        # Puertas
        for pu in self.mundo.puertas:
            col = COLORES_LETRA[pu.letra]
            alto = int(TILE * (1 - pu.visual))
            if alto > 1:
                marco = pygame.Rect(pu.cx * TILE + 5, pu.cy * TILE, TILE - 10, alto)
                pygame.draw.rect(s, oscurecer(col, 0.38), marco, border_radius=6)
                if alto > 5:
                    pygame.draw.rect(s, oscurecer(col, 0.68), marco.inflate(-6, -5), border_radius=4)
                    pygame.draw.rect(s, aclarar(col, 0.22), marco.inflate(-12, -10), border_radius=3)
                    pygame.draw.circle(s, aclarar(col, 0.55), (marco.centerx, marco.centery), 3)
        # Cajas
        for c in self.mundo.cajas:
            r = pygame.Rect(int(c.x), int(c.y), c.w, c.h)
            pygame.draw.ellipse(s, (7, 10, 20), (r.x + 1, r.bottom - 3, r.w, 8))
            pygame.draw.rect(s, (82, 48, 41), r, border_radius=6)
            pygame.draw.rect(s, (184, 119, 70), r.inflate(-4, -4), border_radius=5)
            pygame.draw.rect(s, (222, 164, 95), r.inflate(-10, -10), border_radius=4)
            pygame.draw.rect(s, (102, 61, 42), r, 2, border_radius=6)
            pygame.draw.line(s, (142, 83, 49), (r.x + 7, r.y + 8), (r.right - 7, r.y + 8), 2)
            pygame.draw.line(s, (142, 83, 49), (r.x + 7, r.bottom - 8), (r.right - 7, r.bottom - 8), 2)
            pygame.draw.circle(s, (255, 213, 132), r.center, 3)

    def dibujar_personaje(self, s, c):
        """Sprites elementales: ?mbar es una llama y Zafiro una gota/cristal."""
        col = c.perfil["color"]
        brillo = aclarar(col, 0.40)
        sombra = oscurecer(col, 0.42)
        r = pygame.Rect(int(c.x), int(c.y), c.w, c.h)
        paso = int(self.t_anim * 11) % 2 if c.suelo else 0
        flotacion = -1 if not c.suelo else 0
        pygame.draw.ellipse(s, (8, 11, 23), (r.x + 2, r.bottom - 3, r.w - 4, 8))
        pygame.draw.ellipse(s, aclarar(col, 0.12), r.inflate(13, 13), 2)

        if c.clave == "ambar":
            # Silueta irregular y capas calidas para que parezca fuego vivo.
            flicker = int(math.sin(self.t_anim * 12) * 2)
            pygame.draw.polygon(s, (184, 53, 40), [
                (r.centerx, r.y - 4 + flicker), (r.centerx + 6, r.y + 7),
                (r.right - 1, r.y + 13), (r.right - 3, r.bottom - 7),
                (r.centerx + 5, r.bottom - 1), (r.centerx, r.bottom - 7),
                (r.x + 5, r.bottom - 1), (r.x + 2, r.y + 13), (r.centerx - 5, r.y + 7)])
            pygame.draw.ellipse(s, (232, 83, 42), (r.x + 5, r.y + 12 + flotacion, r.w - 10, r.h - 14))
            pygame.draw.polygon(s, col, [
                (r.centerx, r.y + 4 + flicker), (r.centerx + 4, r.y + 15),
                (r.right - 6, r.y + 18), (r.right - 7, r.bottom - 10),
                (r.centerx, r.bottom - 4), (r.x + 7, r.bottom - 10), (r.x + 6, r.y + 18)])
            pygame.draw.ellipse(s, brillo, (r.x + 9, r.y + 19 + flotacion, r.w - 18, r.h - 23))
            # Peque?as lenguas laterales y brasas animadas.
            for lado in (-1, 1):
                px = r.centerx + lado * (r.w // 2 - 1)
                pygame.draw.polygon(s, (255, 157, 57), [
                    (px, r.y + 20), (px + lado * 7, r.y + 14), (px + lado * 4, r.y + 29)])
                pygame.draw.circle(s, (255, 235, 155),
                                   (r.centerx + lado * (5 + paso), r.bottom - 2), 2)
            pygame.draw.polygon(s, (255, 232, 154), [
                (r.centerx, r.y + 25), (r.centerx + 4, r.y + 31),
                (r.centerx, r.y + 37), (r.centerx - 4, r.y + 31)])
        else:
            # Cuerpo en forma de gota con una faceta de hielo y reflejos acuosos.
            pygame.draw.polygon(s, (30, 94, 173), [
                (r.centerx, r.y - 4), (r.centerx + 8, r.y + 8),
                (r.right - 1, r.y + 18), (r.right - 2, r.bottom - 10),
                (r.centerx, r.bottom), (r.x + 2, r.bottom - 10),
                (r.x + 1, r.y + 18), (r.centerx - 8, r.y + 8)])
            pygame.draw.ellipse(s, col, (r.x + 4, r.y + 15 + flotacion, r.w - 8, r.h - 18))
            pygame.draw.polygon(s, brillo, [
                (r.centerx, r.y + 1), (r.centerx + 6, r.y + 13),
                (r.right - 5, r.y + 20), (r.right - 6, r.bottom - 11),
                (r.centerx, r.bottom - 4), (r.x + 6, r.bottom - 11),
                (r.x + 5, r.y + 20), (r.centerx - 6, r.y + 13)])
            pygame.draw.polygon(s, (225, 250, 255), [
                (r.centerx, r.y - 1), (r.centerx + 5, r.y + 9),
                (r.centerx, r.y + 16), (r.centerx - 4, r.y + 8)])
            pygame.draw.ellipse(s, (65, 194, 239),
                                (r.x + 7, r.y + 25 + flotacion, r.w - 14, 6), 1)
            pygame.draw.circle(s, (209, 249, 255), (r.x + 6, r.y + 14), 2)
            pygame.draw.circle(s, (209, 249, 255), (r.right - 6, r.y + 20), 2)
            pygame.draw.circle(s, (147, 228, 255), (r.x + 2, r.y + 29), 3)
            pygame.draw.circle(s, (147, 228, 255), (r.right - 2, r.y + 29), 3)

        # Caras expresivas y pupilas que siguen la direccion de movimiento.
        ojo_y = r.y + 21 + flotacion
        for off in (-1, 1):
            ox = r.centerx + off * 5 + c.mirando * 2
            pygame.draw.ellipse(s, (250, 253, 255), (ox - 3, ojo_y - 4, 7, 10))
            pygame.draw.circle(s, (22, 31, 52), (ox + c.mirando, ojo_y + 1), 2)
            pygame.draw.circle(s, BLANCO, (ox + c.mirando, ojo_y), 1)
        pygame.draw.arc(s, sombra, (r.centerx - 4, ojo_y + 3, 8, 5), 0.1, 3.0, 1)
        if c.clave == "ambar":
            pygame.draw.polygon(s, (255, 157, 57), [(r.x + 5, ojo_y + 8), (r.x - 2, ojo_y + 5), (r.x + 3, ojo_y + 16)])
            pygame.draw.polygon(s, (255, 157, 57), [(r.right - 5, ojo_y + 8), (r.right + 2, ojo_y + 5), (r.right - 3, ojo_y + 16)])
        else:
            pygame.draw.arc(s, (211, 250, 255), (r.x + 6, r.bottom - 9, r.w - 12, 8), 0.1, 3.0, 2)

    def dibujar_burbuja(self, s, ia, c):
        if ia.t_mensaje <= 0 or not ia.mensaje:
            return
        img = self.texto(self.f_peq, ia.mensaje, (20, 20, 40))
        r = img.get_rect()
        r.midbottom = (int(c.x + c.w / 2), int(c.y) - 14)
        r.clamp_ip(pygame.Rect(2, 44, ANCHO - 4, ALTO))
        caja = r.inflate(14, 8)
        pygame.draw.rect(s, (245, 245, 255), caja, border_radius=8)
        pygame.draw.polygon(s, (245, 245, 255), [(c.x + c.w / 2 - 5, caja.bottom - 1), (c.x + c.w / 2 + 5, caja.bottom - 1),
                                                 (c.x + c.w / 2, caja.bottom + 6)])
        s.blit(img, r)

    def estado_ia(self, clave):
        ia = self.ias.get(clave)
        if not ia:
            return ""
        return {"auto": "decidiendo ruta", "esperar": "esperando", "seguir": "siguiéndote", "boton": "yendo a un botón",
                "ir": "en camino"}.get(ia.modo, ia.modo)

    def dibujar_hud(self, s):
        self.poner(s, self.f_med, f"Nivel {self.idx + 1}/{len(NIVELES)}: {self.nivel.titulo}", BLANCO, (10, 2))
        m, seg = int(self.tiempo // 60), int(self.tiempo % 60)
        self.poner(s, self.f_med, f"{m}:{seg:02d}", BLANCO, (ANCHO - 10, 2), "der")
        if self.modo_juego == "dos":
            ayuda = "Ámbar: A D W     Zafiro: flechas     Retroceso: reiniciar     P: pausa     ESC: menú"
        else:
            ia = OTRO[self.humano]
            ayuda = (f"IA auto  T: retomar auto  Q: sígueme  E: espera  R: botón  TAB: cambiar  "
                     f"| {PERFILES[ia]['nombre']} (IA): {self.estado_ia(ia)}")
        self.poner(s, self.f_peq, ayuda, GRIS, (10, 24))
        if self.tiempo < 7 and self.estado == "jugando":
            banda = pygame.Surface((ANCHO, 26), pygame.SRCALPHA)
            banda.fill((0, 0, 0, 150))
            s.blit(banda, (0, 44))
            self.poner(s, self.f_peq, self.nivel.pista, (255, 235, 160), (ANCHO // 2, 57), "centro")

    def dibujar_pantalla_menu(self, s):
        s.blit(self.fondo, (0, 0))
        # Motas luminosas y franjas para evocar una portada arcade de navegador.
        for i in range(18):
            x = (i * 137 + int(self.t_anim * (12 + i % 5))) % ANCHO
            y = (i * 83 + int(self.t_anim * (5 + i % 3))) % ALTO
            pygame.draw.circle(s, (55, 78, 122), (x, y), 2 + i % 3)
        panel = pygame.Rect(96, 35, ANCHO - 192, ALTO - 70)
        pygame.draw.rect(s, (8, 12, 28), panel.move(0, 8), border_radius=26)
        pygame.draw.rect(s, (27, 36, 68), panel, border_radius=26)
        pygame.draw.rect(s, (91, 120, 184), panel, 2, border_radius=26)
        pygame.draw.rect(s, (255, 174, 70), (panel.x + 2, panel.y + 2, panel.w // 2 - 2, 7), border_top_left_radius=24)
        pygame.draw.rect(s, (75, 174, 255), (panel.centerx, panel.y + 2, panel.w // 2 - 2, 7), border_top_right_radius=24)
        titulo = self.f_gde.render("AMBAR Y ZAFIRO", True, (255, 224, 131))
        sombra = self.f_gde.render("AMBAR Y ZAFIRO", True, (94, 53, 42))
        s.blit(sombra, sombra.get_rect(center=(ANCHO // 2 + 3, 91 + 4)))
        s.blit(titulo, titulo.get_rect(center=(ANCHO // 2, 91)))
        self.poner(s, self.f_med, "DOS HEROES  •  UNA AVENTURA  •  OCHO CAMARAS", (170, 203, 242),
                   (ANCHO // 2, 133), "centro")

        self.menu_rects = []
        opciones = [
            ("1", "AVENTURA AMBAR", "Juega con Ámbar; Zafiro te ayuda con IA.", (247, 145, 65)),
            ("2", "AVENTURA ZAFIRO", "Juega con Zafiro; Ámbar te ayuda con IA.", (85, 175, 245)),
            ("3", "DOS JUGADORES", "Cooperad con el mismo teclado.", (169, 125, 245)),
        ]
        for i, (numero, nombre, detalle, tono) in enumerate(opciones):
            r = pygame.Rect(150, 165 + i * 77, 660, 65)
            hover = r.collidepoint(self.mouse_pos)
            pygame.draw.rect(s, (16, 22, 42), r.move(0, 4), border_radius=13)
            pygame.draw.rect(s, (49, 62, 99) if hover else (36, 47, 78), r, border_radius=13)
            pygame.draw.rect(s, tono, r, 2 if hover else 1, border_radius=13)
            pygame.draw.circle(s, tono, (r.x + 34, r.centery), 19)
            self.poner(s, self.f_med, numero, (20, 25, 45), (r.x + 34, r.centery), "centro")
            self.poner(s, self.f_med, nombre, BLANCO, (r.x + 68, r.y + 9))
            self.poner(s, self.f_peq, detalle, (180, 192, 220), (r.x + 68, r.y + 37))
            self.menu_rects.append((r, ("modo", ("ambar", "zafiro", "dos")[i])))

        selector = pygame.Rect(235, 407, 490, 47)
        pygame.draw.rect(s, (18, 25, 47), selector, border_radius=12)
        pygame.draw.rect(s, (73, 94, 144), selector, 1, border_radius=12)
        left = pygame.Rect(selector.x + 10, selector.y + 5, 48, 37)
        right = pygame.Rect(selector.right - 58, selector.y + 5, 48, 37)
        for r, signo, delta in ((left, "<", -1), (right, ">", 1)):
            pygame.draw.rect(s, (66, 92, 145) if r.collidepoint(self.mouse_pos) else (43, 59, 96), r, border_radius=9)
            self.poner(s, self.f_med, signo, BLANCO, r.center, "centro")
            self.menu_rects.append((r, ("nivel", delta)))
        self.poner(s, self.f_med, f"CAMARA {self.nivel_inicio + 1:02d} / {len(NIVELES):02d}   ·   {NIVELES[self.nivel_inicio].titulo.upper()}",
                   (255, 224, 131), selector.center, "centro")

        for i, texto in enumerate(("AMBAR: A/D mueve · W salta · empuja cajas · resiste lava",
                                   "ZAFIRO: flechas mueve/salta · salta alto · resiste agua",
                                   "IA: actua sola con botones y salidas. T auto · Q seguir · E esperar · R boton · TAB cambiar")):
            self.poner(s, self.f_peq, texto, (168, 181, 211), (ANCHO // 2, 474 + i * 20), "centro")
        self.poner(s, self.f_peq, "CLICK O TECLAS 1 / 2 / 3 PARA JUGAR     ·     FLECHAS PARA ELEGIR CAMARA",
                   (116, 139, 183), (ANCHO // 2, 552), "centro")
        for i, clave in enumerate(("ambar", "zafiro")):
            c = Personaje(clave, 0, 0)
            c.x, c.y = ANCHO // 2 - 156 + i * 310, 85
            c.mirando = 1 if i == 0 else -1
            self.dibujar_personaje(s, c)

    def click_menu(self, posicion):
        for rect, accion in self.menu_rects:
            if not rect.collidepoint(posicion):
                continue
            tipo, valor = accion
            if tipo == "modo":
                self.empezar(valor)
            else:
                self.nivel_inicio = max(0, min(len(NIVELES) - 1, self.nivel_inicio + valor))
            return

    def velo(self, s, textos):
        v = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        v.fill((3, 7, 20, 190))
        s.blit(v, (0, 0))
        tono = (255, 118, 116) if self.estado == "muerto" else (137, 222, 173)
        panel = pygame.Rect(140, 188, ANCHO - 280, 224)
        pygame.draw.rect(s, (9, 15, 33), panel.move(0, 7), border_radius=24)
        pygame.draw.rect(s, (25, 35, 64), panel, border_radius=24)
        pygame.draw.rect(s, tono, panel, 2, border_radius=24)
        for i, (f, t, col, y) in enumerate(textos):
            self.poner(s, f, t, col, (ANCHO // 2, y), "centro")

    def dibujar(self):
        s = self.lienzo
        if self.estado == "menu":
            self.dibujar_pantalla_menu(s)
        else:
            s.blit(self.fondo_nivel, (0, 0))
            self.dibujar_peligros(s)
            self.dibujar_objetos(s)
            for c in self.pers.values():
                self.dibujar_personaje(s, c)
            for clave, ia in self.ias.items():
                self.dibujar_burbuja(s, ia, self.pers[clave])
            self.dibujar_hud(s)
            if self.pausado:
                self.velo(s, [(self.f_gde, "PAUSA", BLANCO, ALTO // 2)])
            elif self.estado == "muerto":
                self.velo(s, [(self.f_gde, "¡Oh no!", (255, 120, 120), 240), (self.f_med, self.causa, BLANCO, 300),
                              (self.f_peq, "ENTER o Retroceso: reintentar   |   ESC: menú", GRIS, 350)])
            elif self.estado == "nivel_ok":
                ultimo = self.idx == len(NIVELES) - 1
                titulo = "¡Escaparon de todas las habitaciones!" if ultimo else "¡Nivel completado!"
                sub = "ENTER: volver al menú" if ultimo else "ENTER: siguiente nivel"
                m, seg = int(self.tiempo // 60), int(self.tiempo % 60)
                self.velo(s, [(self.f_gde if not ultimo else self.f_med, titulo, (140, 240, 160), 240),
                              (self.f_med, f"Tiempo: {m}:{seg:02d}", BLANCO, 300), (self.f_peq, sub, GRIS, 350)])
        # Escalar a la ventana sin deformar
        ventana = pygame.display.get_surface()
        w, h = ventana.get_size()
        f = min(w / ANCHO, h / ALTO)
        tam = (max(1, int(ANCHO * f)), max(1, int(ALTO * f)))
        ventana.fill((0, 0, 0))
        ventana.blit(pygame.transform.smoothscale(s, tam) if tam != (ANCHO, ALTO) else s,
                     ((w - tam[0]) // 2, (h - tam[1]) // 2))

    # ---------- Bucle principal ----------
    def tecla(self, k):
        if self.estado == "menu":
            if k in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.empezar(("ambar", "zafiro", "dos")[k - pygame.K_1])
            elif k == pygame.K_RIGHT:
                self.nivel_inicio = min(len(NIVELES) - 1, self.nivel_inicio + 1)
            elif k == pygame.K_LEFT:
                self.nivel_inicio = max(0, self.nivel_inicio - 1)
            elif k == pygame.K_ESCAPE:
                return False
            return True
        if k == pygame.K_ESCAPE:
            self.estado = "menu"
        elif k == pygame.K_p and self.estado == "jugando":
            self.pausado = not self.pausado
        elif k == pygame.K_BACKSPACE:
            self.cargar_nivel(self.idx)
        elif k == pygame.K_RETURN:
            if self.estado == "muerto":
                self.cargar_nivel(self.idx)
            elif self.estado == "nivel_ok":
                if self.idx + 1 < len(NIVELES):
                    self.cargar_nivel(self.idx + 1)
                else:
                    self.estado = "menu"
        elif self.estado == "jugando" and not self.pausado:
            if k == pygame.K_q:
                self.orden_ia("seguir")
            elif k == pygame.K_e:
                self.orden_ia("esperar")
            elif k == pygame.K_r:
                self.orden_ia("boton")
            elif k == pygame.K_t:
                self.orden_ia("auto")
            elif k == pygame.K_TAB:
                self.cambiar_personaje()
        return True

    def posicion_lienzo(self, posicion):
        ventana = pygame.display.get_surface()
        w, h = ventana.get_size()
        factor = min(w / ANCHO, h / ALTO)
        ox, oy = (w - ANCHO * factor) / 2, (h - ALTO * factor) / 2
        return ((posicion[0] - ox) / factor, (posicion[1] - oy) / factor)

    def ejecutar(self):
        acumulado = 0.0
        corriendo = True
        while corriendo:
            dt = min(self.reloj.tick(FPS) / 1000, 0.1)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    corriendo = False
                elif e.type == pygame.KEYDOWN:
                    corriendo = self.tecla(e.key) and corriendo
                elif e.type == pygame.MOUSEMOTION and self.estado == "menu":
                    self.mouse_pos = self.posicion_lienzo(e.pos)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.estado == "menu":
                    self.mouse_pos = self.posicion_lienzo(e.pos)
                    self.click_menu(self.mouse_pos)
            acumulado += dt
            while acumulado >= 1 / FPS:
                self.paso()
                acumulado -= 1 / FPS
            self.t_anim += dt
            self.dibujar()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    inicio = 0
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        inicio = max(0, min(len(NIVELES) - 1, int(sys.argv[1]) - 1))
    Juego(nivel_inicio=inicio).ejecutar()
