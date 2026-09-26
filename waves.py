"""Режисер хвиль.

Кожна хвиля має бюджет (8 + 4 * номер). Шаблон хвилі визначає, яких ворогів
"купуємо" за цей бюджет, якими загонами вони йдуть і з яких боків заходять.
Кожна 5-та хвиля додає елітного ворога. Перед появою ворога на місці спавну
кілька десятих секунди видно попередження.
"""
import math
import random

from kivy.metrics import dp

from geometry import clamp, point_in_rects, push_out
from settings import ELITE, ENEMY_TYPES, WAVE_TEMPLATES, WAVES

SIDES = ("top", "bottom", "left", "right")
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


class WaveDirector:
    def __init__(self, game):
        self.game = game
        self.wave = 0
        self.state = "break"
        self.timer = WAVES["first_break"]
        self.groups = []        # [пауза, сторона, [типи], elite]
        self.warnings = []      # [x, y, час, тип, elite]
        self.last_template = None

    # ---------- Інформація ----------
    @property
    def remaining(self):
        queued = sum(len(g[2]) for g in self.groups)
        return len(self.game.enemies) + len(self.warnings) + queued

    def alive_cap(self):
        return min(WAVES["alive_max"], WAVES["alive_base"] + self.wave)

    # ---------- Планування ----------
    def pick_template(self, n):
        forced = {1: "rush", 2: "ranged", 3: "siege"}
        if n in forced:
            return forced[n]
        options = [k for k in WAVE_TEMPLATES if k != self.last_template]
        return random.choice(options)

    @staticmethod
    def unlocked(n):
        kinds = {"runner"}
        if n >= 2:
            kinds.add("shooter")
        if n >= 3:
            kinds.add("tank")
        return kinds

    def side_plan(self, mode):
        if mode == "one":
            return [random.choice(SIDES)]
        if mode == "pincer":
            s = random.choice(SIDES)
            return [s, OPPOSITE[s]]
        sides = list(SIDES)
        random.shuffle(sides)
        return sides

    def start_next(self):
        self.wave += 1
        n = self.wave
        name = self.pick_template(n)
        self.last_template = name
        tpl = WAVE_TEMPLATES[name]
        budget = WAVES["budget_base"] + WAVES["budget_per_wave"] * n
        allowed = self.unlocked(n)
        weights = {k: w for k, w in tpl["weights"].items() if k in allowed and w > 0}

        elite_kind = None
        if n % WAVES["elite_every"] == 0:
            elite_kind = random.choice(["tank", "shooter"] if "tank" in allowed else ["shooter"])
            budget -= ENEMY_TYPES[elite_kind]["cost"] * ELITE["cost"]

        kinds = []
        while True:
            affordable = [k for k in weights if ENEMY_TYPES[k]["cost"] <= budget]
            if not affordable:
                break
            k = random.choices(affordable, [weights[a] for a in affordable])[0]
            kinds.append(k)
            budget -= ENEMY_TYPES[k]["cost"]
        random.shuffle(kinds)

        sides = self.side_plan(tpl["sides"])
        gmin, gmax = tpl["group"]
        self.groups = []
        while kinds:
            size = random.randint(gmin, gmax)
            chunk, kinds = kinds[:size], kinds[size:]
            gap = 0.6 if not self.groups else tpl["gap"]
            self.groups.append([gap, sides[len(self.groups) % len(sides)], chunk, False])
        if elite_kind:
            self.groups.append([tpl["gap"], random.choice(SIDES), [elite_kind], True])

        self.state = "active"
        self.game.on_wave_start(n, tpl["title"], elite_kind is not None)

    # ---------- Спавн ----------
    def place_group(self, side, kinds, elite):
        g = self.game
        p = g.player
        m = dp(40)
        spread = dp(70)
        for kind in kinds:
            x, y = g.center
            for attempt in range(25):
                if side == "top":
                    ax, ay = random.uniform(g.x + m, g.right - m), g.top - m
                elif side == "bottom":
                    ax, ay = random.uniform(g.x + m, g.right - m), g.y + m
                elif side == "left":
                    ax, ay = g.x + m, random.uniform(g.y + m, g.top - m)
                else:
                    ax, ay = g.right - m, random.uniform(g.y + m, g.top - m)
                x = clamp(ax + random.uniform(-spread, spread), g.x + m, g.right - m)
                y = clamp(ay + random.uniform(-spread, spread), g.y + m, g.top - m)
                x, y = push_out(x, y, dp(38), g.solids)
                ok = (math.hypot(x - p.x, y - p.y) > dp(280)
                      and not point_in_rects(x, y, dp(20), g.solids)
                      and all(math.hypot(x - w[0], y - w[1]) > dp(40) for w in self.warnings))
                if ok:
                    break
            self.warnings.append([x, y, WAVES["warn_time"], kind, elite])

    def update(self, dt):
        g = self.game
        if g.over:
            return
        if self.state == "break":
            self.timer -= dt
            if self.timer <= 0:
                self.start_next()
            return

        # Попередження перетворюються на ворогів
        for w in self.warnings:
            w[2] -= dt
        for w in [w for w in self.warnings if w[2] <= 0]:
            g.spawn_enemy(w[3], w[0], w[1], w[4])
        self.warnings = [w for w in self.warnings if w[2] > 0]

        # Наступний загін
        if self.groups:
            grp = self.groups[0]
            field_empty = not g.enemies and not self.warnings
            if field_empty:
                grp[0] = min(grp[0], 0.4)
            grp[0] -= dt
            room = self.alive_cap() - len(g.enemies) - len(self.warnings)
            if grp[0] <= 0 and (room >= len(grp[2]) or field_empty):
                self.groups.pop(0)
                self.place_group(grp[1], grp[2], grp[3])
        elif not g.enemies and not self.warnings:
            self.state = "break"
            self.timer = WAVES["break"]
            g.on_wave_clear(self.wave)
