"""
Pong 2D con tres modos de juego:
  1) PC vs Usuario
  2) PC vs Usuario + Usuario (los dos usuarios forman equipo contra la PC)
  3) Usuario vs Usuario

Requiere: pygame  (pip install pygame   o   pip install pygame-ce)
"""
import random
import sys

import pygame

ANCHO, ALTO = 900, 600
FPS = 60
PUNTOS_PARA_GANAR = 7
VEL_MAX_PELOTA = 14

FONDO = (15, 15, 28)
BLANCO = (235, 235, 245)
GRIS = (90, 90, 110)
ROJO = (255, 100, 100)    # PC
AZUL = (90, 160, 255)     # Usuario 1
VERDE = (110, 220, 150)   # Usuario 2


class Paleta:
    def __init__(self, x, color, alto=100, velocidad=7):
        self.rect = pygame.Rect(x, ALTO // 2 - alto // 2, 14, alto)
        self.color = color
        self.velocidad = velocidad

    def mover(self, direccion):
        """direccion: -1 sube, 1 baja."""
        self.rect.y += direccion * self.velocidad
        self.rect.clamp_ip(pygame.Rect(0, 0, ANCHO, ALTO))

    def dibujar(self, pantalla):
        pygame.draw.rect(pantalla, self.color, self.rect, border_radius=6)


class Pelota:
    TAM = 16

    def __init__(self):
        self.rect = pygame.Rect(0, 0, self.TAM, self.TAM)
        self.x = self.y = 0.0
        self.vel_x = self.vel_y = 0.0
        self.reiniciar(random.choice([-1, 1]))

    def reiniciar(self, direccion):
        self.x = ANCHO / 2 - self.TAM / 2
        self.y = ALTO / 2 - self.TAM / 2
        self.vel_x = 6 * direccion
        self.vel_y = random.choice([-1, 1]) * random.uniform(2, 4)
        self.rect.topleft = (round(self.x), round(self.y))

    def mover(self):
        self.x += self.vel_x
        self.y += self.vel_y
        # Rebote en techo y suelo
        if self.y <= 0:
            self.y = 0
            self.vel_y = abs(self.vel_y)
        elif self.y + self.TAM >= ALTO:
            self.y = ALTO - self.TAM
            self.vel_y = -abs(self.vel_y)
        self.rect.topleft = (round(self.x), round(self.y))

    def rebotar_en(self, paleta):
        """Devuelve True si rebotó contra la paleta."""
        if not self.rect.colliderect(paleta.rect):
            return False
        es_izquierda = paleta.rect.centerx < ANCHO // 2
        # Solo rebota si la pelota va hacia esa paleta
        if es_izquierda and self.vel_x > 0:
            return False
        if not es_izquierda and self.vel_x < 0:
            return False

        # El ángulo depende de dónde golpea: centro = recto, borde = diagonal
        desplazamiento = (self.rect.centery - paleta.rect.centery) / (paleta.rect.height / 2)
        desplazamiento = max(-1, min(1, desplazamiento))
        velocidad = min(abs(self.vel_x) * 1.06, VEL_MAX_PELOTA)
        self.vel_x = velocidad if es_izquierda else -velocidad
        self.vel_y = desplazamiento * 7

        # Sacar la pelota de la paleta para que no se quede pegada
        if es_izquierda:
            self.rect.left = paleta.rect.right
        else:
            self.rect.right = paleta.rect.left
        self.x, self.y = float(self.rect.x), float(self.rect.y)
        return True

    def dibujar(self, pantalla):
        pygame.draw.ellipse(pantalla, BLANCO, self.rect)


class Juego:
    TECLAS_MODO = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3}

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pong 2D - PC y Usuarios")
        self.pantalla = pygame.display.set_mode((ANCHO, ALTO))
        self.reloj = pygame.time.Clock()
        self.f_grande = pygame.font.SysFont("consolas", 64, bold=True)
        self.f_media = pygame.font.SysFont("consolas", 28)
        self.f_peq = pygame.font.SysFont("consolas", 18)
        self.estado = "menu"      # menu | jugando | fin
        self.modo = 1
        self.pausado = False
        self.ganador = ""
        self.puntos = [0, 0]
        self.nombres = ("", "")
        self.izq, self.der, self.controles = [], [], []
        self.ia = None
        self.pelota = Pelota()
        self.pausa_hasta = 0

    # ---------- Preparación de cada modo ----------
    def iniciar(self, modo):
        self.modo = modo
        self.estado = "jugando"
        self.pausado = False
        self.puntos = [0, 0]
        self.pelota = Pelota()
        self.pausa_hasta = pygame.time.get_ticks() + 1000

        w, s = (pygame.K_w,), (pygame.K_s,)
        arriba, abajo = (pygame.K_UP,), (pygame.K_DOWN,)
        x_izq = 30
        x_der = ANCHO - 44

        if modo == 1:    # PC vs Usuario
            self.nombres = ("PC", "USUARIO")
            pc = Paleta(x_izq, ROJO, velocidad=5.5)
            usuario = Paleta(x_der, AZUL)
            self.izq, self.der, self.ia = [pc], [usuario], pc
            # El usuario puede usar W/S o las flechas
            self.controles = [(usuario, w + arriba, s + abajo)]
        elif modo == 2:  # PC vs Usuario + Usuario (equipo)
            self.nombres = ("PC", "USUARIOS")
            pc = Paleta(x_izq, ROJO, alto=170, velocidad=5.5)
            u1 = Paleta(x_der, AZUL)
            u2 = Paleta(x_der - 40, VERDE)
            self.izq, self.der, self.ia = [pc], [u1, u2], pc
            self.controles = [(u1, w, s), (u2, arriba, abajo)]
        else:            # Usuario vs Usuario
            self.nombres = ("USUARIO 1", "USUARIO 2")
            u1 = Paleta(x_izq, AZUL)
            u2 = Paleta(x_der, VERDE)
            self.izq, self.der, self.ia = [u1], [u2], None
            self.controles = [(u1, w, s), (u2, arriba, abajo)]

    # ---------- Lógica ----------
    def mover_ia(self):
        pc = self.ia
        objetivo = ALTO / 2                      # sin pelota cerca, vuelve al centro
        if self.pelota.vel_x < 0:                # la pelota viene hacia la PC
            objetivo = self.pelota.rect.centery
        if pc.rect.centery < objetivo - 12:
            pc.mover(1)
        elif pc.rect.centery > objetivo + 12:
            pc.mover(-1)

    def actualizar(self):
        if self.pausado or pygame.time.get_ticks() < self.pausa_hasta:
            return
        teclas = pygame.key.get_pressed()
        for paleta, arriba, abajo in self.controles:
            if any(teclas[k] for k in arriba):
                paleta.mover(-1)
            if any(teclas[k] for k in abajo):
                paleta.mover(1)
        if self.ia:
            self.mover_ia()

        self.pelota.mover()
        for paleta in self.izq + self.der:
            if self.pelota.rebotar_en(paleta):
                break

        if self.pelota.rect.right < 0:           # se fue por la izquierda
            self.puntos[1] += 1
            self.punto_marcado(-1)
        elif self.pelota.rect.left > ANCHO:      # se fue por la derecha
            self.puntos[0] += 1
            self.punto_marcado(1)

    def punto_marcado(self, direccion):
        if max(self.puntos) >= PUNTOS_PARA_GANAR:
            self.estado = "fin"
            self.ganador = self.nombres[0 if self.puntos[0] > self.puntos[1] else 1]
        else:
            self.pelota.reiniciar(direccion)
            self.pausa_hasta = pygame.time.get_ticks() + 800

    # ---------- Eventos ----------
    def manejar_eventos(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type != pygame.KEYDOWN:
                continue
            if self.estado == "menu":
                if e.key in self.TECLAS_MODO:
                    self.iniciar(self.TECLAS_MODO[e.key])
                elif e.key == pygame.K_ESCAPE:
                    return False
            else:
                if e.key == pygame.K_ESCAPE:
                    self.estado = "menu"
                elif e.key == pygame.K_p and self.estado == "jugando":
                    self.pausado = not self.pausado
                elif e.key == pygame.K_RETURN and self.estado == "fin":
                    self.iniciar(self.modo)
        return True

    # ---------- Dibujo ----------
    def texto(self, fuente, contenido, color, centro):
        img = fuente.render(contenido, True, color)
        self.pantalla.blit(img, img.get_rect(center=centro))

    def dibujar_menu(self):
        self.texto(self.f_grande, "PONG 2D", BLANCO, (ANCHO // 2, 110))
        opciones = ["1  -  PC vs Usuario",
                    "2  -  PC vs Usuario + Usuario (equipo)",
                    "3  -  Usuario vs Usuario"]
        for i, op in enumerate(opciones):
            self.texto(self.f_media, op, BLANCO, (ANCHO // 2, 230 + i * 60))
        ayuda = ["Usuario 1: W / S      Usuario 2: flechas arriba / abajo",
                 "En el modo 1 puedes usar W/S o las flechas",
                 f"Gana quien llegue a {PUNTOS_PARA_GANAR} puntos   |   P: pausa   |   ESC: menú"]
        for i, linea in enumerate(ayuda):
            self.texto(self.f_peq, linea, GRIS, (ANCHO // 2, 440 + i * 28))

    def dibujar_juego(self):
        for y in range(0, ALTO, 30):             # línea central
            pygame.draw.rect(self.pantalla, GRIS, (ANCHO // 2 - 2, y, 4, 16))
        self.texto(self.f_grande, str(self.puntos[0]), BLANCO, (ANCHO // 4, 55))
        self.texto(self.f_grande, str(self.puntos[1]), BLANCO, (3 * ANCHO // 4, 55))
        self.texto(self.f_peq, self.nombres[0], GRIS, (ANCHO // 4, 105))
        self.texto(self.f_peq, self.nombres[1], GRIS, (3 * ANCHO // 4, 105))
        for paleta in self.izq + self.der:
            paleta.dibujar(self.pantalla)
        self.pelota.dibujar(self.pantalla)
        self.texto(self.f_peq, "P: pausa   ESC: menú", GRIS, (ANCHO // 2, ALTO - 20))
        if self.pausado:
            self.texto(self.f_grande, "PAUSA", BLANCO, (ANCHO // 2, ALTO // 2))

    def dibujar_fin(self):
        self.dibujar_juego()
        velo = pygame.Surface((ANCHO, ALTO), pygame.SRCALPHA)
        velo.fill((0, 0, 0, 170))
        self.pantalla.blit(velo, (0, 0))
        self.texto(self.f_grande, f"¡GANA {self.ganador}!", BLANCO, (ANCHO // 2, 240))
        self.texto(self.f_media, f"{self.puntos[0]}  -  {self.puntos[1]}", BLANCO, (ANCHO // 2, 320))
        self.texto(self.f_peq, "ENTER: revancha   |   ESC: volver al menú", GRIS, (ANCHO // 2, 390))

    def dibujar(self):
        self.pantalla.fill(FONDO)
        if self.estado == "menu":
            self.dibujar_menu()
        elif self.estado == "jugando":
            self.dibujar_juego()
        else:
            self.dibujar_fin()

    # ---------- Bucle principal ----------
    def ejecutar(self):
        corriendo = True
        while corriendo:
            corriendo = self.manejar_eventos()
            if self.estado == "jugando":
                self.actualizar()
            self.dibujar()
            pygame.display.flip()
            self.reloj.tick(FPS)
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Juego().ejecutar()