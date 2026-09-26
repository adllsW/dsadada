"""Ігрове поле: введення, фізика, стрільба, видимість, малювання."""
import math
import random

from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, Mesh, PopMatrix, PushMatrix, Rectangle,
                           Translate)
from kivy.metrics import dp
from kivy.uix.widget import Widget

import ai
from effects import Effects
from entities import Bullet, Enemy, Player
from geometry import (clamp, first_rect_hit, norm, point_in_rects, push_out,
                      segment_circle_t, dist_to_rect)
from navigation import NavGrid
from settings import (ENEMY_RING, ELITE_RING, HERO_COLOR, HERO_RING, HERO_SCARF, MAP_LAYOUT,
                      MAP_TILE, NAV_CELL, NAV_CLEARANCE, PLAYER, VISION, WAVES, WEAPONS)
from ui import FONT, circle, draw_character, gun_px, hp_bar, shooter_gun
from waves import WaveDirector

KEY_DIRS = {
    119: (0, 1), 273: (0, 1),    # W, вгору
    115: (0, -1), 274: (0, -1),  # S, вниз
    97: (-1, 0), 276: (-1, 0),   # A, вліво
    100: (1, 0), 275: (1, 0),    # D, вправо
}


class Game(Widget):
    def __init__(self, screen, move_stick, aim_stick, **kwargs):
        super().__init__(**kwargs)
        self.screen = screen
        self.move_stick = move_stick
        self.aim_stick = aim_stick
        self.aim_stick.bind(on_release_stick=self.on_aim_release)
        self.keys = set()
        self.blocks = []          # [(x, y, w, h, kind)] - стіни та ящики
        self.solids = []          # [(x, y, w, h)] - для руху й зору
        self.bullet_solids = []   # solids + межі арени
        self.bushes = []
        self.nav = NavGrid()
        self.effects = Effects(FONT)
        self._shake_tr = None
        self.bind(pos=self.build_level, size=self.build_level)
        self.reset(0)

    # ============================================================
    #  Стан
    # ============================================================
    def reset(self, weapon_index):
        self.player = Player()
        self.need_place = True
        self.enemies = []
        self.bullets = []
        self.pickups = []          # [x, y, life]
        self.effects.clear()
        self.director = WaveDirector(self)
        self.score = 0
        self.kills = 0
        self.time = 0.0
        self.shake = 0.0
        self.hurt_flash = 0.0
        self.bloom = 0.0
        self.paused = False
        self.over = False
        self.mouse_down = False
        self.keys.clear()
        self.last_known = None
        self.goal = (self.center_x, self.center_y)
        self.unseen = 0.0
        self.set_weapon(weapon_index, notify=False)

    def set_weapon(self, index, notify=True):
        self.weapon_index = index % len(WEAPONS)
        self.weapon = WEAPONS[self.weapon_index]
        self.player.cooldown = min(self.player.cooldown, 0.25)
        self.bloom = 0.0
        if notify:
            self.screen.update_slots()

    # ============================================================
    #  Рівень
    # ============================================================
    def build_level(self, *args):
        tile = dp(MAP_TILE)
        self.blocks, self.bushes = [], []
        for kind, fx, fy, cols, rows in MAP_LAYOUT:
            w, h = cols * tile, rows * tile
            x = self.x + self.width * fx - w / 2
            y = self.y + self.height * fy - h / 2
            if kind == "bush":
                self.bushes.append((x, y, w, h))
            else:
                self.blocks.append((x, y, w, h, kind))
        self.solids = [b[:4] for b in self.blocks]
        big = dp(200)
        self.bullet_solids = self.solids + [
            (self.x - big, self.y - big, self.width + 2 * big, big),      # низ
            (self.x - big, self.top, self.width + 2 * big, big),          # верх
            (self.x - big, self.y, big, self.height),                     # ліво
            (self.right, self.y, big, self.height),                       # право
        ]
        if self.width > 100:
            self.nav.build(self.x, self.y, self.width, self.height, dp(NAV_CELL), self.solids,
                           {k: dp(v) for k, v in NAV_CLEARANCE.items()})
        self.draw_static()

    # ============================================================
    #  Введення
    # ============================================================
    def keyboard_dir(self):
        dx = sum(KEY_DIRS[k][0] for k in self.keys if k in KEY_DIRS)
        dy = sum(KEY_DIRS[k][1] for k in self.keys if k in KEY_DIRS)
        return dx, dy

    def on_touch_down(self, touch):
        if touch.device == "mouse" and self.collide_point(*touch.pos):
            button = getattr(touch, "button", "left")
            if button in ("scrollup", "scrolldown"):
                if not self.paused and not self.over:
                    self.set_weapon(self.weapon_index + (1 if button == "scrolldown" else -1))
                return True
            if button == "left":
                self.mouse_down = True
                touch.grab(self)
                return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.mouse_down = False
            return True
        return super().on_touch_up(touch)

    def current_aim(self):
        a = self.aim_stick
        if a.active and a.mag >= 0.3:
            return a.dx, a.dy
        mx, my = self.to_widget(*Window.mouse_pos)
        if self.collide_point(mx, my):
            dx, dy = mx - self.player.x, my - self.player.y
            if math.hypot(dx, dy) > dp(5):
                return dx, dy
        return None

    def auto_aim_dir(self):
        """Найближчий видимий ворог у межах дальності, до якого є пряма лінія."""
        p = self.player
        reach = dp(self.weapon["range"]) * 1.15
        best, best_d = None, reach
        for e in self.enemies:
            if not e.visible:
                continue
            d = math.hypot(e.x - p.x, e.y - p.y)
            if d < best_d and self.segment_clear(p.x, p.y, e.x, e.y):
                best, best_d = e, d
        if best:
            return best.x - p.x, best.y - p.y
        return math.cos(p.angle), math.sin(p.angle)

    def on_aim_release(self, stick, dx, dy):
        if self.paused or self.over:
            return
        if stick.max_mag < 0.3 and self.player.cooldown <= 0:
            self.fire(self.auto_aim_dir())

    # ============================================================
    #  Допоміжні для AI
    # ============================================================
    def segment_clear(self, x1, y1, x2, y2, pad=0.0):
        return first_rect_hit(x1, y1, x2, y2, self.solids, pad) is None

    def steer(self, e):
        """Напрямок до мети: напряму, якщо шлях вільний, інакше за картою шляхів."""
        gx, gy = self.goal
        ux, uy, d = norm(gx - e.x, gy - e.y)
        if d < 1:
            return 0.0, 0.0
        if self.segment_clear(e.x, e.y, gx, gy, e.r * 0.85) or not self.nav.blocked:
            return ux, uy
        dist = self.nav.field(e.nav, gx, gy, self.time)
        direction = self.nav.direction(e.nav, e.x, e.y, dist)
        return direction if direction else (ux, uy)

    def can_see(self, e):
        p = self.player
        if self.over:
            return False
        d = math.hypot(p.x - e.x, p.y - e.y)
        if d > dp(VISION["sight"]):
            return False
        if p.hidden and d > dp(VISION["bush_reveal"]):
            return False
        return self.segment_clear(e.x, e.y, p.x, p.y)

    # ============================================================
    #  Головний цикл
    # ============================================================
    def update(self, dt):
        if self.paused:
            return
        dt = min(dt, 1 / 20)
        self.time += dt
        if self.width > 100 and not self.nav.blocked:
            self.build_level()
        if self.need_place and self.width > 100:
            self.player.x, self.player.y = self.center
            self.last_known = self.center
            self.need_place = False
        if not self.over:
            self.update_player(dt)
        self.update_awareness(dt)
        for e in list(self.enemies):
            ai.update(self, e, dt)
        self.handle_contacts()
        self.update_bullets(dt)
        self.update_pickups(dt)
        self.effects.update(dt)
        self.director.update(dt)
        self.enemies = [e for e in self.enemies if e.hp > 0]
        self.shake = max(0.0, self.shake - dp(40) * dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 2.5)
        self.bloom = max(0.0, self.bloom - dt * 0.9)
        self.draw()
        self.screen.update_hud()

    # ---------- Герой ----------
    def update_player(self, dt):
        p = self.player
        kx, ky = self.keyboard_dir()
        mx = self.move_stick.dx + kx
        my = self.move_stick.dy + ky
        ux, uy, length = norm(mx, my)
        if length > 1:
            mx, my = ux, uy
        old_x, old_y = p.x, p.y
        p.x = clamp(p.x + (mx * p.speed + p.kx) * dt, self.x + p.r, self.right - p.r)
        p.y = clamp(p.y + (my * p.speed + p.ky) * dt, self.y + p.r, self.top - p.r)
        p.x, p.y = push_out(p.x, p.y, p.r, self.solids)
        p.vx, p.vy = (p.x - old_x) / dt, (p.y - old_y) / dt
        damp = max(0.0, 1 - 9 * dt)
        p.kx *= damp
        p.ky *= damp
        if length > 0.1:
            p.walk += dt * 14

        p.invul -= dt
        p.cooldown -= dt
        p.reveal -= dt
        p.recoil = max(0.0, p.recoil - dt * 8)
        p.in_bush = point_in_rects(p.x, p.y, 0, self.bushes)
        p.hidden = p.in_bush and p.reveal <= 0
        if p.in_bush and length > 0.1 and random.random() < dt * 10:
            self.effects.burst(p.x, p.y, (0.3, 0.7, 0.3), n=2, speed=70, size=3, life=0.4)

        aim = self.current_aim()
        a = self.aim_stick
        fire_dir = None
        if a.active and a.mag >= 0.3:
            fire_dir = (a.dx, a.dy)
        elif 32 in self.keys:                  # пробіл - автонаведення
            fire_dir = self.auto_aim_dir()
        elif self.mouse_down and aim:
            fire_dir = aim

        if fire_dir:
            p.angle = math.atan2(fire_dir[1], fire_dir[0])
        elif aim:
            p.angle = math.atan2(aim[1], aim[0])
        elif length > 0.1:
            p.angle = math.atan2(my, mx)

        if fire_dir and p.cooldown <= 0:
            self.fire(fire_dir)

    # ---------- Видимість ----------
    def update_awareness(self, dt):
        p = self.player
        anyone_sees = False
        reveal = dp(VISION["bush_reveal"])
        for e in self.enemies:
            was = e.sees
            e.sees = self.can_see(e)
            if e.sees and not was:
                e.alert_t = 0.8
            anyone_sees = anyone_sees or e.sees
            e.in_bush = point_in_rects(e.x, e.y, 0, self.bushes)
            e.visible = (not e.in_bush or e.reveal > 0
                         or math.hypot(e.x - p.x, e.y - p.y) < reveal)

        if anyone_sees:
            self.last_known = (p.x, p.y)       # вороги передають позицію одне одному
            self.unseen = 0.0
        else:
            self.unseen += dt
            if self.last_known is None or self.unseen > VISION["forget_after"]:
                # Довго не бачили - "здогадуються" приблизно, де герой
                j = dp(160)
                self.last_known = (clamp(p.x + random.uniform(-j, j), self.x, self.right),
                                   clamp(p.y + random.uniform(-j, j), self.y, self.top))
                self.unseen = VISION["forget_after"] * 0.5
        self.goal = self.last_known

    # ---------- Рух ворогів ----------
    def move_enemy(self, e, mx, my, mult, dt):
        rushing = e.state in ("dash", "charge")
        if not rushing:
            for o in self.enemies:
                if o is e:
                    continue
                ox, oy = e.x - o.x, e.y - o.y
                od = math.hypot(ox, oy)
                min_d = e.r + o.r
                if 0 < od < min_d:
                    push = (min_d - od) / min_d * 1.6
                    mx += ox / od * push
                    my += oy / od * push
        speed = e.speed * mult
        want = math.hypot(mx, my) * speed * dt
        if want <= 0:
            return
        old_x, old_y = e.x, e.y
        e.x = clamp(e.x + mx * speed * dt, self.x + e.r, self.right - e.r)
        e.y = clamp(e.y + my * speed * dt, self.y + e.r, self.top - e.r)
        e.x, e.y = push_out(e.x, e.y, e.r, self.solids)
        moved = math.hypot(e.x - old_x, e.y - old_y)
        if moved < want * 0.35 and mult > 0:
            self.on_enemy_blocked(e)

    def on_enemy_blocked(self, e):
        if e.state == "dash":
            e.state, e.timer = "recover", 0.5
        elif e.state == "charge":
            # Танк влетів у стіну - оглушений і вразливий
            e.state, e.timer = "stunned", e.t["stun"]
            e.atk_cd = e.t["charge_cd"] * e.cd_mult
            self.shake = max(self.shake, dp(9))
            fx, fy = e.x + e.dash[0] * e.r, e.y + e.dash[1] * e.r
            self.effects.cone(fx, fy, math.atan2(-e.dash[1], -e.dash[0]), 1.2,
                              (0.6, 0.55, 0.5), n=14, speed=260, size=5, life=0.5)
            self.effects.ring(fx, fy, dp(5), dp(45), 0.3, (1, 1, 1), 3)
            self.effects.text(e.x, e.y + e.r + dp(10), "ОГЛУШЁН", (1, 0.9, 0.3), 15, 1.0, 40)
        else:
            e.strafe = -e.strafe

    def handle_contacts(self):
        if self.over:
            return
        p = self.player
        for e in self.enemies:
            dx, dy = p.x - e.x, p.y - e.y
            ux, uy, d = norm(dx, dy)
            if d >= e.r + p.r:
                continue
            if e.state == "dash":
                self.damage_player(e.t["dash_damage"] * e.dmg_mult, ux, uy, dp(420))
                e.state, e.timer = "recover", 0.5
            elif e.state == "charge":
                self.damage_player(e.t["charge_damage"] * e.dmg_mult, ux, uy, dp(900))
                e.state = "advance"
                e.atk_cd = e.t["charge_cd"] * e.cd_mult
            elif e.hit_cd <= 0:
                self.damage_player(e.t["damage"] * e.dmg_mult, ux, uy, dp(300))
                e.hit_cd = 0.9
            # Розштовхуємо, щоб не злипались
            overlap = e.r + p.r - d
            if ux or uy:
                e.x -= ux * overlap * 0.6
                e.y -= uy * overlap * 0.6
                e.x, e.y = push_out(e.x, e.y, e.r, self.solids)

    # ============================================================
    #  Стрільба
    # ============================================================
    def fire(self, direction):
        p = self.player
        w = self.weapon
        ang = math.atan2(direction[1], direction[0])
        p.angle = ang
        ca, sa = math.cos(ang), math.sin(ang)
        muzzle = p.r + dp(w["gun"][0]) * 0.8
        mx, my = p.x + ca * muzzle, p.y + sa * muzzle
        # Якщо ствол упирається в стіну - куля стартує з центру і влучить у стіну
        if not self.segment_clear(p.x, p.y, mx, my):
            ox, oy = p.x, p.y
        else:
            ox, oy = mx, my

        spread = w["spread"] + self.bloom
        n = w["pellets"]
        for i in range(n):
            if n > 1:
                a = ang - spread / 2 + spread * i / (n - 1) + random.uniform(-0.04, 0.04)
            else:
                a = ang + random.uniform(-spread, spread) / 2
            speed = dp(w["speed"]) * (random.uniform(0.9, 1.0) if n > 1 else 1.0)
            rng = dp(w["range"]) * (random.uniform(0.85, 1.0) if n > 1 else 1.0)
            self.bullets.append(Bullet(
                ox, oy, math.cos(a) * speed, math.sin(a) * speed,
                w["damage"], dp(w["radius"]), w["color"], "player", rng,
                falloff=w["falloff"], push=dp(w["push"]),
                explode=dp(w.get("explode", 0)), explode_dmg=w.get("explode_dmg", 0)))

        p.cooldown = w["cooldown"]
        p.recoil = 1.0
        p.reveal = VISION["reveal_after_shot"]
        p.kx -= ca * dp(w["recoil"])
        p.ky -= sa * dp(w["recoil"])
        self.bloom = min(w["bloom_max"], self.bloom + w["bloom"])
        self.shake = max(self.shake, dp(w["kick"]))
        self.effects.muzzle(mx, my, ang, w["flash"])
        self.effects.cone(mx, my, ang, 0.5, (1, 0.85, 0.4), n=3, speed=150, size=2, life=0.12)

    def enemy_fire(self, e):
        ux, uy, d = norm(e.aim[0] - e.x, e.aim[1] - e.y)
        if not d:
            return
        ang = math.atan2(uy, ux)
        speed = dp(e.t["bullet_speed"])
        angles = [ang - 0.18, ang, ang + 0.18] if e.elite else [ang]
        mz = e.r * 1.6
        sx, sy = e.x + ux * mz, e.y + uy * mz
        if not self.segment_clear(e.x, e.y, sx, sy):
            sx, sy = e.x, e.y
        for a in angles:
            self.bullets.append(Bullet(sx, sy, math.cos(a) * speed, math.sin(a) * speed,
                                       e.t["damage"] * e.dmg_mult, dp(6), (1, 0.35, 0.35),
                                       "enemy", dp(e.t["range"]) * 1.2))
        e.reveal = 0.5
        self.effects.muzzle(e.x + ux * mz, e.y + uy * mz, ang, 14)

    def update_bullets(self, dt):
        """Swept-зіткнення: перевіряємо весь відрізок, який куля пролетіла за кадр."""
        p = self.player
        alive = []
        for b in self.bullets:
            sx, sy = b.vx * dt, b.vy * dt
            step = math.hypot(sx, sy)
            left = b.range - b.traveled
            frac = min(1.0, left / step) if step > 0 else 1.0
            nx, ny = b.x + sx * frac, b.y + sy * frac

            best_t = first_rect_hit(b.x, b.y, nx, ny, self.bullet_solids, b.r * 0.4)
            target = "wall" if best_t is not None else None
            if b.owner == "player":
                for e in self.enemies:
                    if e.hp <= 0:
                        continue
                    t = segment_circle_t(b.x, b.y, nx, ny, e.x, e.y, e.r + b.r)
                    if t is not None and (best_t is None or t < best_t):
                        best_t, target = t, e
            elif not self.over:
                t = segment_circle_t(b.x, b.y, nx, ny, p.x, p.y, p.r + b.r * 0.5)
                if t is not None and (best_t is None or t < best_t):
                    best_t, target = t, p

            b.px, b.py = b.x, b.y
            if target is not None:
                hx = b.x + (nx - b.x) * best_t
                hy = b.y + (ny - b.y) * best_t
                b.traveled += step * frac * best_t
                self.bullet_hit(b, target, hx, hy)
                continue

            b.x, b.y = nx, ny
            b.traveled += step * frac
            if b.traveled >= b.range - 0.5:
                if b.explode:
                    self.explode(b.x, b.y, b)
                else:
                    self.effects.burst(b.x, b.y, (0.8, 0.75, 0.6), n=2, speed=40, size=2, life=0.2)
                continue
            if b.explode and random.random() < 0.8:
                self.effects.particles.append([b.x, b.y, 0, 0, 0.45, 0.45, dp(5),
                                               (0.55, 0.55, 0.55), 0])
            alive.append(b)
        self.bullets = alive

    def bullet_hit(self, b, target, hx, hy):
        ux, uy, _ = norm(b.vx, b.vy)
        if b.explode:
            # Вибух трохи перед поверхнею, щоб стіна не "з'їла" його центр
            self.explode(hx - ux * dp(4), hy - uy * dp(4), b,
                         direct=target if isinstance(target, Enemy) else None)
        elif target == "wall":
            self.effects.cone(hx - ux * dp(2), hy - uy * dp(2), math.atan2(-uy, -ux), 0.9,
                              (0.75, 0.65, 0.5), n=4, speed=140, size=2.5, life=0.25)
        elif target is self.player:
            self.damage_player(b.dmg, ux, uy, dp(160))
        else:
            self.hurt_enemy(target, b.current_damage(), ux, uy, b.push, source="bullet")

    def explode(self, x, y, b, direct=None):
        radius = b.explode
        if direct is not None:
            ux, uy, _ = norm(direct.x - x, direct.y - y)
            self.hurt_enemy(direct, b.dmg, ux, uy, 0, source="explosion")
        for e in self.enemies:
            if e.hp <= 0:
                continue
            ux, uy, d = norm(e.x - x, e.y - y)
            if d > radius + e.r:
                continue
            if not self.segment_clear(x, y, e.x, e.y):      # стіна гасить вибух
                continue
            k = min(1.0, d / radius)
            self.hurt_enemy(e, b.explode_dmg * (1 - 0.6 * k), ux, uy, dp(28) * (1 - k),
                            source="explosion")
        self.effects.flash(x, y, radius * 0.7, 0.18)
        self.effects.ring(x, y, radius * 0.2, radius * 1.15, 0.35, (1, 0.8, 0.5), 4)
        self.effects.burst(x, y, (1, 0.55, 0.15), n=24, speed=260, size=6, life=0.5)
        self.effects.burst(x, y, (0.35, 0.35, 0.35), n=10, speed=110, size=9, life=0.8, drag=2)
        self.effects.decal(x, y, radius * 0.55, radius * 0.45, (0.1, 0.08, 0.05), 9.0, 0.45)
        self.shake = max(self.shake, dp(11))

    # ============================================================
    #  Шкода
    # ============================================================
    def hurt_enemy(self, e, dmg, ux, uy, push, source="bullet"):
        if e.hp <= 0:
            return
        armored = False
        if e.kind == "tank" and source == "bullet" and e.state != "stunned":
            fx, fy = math.cos(e.angle), math.sin(e.angle)
            if -(ux * fx + uy * fy) > 0.45:       # влучання в броню спереду
                dmg *= 1 - e.t["armor"]
                armored = True
        crit = e.state == "stunned"
        if crit:
            dmg *= 1.5
        e.hp -= dmg
        e.flash = 0.08
        e.reveal = 0.6
        if e.state not in ("charge",):
            k = 0.25 if e.kind == "tank" else 1.0
            e.x += ux * push * k
            e.y += uy * push * k
            e.x, e.y = push_out(e.x, e.y, e.r, self.solids)

        if armored:
            self.effects.cone(e.x - ux * e.r, e.y - uy * e.r, math.atan2(-uy, -ux), 0.8,
                              (0.85, 0.85, 0.95), n=4, speed=180, size=2.5, life=0.2)
            self.effects.text(e.x, e.y + e.r + dp(18),str(max(1, round(dmg))), (0.65, 0.65, 0.75), 13)
        else:
            self.effects.burst(e.x, e.y, e.t["color"], n=4, speed=140, size=3, life=0.25)
            color = (1, 0.85, 0.2) if crit else (1, 1, 1)
            self.effects.text(e.x, e.y + e.r + dp(18),str(max(1, round(dmg))), color, 18 if crit else 15)
        if e.hp <= 0:
            self.kill_enemy(e)

    def kill_enemy(self, e):
        self.score += e.score
        self.kills += 1
        c = e.t["color"]
        self.effects.burst(e.x, e.y, c, n=20, speed=240, size=6, life=0.55)
        self.effects.ring(e.x, e.y, e.r * 0.5, e.r * 2.2, 0.3, c, 3)
        self.effects.flash(e.x, e.y, e.r * 1.2, 0.12, (1, 1, 1))
        self.effects.decal(e.x, e.y, e.r * 1.1, e.r * 0.8, (c[0] * 0.5, c[1] * 0.5, c[2] * 0.5),
                           7.0, 0.4)
        self.effects.text(e.x, e.y + e.r + dp(14), f"+{e.score}", (1, 0.85, 0.3), 16, 0.9, 50)
        self.shake = max(self.shake, dp(8) if e.kind == "tank" else dp(3))
        if e.elite or random.random() < e.t["drop"]:
            self.pickups.append([e.x, e.y, 10.0])

    def damage_player(self, amount, ux=0.0, uy=0.0, knock=0.0):
        p = self.player
        if p.invul > 0 or self.over:
            return
        p.hp -= amount
        p.invul = PLAYER["invul"]
        p.reveal = max(p.reveal, VISION["reveal_after_hit"])
        p.kx += ux * knock
        p.ky += uy * knock
        self.hurt_flash = 1.0
        self.shake = max(self.shake, dp(8))
        self.effects.burst(p.x, p.y, (1, 0.3, 0.3), n=10, speed=180, size=4, life=0.35)
        self.effects.text(p.x, p.y + p.r + dp(18), f"-{round(amount)}", (1, 0.35, 0.35), 17)
        if p.hp <= 0:
            p.hp = 0
            self.over = True
            self.mouse_down = False
            self.effects.burst(p.x, p.y, HERO_COLOR, n=40, speed=300, size=7, life=0.9)
            self.effects.ring(p.x, p.y, p.r, p.r * 4, 0.5, HERO_COLOR, 4)
            self.shake = dp(14)
            self.screen.schedule_game_over()

    # ============================================================
    #  Хвилі та бонуси
    # ============================================================
    def spawn_enemy(self, kind, x, y, elite):
        self.enemies.append(Enemy(kind, x, y, self.director.wave, elite))
        self.effects.ring(x, y, dp(40), dp(8), 0.3, (1, 1, 1), 2)
        self.effects.burst(x, y, (1, 1, 1), n=8, speed=120, size=4, life=0.3)

    def on_wave_start(self, n, title, elite):
        self.screen.show_banner(f"Волна {n}", title + (" + элита" if elite else ""))

    def on_wave_clear(self, n):
        bonus = WAVES["clear_bonus"] * n
        self.score += bonus
        p = self.player
        p.hp = min(p.max_hp, p.hp + WAVES["heal"])
        self.effects.ring(p.x, p.y, p.r, p.r * 3, 0.5, HERO_RING, 3)
        self.screen.show_banner("Волна пройдена!", f"+{bonus} очков, +{WAVES['heal']} HP")

    def update_pickups(self, dt):
        p = self.player
        keep = []
        for pk in self.pickups:
            pk[2] -= dt
            if not self.over and math.hypot(pk[0] - p.x, pk[1] - p.y) < p.r + dp(16):
                p.hp = min(p.max_hp, p.hp + 20)
                self.effects.burst(pk[0], pk[1], (0.4, 1, 0.5), n=12, speed=150, size=4, life=0.4)
                self.effects.text(p.x, p.y + p.r + dp(18), "+20", (0.4, 1, 0.5), 17)
                continue
            if pk[2] > 0:
                keep.append(pk)
        self.pickups = keep

    # ============================================================
    #  Малювання
    # ============================================================
    def draw_static(self):
        """Підлога, стіни й ящики: малюються лише при зміні розміру."""
        self.canvas.before.clear()
        self.canvas.after.clear()
        tile = dp(64)
        with self.canvas.before:
            PushMatrix()
            self._shake_tr = Translate(0, 0)     # тряска зсуває всю сцену
            Color(0.87, 0.68, 0.47, 1)
            Rectangle(pos=(self.x - dp(20), self.y - dp(20)),
                      size=(self.width + dp(40), self.height + dp(40)))
            Color(0.83, 0.63, 0.42, 1)
            for i in range(int(self.width / tile) + 1):
                for j in range(int(self.height / tile) + 1):
                    if (i + j) % 2:
                        Rectangle(pos=(self.x + i * tile, self.y + j * tile), size=(tile, tile))
            Color(0.55, 0.36, 0.22, 1)
            Line(rectangle=(self.x + dp(3), self.y + dp(3), self.width - dp(6),
                            self.height - dp(6)), width=dp(3))
            Color(0, 0, 0, 0.18)
            for x, y, w, h, _ in self.blocks:
                Rectangle(pos=(x + dp(6), y - dp(8)), size=(w, h))
            for x, y, w, h, kind in self.blocks:
                if kind == "wall":
                    self.draw_wall(x, y, w, h)
                else:
                    self.draw_crates(x, y, w, h)
        with self.canvas.after:
            PopMatrix()

    @staticmethod
    def draw_wall(x, y, w, h):
        depth = dp(10)
        Color(0.33, 0.33, 0.38, 1)
        Rectangle(pos=(x, y), size=(w, h))
        Color(0.58, 0.58, 0.64, 1)
        Rectangle(pos=(x, y + depth), size=(w, h - depth))
        Color(0.45, 0.45, 0.5, 1)
        brick = dp(24)
        rows = max(1, int((h - depth) / brick))
        for r in range(rows):
            by = y + depth + r * (h - depth) / rows
            if r:
                Line(points=[x, by, x + w, by], width=dp(1.2))
            bx = x + (brick if r % 2 else 0)
            while bx < x + w:
                if bx > x:
                    Line(points=[bx, by, bx, by + (h - depth) / rows], width=dp(1.2))
                bx += brick * 2
        Color(0.2, 0.2, 0.24, 1)
        Line(rectangle=(x, y, w, h), width=dp(1.5))

    @staticmethod
    def draw_crates(x, y, w, h):
        size = dp(MAP_TILE)
        cols, rows = max(1, round(w / size)), max(1, round(h / size))
        pad = dp(3)
        for i in range(cols):
            for j in range(rows):
                cx, cy = x + i * size, y + j * size
                Color(0.45, 0.28, 0.13, 1)
                Rectangle(pos=(cx, cy), size=(size, size))
                Color(0.74, 0.5, 0.26, 1)
                Rectangle(pos=(cx + pad, cy + pad), size=(size - 2 * pad, size - 2 * pad))
                Color(0.5, 0.32, 0.15, 1)
                Line(points=[cx + pad, cy + pad, cx + size - pad, cy + size - pad], width=dp(2.5))
                Line(points=[cx + pad, cy + size - pad, cx + size - pad, cy + pad], width=dp(2.5))
                Line(rectangle=(cx + pad * 2, cy + pad * 2, size - pad * 4, size - pad * 4),
                     width=dp(1.2))

    def draw(self):
        p = self.player
        if self._shake_tr is not None:
            self._shake_tr.x = random.uniform(-self.shake, self.shake)
            self._shake_tr.y = random.uniform(-self.shake, self.shake)
        self.canvas.clear()
        with self.canvas:
            self.effects.draw_decals()
            self.draw_warnings()
            for pk in self.pickups:
                self.draw_pickup(pk)
            if not self.over:
                self.draw_aim_guide()
            self.draw_telegraphs()

            objs = [(e.y, e) for e in self.enemies]
            if not self.over:
                objs.append((p.y, p))
            for _, obj in sorted(objs, key=lambda t: -t[0]):
                if obj is p:
                    self.draw_player()
                else:
                    self.draw_enemy(obj)

            self.draw_bushes()
            self.draw_bullets()
            self.effects.draw_top()
            self.draw_overheads()
            self.effects.draw_texts()
            self.draw_vignette()

    # ---------- Приціл ----------
    def ray_length(self, x, y, ang, reach):
        ex, ey = x + math.cos(ang) * reach, y + math.sin(ang) * reach
        t = first_rect_hit(x, y, ex, ey, self.bullet_solids)
        return reach * t if t is not None else reach

    def draw_aim_guide(self):
        aim = self.current_aim()
        if not aim:
            return
        p = self.player
        w = self.weapon
        ang = math.atan2(aim[1], aim[0])
        reach = dp(w["range"])
        spread = w["spread"] + self.bloom
        Color(1, 1, 1, 0.26)
        if w["pellets"] > 1 or spread > 0.06:
            rays = 13 if w["pellets"] > 1 else 7
            pts = [p.x, p.y]
            for i in range(rays):
                a = ang - spread / 2 + spread * i / (rays - 1)
                length = self.ray_length(p.x, p.y, a, reach)
                pts += [p.x + math.cos(a) * length, p.y + math.sin(a) * length]
            pts += [p.x, p.y]
            Line(points=pts, width=dp(2))
        else:
            length = self.ray_length(p.x, p.y, ang, reach)
            ex, ey = p.x + math.cos(ang) * length, p.y + math.sin(ang) * length
            Line(points=[p.x, p.y, ex, ey], width=dp(4), cap="round")
            if w.get("explode"):
                Line(circle=(ex, ey, dp(w["explode"])), width=dp(1.5))

    # ---------- Попередження ворогів ----------
    def draw_telegraphs(self):
        for e in self.enemies:
            if not e.visible:
                continue
            if e.kind == "shooter" and e.state == "aim":
                k = 1 - max(0.0, e.timer) / e.t["aim_time"]
                ux, uy, _ = norm(e.aim[0] - e.x, e.aim[1] - e.y)
                ang = math.atan2(uy, ux)
                length = self.ray_length(e.x, e.y, ang, dp(e.t["range"]))
                Color(1, 0.15, 0.15, 0.25 + 0.55 * k)
                Line(points=[e.x, e.y, e.x + ux * length, e.y + uy * length],
                     width=dp(1) + dp(2) * k)
            elif e.kind == "tank" and e.state == "windup":
                k = 1 - max(0.0, e.timer) / e.t["windup"]
                ang = e.angle
                reach = dp(e.t["charge_speed"]) * e.t["charge_time"]
                length = self.ray_length(e.x, e.y, ang, reach)
                ca, sa = math.cos(ang), math.sin(ang)
                nx, ny = -sa * e.r, ca * e.r
                Color(1, 0.2, 0.2, 0.12 + 0.25 * k)
                ex, ey = e.x + ca * length, e.y + sa * length
                Mesh(vertices=[e.x + nx, e.y + ny, 0, 0, ex + nx, ey + ny, 0, 0,
                               ex - nx, ey - ny, 0, 0, e.x - nx, e.y - ny, 0, 0],
                     indices=[0, 1, 2, 2, 3, 0], mode="triangles")
            elif e.kind == "runner" and e.state == "windup":
                p = self.player
                ux, uy, _ = norm(p.x - e.x, p.y - e.y)
                reach = dp(e.t["dash_speed"]) * e.t["dash_time"]
                Color(1, 0.9, 0.2, 0.5)
                Line(points=[e.x, e.y, e.x + ux * reach, e.y + uy * reach], width=dp(2.5),
                     cap="round")

    def draw_warnings(self):
        for x, y, t, kind, elite in self.director.warnings:
            k = 1 - t / WAVES["warn_time"]
            pulse = 0.5 + 0.5 * math.sin(self.time * 18)
            color = ELITE_RING if elite else (1, 0.25, 0.25)
            Color(*color, 0.25 + 0.35 * pulse)
            circle(x, y, dp(10) + dp(16) * k)
            Color(*color, 0.9)
            Line(circle=(x, y, dp(30) - dp(12) * k), width=dp(2))

    # ---------- Персонажі ----------
    def draw_player(self):
        p = self.player
        blink = p.invul > 0 and int(p.invul * 20) % 2 == 0
        y = p.y + math.sin(p.walk) * dp(2)
        draw_character(p.x, y, p.r, p.angle, HERO_COLOR, gun=gun_px(self.weapon),
                       flash=blink, recoil=p.recoil * dp(5),
                       ring_color=HERO_RING, scarf=HERO_SCARF)

    def draw_enemy(self, e):
        for tx, ty, life in e.trail:
            Color(*e.t["color"], 0.35 * life / 0.22)
            circle(tx, ty, e.r * 0.9)
        x, y = e.x, e.y + math.sin(e.walk) * dp(1.5)
        if e.state == "windup":
            x += random.uniform(-dp(1.5), dp(1.5))
            y += random.uniform(-dp(1.5), dp(1.5))
        flash = e.flash > 0 or (e.state == "windup" and int(self.time * 16) % 2 == 0)
        color = e.t["color"]
        if e.state == "stunned":
            color = tuple(0.5 * c + 0.3 for c in color)
        draw_character(x, y, e.r, e.angle, color,
                       gun=shooter_gun(e.r / dp(19)) if e.kind == "shooter" else None,
                       angry=True, flash=flash, armor=e.kind == "tank",
                       ring_color=ELITE_RING if e.elite else ENEMY_RING)
        if e.kind == "tank" and e.state != "stunned":
            # Броня спереду (кут Kivy: 0 - вгору, за годинниковою)
            kdeg = 90 - math.degrees(e.angle)
            Color(0.8, 0.8, 0.9, 0.9)
            Line(circle=(x, y, e.r + dp(5), kdeg - 60, kdeg + 60), width=dp(3.5))
        if e.state == "stunned":
            for i in range(3):
                a = self.time * 5 + i * 2 * math.pi / 3
                Color(1, 0.9, 0.3, 1)
                circle(x + math.cos(a) * e.r * 0.8, y + e.r + dp(6) + math.sin(a) * dp(4), dp(3.5))

    def draw_overheads(self):
        """Смужки здоров'я та значки над персонажами (поверх кущів)."""
        p = self.player
        if not self.over:
            hp_bar(p.x, p.y + p.r + dp(14), dp(56), p.hp / p.max_hp, (0.3, 0.9, 0.4))
            if p.hidden:
                Color(*HERO_RING, 0.9)
                Line(circle=(p.x, p.y, p.r + dp(4)), width=dp(2))
        for e in self.enemies:
            if not e.visible:
                continue
            if e.hp < e.max_hp or e.elite:
                hp_bar(e.x, e.y + e.r + dp(10), e.r * 2.2, e.hp / e.max_hp,
                       ELITE_RING if e.elite else (0.95, 0.3, 0.3))
            icon = None
            if e.alert_t > 0:
                icon, color = "!", (1, 0.85, 0.2)
            elif e.searching and self.unseen > 0.4:
                icon, color = "?", (1, 1, 1)
            if icon:
                tex = self.effects.texture(icon, 22)
                Color(*color, 1)
                Rectangle(texture=tex, pos=(e.x - tex.width / 2, e.y + e.r + dp(16)),
                          size=tex.size)

    def draw_bushes(self):
        """Кущі поверх персонажів. Біля героя кущ прозоріший - видно, хто всередині."""
        p = self.player
        r = dp(MAP_TILE) * 0.42
        reveal = dp(VISION["bush_reveal"])
        for bush in self.bushes:
            bx, by, bw, bh = bush
            near = not self.over and dist_to_rect(p.x, p.y, bush) < reveal
            alpha = 0.55 if near else 1.0
            cols = max(1, round(bw / (r * 1.6)))
            rows = max(1, round(bh / (r * 1.6)))
            for layer, (color, k) in enumerate((((0.13, 0.42, 0.18), 1.0),
                                                ((0.22, 0.62, 0.26), 0.82))):
                Color(*color, alpha)
                for i in range(cols):
                    for j in range(rows):
                        cx = bx + (i + 0.5) * bw / cols
                        cy = by + (j + 0.5) * bh / rows + (dp(3) if layer else 0)
                        circle(cx, cy, r * k * (1.05 if (i + j) % 2 else 0.95))
            Color(0.45, 0.85, 0.4, 0.5 * alpha)
            for i in range(cols):
                for j in range(rows):
                    cx = bx + (i + 0.5) * bw / cols
                    cy = by + (j + 0.5) * bh / rows
                    circle(cx - r * 0.25, cy + r * 0.3, r * 0.25)

    def draw_bullets(self):
        for b in self.bullets:
            if b.owner == "player":
                # Трасер: хвіст від попередньої позиції
                Color(*b.color, 0.35)
                Line(points=[b.px, b.py, b.x, b.y], width=b.r * 0.8, cap="round")
                Color(*b.color, 0.3)
                circle(b.x, b.y, b.r * 1.8)
                Color(*b.color, 1)
                circle(b.x, b.y, b.r)
            else:
                Color(0.4, 0, 0, 1)
                circle(b.x, b.y, b.r + dp(2))
                Color(*b.color, 1)
                circle(b.x, b.y, b.r)

    def draw_pickup(self, pk):
        x, y, life = pk
        if life < 3 and int(life * 8) % 2 == 0:
            return
        y += math.sin(life * 4) * dp(3)
        r = dp(13)
        Color(0, 0, 0, 0.2)
        Ellipse(pos=(x - r, y - r * 1.4), size=(2 * r, r * 0.7))
        Color(0.5, 0.05, 0.1, 1)
        circle(x, y, r + dp(2))
        Color(0.95, 0.25, 0.3, 1)
        circle(x, y, r)
        Color(1, 1, 1, 1)
        Rectangle(pos=(x - r * 0.55, y - r * 0.16), size=(r * 1.1, r * 0.32))
        Rectangle(pos=(x - r * 0.16, y - r * 0.55), size=(r * 0.32, r * 1.1))

    def draw_vignette(self):
        p = self.player
        low = 0.0
        if not self.over and p.hp < p.max_hp * 0.3:
            low = 0.25 + 0.15 * math.sin(self.time * 6)
        k = max(self.hurt_flash * 0.45, low)
        if k <= 0.01:
            return
        t = dp(46)
        m = dp(30)          # запас на тряску
        x0, y0, x1, y1 = self.x - m, self.y - m, self.right + m, self.top + m
        Color(0.85, 0.05, 0.05, k)
        Rectangle(pos=(x0, y0), size=(x1 - x0, t + m))
        Rectangle(pos=(x0, y1 - t - m), size=(x1 - x0, t + m))
        Rectangle(pos=(x0, y0), size=(t + m, y1 - y0))
        Rectangle(pos=(x1 - t - m, y0), size=(t + m, y1 - y0))
