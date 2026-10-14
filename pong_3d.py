"""
Pong 3D con Ursina y tres modos de juego:
  1) PC vs Usuario
  2) PC vs Usuario + Usuario (los dos usuarios forman equipo contra la PC)
  3) Usuario vs Usuario

Requiere: ursina  (pip install ursina)
"""
import random

from ursina import *

# ---------- Configuración ----------
ANCHO_MESA = 28          # eje X (izquierda-derecha)
FONDO_MESA = 16          # eje Z (profundidad, "arriba-abajo" en pantalla)
X_PALETA = 12.5
LIMITE_X = 14.5          # a partir de aquí la pelota se considera fuera
RADIO = 0.4
GROSOR_PALETA = 0.6
PUNTOS_PARA_GANAR = 7
VEL_INICIAL = 12
VEL_MAX = 26
VEL_JUGADOR = 13
VEL_PC = 7.5             # súbela para una PC más difícil, bájala para una más fácil

app = Ursina(title="Pong 3D - PC y Usuarios")
window.color = color.black
camera.position = (0, 22, -18)
camera.rotation_x = 50
camera.fov = 68

# ---------- Escenario (siempre visible) ----------
mesa = Entity(model='cube', texture='white_cube', texture_scale=(ANCHO_MESA / 2, FONDO_MESA / 2),
              color=color.rgb32(40, 60, 110), scale=(ANCHO_MESA, 0.5, FONDO_MESA), y=-0.25)
pared_arriba = Entity(model='cube', color=color.light_gray, scale=(ANCHO_MESA, 0.8, 0.5),
                      position=(0, 0.4, FONDO_MESA / 2 + 0.25))
pared_abajo = Entity(model='cube', color=color.light_gray, scale=(ANCHO_MESA, 0.8, 0.5),
                     position=(0, 0.4, -FONDO_MESA / 2 - 0.25))
red = Entity(model='cube', color=color.gray, scale=(0.15, 0.05, FONDO_MESA), position=(0, 0.03, 0))


class Paleta(Entity):
    def __init__(self, x, color_paleta, largo=3, velocidad=VEL_JUGADOR):
        super().__init__(model='cube', color=color_paleta,
                         scale=(GROSOR_PALETA, 0.8, largo), position=(x, 0.4, 0))
        self.velocidad = velocidad

    def mover(self, direccion, dt):
        """direccion: 1 sube (hacia el fondo), -1 baja (hacia la cámara)."""
        limite = FONDO_MESA / 2 - self.scale_z / 2
        nuevo_z = self.z + direccion * self.velocidad * dt
        self.z = max(-limite, min(limite, nuevo_z))


class Pelota(Entity):
    def __init__(self):
        super().__init__(model='sphere', color=color.white, scale=RADIO * 2, position=(0, 0.5, 0))
        self.vx = 0
        self.vz = 0
        self.reiniciar(random.choice([-1, 1]))

    def reiniciar(self, direccion):
        self.position = (0, 0.5, 0)
        self.vx = VEL_INICIAL * direccion
        self.vz = random.choice([-1, 1]) * random.uniform(3, 6)

    def mover(self, dt):
        self.x += self.vx * dt
        self.z += self.vz * dt
        limite = FONDO_MESA / 2 - RADIO
        if self.z > limite:
            self.z = limite
            self.vz = -abs(self.vz)
        elif self.z < -limite:
            self.z = -limite
            self.vz = abs(self.vz)

    def rebotar_en(self, paleta):
        """Devuelve True si rebotó contra la paleta."""
        es_izquierda = paleta.x < 0
        if es_izquierda and self.vx > 0:
            return False
        if not es_izquierda and self.vx < 0:
            return False
        contacto_x = GROSOR_PALETA / 2 + RADIO
        if abs(self.x - paleta.x) > contacto_x:
            return False
        if abs(self.z - paleta.z) > paleta.scale_z / 2 + RADIO:
            return False

        # El ángulo depende de dónde golpea: centro = recto, borde = diagonal
        desplazamiento = (self.z - paleta.z) / (paleta.scale_z / 2)
        desplazamiento = max(-1, min(1, desplazamiento))
        velocidad = min(abs(self.vx) * 1.06, VEL_MAX)
        self.vx = velocidad if es_izquierda else -velocidad
        self.vz = desplazamiento * 10
        self.x = paleta.x + (contacto_x if es_izquierda else -contacto_x)
        return True


class Juego:
    def __init__(self):
        self.estado = "menu"       # menu | jugando | fin
        self.modo = 1
        self.pausado = False
        self.espera = 0
        self.puntos = [0, 0]
        self.nombres = ("", "")
        self.izq, self.der, self.controles = [], [], []
        self.ia = None
        self.pelota = None
        self.textos_menu = []
        self.textos_juego = []
        self.marcador = []
        self.texto_fin = None
        self.crear_menu()

    # ---------- Menú ----------
    def crear_menu(self):
        lineas = [
            ("PONG 3D", 4, (0, 0.40), color.white),
            ("1  -  PC vs Usuario", 1.6, (0, 0.20), color.white),
            ("2  -  PC vs Usuario + Usuario (equipo)", 1.6, (0, 0.13), color.white),
            ("3  -  Usuario vs Usuario", 1.6, (0, 0.06), color.white),
            ("Usuario 1: W / S      Usuario 2: flechas arriba / abajo", 1.1, (0, -0.07), color.light_gray),
            ("En el modo 1 puedes usar W/S o las flechas", 1.1, (0, -0.12), color.light_gray),
            (f"Gana quien llegue a {PUNTOS_PARA_GANAR} puntos  |  P: pausa  |  M: menu",
             1.1, (0, -0.17), color.light_gray),
        ]
        self.textos_menu = [Text(text=t, scale=s, position=p, origin=(0, 0), color=c)
                            for t, s, p, c in lineas]

    def mostrar_menu(self, visible):
        for t in self.textos_menu:
            t.enabled = visible

    # ---------- Preparación de cada modo ----------
    def limpiar(self):
        for e in self.izq + self.der + self.textos_juego + self.marcador:
            destroy(e)
        if self.pelota:
            destroy(self.pelota)
        if self.texto_fin:
            destroy(self.texto_fin)
        self.izq, self.der, self.controles = [], [], []
        self.textos_juego, self.marcador = [], []
        self.pelota = None
        self.texto_fin = None
        self.ia = None

    def iniciar(self, modo):
        self.limpiar()
        self.modo = modo
        self.estado = "jugando"
        self.pausado = False
        self.puntos = [0, 0]
        self.espera = 1.0
        self.mostrar_menu(False)
        self.pelota = Pelota()

        sube_u1, baja_u1 = ('w',), ('s',)
        sube_u2, baja_u2 = ('up arrow',), ('down arrow',)

        if modo == 1:      # PC vs Usuario
            self.nombres = ("PC", "USUARIO")
            pc = Paleta(-X_PALETA, color.red, velocidad=VEL_PC)
            usuario = Paleta(X_PALETA, color.azure)
            self.izq, self.der, self.ia = [pc], [usuario], pc
            self.controles = [(usuario, sube_u1 + sube_u2, baja_u1 + baja_u2)]
        elif modo == 2:    # PC vs Usuario + Usuario (equipo)
            self.nombres = ("PC", "USUARIOS")
            pc = Paleta(-X_PALETA, color.red, largo=5, velocidad=VEL_PC)
            u1 = Paleta(X_PALETA, color.azure)
            u2 = Paleta(X_PALETA - 2, color.lime)
            self.izq, self.der, self.ia = [pc], [u1, u2], pc
            self.controles = [(u1, sube_u1, baja_u1), (u2, sube_u2, baja_u2)]
        else:              # Usuario vs Usuario
            self.nombres = ("USUARIO 1", "USUARIO 2")
            u1 = Paleta(-X_PALETA, color.azure)
            u2 = Paleta(X_PALETA, color.lime)
            self.izq, self.der, self.ia = [u1], [u2], None
            self.controles = [(u1, sube_u1, baja_u1), (u2, sube_u2, baja_u2)]

        self.marcador = [
            Text(text="0", scale=4, position=(-0.25, 0.45), origin=(0, 0), color=color.white),
            Text(text="0", scale=4, position=(0.25, 0.45), origin=(0, 0), color=color.white),
        ]
        self.textos_juego = [
            Text(text=self.nombres[0], scale=1.2, position=(-0.25, 0.37), origin=(0, 0), color=color.light_gray),
            Text(text=self.nombres[1], scale=1.2, position=(0.25, 0.37), origin=(0, 0), color=color.light_gray),
            Text(text="P: pausa   M: menu", scale=1, position=(0, -0.46), origin=(0, 0), color=color.gray),
        ]

    # ---------- Lógica ----------
    def mover_ia(self, dt):
        pc = self.ia
        objetivo = 0                       # sin pelota cerca, vuelve al centro
        if self.pelota.vx < 0:             # la pelota viene hacia la PC
            objetivo = self.pelota.z
        if pc.z < objetivo - 0.4:
            pc.mover(1, dt)
        elif pc.z > objetivo + 0.4:
            pc.mover(-1, dt)

    def actualizar(self, dt):
        if self.estado != "jugando" or self.pausado:
            return
        if self.espera > 0:
            self.espera -= dt
            return

        for paleta, sube, baja in self.controles:
            if any(held_keys[k] for k in sube):
                paleta.mover(1, dt)
            if any(held_keys[k] for k in baja):
                paleta.mover(-1, dt)
        if self.ia:
            self.mover_ia(dt)

        self.pelota.mover(dt)
        for paleta in self.izq + self.der:
            if self.pelota.rebotar_en(paleta):
                break

        if self.pelota.x < -LIMITE_X:          # se fue por la izquierda
            self.puntos[1] += 1
            self.punto_marcado(-1)
        elif self.pelota.x > LIMITE_X:         # se fue por la derecha
            self.puntos[0] += 1
            self.punto_marcado(1)

    def punto_marcado(self, direccion):
        for i in range(2):
            self.marcador[i].text = str(self.puntos[i])
        if max(self.puntos) >= PUNTOS_PARA_GANAR:
            self.estado = "fin"
            ganador = self.nombres[0 if self.puntos[0] > self.puntos[1] else 1]
            self.texto_fin = Text(
                text=f"GANA {ganador}\n\nENTER: revancha   |   M: menu",
                scale=2, position=(0, 0.1), origin=(0, 0), color=color.yellow)
        else:
            self.pelota.reiniciar(direccion)
            self.espera = 0.8

    def volver_al_menu(self):
        self.limpiar()
        self.estado = "menu"
        self.mostrar_menu(True)

    # ---------- Teclas ----------
    def tecla(self, key):
        if self.estado == "menu":
            if key in ('1', '2', '3'):
                self.iniciar(int(key))
        else:
            if key in ('m', 'escape'):
                self.volver_al_menu()
            elif key == 'p' and self.estado == "jugando":
                self.pausado = not self.pausado
            elif key == 'enter' and self.estado == "fin":
                self.iniciar(self.modo)


juego = Juego()


def update():
    # Limitamos dt para que un tirón de FPS no haga que la pelota atraviese una paleta
    juego.actualizar(min(time.dt, 1 / 30))


def input(key):
    juego.tecla(key)


if __name__ == "__main__":
    app.run()