"""
Pong 3D con Ursina y tres modos de juego:
  1) PC vs Usuario
  2) PC vs Usuario + Usuario (los dos usuarios forman equipo contra la PC)
  3) Usuario vs Usuario

Requiere: ursina  (pip install ursina)
"""
import random
import math
from pathlib import Path

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
VEL_JUGADOR = 13
VEL_PC = 7.5             # súbela para una PC más difícil, bájala para una más fácil
DURACION_PODER = 5.0
MAX_PELOTAS = 3

DIRECTORIO = Path(__file__).resolve().parent


class Sonidos:
    """Precarga los WAV para evitar búsquedas y pausas durante la partida."""
    def __init__(self):
        self.audios = {}

    def preparar(self):
        for nombre in ("pared", "rebote", "punto", "poder"):
            ruta = DIRECTORIO / "pong_sounds" / f"{nombre}.wav"
            if not ruta.is_file():
                continue
            try:
                # Ursina distingue Path (archivo directo) de str (nombre de recurso).
                self.audios[nombre] = Audio(ruta, autoplay=False, auto_destroy=False)
            except Exception:
                pass

    def reproducir(self, nombre, volumen=0.45):
        try:
            audio = self.audios.get(nombre)
            if audio:
                audio.volume = volumen
                audio.play()
        except Exception:
            # Los dispositivos de audio pueden no estar disponibles en algunos equipos.
            pass


sonidos = Sonidos()

app = Ursina(title="Pong 3D - PC y Usuarios")
sonidos.preparar()
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
        self.velocidad_base = velocidad
        self._color_original = color_paleta
        self.congelada = 0
        self.en_fuego = 0
        self.impulso = 0
        self.controles_invertidos = 0
        self.largo_base = largo

    def mover(self, direccion, dt):
        """direccion: 1 sube (hacia el fondo), -1 baja (hacia la cámara)."""
        limite = max(0, FONDO_MESA / 2 - self.scale_z / 2)
        if self.congelada > 0:
            return
        if self.controles_invertidos > 0:
            direccion *= -1
        multiplicador = 1.45 if self.impulso > 0 else 1
        nuevo_z = self.z + direccion * self.velocidad * multiplicador * dt
        self.z = max(-limite, min(limite, nuevo_z))


class Pelota(Entity):
    def __init__(self, velocidad_inicial=VEL_INICIAL, radio=RADIO):
        super().__init__(model='sphere', color=color.white, scale=radio * 2, position=(0, 0.5, 0))
        self.velocidad_inicial = velocidad_inicial
        self.radio = radio
        self.vx = 0
        self.vz = 0
        self.efecto = ""
        self.reiniciar(random.choice([-1, 1]))

    def reiniciar(self, direccion):
        self.position = (0, 0.5, 0)
        self.vx = self.velocidad_inicial * direccion
        self.vz = random.choice([-1, 1]) * random.uniform(3, 6)
        self.efecto = ""

    def mover(self, dt):
        self.x += self.vx * dt
        self.z += self.vz * dt
        limite = max(0, FONDO_MESA / 2 - self.radio)
        if limite == 0:
            self.z = 0
            self.vz = 0
            return
        if self.z > limite:
            self.z = limite
            self.vz = -abs(self.vz)
            sonidos.reproducir("pared", 0.22)
        elif self.z < -limite:
            self.z = -limite
            self.vz = abs(self.vz)
            sonidos.reproducir("pared", 0.22)

    def rebotar_en(self, paleta):
        """Devuelve True si rebotó contra la paleta."""
        es_izquierda = paleta.x < 0
        if es_izquierda and self.vx > 0:
            return False
        if not es_izquierda and self.vx < 0:
            return False
        contacto_x = GROSOR_PALETA / 2 + self.radio
        if abs(self.x - paleta.x) > contacto_x:
            return False
        if abs(self.z - paleta.z) > paleta.scale_z / 2 + self.radio:
            return False

        # El ángulo depende de dónde golpea: centro = recto, borde = diagonal
        desplazamiento = (self.z - paleta.z) / (paleta.scale_z / 2)
        desplazamiento = max(-1, min(1, desplazamiento))
        velocidad = math.hypot(self.vx, self.vz) * 1.08
        angulo = math.radians(desplazamiento * 50)
        self.vx = velocidad * math.cos(angulo) * (1 if es_izquierda else -1)
        self.vz = velocidad * math.sin(angulo)
        self.x = paleta.x + (contacto_x if es_izquierda else -contacto_x)
        sonidos.reproducir("rebote", 0.35)
        return True


class Potenciador(Entity):
    TIPOS = {
        "congelar": ("HIELO", color.azure),
        "fuego": ("FUEGO", color.orange),
        "multibola": ("X3", color.violet),
        "pelota_rapida": ("RAPIDA", color.yellow),
        "paleta_rapida": ("TURBO", color.lime),
        "tiempo_lento": ("LENTO", color.cyan),
        "control_invertido": ("INVIERTE", color.magenta),
        "teletransporte": ("PORTAL", color.azure),
        "pelota_gigante": ("GIGANTE", color.orange),
        "caos": ("CAOS", color.red),
    }

    def __init__(self, tipo, posicion):
        etiqueta, tono = self.TIPOS[tipo]
        super().__init__(model="sphere", color=tono, scale=0.9, position=posicion,
                         collider="sphere")
        self.tipo = tipo
        self.etiqueta = Text(text=etiqueta, scale=0.7, parent=self,
                             position=(0, 1.2, 0), billboard=True, color=tono)
        self.fase = random.uniform(0, 6.28)
        self.tiempo = 0

    def update(self):
        self.tiempo += time.dt
        self.rotation_y += 70 * time.dt
        self.y = 0.65 + math.sin(self.tiempo * 3 + self.fase) * 0.12


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
        self.pelotas = []
        self.potenciadores = []
        self.multiplicador_tamano_pelota = 1.0
        self.config = {
            "velocidad_pelota": float(VEL_INICIAL),
            "tamano_pelota": float(RADIO),
            "largo_paletas": 1.0,
            "velocidad_paletas": 1.0,
            "intervalo_poder": 8.0,
            "duracion_poder": DURACION_PODER,
        }
        self.opciones_admin = [
            ("Velocidad de pelota", "velocidad_pelota", 1, None, 1, " u/s"),
            ("Radio de pelota", "tamano_pelota", 0.2, None, 0.1, " u"),
            ("Longitud de paletas", "largo_paletas", 0.5, None, 0.1, "x"),
            ("Velocidad de paletas", "velocidad_paletas", 0.5, None, 0.1, "x"),
            ("Intervalo entre poderes", "intervalo_poder", 3, 20, 1, " s"),
            ("Duración de los efectos", "duracion_poder", 2, 15, 1, " s"),
        ]
        self.admin_abierto = False
        self.admin_seleccion = 0
        self.panel_admin = None
        self.titulo_admin = None
        self.filas_admin = []
        self.ayuda_admin = None
        self.temporizador_potenciador = self.config["intervalo_poder"]
        self.escala_tiempo = 1
        self.temporizador_lento = 0
        self.efecto_texto = None
        self.textos_menu = []
        self.textos_juego = []
        self.marcador = []
        self.texto_fin = None
        self.crear_menu()
        self.crear_menu_admin()

    # ---------- Menú ----------
    def crear_menu(self):
        lineas = [
            ("PONG 3D", 4, (0, 0.40), color.white),
            ("1  -  PC vs Usuario", 1.6, (0, 0.20), color.white),
            ("2  -  PC vs Usuario + Usuario (equipo)", 1.6, (0, 0.13), color.white),
            ("3  -  Usuario vs Usuario", 1.6, (0, 0.06), color.white),
            ("Usuario 1: W / S      Usuario 2: flechas arriba / abajo", 1.1, (0, -0.07), color.light_gray),
            ("En el modo 1 puedes usar W/S o las flechas", 1.1, (0, -0.12), color.light_gray),
            ("Recoge esferas: hielo, fuego, multibola, portal y poderes caóticos", 1.0, (0, -0.17), color.light_gray),
            (f"Gana quien llegue a {PUNTOS_PARA_GANAR} puntos  |  P: pausa  |  M: menu | F1: admin",
             1.1, (0, -0.22), color.light_gray),
        ]
        self.textos_menu = [Text(text=t, scale=s, position=p, origin=(0, 0), color=c)
                            for t, s, p, c in lineas]

    def mostrar_menu(self, visible):
        for t in self.textos_menu:
            t.enabled = visible

    def crear_menu_admin(self):
        self.panel_admin = Entity(parent=camera.ui, model="quad", color=color.rgba32(12, 18, 35, 235),
                                  scale=(0.9, 0.82), z=1, enabled=False)
        self.titulo_admin = Text(parent=camera.ui, text="ADMINISTRACIÓN DEL JUEGO",
                                 position=(0, 0.31), origin=(0, 0), scale=1.6,
                                 color=color.yellow, enabled=False)
        self.filas_admin = [
            Text(parent=camera.ui, position=(-0.32, 0.18 - i * 0.085),
                 origin=(-0.5, 0), scale=1.15, enabled=False)
            for i in range(len(self.opciones_admin))
        ]
        self.ayuda_admin = Text(parent=camera.ui,
                                text="↑ / ↓ elegir     ← / → ajustar     F1 / ESC cerrar",
                                position=(0, -0.28), origin=(0, 0), scale=1.0,
                                color=color.light_gray, enabled=False)
        self.actualizar_menu_admin()

    def actualizar_menu_admin(self):
        for i, (etiqueta, llave, minimo, maximo, paso, unidad) in enumerate(self.opciones_admin):
            valor = self.config[llave]
            formato = f"{valor:.1f}" if paso < 1 else f"{valor:.0f}"
            marca = "▶" if i == self.admin_seleccion else " "
            fila = self.filas_admin[i]
            fila.text = f"{marca}  {etiqueta}: {formato}{unidad}"
            fila.color = color.azure if i == self.admin_seleccion else color.white

    def mostrar_menu_admin(self, visible):
        self.admin_abierto = visible
        self.panel_admin.enabled = visible
        self.titulo_admin.enabled = visible
        self.ayuda_admin.enabled = visible
        for fila in self.filas_admin:
            fila.enabled = visible

    def ajustar_opcion_admin(self, direccion):
        etiqueta, llave, minimo, maximo, paso, unidad = self.opciones_admin[self.admin_seleccion]
        anterior = self.config[llave]
        nuevo = max(minimo, anterior + direccion * paso)
        if maximo is not None:
            nuevo = min(maximo, nuevo)
        nuevo = round(nuevo, 1) if paso < 1 else int(nuevo)
        if nuevo == anterior:
            return
        self.config[llave] = nuevo

        if llave == "velocidad_pelota":
            factor = nuevo / anterior
            for pelota in self.pelotas:
                pelota.velocidad_inicial = nuevo
                pelota.vx *= factor
                pelota.vz *= factor
        elif llave == "largo_paletas":
            self.aplicar_configuracion_paletas()
        elif llave == "velocidad_paletas":
            self.aplicar_configuracion_paletas()
        elif llave == "tamano_pelota":
            self.aplicar_configuracion_pelotas()
        elif llave == "intervalo_poder":
            self.temporizador_potenciador = min(self.temporizador_potenciador, nuevo)
        elif llave == "duracion_poder":
            factor = nuevo / anterior
            for paleta in self.izq + self.der:
                paleta.congelada *= factor
                paleta.en_fuego *= factor
                paleta.impulso *= factor
                paleta.controles_invertidos *= factor
            self.temporizador_lento *= factor
        self.actualizar_menu_admin()

    def aplicar_configuracion_paletas(self):
        for paleta in self.izq + self.der:
            largo = paleta.largo_base * self.config["largo_paletas"]
            paleta.scale_z = max(1.2, largo * (0.58 if paleta.en_fuego > 0 else 1))
            paleta.velocidad = paleta.velocidad_base * self.config["velocidad_paletas"]
            limite = max(0, FONDO_MESA / 2 - paleta.scale_z / 2)
            paleta.z = max(-limite, min(limite, paleta.z))

    def aplicar_configuracion_pelotas(self):
        radio = self.config["tamano_pelota"] * self.multiplicador_tamano_pelota
        for pelota in self.pelotas:
            pelota.radio = radio
            pelota.scale = radio * 2
            limite = max(0, FONDO_MESA / 2 - radio)
            pelota.z = max(-limite, min(limite, pelota.z))

    # ---------- Preparación de cada modo ----------
    def limpiar(self):
        for e in self.izq + self.der + self.textos_juego + self.marcador:
            destroy(e)
        bolas = self.pelotas or ([self.pelota] if self.pelota else [])
        for pelota in bolas:
            destroy(pelota)
        for poder in self.potenciadores:
            destroy(poder)
        if self.efecto_texto:
            destroy(self.efecto_texto)
        if self.texto_fin:
            destroy(self.texto_fin)
        self.izq, self.der, self.controles = [], [], []
        self.textos_juego, self.marcador = [], []
        self.pelota = None
        self.pelotas = []
        self.potenciadores = []
        self.texto_fin = None
        self.efecto_texto = None
        self.ia = None

    def iniciar(self, modo):
        self.limpiar()
        self.modo = modo
        self.estado = "jugando"
        self.pausado = False
        self.puntos = [0, 0]
        self.espera = 1.0
        self.escala_tiempo = 1
        self.temporizador_lento = 0
        self.temporizador_potenciador = self.config["intervalo_poder"]
        self.mostrar_menu(False)
        self.multiplicador_tamano_pelota = 1.0
        self.pelota = Pelota(self.config["velocidad_pelota"], self.config["tamano_pelota"])
        self.pelotas = [self.pelota]

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

        self.aplicar_configuracion_paletas()

        self.marcador = [
            Text(text="0", scale=4, position=(-0.25, 0.45), origin=(0, 0), color=color.white),
            Text(text="0", scale=4, position=(0.25, 0.45), origin=(0, 0), color=color.white),
        ]
        self.textos_juego = [
            Text(text=self.nombres[0], scale=1.2, position=(-0.25, 0.37), origin=(0, 0), color=color.light_gray),
            Text(text=self.nombres[1], scale=1.2, position=(0.25, 0.37), origin=(0, 0), color=color.light_gray),
            Text(text="P: pausa   M: menu   F1: admin", scale=1, position=(0, -0.46), origin=(0, 0), color=color.gray),
            Text(text="Poderes: recoge las esferas | efecto temporal", scale=0.9,
                 position=(0, -0.41), origin=(0, 0), color=color.light_gray),
        ]

    def mostrar_efecto(self, mensaje, tono=color.white):
        if self.efecto_texto:
            destroy(self.efecto_texto)
        self.efecto_texto = Text(text=mensaje, scale=1.5, position=(0, 0.28),
                                 origin=(0, 0), color=tono)
        invoke(destroy, self.efecto_texto, delay=1.8)

    def crear_potenciador(self):
        tipo = random.choice(tuple(Potenciador.TIPOS))
        poder = Potenciador(tipo, (random.uniform(-3.5, 3.5), 0.65,
                                   random.uniform(-5.5, 5.5)))
        self.potenciadores.append(poder)

    def aplicar_potenciador(self, poder, pelota):
        destino_izq = pelota.vx < 0
        equipo_objetivo = self.izq if destino_izq else self.der
        nombre, tono = Potenciador.TIPOS[poder.tipo]

        if poder.tipo == "congelar":
            for paleta in equipo_objetivo:
                paleta.congelada = self.config["duracion_poder"]
            mensaje = f"{nombre}: paletas congeladas"
        elif poder.tipo == "fuego":
            for paleta in equipo_objetivo:
                paleta.en_fuego = self.config["duracion_poder"]
                paleta.scale_z = max(1.2, paleta.largo_base * self.config["largo_paletas"] * 0.58)
                paleta.color = color.orange
            mensaje = f"{nombre}: paletas dañadas"
        elif poder.tipo == "multibola":
            cantidad = min(2, MAX_PELOTAS - len(self.pelotas))
            for _ in range(cantidad):
                extra = Pelota(self.config["velocidad_pelota"],
                               self.config["tamano_pelota"] * self.multiplicador_tamano_pelota)
                extra.position = pelota.position
                extra.vx = pelota.vx * random.choice((0.85, 1.0, 1.1))
                extra.vz = -pelota.vz if random.choice((True, False)) else pelota.vz
                self.pelotas.append(extra)
            mensaje = "MULTIBOLA: hasta 3 pelotas"
        elif poder.tipo == "pelota_rapida":
            for bola in self.pelotas:
                bola.vx *= 1.35
                bola.vz *= 1.35
            mensaje = "RAPIDA: pelota acelerada"
        elif poder.tipo == "paleta_rapida":
            for paleta in equipo_objetivo:
                paleta.impulso = self.config["duracion_poder"]
            mensaje = "TURBO: paletas aliadas aceleradas"
        elif poder.tipo == "control_invertido":
            for paleta in equipo_objetivo:
                paleta.controles_invertidos = self.config["duracion_poder"]
            mensaje = "INVIERTE: controles rivales al revés"
        elif poder.tipo == "teletransporte":
            pelota.x = random.uniform(-5, 5)
            limite_z = max(0, FONDO_MESA / 2 - pelota.radio)
            pelota.z = random.uniform(-limite_z, limite_z)
            pelota.vx *= -1
            pelota.vz = random.choice((-1, 1)) * random.uniform(5, 12)
            mensaje = "PORTAL: la pelota cambió de lugar"
        elif poder.tipo == "pelota_gigante":
            self.multiplicador_tamano_pelota *= 1.35
            self.aplicar_configuracion_pelotas()
            mensaje = "GIGANTE: todas las pelotas crecieron"
        elif poder.tipo == "caos":
            for bola in self.pelotas:
                bola.vx = random.choice((-1, 1)) * max(
                    abs(bola.vx) * 1.25, self.config["velocidad_pelota"])
                bola.vz = random.choice((-1, 1)) * random.uniform(8, 18)
            mensaje = "CAOS: trayectorias alteradas"
        else:
            self.escala_tiempo = 0.58
            self.temporizador_lento = self.config["duracion_poder"]
            mensaje = "LENTO: tiempo ralentizado"

        self.mostrar_efecto(mensaje, tono)
        sonidos.reproducir("poder", 0.55)

    def actualizar_efectos(self, dt_real):
        if self.escala_tiempo < 1:
            self.temporizador_lento -= dt_real
            if self.temporizador_lento <= 0:
                self.escala_tiempo = 1
        for paleta in self.izq + self.der:
            if paleta.congelada > 0:
                paleta.congelada = max(0, paleta.congelada - dt_real)
            if paleta.en_fuego > 0:
                paleta.en_fuego = max(0, paleta.en_fuego - dt_real)
                if paleta.en_fuego == 0:
                    paleta.scale_z = paleta.largo_base * self.config["largo_paletas"]
                    paleta.color = paleta._color_original
            if paleta.impulso > 0:
                paleta.impulso = max(0, paleta.impulso - dt_real)
            if paleta.controles_invertidos > 0:
                paleta.controles_invertidos = max(0, paleta.controles_invertidos - dt_real)

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
        if self.estado != "jugando" or self.pausado or self.admin_abierto:
            return
        self.actualizar_efectos(dt)
        dt = min(dt, 1 / 30) * self.escala_tiempo
        if self.espera > 0:
            self.espera -= dt
            return

        self.temporizador_potenciador -= dt
        if self.temporizador_potenciador <= 0 and len(self.potenciadores) < 2:
            self.crear_potenciador()
            self.temporizador_potenciador = self.config["intervalo_poder"]

        for paleta, sube, baja in self.controles:
            if any(held_keys[k] for k in sube):
                paleta.mover(1, dt)
            if any(held_keys[k] for k in baja):
                paleta.mover(-1, dt)
        if self.ia:
            self.mover_ia(dt)

        marco_punto = False
        for pelota in tuple(self.pelotas):
            distancia = max(abs(pelota.vx), abs(pelota.vz)) * dt
            pasos = max(1, math.ceil(distancia / 0.35))
            dt_paso = dt / pasos
            for _ in range(pasos):
                pelota.mover(dt_paso)
                for paleta in self.izq + self.der:
                    if pelota.rebotar_en(paleta):
                        break

                tocado = next((p for p in self.potenciadores
                               if abs(pelota.x - p.x) < 0.9 and
                               abs(pelota.z - p.z) < 0.9), None)
                if tocado:
                    self.aplicar_potenciador(tocado, pelota)
                    self.potenciadores.remove(tocado)
                    destroy(tocado)

                if pelota.x < -LIMITE_X:
                    self.puntos[1] += 1
                    sonidos.reproducir("punto", 0.55)
                    self.punto_marcado(-1)
                    marco_punto = True
                    break
                elif pelota.x > LIMITE_X:
                    self.puntos[0] += 1
                    sonidos.reproducir("punto", 0.55)
                    self.punto_marcado(1)
                    marco_punto = True
                    break
            if marco_punto:
                break

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
            for bola in self.pelotas:
                if bola is not self.pelota:
                    destroy(bola)
            self.pelotas = [self.pelota]
            self.pelota.reiniciar(direccion)
            self.espera = 0.8

    def volver_al_menu(self):
        self.limpiar()
        self.estado = "menu"
        self.mostrar_menu(True)

    # ---------- Teclas ----------
    def tecla(self, key):
        if key == "f1":
            self.mostrar_menu_admin(not self.admin_abierto)
            return
        if self.admin_abierto:
            if key == "escape":
                self.mostrar_menu_admin(False)
            elif key == "up arrow":
                self.admin_seleccion = (self.admin_seleccion - 1) % len(self.opciones_admin)
                self.actualizar_menu_admin()
            elif key == "down arrow":
                self.admin_seleccion = (self.admin_seleccion + 1) % len(self.opciones_admin)
                self.actualizar_menu_admin()
            elif key == "left arrow":
                self.ajustar_opcion_admin(-1)
            elif key == "right arrow":
                self.ajustar_opcion_admin(1)
            return

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
    juego.actualizar(time.dt)


def input(key):
    juego.tecla(key)


if __name__ == "__main__":
    app.run()
