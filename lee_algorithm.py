"""
Волновой алгоритм Ли — поиск кратчайшего пути в сетке
Дисциплина: Скриптовые языки
"""

import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2
import math
import time
from collections import deque

# ─────────────────────────────────────────────
#  НАСТРОЙКИ ПОДКЛЮЧЕНИЯ К PostgreSQL
#  ← поменяй user, password, dbname под себя
# ─────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "lee_db",
    "user":     "postgres",
    "password": "2005",
}

DEFAULT_ROWS = 30
DEFAULT_COLS = 30
CELL_SIZE    = 22   # пиксели

# ─────────────────────────────────────────────
#  ТИПЫ ПОВЕРХНОСТИ
#  cell_type -> (цвет, стоимость прохода, подпись)
# ─────────────────────────────────────────────
SURFACES = {
    "empty":  ("#ffffff", 1.0,  "Обычная"),
    "road":   ("#a9dfbf", 0.5,  "Дорога (×0.5)"),
    "swamp":  ("#a9cce3", 2.0,  "Болото (×2)"),
    "sand":   ("#f9e79f", 1.5,  "Песок (×1.5)"),
    "wall":   ("#2c3e50", None, "Стена"),
}

COLOR_START = "#27ae60"
COLOR_END   = "#e74c3c"
COLOR_WAVE  = "#aed6f1"
COLOR_PATH  = "#f39c12"
COLOR_GRID  = "#bdc3c7"

# ─────────────────────────────────────────────
#  ТИПЫ ШАГОВ
# ─────────────────────────────────────────────
DIRS_STRAIGHT = [(-1,0),(1,0),(0,-1),(0,1)]
DIRS_DIAGONAL = [(-1,-1),(-1,1),(1,-1),(1,1)]
DIRS_KNIGHT   = [(-2,-1),(-2,1),(2,-1),(2,1),
                 (-1,-2),(-1,2),(1,-2),(1,2)]

KNIGHT_BLOCKERS = {
    (-2,-1): [(-1,0),(-1,-1)],  (-2, 1): [(-1,0),(-1, 1)],
    ( 2,-1): [( 1,0),( 1,-1)],  ( 2, 1): [( 1,0),( 1, 1)],
    (-1,-2): [(0,-1),(-1,-1)],  (-1, 2): [(0, 1),(-1, 1)],
    ( 1,-2): [(0,-1),( 1,-1)],  ( 1, 2): [(0, 1),( 1, 1)],
}


# ─────────────────────────────────────────────
#  БАЗА ДАННЫХ
# ─────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS grids (
        id         SERIAL PRIMARY KEY,
        rows       INTEGER NOT NULL,
        cols       INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS cells (
        id        SERIAL PRIMARY KEY,
        grid_id   INTEGER REFERENCES grids(id) ON DELETE CASCADE,
        row       INTEGER NOT NULL,
        col       INTEGER NOT NULL,
        cell_type VARCHAR(20) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS path_results (
        id          SERIAL PRIMARY KEY,
        grid_id     INTEGER REFERENCES grids(id) ON DELETE CASCADE,
        found       BOOLEAN NOT NULL,
        path_length REAL,
        path_cells  TEXT,
        steps_count INTEGER,
        duration_ms REAL,
        saved_at    TIMESTAMP DEFAULT NOW()
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def save_grid(grid, rows, cols):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO grids (rows, cols) VALUES (%s, %s) RETURNING id",
                (rows, cols)
            )
            grid_id = cur.fetchone()[0]
            data = [
                (grid_id, r, c, grid[r][c])
                for r in range(rows)
                for c in range(cols)
                if grid[r][c] != "empty"
            ]
            if data:
                cur.executemany(
                    "INSERT INTO cells (grid_id, row, col, cell_type) VALUES (%s,%s,%s,%s)",
                    data
                )
        conn.commit()
    return grid_id


def save_result(grid_id, found, path, steps, duration_ms):
    path_length = _path_cost(path) if found and path else None
    path_str    = ";".join(f"{r},{c}" for r, c in path) if path else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO path_results
                   (grid_id, found, path_length, path_cells, steps_count, duration_ms)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (grid_id, found, path_length, path_str, steps, duration_ms)
            )
        conn.commit()


def _path_cost(path):
    total = 0.0
    for i in range(1, len(path)):
        dr = abs(path[i][0] - path[i-1][0])
        dc = abs(path[i][1] - path[i-1][1])
        d  = dr + dc
        if d == 1:
            base = 1.0
        elif d == 2:
            base = math.sqrt(2)
        else:
            base = math.sqrt(5)
        total += base
    return round(total, 4)


# ─────────────────────────────────────────────
#  АЛГОРИТМ ЛИ
# ─────────────────────────────────────────────
def lee(grid, rows, cols, start, end,
        use_straight=True, use_diag=True, use_knight=True):
    INF  = float("inf")
    dist = [[INF] * cols for _ in range(rows)]
    prev = [[None]  * cols for _ in range(rows)]

    dist[start[0]][start[1]] = 0
    queue = deque([start])
    wave_order = []
    steps = 0

    while queue:
        r, c = queue.popleft()
        wave_order.append((r, c))
        steps += 1

        if (r, c) == end:
            break

        neighbours = []
        if use_straight:
            for dr, dc in DIRS_STRAIGHT:
                neighbours.append((dr, dc, 1.0))
        if use_diag:
            for dr, dc in DIRS_DIAGONAL:
                neighbours.append((dr, dc, math.sqrt(2)))
        if use_knight:
            for dr, dc in DIRS_KNIGHT:
                neighbours.append((dr, dc, math.sqrt(5)))

        for dr, dc, base_cost in neighbours:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            cell = grid[nr][nc]
            if cell == "wall":
                continue

            # проверка блокировки для шага конём
            if base_cost == math.sqrt(5):
                blocked = any(
                    grid[r + br][c + bc] == "wall"
                    for br, bc in KNIGHT_BLOCKERS.get((dr, dc), [])
                    if 0 <= r+br < rows and 0 <= c+bc < cols
                )
                if blocked:
                    continue

            # стоимость с учётом типа поверхности целевой клетки
            surf_cost = SURFACES.get(cell, SURFACES["empty"])[1] or 1.0
            new_dist  = dist[r][c] + base_cost * surf_cost

            if new_dist < dist[nr][nc]:
                dist[nr][nc] = new_dist
                prev[nr][nc] = (r, c)
                queue.append((nr, nc))

    if dist[end[0]][end[1]] == INF:
        return None, wave_order, steps

    path, cur = [], end
    while cur:
        path.append(cur)
        cur = prev[cur[0]][cur[1]]
    path.reverse()
    return path, wave_order, steps


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
class LeeApp:
    def __init__(self, root):
        self.root  = root
        self.root.title("Алгоритм Ли — поиск кратчайшего пути")
        self.root.resizable(False, False)

        self.rows  = DEFAULT_ROWS
        self.cols  = DEFAULT_COLS
        self.grid  = [["empty"] * self.cols for _ in range(self.rows)]
        self.start = None
        self.end   = None

        self.use_straight = tk.BooleanVar(value=True)
        self.use_diag     = tk.BooleanVar(value=True)
        self.use_knight   = tk.BooleanVar(value=True)
        self.anim_speed   = tk.IntVar(value=5)
        self.mode_var     = tk.StringVar(value="wall")

        self._build_ui()
        self._draw_grid()

        try:
            init_db()
            self.db_ok = True
        except Exception as e:
            self.db_ok = False
            messagebox.showwarning(
                "БД недоступна",
                f"PostgreSQL не подключён:\n{e}\n\nПрограмма работает без сохранения."
            )

    # ── UI ────────────────────────────────────
    def _build_ui(self):
        ctrl = tk.Frame(self.root, bg="#ecf0f1", padx=10, pady=10, width=215)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="Алгоритм Ли",
                 font=("Arial", 14, "bold"), bg="#ecf0f1").pack(pady=(0, 8))

        # инструменты
        tk.Label(ctrl, text="Инструмент:", bg="#ecf0f1",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        tools = [
            ("🧱 Стена",           "wall"),
            ("🌿 Болото (×2)",     "swamp"),
            ("🛤  Дорога (×0.5)", "road"),
            ("🏜  Песок (×1.5)",  "sand"),
            ("🟢 Старт",           "start"),
            ("🔴 Финиш",           "end"),
            ("🧹 Ластик",          "erase"),
        ]
        for text, val in tools:
            tk.Radiobutton(ctrl, text=text, variable=self.mode_var, value=val,
                           bg="#ecf0f1").pack(anchor="w")

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=6)

        # типы шагов
        tk.Label(ctrl, text="Типы шагов:", bg="#ecf0f1",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        tk.Checkbutton(ctrl, text="↔ Прямые (×1)",
                       variable=self.use_straight, bg="#ecf0f1").pack(anchor="w")
        tk.Checkbutton(ctrl, text="↗ Диагональ (×√2)",
                       variable=self.use_diag,     bg="#ecf0f1").pack(anchor="w")
        tk.Checkbutton(ctrl, text="♞ Конём (×√5)",
                       variable=self.use_knight,   bg="#ecf0f1").pack(anchor="w")

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=6)

        # скорость анимации
        tk.Label(ctrl, text="Скорость анимации:", bg="#ecf0f1",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        tk.Scale(ctrl, from_=1, to=10, orient="horizontal",
                 variable=self.anim_speed, bg="#ecf0f1").pack(fill="x")

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=6)

        # кнопки
        bs = {"width": 20, "pady": 3, "font": ("Arial", 9)}
        tk.Button(ctrl, text="▶ Найти путь",       bg="#27ae60", fg="white",
                  command=self._run,            **bs).pack(pady=2)
        tk.Button(ctrl, text="🔀 Случайная карта",  bg="#8e44ad", fg="white",
                  command=self._random_map,     **bs).pack(pady=2)
        tk.Button(ctrl, text="🗑  Очистить всё",    bg="#e74c3c", fg="white",
                  command=self._clear_all,      **bs).pack(pady=2)
        tk.Button(ctrl, text="💾 Сохранить в БД",   bg="#2980b9", fg="white",
                  command=self._save_to_db,     **bs).pack(pady=2)

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=6)

        # статус
        tk.Label(ctrl, text="Статус:", bg="#ecf0f1",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Ставь старт и финиш")
        tk.Label(ctrl, textvariable=self.status_var, bg="#ecf0f1",
                 wraplength=195, justify="left", fg="#2c3e50").pack(anchor="w")

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=6)

        # легенда
        tk.Label(ctrl, text="Легенда:", bg="#ecf0f1",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        legend = [
            (COLOR_START,          "Старт"),
            (COLOR_END,            "Финиш"),
            (SURFACES["wall"][0],  "Стена"),
            (SURFACES["swamp"][0], "Болото (×2)"),
            (SURFACES["road"][0],  "Дорога (×0.5)"),
            (SURFACES["sand"][0],  "Песок (×1.5)"),
            (COLOR_WAVE,           "Волна"),
            (COLOR_PATH,           "Путь"),
        ]
        for color, label in legend:
            f = tk.Frame(ctrl, bg="#ecf0f1")
            f.pack(anchor="w", pady=1)
            tk.Label(f, bg=color, width=2, relief="solid").pack(side="left", padx=(0,5))
            tk.Label(f, text=label, bg="#ecf0f1", font=("Arial", 8)).pack(side="left")

        # канвас
        cw = self.cols * CELL_SIZE + 1
        ch = self.rows * CELL_SIZE + 1
        frame = tk.Frame(self.root, bd=2, relief="sunken")
        frame.pack(side=tk.LEFT, padx=10, pady=10)
        self.canvas = tk.Canvas(frame, width=cw, height=ch,
                                bg=COLOR_GRID, cursor="crosshair")
        self.canvas.pack()
        self.canvas.bind("<Button-1>",  self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)

    # ── отрисовка ─────────────────────────────
    def _draw_grid(self):
        self.canvas.delete("all")
        self.rects = {}
        for r in range(self.rows):
            for c in range(self.cols):
                x1, y1 = c * CELL_SIZE, r * CELL_SIZE
                rect = self.canvas.create_rectangle(
                    x1, y1, x1 + CELL_SIZE, y1 + CELL_SIZE,
                    fill=self._cell_color(r, c), outline=COLOR_GRID, width=1
                )
                self.rects[(r, c)] = rect

    def _cell_color(self, r, c):
        if (r, c) == self.start: return COLOR_START
        if (r, c) == self.end:   return COLOR_END
        ct = self.grid[r][c]
        if ct == "wave": return COLOR_WAVE
        if ct == "path": return COLOR_PATH
        return SURFACES.get(ct, SURFACES["empty"])[0]

    def _update_cell(self, r, c):
        self.canvas.itemconfig(self.rects[(r, c)], fill=self._cell_color(r, c))

    # ── мышь ──────────────────────────────────
    def _on_click(self, e):
        r, c = e.y // CELL_SIZE, e.x // CELL_SIZE
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self._apply_tool(r, c)

    def _on_drag(self, e):
        r, c = e.y // CELL_SIZE, e.x // CELL_SIZE
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self._apply_tool(r, c)

    def _apply_tool(self, r, c):
        mode = self.mode_var.get()
        if mode == "start":
            old, self.start = self.start, (r, c)
            self.grid[r][c] = "empty"
            if old: self._update_cell(*old)
            self._update_cell(r, c)
        elif mode == "end":
            old, self.end = self.end, (r, c)
            self.grid[r][c] = "empty"
            if old: self._update_cell(*old)
            self._update_cell(r, c)
        elif mode == "erase":
            self.grid[r][c] = "empty"
            if (r, c) == self.start: self.start = None
            if (r, c) == self.end:   self.end   = None
            self._update_cell(r, c)
        else:
            if (r, c) not in (self.start, self.end):
                self.grid[r][c] = mode
                self._update_cell(r, c)

    # ── кнопки ────────────────────────────────
    def _clear_all(self):
        self.start = self.end = None
        self.grid  = [["empty"] * self.cols for _ in range(self.rows)]
        self._draw_grid()
        self.status_var.set("Ставь старт и финиш")

    def _random_map(self):
        import random
        self._clear_all()
        surf_pool = ["wall", "wall", "wall", "swamp", "swamp", "road", "sand"]
        for r in range(self.rows):
            for c in range(self.cols):
                if random.random() < 0.30:
                    self.grid[r][c] = random.choice(surf_pool)
                    self._update_cell(r, c)
        self.status_var.set("Случайная карта готова")

    def _save_to_db(self):
        if not self.db_ok:
            messagebox.showwarning("БД", "PostgreSQL недоступен")
            return
        try:
            gid = save_grid(self.grid, self.rows, self.cols)
            self.status_var.set(f"Сохранено в БД\ngrid_id = {gid}")
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e))

    # ── запуск алгоритма ──────────────────────
    def _run(self):
        if not self.start or not self.end:
            messagebox.showinfo("Внимание", "Поставь старт 🟢 и финиш 🔴!")
            return

        # сброс предыдущего запуска
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] in ("wave", "path"):
                    self.grid[r][c] = "empty"
                    self._update_cell(r, c)

        self.status_var.set("Ищу путь…")
        self.root.update()

        t0 = time.time()
        path, wave_order, steps = lee(
            self.grid, self.rows, self.cols,
            self.start, self.end,
            use_straight=self.use_straight.get(),
            use_diag=self.use_diag.get(),
            use_knight=self.use_knight.get(),
        )
        duration_ms = (time.time() - t0) * 1000

        # анимация волны
        delay = max(1, 11 - self.anim_speed.get())
        skip  = max(1, len(wave_order) // 400)
        for i, (r, c) in enumerate(wave_order):
            if (r, c) in (self.start, self.end): continue
            if self.grid[r][c] == "empty":
                self.grid[r][c] = "wave"
                self._update_cell(r, c)
            if i % skip == 0:
                self.root.update()
                self.root.after(delay)

        # анимация пути
        if path:
            for r, c in path:
                if (r, c) in (self.start, self.end): continue
                self.grid[r][c] = "path"
                self._update_cell(r, c)
            cost = _path_cost(path)
            self.status_var.set(
                f"✅ Путь найден!\n"
                f"Длина: {cost:.3f}\n"
                f"Клеток в пути: {len(path)}\n"
                f"Проверено: {steps}\n"
                f"Время: {duration_ms:.1f} мс"
            )
        else:
            self.status_var.set("❌ Путь не найден!")

        # сохранение в БД
        if self.db_ok:
            try:
                gid = save_grid(self.grid, self.rows, self.cols)
                save_result(gid, path is not None, path, steps, duration_ms)
            except Exception:
                pass


# ─────────────────────────────────────────────
#  ТОЧКА ВХОДА
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    LeeApp(root)
    root.mainloop()
