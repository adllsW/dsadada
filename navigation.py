"""Пошук шляху для ворогів.

Арена ділиться на сітку. Для цілі (остання відома позиція героя) алгоритм Дейкстри
рахує відстань від цілі до кожної клітинки - це "поле потоку". Кожен ворог просто
крокує в сусідню клітинку з меншою відстанню, тож одна карта обслуговує всіх
ворогів одного розміру одразу.

Карт дві: для малих ворогів і для великих (танк) - їм потрібен більший запас від стін.
"""
import heapq
import math

from geometry import clamp, dist_to_rect, norm

SQRT2 = math.sqrt(2)
NEIGHBOURS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2)]
BLOCKED_COST = 12.0     # заблоковані клітинки прохідні, але дуже "дорогі"
MIN_REBUILD = 0.25      # перераховувати поле не частіше, ніж раз на 0.25 с


class NavGrid:
    def __init__(self):
        self.cols = self.rows = 0
        self.cell = 1.0
        self.x0 = self.y0 = 0.0
        self.blocked = {}
        self.fields = {}     # клас -> (клітинка цілі, час розрахунку, відстані)

    def build(self, x0, y0, width, height, cell, solids, clearances):
        """clearances: {"small": запас, "big": запас} у пікселях."""
        self.x0, self.y0, self.cell = x0, y0, cell
        self.cols = max(1, int(width // cell))
        self.rows = max(1, int(height // cell))
        self.blocked = {}
        for name, c in clearances.items():
            grid = bytearray(self.cols * self.rows)
            for j in range(self.rows):
                cy = y0 + (j + 0.5) * cell
                for i in range(self.cols):
                    cx = x0 + (i + 0.5) * cell
                    if (cx < x0 + c or cx > x0 + width - c or cy < y0 + c or cy > y0 + height - c
                            or any(dist_to_rect(cx, cy, r) < c for r in solids)):
                        grid[j * self.cols + i] = 1
            self.blocked[name] = grid
        self.fields = {}

    def cell_of(self, x, y):
        i = clamp(int((x - self.x0) / self.cell), 0, self.cols - 1)
        j = clamp(int((y - self.y0) / self.cell), 0, self.rows - 1)
        return i, j

    def center(self, i, j):
        return self.x0 + (i + 0.5) * self.cell, self.y0 + (j + 0.5) * self.cell

    def field(self, name, gx, gy, now):
        goal = self.cell_of(gx, gy)
        cached = self.fields.get(name)
        if cached and (cached[0] == goal or now - cached[1] < MIN_REBUILD):
            return cached[2]
        dist = self._dijkstra(name, goal)
        self.fields[name] = (goal, now, dist)
        return dist

    def _dijkstra(self, name, goal):
        cols, rows = self.cols, self.rows
        blocked = self.blocked[name]
        dist = [math.inf] * (cols * rows)
        gi, gj = goal
        dist[gj * cols + gi] = 0.0
        heap = [(0.0, gi, gj)]
        while heap:
            d, i, j = heapq.heappop(heap)
            if d > dist[j * cols + i]:
                continue
            for di, dj, cost in NEIGHBOURS:
                ni, nj = i + di, j + dj
                if not (0 <= ni < cols and 0 <= nj < rows):
                    continue
                # Не зрізаємо кути по діагоналі
                if di and dj and (blocked[j * cols + ni] or blocked[nj * cols + i]):
                    continue
                nidx = nj * cols + ni
                nd = d + cost * (BLOCKED_COST if blocked[nidx] else 1.0)
                if nd < dist[nidx]:
                    dist[nidx] = nd
                    heapq.heappush(heap, (nd, ni, nj))
        return dist

    def direction(self, name, x, y, dist):
        """Одиничний напрямок до сусідньої клітинки, ближчої до цілі, або None."""
        cols = self.cols
        blocked = self.blocked[name]
        i, j = self.cell_of(x, y)
        best = dist[j * cols + i]
        target = None
        for di, dj, _ in NEIGHBOURS:
            ni, nj = i + di, j + dj
            if not (0 <= ni < cols and 0 <= nj < self.rows):
                continue
            if di and dj and (blocked[j * cols + ni] or blocked[nj * cols + i]):
                continue
            v = dist[nj * cols + ni]
            if v < best:
                best, target = v, (ni, nj)
        if target is None:
            return None
        cx, cy = self.center(*target)
        ux, uy, length = norm(cx - x, cy - y)
        return (ux, uy) if length else None

    def is_free(self, name, x, y):
        i, j = self.cell_of(x, y)
        return not self.blocked[name][j * self.cols + i]
