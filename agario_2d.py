"""
Agar 2D - juego estilo agar.io

Controles:
  Mouse            -> la célula se mueve hacia el cursor
  W A S D / flechas-> alternativa con teclado
  ESPACIO          -> sprint (gasta masa mientras lo mantienes)
  P                -> pausa
  ENTER            -> volver a jugar (cuando te comen)
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
MASA_COMIDA = 2
RADIO_K = 3.2             # radio = RADIO_K * raiz(masa)
VENTAJA = 1.15            # hace falta tener 15% más de masa para comerse a otra
MASA_MIN_SPRINT = 25
COSTO_SPRINT = 0.04       # fracción de masa por segundo que cuesta el sprint
MASA_MAX_NPC = 12000
INMUNIDAD_INICIAL = 6.0   # segundos sin poder ser comido al empezar
SPRINT_NPC_MAX = 1.5      # un NPC solo puede hacer sprint 1.5 s seguidos...
SPRINT_NPC_ESPERA = 5.0   # ...y luego debe descansar 5 s
RADIO_COMIDA = 6

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

    @property
    def r(self):
        return RADIO_K * math.sqrt(self.masa)

    def velocidad(self):
        v = 230 * self.masa ** -0.08
        if self.sprint:
            v *= 1.6
        return v if self.es_jugador else v * self.factor_vel

    def mover(self, dt):
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
        self.celulas = [self.jugador]
        for _ in range(N_NPC):
            self.celulas.append(self.crear_npc(lejos_de=self.jugador))
        self.cola_respawn = []
        self.estado = "jugando"      # jugando | muerto
        self.pausado = False
        self.cam_x, self.cam_y = self.jugador.x, self.jugador.y
        self.escala = 1.0
        self.tiempo = 0.0
        self.masa_max = MASA_INICIAL
        self.asesino = ""

    def nueva_comida(self):
        return Comida(random.uniform(0, MUNDO), random.uniform(0, MUNDO), color_aleatorio(0.8))

    # ---------- Entrada del jugador ----------
    def leer_entrada(self):
        """Devuelve (dir_x, dir_y, sprint). Separado para poder probarlo."""
        teclas = pygame.key.get_pressed()
        kx = (teclas[pygame.K_d] or teclas[pygame.K_RIGHT]) - (teclas[pygame.K_a] or teclas[pygame.K_LEFT])
        ky = (teclas[pygame.K_s] or teclas[pygame.K_DOWN]) - (teclas[pygame.K_w] or teclas[pygame.K_UP])
        sprint = bool(teclas[pygame.K_SPACE])
        if kx or ky:
            dx, dy = normalizar(kx, ky)
            return dx, dy, sprint
        w, h = pygame.display.get_surface().get_size()
        mx, my = pygame.mouse.get_pos()
        vx, vy = mx - w / 2, my - h / 2
        dist = math.hypot(vx, vy)
        if dist < 6:
            return 0.0, 0.0, sprint
        zona = max(40, self.jugador.r * self.escala)   # cerca del centro va más despacio
        fuerza = min(1.0, dist / zona)
        dx, dy = normalizar(vx, vy)
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
        if self.pausado:
            return
        if self.estado == "jugando":
            self.tiempo += dt
            dx, dy, sprint = self.leer_entrada()
            j = self.jugador
            j.tx, j.ty = dx, dy
            j.sprint = sprint and j.masa > MASA_MIN_SPRINT

        for c in self.celulas:
            if not c.es_jugador:
                c.t_pensar -= dt
                if c.t_pensar <= 0:
                    self.pensar(c)
                    c.t_pensar = random.uniform(0.2, 0.3)
            c.mover(dt)
            n = self.comida.comer(c.x, c.y, c.r * 0.9)
            if n:
                c.masa += n * MASA_COMIDA
                for _ in range(n):
                    self.comida.agregar(self.nueva_comida())
            if not c.es_jugador:
                c.masa = min(c.masa, MASA_MAX_NPC)

        self.resolver_comidas()

        # Reaparición de NPC comidos, para mantener siempre el mismo número
        for i in range(len(self.cola_respawn)):
            self.cola_respawn[i] -= dt
        pendientes = [t for t in self.cola_respawn if t > 0]
        for _ in range(len(self.cola_respawn) - len(pendientes)):
            self.celulas.append(self.crear_npc(lejos_de=self.jugador))
        self.cola_respawn = pendientes

        # Cámara y zoom: al crecer, la cámara se aleja
        if self.estado == "jugando":
            self.cam_x += (self.jugador.x - self.cam_x) * min(1.0, 8 * dt)
            self.cam_y += (self.jugador.y - self.cam_y) * min(1.0, 8 * dt)
            self.masa_max = max(self.masa_max, self.jugador.masa)
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
                if b.es_jugador and self.tiempo < INMUNIDAD_INICIAL:
                    continue
                if a.masa > b.masa * VENTAJA:
                    limite = a.r - b.r * 0.4
                    if (a.x - b.x) ** 2 + (a.y - b.y) ** 2 < limite * limite:
                        a.masa += b.masa
                        a.comidos += 1
                        b.viva = False
                        if b.es_jugador:
                            self.estado = "muerto"
                            self.asesino = a.nombre
                        else:
                            self.cola_respawn.append(random.uniform(2, 6))
        self.celulas = [c for c in celulas if c.viva]

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
            self.poner_texto(pantalla, self.f_media, f"Masa: {int(j.masa)}", BLANCO, (14, 12))
            self.poner_texto(pantalla, self.f_peq, f"Puesto: {puesto} de {len(orden)}", GRIS, (14, 42))
            self.poner_texto(pantalla, self.f_peq, f"Comidos: {j.comidos}", GRIS, (14, 62))
            if j.sprint:
                self.poner_texto(pantalla, self.f_peq, "¡SPRINT!", (255, 160, 80), (14, 82))
            if self.tiempo < INMUNIDAD_INICIAL:
                resto = INMUNIDAD_INICIAL - self.tiempo
                self.poner_texto(pantalla, self.f_peq, f"Protegido: {resto:.0f} s", (120, 220, 255), (14, 102))
            if self.tiempo < 10:
                self.poner_texto(pantalla, self.f_peq,
                                 "Mouse: mover  |  ESPACIO: sprint  |  P: pausa  |  Come lo que sea más pequeño que tú",
                                 GRIS, (w // 2, h - 18), centrado=True)

    def dibujar_muerte(self, pantalla, w, h):
        velo = pygame.Surface((w, h), pygame.SRCALPHA)
        velo.fill((0, 0, 0, 170))
        pantalla.blit(velo, (0, 0))
        self.poner_texto(pantalla, self.f_grande, "TE COMIERON", (255, 110, 110), (w // 2, h // 2 - 90), centrado=True)
        self.poner_texto(pantalla, self.f_media, f"Te comió {self.asesino}", BLANCO, (w // 2, h // 2 - 40), centrado=True)
        datos = [f"Masa máxima: {int(self.masa_max)}",
                 f"Células que comiste: {self.jugador.comidos}",
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
        if self.pausado:
            self.poner_texto(pantalla, self.f_grande, "PAUSA", BLANCO, (w // 2, h // 2), centrado=True)
        if self.estado == "muerto":
            self.dibujar_muerte(pantalla, w, h)

    # ---------- Bucle principal ----------
    def manejar_eventos(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    return False
                if e.key == pygame.K_p and self.estado == "jugando":
                    self.pausado = not self.pausado
                if e.key == pygame.K_RETURN and self.estado == "muerto":
                    self.nuevo_juego()
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