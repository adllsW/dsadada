"""Геометрія зіткнень: кола, прямокутники (x, y, w, h) і відрізки."""
import math


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def norm(dx, dy):
    """Одиничний вектор і довжина: (ux, uy, length)."""
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0, 0.0, 0.0
    return dx / length, dy / length, length


def push_out(x, y, r, rects):
    """Виштовхує коло (x, y, r) з прямокутників."""
    for rx, ry, rw, rh in rects:
        cx = clamp(x, rx, rx + rw)
        cy = clamp(y, ry, ry + rh)
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d >= r:
            continue
        if d > 1e-6:
            x += dx / d * (r - d)
            y += dy / d * (r - d)
        else:
            # Центр усередині прямокутника - до найближчої сторони
            left, right = x - rx, rx + rw - x
            bottom, top = y - ry, ry + rh - y
            m = min(left, right, bottom, top)
            if m == left:
                x = rx - r
            elif m == right:
                x = rx + rw + r
            elif m == bottom:
                y = ry - r
            else:
                y = ry + rh + r
    return x, y


def point_in_rects(x, y, pad, rects):
    for rx, ry, rw, rh in rects:
        if rx - pad <= x <= rx + rw + pad and ry - pad <= y <= ry + rh + pad:
            return True
    return False


def dist_to_rect(x, y, rect):
    rx, ry, rw, rh = rect
    return math.hypot(x - clamp(x, rx, rx + rw), y - clamp(y, ry, ry + rh))


def segment_rect_t(x1, y1, x2, y2, rx, ry, rw, rh, pad=0.0):
    """Частка відрізка (0..1), на якій він входить у прямокутник, або None.

    Метод "слабів": перетинаємо відрізок зі смугами по X і по Y.
    """
    dx, dy = x2 - x1, y2 - y1
    t_min, t_max = 0.0, 1.0
    for p, d, lo, hi in ((x1, dx, rx - pad, rx + rw + pad),
                         (y1, dy, ry - pad, ry + rh + pad)):
        if abs(d) < 1e-9:
            if p < lo or p > hi:
                return None
        else:
            t1 = (lo - p) / d
            t2 = (hi - p) / d
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > t_min:
                t_min = t1
            if t2 < t_max:
                t_max = t2
            if t_min > t_max:
                return None
    return t_min


def segment_circle_t(x1, y1, x2, y2, cx, cy, r):
    """Частка відрізка (0..1), на якій він торкається кола, або None."""
    dx, dy = x2 - x1, y2 - y1
    fx, fy = x1 - cx, y1 - cy
    c = fx * fx + fy * fy - r * r
    if c <= 0:
        return 0.0          # початок уже всередині кола
    a = dx * dx + dy * dy
    if a < 1e-12:
        return None
    b = 2 * (fx * dx + fy * dy)
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    return t if 0.0 <= t <= 1.0 else None


def first_rect_hit(x1, y1, x2, y2, rects, pad=0.0):
    """Найближче влучання відрізка в будь-який прямокутник: t або None."""
    best = None
    for rx, ry, rw, rh in rects:
        t = segment_rect_t(x1, y1, x2, y2, rx, ry, rw, rh, pad)
        if t is not None and (best is None or t < best):
            best = t
    return best


def segment_clear(x1, y1, x2, y2, rects, pad=0.0):
    return first_rect_hit(x1, y1, x2, y2, rects, pad) is None
