"""Штучний інтелект ворогів.

Кожна функція повертає (mx, my, mult): напрямок руху і множник швидкості.
Рух, зіткнення зі стінами та іншими ворогами виконує Game.move_enemy.

Спільне для всіх:
  * ворог бачить героя лише по прямій (стіни й ящики блокують зір),
    а героя в кущі - тільки зблизька;
  * якщо героя не видно, ворог іде до останньої відомої позиції (карта шляхів)
    і обшукує місце навколо неї.
"""
import math
import random

from kivy.metrics import dp

from geometry import norm


def update(game, e, dt):
    e.atk_cd -= dt
    e.hit_cd -= dt
    e.flash -= dt
    e.reveal -= dt
    e.alert_t -= dt
    e.walk += dt * 10
    for tr in e.trail:
        tr[2] -= dt
    e.trail = [tr for tr in e.trail if tr[2] > 0]

    mx, my, mult = BEHAVIOURS[e.kind](game, e, dt)
    game.move_enemy(e, mx, my, mult, dt)

    if e.state in ("dash", "charge"):
        e.trail.append([e.x, e.y, 0.22])


# ------------------------------------------------------------
#  Допоміжні
# ------------------------------------------------------------
def to_player(game, e):
    p = game.player
    return norm(p.x - e.x, p.y - e.y)


def face(e, dx, dy):
    if dx or dy:
        e.angle = math.atan2(dy, dx)


def turn_towards(e, dx, dy, rate, dt):
    """Плавний поворот з обмеженою швидкістю (рад/с)."""
    if not (dx or dy):
        return
    target = math.atan2(dy, dx)
    diff = (target - e.angle + math.pi) % (2 * math.pi) - math.pi
    step = rate * dt
    e.angle += max(-step, min(step, diff))


def pursue(game, e, dt):
    """Рух до останньої відомої позиції героя, а поруч з нею - обшук."""
    gx, gy = game.goal
    _, _, d = norm(gx - e.x, gy - e.y)
    e.searching = not e.sees
    if not e.sees and d < dp(70):
        e.wander += random.uniform(-3.0, 3.0) * dt
        mx, my = math.cos(e.wander), math.sin(e.wander)
        return mx * 0.5, my * 0.5, 1.0
    mx, my = game.steer(e)
    return mx, my, 1.0


# ------------------------------------------------------------
#  Бігун: зигзаг на підході, ривок з коротким замахом
# ------------------------------------------------------------
def runner(game, e, dt):
    t = e.t
    p = game.player
    ux, uy, d = to_player(game, e)

    if e.state == "windup":
        e.timer -= dt
        face(e, ux, uy)
        if e.timer <= 0:
            lead = 0.18
            dx, dy, length = norm(p.x + p.vx * lead - e.x, p.y + p.vy * lead - e.y)
            e.dash = (dx, dy) if length else (ux, uy)
            e.state, e.timer = "dash", t["dash_time"]
            game.effects.burst(e.x, e.y, (0.9, 0.85, 0.6), n=6, speed=90, size=4, life=0.3)
        return 0.0, 0.0, 0.0

    if e.state == "dash":
        e.timer -= dt
        face(e, *e.dash)
        if e.timer <= 0:
            e.state, e.timer = "recover", 0.45
        return e.dash[0], e.dash[1], t["dash_speed"] / t["speed"]

    if e.state == "recover":
        e.timer -= dt
        if e.timer <= 0:
            e.state = "chase"
        mx, my, _ = pursue(game, e, dt)
        face(e, mx, my)
        return mx, my, 0.35

    # chase
    if (e.sees and d < dp(t["dash_range"]) and e.atk_cd <= 0
            and game.segment_clear(e.x, e.y, p.x, p.y, e.r * 0.7)):
        e.state, e.timer = "windup", t["windup"]
        e.atk_cd = t["dash_cd"] * e.cd_mult
        return 0.0, 0.0, 0.0

    mx, my, mult = pursue(game, e, dt)
    if e.sees:
        face(e, ux, uy)
        if d > dp(180):
            # Зигзаг - по ньому важче влучити
            wob = math.sin(game.time * 6 + e.phase) * 0.75
            mx, my, _ = norm(mx - my * wob, my + mx * wob)
    else:
        face(e, mx, my)
    return mx, my, mult


# ------------------------------------------------------------
#  Стрілець: дистанція, стрейф, прицілювання з лазером, втеча
# ------------------------------------------------------------
def shooter(game, e, dt):
    t = e.t
    p = game.player
    ux, uy, d = to_player(game, e)

    if e.state == "aim":
        e.timer -= dt
        if not e.sees:
            e.state, e.atk_cd = "move", 0.5
            return 0.0, 0.0, 0.0
        lead = d / dp(t["bullet_speed"]) * 0.55
        e.aim = (p.x + p.vx * lead, p.y + p.vy * lead)
        face(e, e.aim[0] - e.x, e.aim[1] - e.y)
        if e.timer <= 0:
            game.enemy_fire(e)
            e.state = "move"
            e.atk_cd = t["shoot_cd"] * e.cd_mult * random.uniform(0.85, 1.15)
        return 0.0, 0.0, 0.0

    if not e.sees:
        mx, my, mult = pursue(game, e, dt)
        face(e, mx, my)
        return mx, my, mult

    e.searching = False
    face(e, ux, uy)
    e.timer -= dt
    if e.timer <= 0:
        e.strafe = -e.strafe
        e.timer = random.uniform(1.2, 2.8)

    keep = dp(t["keep"])
    sx, sy = -uy * e.strafe, ux * e.strafe
    if d < dp(t["flee"]):                       # герой занадто близько - тікає
        mx, my, mult = -ux + sx * 0.4, -uy + sy * 0.4, 1.35
    elif d < keep - dp(70):                     # відходить, стрейфлячи
        mx, my, mult = -ux * 0.8 + sx * 0.5, -uy * 0.8 + sy * 0.5, 1.0
    elif d > keep + dp(60):                     # підходить ближче
        mx, my, mult = pursue(game, e, dt)
    else:                                       # на своїй дистанції - стрейф
        mx, my, mult = sx * 0.75, sy * 0.75, 1.0

    if e.atk_cd <= 0 and dp(60) < d < dp(t["range"]):
        e.state, e.timer = "aim", t["aim_time"]
        e.aim = (p.x, p.y)
        return 0.0, 0.0, 0.0
    return mx, my, mult


# ------------------------------------------------------------
#  Танк: броня спереду, повільний поворот, таран, оглушення об стіну
# ------------------------------------------------------------
def tank(game, e, dt):
    t = e.t
    p = game.player
    ux, uy, d = to_player(game, e)
    turn = t["turn"]

    if e.state == "stunned":
        e.timer -= dt
        if e.timer <= 0:
            e.state = "advance"
        return 0.0, 0.0, 0.0

    if e.state == "windup":
        e.timer -= dt
        if e.timer > t["windup"] * 0.3:        # останні 30% замаху напрямок зафіксовано
            turn_towards(e, ux, uy, turn * 1.6, dt)
        if e.timer <= 0:
            e.dash = (math.cos(e.angle), math.sin(e.angle))
            e.state, e.timer = "charge", t["charge_time"]
            game.shake = max(game.shake, dp(4))
        return 0.0, 0.0, 0.0

    if e.state == "charge":
        e.timer -= dt
        if random.random() < dt * 30:
            game.effects.burst(e.x - e.dash[0] * e.r, e.y - e.dash[1] * e.r,
                               (0.75, 0.62, 0.45), n=2, speed=60, size=6, life=0.45)
        if e.timer <= 0:
            e.state = "advance"
            e.atk_cd = t["charge_cd"] * e.cd_mult
        return e.dash[0], e.dash[1], t["charge_speed"] / t["speed"]

    # advance
    if (e.sees and dp(90) < d < dp(t["charge_range"]) and e.atk_cd <= 0
            and game.segment_clear(e.x, e.y, p.x, p.y, e.r * 0.8)):
        e.state, e.timer = "windup", t["windup"]
        return 0.0, 0.0, 0.0

    mx, my, mult = pursue(game, e, dt)
    if e.sees:
        turn_towards(e, ux, uy, turn, dt)
    else:
        turn_towards(e, mx, my, turn, dt)
    return mx, my, mult


BEHAVIOURS = {"runner": runner, "shooter": shooter, "tank": tank}
