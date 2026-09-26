"""Візуальні ефекти: частинки, кільця, спалахи, сліди на підлозі, числа шкоди.

Методи draw_* викликаються всередині `with canvas:`.
"""
import math
import random

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, PopMatrix, PushMatrix, Rectangle, Rotate, Line
from kivy.metrics import dp, sp

MAX_DECALS = 70
MAX_PARTICLES = 700


def _circle(x, y, r):
    Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))


class Effects:
    def __init__(self, font):
        self.font = font
        self._textures = {}
        self.clear()

    def clear(self):
        self.particles = []  # [x, y, vx, vy, life, max, r, color, drag]
        self.rings = []      # [x, y, r0, r1, life, max, color, width]
        self.flashes = []    # [x, y, r, life, max, color]
        self.decals = []     # [x, y, rx, ry, life, max, color, alpha]
        self.texts = []      # [x, y, vy, life, max, texture, color]
        self.muzzles = []    # [x, y, angle, size, life, max]

    # ---------- Текстури тексту (кешуються) ----------
    def texture(self, text, size=16):
        key = (text, size)
        tex = self._textures.get(key)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=sp(size), font_name=self.font, bold=True,
                            outline_width=2, outline_color=(0, 0, 0))
            lbl.refresh()
            tex = lbl.texture
            self._textures[key] = tex
        return tex

    # ---------- Створення ----------
    def burst(self, x, y, color, n=8, speed=160, size=4, life=0.4, drag=4.0):
        if len(self.particles) > MAX_PARTICLES:
            n = min(n, 2)
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            s = dp(speed) * random.uniform(0.3, 1.0)
            lf = life * random.uniform(0.7, 1.2)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, lf, lf,
                                   dp(size) * random.uniform(0.6, 1.2), color, drag])

    def cone(self, x, y, angle, width, color, n=6, speed=200, size=3, life=0.25):
        """Частинки віялом (іскри від стіни, гільзи, листя)."""
        for _ in range(n):
            a = angle + random.uniform(-width, width)
            s = dp(speed) * random.uniform(0.4, 1.0)
            lf = life * random.uniform(0.7, 1.2)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, lf, lf,
                                   dp(size) * random.uniform(0.6, 1.2), color, 5.0])

    def ring(self, x, y, r0, r1, life, color, width=3):
        self.rings.append([x, y, r0, r1, life, life, color, dp(width)])

    def flash(self, x, y, r, life, color=(1, 0.95, 0.7)):
        self.flashes.append([x, y, r, life, life, color])

    def decal(self, x, y, rx, ry, color, life=8.0, alpha=0.35):
        self.decals.append([x, y, rx, ry, life, life, color, alpha])
        if len(self.decals) > MAX_DECALS:
            self.decals.pop(0)

    def text(self, x, y, text, color=(1, 1, 1), size=16, life=0.7, vy=70):
        tex = self.texture(text, size)
        self.texts.append([x + random.uniform(-dp(8), dp(8)), y, dp(vy), life, life, tex, color])

    def muzzle(self, x, y, angle, size):
        self.muzzles.append([x, y, angle, dp(size), 0.06, 0.06])

    # ---------- Оновлення ----------
    def update(self, dt):
        for pt in self.particles:
            f = max(0.0, 1 - pt[8] * dt)
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[2] *= f
            pt[3] *= f
            pt[4] -= dt
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        for lst, idx in ((self.rings, 4), (self.flashes, 3), (self.decals, 4),
                         (self.muzzles, 4)):
            for item in lst:
                item[idx] -= dt
        self.rings = [r for r in self.rings if r[4] > 0]
        self.flashes = [f for f in self.flashes if f[3] > 0]
        self.decals = [d for d in self.decals if d[4] > 0]
        self.muzzles = [m for m in self.muzzles if m[4] > 0]
        for t in self.texts:
            t[1] += t[2] * dt
            t[2] *= max(0.0, 1 - 3 * dt)
            t[3] -= dt
        self.texts = [t for t in self.texts if t[3] > 0]

    # ---------- Малювання ----------
    def draw_decals(self):
        for x, y, rx, ry, life, max_life, color, alpha in self.decals:
            k = min(1.0, life / (max_life * 0.3))   # плавно зникає в кінці
            Color(*color, alpha * k)
            Ellipse(pos=(x - rx, y - ry), size=(2 * rx, 2 * ry))

    def draw_top(self):
        for x, y, r, life, max_life, color in self.flashes:
            k = life / max_life
            Color(*color, 0.8 * k)
            _circle(x, y, r * (1.2 - 0.4 * k))
        for x, y, r0, r1, life, max_life, color, width in self.rings:
            k = life / max_life
            Color(*color, 0.8 * k)
            Line(circle=(x, y, r1 + (r0 - r1) * k), width=width * (0.4 + 0.6 * k))
        for x, y, _, _, life, max_life, r, color, _ in self.particles:
            k = life / max_life
            Color(*color, k)
            _circle(x, y, r * (0.4 + 0.6 * k))
        for x, y, angle, s, life, max_life in self.muzzles:
            k = life / max_life
            PushMatrix()
            Rotate(angle=math.degrees(angle), origin=(x, y))
            Color(1, 0.8, 0.35, 0.9 * k)
            Ellipse(pos=(x - s * 0.15, y - s * 0.38), size=(s * 1.7, s * 0.76))
            Color(1, 1, 0.85, k)
            Ellipse(pos=(x, y - s * 0.2), size=(s * 0.9, s * 0.4))
            PopMatrix()

    def draw_texts(self):
        for x, y, _, life, max_life, tex, color in self.texts:
            k = min(1.0, life / (max_life * 0.4))
            Color(*color, k)
            Rectangle(texture=tex, pos=(x - tex.width / 2, y), size=tex.size)
