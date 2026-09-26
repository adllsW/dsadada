"""Ігрові об'єкти: герой, вороги, кулі."""
import math
import random

from kivy.metrics import dp

from settings import ELITE, ENEMY_TYPES, NAV_CLEARANCE, PLAYER, SCALING


class Player:
    def __init__(self):
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0      # фактична швидкість (для упередження ворогів)
        self.kx = self.ky = 0.0      # відкидання від ударів і віддачі
        self.r = dp(PLAYER["radius"])
        self.max_hp = PLAYER["hp"]
        self.hp = self.max_hp
        self.speed = dp(PLAYER["speed"])
        self.angle = 0.0
        self.invul = 0.0
        self.cooldown = 0.0
        self.walk = 0.0
        self.recoil = 0.0
        self.reveal = 0.0            # поки > 0, героя видно навіть у кущах
        self.in_bush = False
        self.hidden = False


class Enemy:
    START_STATE = {"runner": "chase", "shooter": "move", "tank": "advance"}

    def __init__(self, kind, x, y, wave, elite=False):
        t = ENEMY_TYPES[kind]
        self.kind = kind
        self.t = t
        self.elite = elite
        self.x, self.y = x, y

        hp_mult = 1 + SCALING["hp_per_wave"] * (wave - 1)
        speed_mult = min(SCALING["speed_max"], 1 + SCALING["speed_per_wave"] * (wave - 1))
        self.cd_mult = max(SCALING["cd_min"], 1 - SCALING["cd_per_wave"] * (wave - 1))
        if elite:
            hp_mult *= ELITE["hp"]
        self.max_hp = t["hp"] * hp_mult
        self.hp = self.max_hp
        self.r = dp(t["radius"]) * (ELITE["radius"] if elite else 1.0)
        self.speed = dp(t["speed"]) * speed_mult
        self.dmg_mult = ELITE["damage"] if elite else 1.0
        self.score = t["score"] * (ELITE["score"] if elite else 1)
        self.nav = "small" if self.r <= dp(NAV_CLEARANCE["small"] - 2) else "big"

        self.state = self.START_STATE[kind]
        self.timer = 0.0
        self.atk_cd = random.uniform(0.6, 1.6)
        self.hit_cd = 0.0
        self.angle = random.uniform(0, 2 * math.pi)
        self.flash = 0.0
        self.reveal = 0.0
        self.walk = random.uniform(0, 6)
        self.strafe = random.choice((-1, 1))
        self.phase = random.uniform(0, 2 * math.pi)
        self.wander = random.uniform(0, 2 * math.pi)
        self.sees = False
        self.visible = True
        self.in_bush = False
        self.alert_t = 0.0
        self.searching = False
        self.dash = (0.0, 0.0)
        self.aim = (x, y)
        self.trail = []          # [x, y, life] - шлейф під час ривка/тарану


class Bullet:
    __slots__ = ("x", "y", "px", "py", "vx", "vy", "dmg", "r", "color", "owner",
                 "range", "traveled", "falloff", "push", "explode", "explode_dmg")

    def __init__(self, x, y, vx, vy, dmg, r, color, owner, rng,
                 falloff=0.0, push=0.0, explode=0.0, explode_dmg=0.0):
        self.x = self.px = x
        self.y = self.py = y
        self.vx, self.vy = vx, vy
        self.dmg = dmg
        self.r = r
        self.color = color
        self.owner = owner
        self.range = rng
        self.traveled = 0.0
        self.falloff = falloff
        self.push = push
        self.explode = explode
        self.explode_dmg = explode_dmg

    def current_damage(self):
        k = min(1.0, self.traveled / self.range) if self.range else 0.0
        return self.dmg * (1 - self.falloff * k)
