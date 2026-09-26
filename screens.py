"""Екрани: головне меню та ігровий екран."""
import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivymd.uix.screen import MDScreen

from game import Game
from settings import (BLUE, DARK, ENEMY_RING, ENEMY_TYPES, GREEN, HERO_COLOR, HERO_RING,
                      HERO_SCARF, ORANGE, PURPLE, RED, WEAPONS, weapon_dps)
from ui import FONT, Joystick, MenuButton, Overlay, draw_character, gun_px, shooter_gun


# ============================================================
#  Ігровий екран
# ============================================================
class GameScreen(MDScreen):
    def __init__(self, app, **kwargs):
        super().__init__(name="game", **kwargs)
        self.app = app
        self.clock_ev = None
        self.over_ev = None
        self.overlay = None
        self._hud_cache = None

        stick = (dp(160), dp(160))
        self.move_stick = Joystick(size_hint=(None, None), size=stick,
                                   pos_hint={"x": 0.03, "y": 0.05})
        self.aim_stick = Joystick(size_hint=(None, None), size=stick,
                                  pos_hint={"right": 0.97, "y": 0.05},
                                  knob_color=(1, 0.3, 0.3, 0.9))
        self.game = Game(self, self.move_stick, self.aim_stick, size_hint=(1, 1))
        self.add_widget(self.game)

        self.info = Label(font_name=FONT, font_size=sp(20), bold=True, markup=True,
                          outline_width=2, outline_color=(0, 0, 0, 0.7),
                          size_hint=(None, None), pos_hint={"x": 0.015, "top": 0.985},
                          halign="left", valign="top", line_height=1.15)
        self.info.bind(texture_size=self.info.setter("size"))
        self.add_widget(self.info)

        self.add_widget(MenuButton(text="II", size=(dp(52), dp(52)), bg=DARK,
                                   pos_hint={"right": 0.985, "top": 0.985},
                                   on_release=lambda *_: self.toggle_pause()))

        self.slots = []
        slot_w, gap = dp(122), dp(8)
        bar = BoxLayout(size_hint=(None, None), spacing=gap, height=dp(46),
                        width=slot_w * len(WEAPONS) + gap * (len(WEAPONS) - 1),
                        pos_hint={"center_x": 0.5, "y": 0.02})
        for i, w in enumerate(WEAPONS):
            slot = MenuButton(text=f"{i + 1}  {w['name']}", font_size=sp(15),
                              size=(slot_w, dp(46)), bg=DARK,
                              on_release=lambda *_, idx=i: self.game.set_weapon(idx))
            self.slots.append(slot)
            bar.add_widget(slot)
        self.add_widget(bar)

        self.banner = Label(font_name=FONT, font_size=sp(54), bold=True, opacity=0, markup=True,
                            color=(1, 0.85, 0.3, 1), outline_width=3,
                            outline_color=(0.25, 0.08, 0, 1), halign="center",
                            size_hint=(1, None), height=dp(130),
                            pos_hint={"center_x": 0.5, "center_y": 0.72})
        self.banner.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.add_widget(self.banner)

    # ---------- Життєвий цикл ----------
    def new_game(self):
        self.close_overlay()
        if self.over_ev:
            self.over_ev.cancel()
            self.over_ev = None
        self.apply_joysticks(self.app.settings["joysticks"])
        self.game.reset(self.app.settings["weapon"])
        self.update_slots()
        self._hud_cache = None

    def on_enter(self, *args):
        Window.bind(on_key_down=self._key_down, on_key_up=self._key_up)
        if not self.clock_ev:
            self.clock_ev = Clock.schedule_interval(self.game.update, 1 / 60)

    def on_leave(self, *args):
        Window.unbind(on_key_down=self._key_down, on_key_up=self._key_up)
        if self.clock_ev:
            self.clock_ev.cancel()
            self.clock_ev = None
        self.game.keys.clear()
        self.close_overlay()

    def apply_joysticks(self, show):
        for s in (self.move_stick, self.aim_stick):
            if show and s.parent is None:
                self.add_widget(s)
            elif not show and s.parent is not None:
                self.remove_widget(s)

    # ---------- Клавіатура ----------
    def _key_down(self, window, key, *args):
        if key == 27:  # Esc
            self.toggle_pause()
            return True
        if self.game.paused or self.game.over:
            return False
        if 49 <= key <= 48 + len(WEAPONS):
            self.game.set_weapon(key - 49)
        elif key == 113:  # Q
            self.game.set_weapon(self.game.weapon_index - 1)
        elif key == 101:  # E
            self.game.set_weapon(self.game.weapon_index + 1)
        self.game.keys.add(key)
        return True

    def _key_up(self, window, key, *args):
        self.game.keys.discard(key)

    # ---------- HUD ----------
    def update_hud(self):
        g = self.game
        hidden = "\n[color=66dd66]В кустах[/color]" if g.player.hidden else ""
        text = (f"[color=ffd24a]Волна {g.director.wave}[/color]\n"
                f"Счёт {g.score}\n"
                f"HP {int(g.player.hp)}/{g.player.max_hp}\n"
                f"Врагов {g.director.remaining}{hidden}")
        if text != self._hud_cache:
            self._hud_cache = text
            self.info.text = text

    def update_slots(self):
        for i, slot in enumerate(self.slots):
            slot.set_bg(ORANGE if i == self.game.weapon_index else DARK)

    def show_banner(self, title, subtitle=""):
        Animation.cancel_all(self.banner)
        text = title
        if subtitle:
            text += f"\n[size={int(sp(24))}][color=ffffff]{subtitle}[/color][/size]"
        self.banner.text = text
        self.banner.opacity = 1
        (Animation(duration=1.1) + Animation(opacity=0, duration=0.6)).start(self.banner)

    # ---------- Вікна ----------
    def open_overlay(self, overlay):
        self.close_overlay()
        self.overlay = overlay
        self.add_widget(overlay)

    def close_overlay(self):
        if self.overlay is not None:
            self.remove_widget(self.overlay)
            self.overlay = None

    def toggle_pause(self):
        g = self.game
        if g.over:
            return
        if g.paused:
            self.close_overlay()
            g.paused = False
        else:
            g.paused = True
            g.mouse_down = False
            g.keys.clear()
            self.open_overlay(Overlay("Пауза", [
                ("Продолжить", self.toggle_pause, GREEN),
                ("Начать заново", self.app.start_game, ORANGE),
                ("Главное меню", self.app.to_menu, RED),
            ]))

    def schedule_game_over(self):
        self.over_ev = Clock.schedule_once(lambda dt: self.show_game_over(), 1.2)

    def show_game_over(self):
        self.over_ev = None
        g = self.game
        new_record = g.score > self.app.best
        if new_record:
            self.app.best = g.score
            self.app.save_best()
        text = (f"Счёт: [b]{g.score}[/b]\n"
                f"Волна: {g.director.wave}\n"
                f"Уничтожено врагов: {g.kills}\n"
                f"Рекорд: {self.app.best}")
        if new_record:
            text += "\n[color=ffd24a][b]Новый рекорд![/b][/color]"
        self.open_overlay(Overlay("Поражение", [
            ("Ещё раз", self.app.start_game, GREEN),
            ("Главное меню", self.app.to_menu, RED),
        ], text=text))


# ============================================================
#  Меню
# ============================================================
class MenuPreview(Widget):
    """Анімація в меню: герой дивиться на курсор, навколо кружляють вороги."""

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.t = 0.0
        self.ev = None

    def start(self):
        if not self.ev:
            self.ev = Clock.schedule_interval(self.tick, 1 / 60)

    def stop(self):
        if self.ev:
            self.ev.cancel()
            self.ev = None

    def tick(self, dt):
        self.t += dt
        cx, cy = self.center
        base = min(self.width, self.height)
        r = base * 0.075
        mx, my = self.to_widget(*Window.mouse_pos)
        hero_angle = math.atan2(my - cy, mx - cx)
        weapon = WEAPONS[self.app.settings["weapon"]]
        scale = r / dp(22)

        items = []
        for i, kind in enumerate(("runner", "shooter", "tank")):
            a = self.t * 0.5 + i * 2 * math.pi / 3
            ex = cx + math.cos(a) * base * 0.44
            ey = cy + math.sin(a) * base * 0.3
            t = ENEMY_TYPES[kind]
            er = r * t["radius"] / 22

            def draw_enemy(ex=ex, ey=ey, er=er, t=t, kind=kind):
                draw_character(ex, ey, er, math.atan2(cy - ey, cx - ex), t["color"],
                               gun=shooter_gun(scale) if kind == "shooter" else None,
                               angry=True, armor=kind == "tank", ring_color=ENEMY_RING)
            items.append((ey, draw_enemy))

        def draw_hero():
            draw_character(cx, cy + math.sin(self.t * 3) * dp(3), r, hero_angle, HERO_COLOR,
                           gun=gun_px(weapon, scale), ring_color=HERO_RING, scarf=HERO_SCARF)
        items.append((cy, draw_hero))

        self.canvas.clear()
        with self.canvas:
            Color(1, 1, 1, 0.05)
            Ellipse(pos=(cx - base * 0.5, cy - base * 0.36), size=(base, base * 0.72))
            for _, draw_fn in sorted(items, key=lambda it: -it[0]):
                draw_fn()


class MenuScreen(MDScreen):
    def __init__(self, app, **kwargs):
        super().__init__(name="menu", **kwargs)
        self.app = app
        with self.canvas.before:
            Color(0.12, 0.09, 0.2, 1)
            self._bg = Rectangle()
            Color(0.95, 0.6, 0.2, 0.07)
            self._glow = Ellipse()
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        self.preview = MenuPreview(app, size_hint=(0.5, 0.68), pos_hint={"x": 0.03, "y": 0.06})
        self.add_widget(self.preview)

        self.add_widget(Label(text="BRAWL ARENA", font_name=FONT, font_size=sp(64), bold=True,
                              color=(1, 0.8, 0.25, 1), outline_width=3,
                              outline_color=(0.3, 0.1, 0, 1),
                              size_hint=(1, None), height=dp(90), pos_hint={"top": 0.96}))
        self.best_label = Label(font_name=FONT, font_size=sp(20), color=(1, 1, 1, 0.8),
                                size_hint=(1, None), height=dp(30), pos_hint={"top": 0.84})
        self.add_widget(self.best_label)

        box = BoxLayout(orientation="vertical", spacing=dp(14), size_hint=(None, None),
                        width=dp(320), pos_hint={"right": 0.93, "center_y": 0.42})
        box.bind(minimum_height=box.setter("height"))
        center = {"center_x": 0.5}
        box.add_widget(MenuButton(text="Играть", bg=GREEN, pos_hint=center,
                                  font_size=sp(26), size=(dp(280), dp(64)),
                                  on_release=lambda *_: app.start_game()))
        self.btn_weapon = MenuButton(bg=ORANGE, pos_hint=center,
                                     on_release=lambda *_: self.cycle_weapon())
        box.add_widget(self.btn_weapon)
        self.btn_sticks = MenuButton(bg=BLUE, pos_hint=center,
                                     on_release=lambda *_: self.toggle_sticks())
        box.add_widget(self.btn_sticks)
        box.add_widget(MenuButton(text="Справка", bg=PURPLE, pos_hint=center,
                                  on_release=lambda *_: self.show_help()))
        box.add_widget(MenuButton(text="Выход", bg=RED, pos_hint=center,
                                  on_release=lambda *_: app.stop()))
        self.add_widget(box)

        self.overlay = None
        self.refresh()
        self.preview.start()

    def _sync_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        r = max(self.width, self.height) * 0.6
        self._glow.pos = (self.width * 0.28 - r / 2, self.height * 0.4 - r / 2)
        self._glow.size = (r, r)

    def refresh(self):
        s = self.app.settings
        self.btn_weapon.text = f"Оружие: {WEAPONS[s['weapon']]['name']}"
        self.btn_sticks.text = f"Джойстики: {'Вкл' if s['joysticks'] else 'Выкл'}"
        self.best_label.text = f"Рекорд: {self.app.best}"

    def cycle_weapon(self):
        s = self.app.settings
        s["weapon"] = (s["weapon"] + 1) % len(WEAPONS)
        self.refresh()

    def toggle_sticks(self):
        s = self.app.settings
        s["joysticks"] = not s["joysticks"]
        self.refresh()

    def show_help(self):
        weapons = "\n".join(f"{w['name']} - {w['desc']} (DPS ~{round(weapon_dps(w))})"
                            for w in WEAPONS)
        text = ("[b]Управление[/b]\n"
                "Левый джойстик - движение, правый - прицел и стрельба\n"
                "На ПК: WASD - движение, мышь - прицел, ЛКМ - стрельба\n"
                "Пробел - автоприцел, 1-4 / Q / E / колесо - оружие, Esc - пауза\n\n"
                "[b]Враги[/b]\n"
                "[color=66dd55]Бегун[/color] - петляет, вблизи делает рывок (жёлтая линия)\n"
                "[color=ff5a5a]Стрелок[/color] - держит дистанцию, перед выстрелом целится лазером\n"
                "[color=9966ee]Танк[/color] - броня спереди, таранит; об стену - оглушение x1.5\n\n"
                f"[b]Оружие[/b]\n{weapons}\n\n"
                "[b]Укрытия[/b]\n"
                "Стены блокируют пули, взрывы и обзор врагов\n"
                "В кустах тебя видно только вблизи; выстрел выдаёт позицию\n"
                "Враги идут туда, где видели тебя последний раз, и обыскивают место")
        self.overlay = Overlay("Справка", [("Назад", self.close_help, BLUE)], text=text,
                               text_font=14)
        self.add_widget(self.overlay)

    def close_help(self):
        if self.overlay is not None:
            self.remove_widget(self.overlay)
            self.overlay = None

    def on_enter(self, *args):
        self.refresh()
        self.preview.start()

    def on_leave(self, *args):
        self.preview.stop()
        self.close_help()
