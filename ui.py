"""Шрифт, кнопки, вікна, джойстик і малювання персонажів."""
import math
import os

from kivy.core.text import LabelBase
from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate,
                           RoundedRectangle)
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.vector import Vector

from geometry import clamp
from settings import BLUE

# ------------------------------------------------------------
#  Шрифт: Arial з Windows, якщо є
# ------------------------------------------------------------
FONT = "Roboto"
_fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_arial = os.path.join(_fonts_dir, "arial.ttf")
_arial_bold = os.path.join(_fonts_dir, "arialbd.ttf")
if os.path.exists(_arial):
    LabelBase.register("GameFont", _arial,
                       fn_bold=_arial_bold if os.path.exists(_arial_bold) else None)
    FONT = "GameFont"


# ------------------------------------------------------------
#  Малювання (викликати всередині `with canvas:`)
# ------------------------------------------------------------
def circle(x, y, r):
    Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))


def hp_bar(x, y, width, frac, color):
    h = dp(6)
    Color(0, 0, 0, 0.6)
    Rectangle(pos=(x - width / 2 - dp(1), y - dp(1)), size=(width + dp(2), h + dp(2)))
    Color(*color, 1)
    Rectangle(pos=(x - width / 2, y), size=(width * clamp(frac, 0, 1), h))


def gun_px(weapon, scale=1.0):
    length, width, color = weapon["gun"]
    return dp(length) * scale, dp(width) * scale, color


def shooter_gun(scale=1.0):
    return dp(18) * scale, dp(8) * scale, (0.3, 0.1, 0.1)


def draw_character(x, y, r, angle, color, gun=None, angry=False, flash=False,
                   recoil=0.0, armor=False, ring_color=None, scarf=None):
    """Персонаж: тінь, кільце команди, зброя, тіло, очі в напрямку погляду."""
    deg = math.degrees(angle)
    outline = (color[0] * 0.35, color[1] * 0.35, color[2] * 0.35, 1)

    Color(0, 0, 0, 0.22)
    Ellipse(pos=(x - r * 1.05, y - r * 1.35), size=(r * 2.1, r * 0.8))

    if ring_color:
        Color(*ring_color, 0.55)
        Line(circle=(x, y - r * 0.15, r * 1.35), width=dp(2))

    PushMatrix()
    Rotate(angle=deg, origin=(x, y))
    if scarf:
        Color(scarf[0] * 0.5, scarf[1] * 0.5, scarf[2] * 0.5, 1)
        Ellipse(pos=(x - r * 1.45, y - r * 0.32), size=(r * 0.95, r * 0.64))
        Color(*scarf, 1)
        Ellipse(pos=(x - r * 1.38, y - r * 0.24), size=(r * 0.8, r * 0.48))
    if gun:
        glen, gw, gcol = gun
        bx = x + r * 0.35 - recoil
        Color(0.1, 0.1, 0.12, 1)
        Rectangle(pos=(bx, y - gw / 2 - dp(2)), size=(glen + dp(2), gw + dp(4)))
        Color(*gcol, 1)
        Rectangle(pos=(bx + dp(1), y - gw / 2), size=(glen, gw))
        Color(1, 1, 1, 0.15)
        Rectangle(pos=(bx + dp(1), y), size=(glen, gw / 2))
    PopMatrix()

    Color(*outline)
    circle(x, y, r + dp(3))
    Color(*((1, 1, 1, 1) if flash else (*color, 1)))
    circle(x, y, r)
    Color(1, 1, 1, 0.2)
    circle(x - r * 0.3, y + r * 0.32, r * 0.42)
    if armor:
        Color(*outline)
        Line(circle=(x, y, r * 0.72), width=max(dp(2), r * 0.08))

    PushMatrix()
    Rotate(angle=deg, origin=(x, y))
    for s in (-1, 1):
        ex, ey = x + r * 0.42, y + s * r * 0.36
        Color(1, 1, 1, 1)
        circle(ex, ey, r * 0.25)
        Color(0.05, 0.05, 0.1, 1)
        circle(ex + r * 0.1, ey, r * 0.13)
        if angry:
            Color(*outline)
            Line(points=[ex - r * 0.2, ey + s * r * 0.36, ex + r * 0.24, ey + s * r * 0.18],
                 width=max(dp(1.6), r * 0.09), cap="round")
    PopMatrix()


# ------------------------------------------------------------
#  Кнопка
# ------------------------------------------------------------
class MenuButton(ButtonBehavior, Label):
    def __init__(self, bg=BLUE, **kwargs):
        kwargs.setdefault("font_name", FONT)
        kwargs.setdefault("font_size", sp(22))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(280), dp(56)))
        kwargs.setdefault("outline_width", 2)
        kwargs.setdefault("outline_color", (0, 0, 0, 0.6))
        self.bg = bg
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0, 0, 0, 0.35)
            self._shadow = RoundedRectangle(radius=[dp(14)])
            self._color = Color()
            self._rect = RoundedRectangle(radius=[dp(14)])
            Color(1, 1, 1, 0.12)
            self._shine = RoundedRectangle(radius=[dp(14), dp(14), 0, 0])
        self.set_bg(bg)
        self.bind(pos=self._sync, size=self._sync, state=lambda *a: self.set_bg(self.bg))
        self._sync()

    def set_bg(self, bg):
        self.bg = bg
        k = 0.8 if self.state == "down" else 1.0
        self._color.rgba = (bg[0] * k, bg[1] * k, bg[2] * k, bg[3] if len(bg) > 3 else 1)

    def _sync(self, *args):
        self._shadow.pos = (self.x, self.y - dp(4))
        self._shadow.size = self.size
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._shine.pos = (self.x, self.y + self.height / 2)
        self._shine.size = (self.width, self.height / 2)


# ------------------------------------------------------------
#  Вікно поверх екрана
# ------------------------------------------------------------
class Overlay(FloatLayout):
    def __init__(self, title, buttons, text="", text_font=19, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(0.03, 0.02, 0.08, 0.75)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

        box = BoxLayout(orientation="vertical", spacing=dp(12), size_hint=(None, None),
                        width=dp(560), pos_hint={"center_x": 0.5, "center_y": 0.5})
        box.bind(minimum_height=box.setter("height"))
        box.add_widget(Label(text=title, font_name=FONT, font_size=sp(42), bold=True,
                             color=(1, 0.82, 0.3, 1), outline_width=3,
                             outline_color=(0.25, 0.08, 0, 1),
                             size_hint=(1, None), height=dp(60)))
        if text:
            lbl = Label(text=text, font_name=FONT, font_size=sp(text_font), markup=True,
                        halign="center", valign="middle", line_height=1.2,
                        size_hint=(1, None))
            lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                     texture_size=lambda w, v: setattr(w, "height", v[1] + dp(8)))
            box.add_widget(lbl)
        for label, callback, color in buttons:
            box.add_widget(MenuButton(text=label, bg=color, pos_hint={"center_x": 0.5},
                                      on_release=lambda *_, cb=callback: cb()))
        self.add_widget(box)

    def _sync(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def on_touch_down(self, touch):
        super().on_touch_down(touch)
        return True

    def on_touch_move(self, touch):
        super().on_touch_move(touch)
        return True

    def on_touch_up(self, touch):
        super().on_touch_up(touch)
        return True


# ------------------------------------------------------------
#  Екранний джойстик
# ------------------------------------------------------------
class Joystick(Widget):
    dx = NumericProperty(0)
    dy = NumericProperty(0)
    active = BooleanProperty(False)
    __events__ = ("on_release_stick",)

    def __init__(self, base_color=(1, 1, 1, 0.25), knob_color=(0.2, 0.5, 1, 0.9), **kwargs):
        super().__init__(**kwargs)
        self.base_color = base_color
        self.knob_color = knob_color
        self.touch_uid = None
        self.max_mag = 0.0
        self.bind(pos=self._redraw, size=self._redraw)

    @property
    def radius(self):
        return min(self.width, self.height) / 2

    @property
    def mag(self):
        return math.hypot(self.dx, self.dy)

    def _redraw(self, *args):
        self.canvas.clear()
        cx, cy = self.center
        r = self.radius
        kr = r * 0.4
        kx, ky = cx + self.dx * r, cy + self.dy * r
        with self.canvas:
            Color(*self.base_color)
            Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            Color(*self.knob_color)
            Ellipse(pos=(kx - kr, ky - kr), size=(2 * kr, 2 * kr))

    def _update(self, touch):
        v = Vector(touch.pos) - Vector(self.center)
        r = self.radius
        if v.length() > r:
            v = v.normalize() * r
        self.dx, self.dy = v.x / r, v.y / r
        self.max_mag = max(self.max_mag, self.mag)
        self._redraw()

    def on_touch_down(self, touch):
        if self.touch_uid is None and Vector(touch.pos).distance(self.center) <= self.radius * 1.3:
            touch.grab(self)
            self.touch_uid = touch.uid
            self.active = True
            self.max_mag = 0.0
            self._update(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._update(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.dispatch("on_release_stick", self.dx, self.dy)
            self.touch_uid = None
            self.active = False
            self.dx = self.dy = 0
            self._redraw()
            return True
        return super().on_touch_up(touch)

    def on_release_stick(self, dx, dy):
        pass
