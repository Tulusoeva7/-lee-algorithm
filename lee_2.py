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
CELL_SIZE    = 22

# ─────────────────────────────────────────────
#  ЦВЕТА
# ─────────────────────────────────────────────
COLOR_START = "#2ecc71"
COLOR_END   = "#e74c3c"
COLOR_WAVE  = "#d6eaf8"
COLOR_PATH  = "#e74c3c"
COLOR_GRID  = "#dfe6e9"
COLOR_BG    = "#f0f3f4"

SURFACES = {
    "empty": ("#ffffff", 1.0,  "Обычная земля"),
    "road":  ("#a9dfbf", 0.5,  "Дорога  ×0.5"),
    "swamp": ("#aed6f1", 2.0,  "Болото  ×2.0"),
    "sand":  ("#fdebd0", 1.5,  "Песок   ×1.5"),
    "wall":  ("#2c3e50", None, "Стена"),
}

# ─────────────────────────────────────────────
#  ШАГИ
# ─────────────────────────────────────────────
DIRS_STRAIGHT = [(-1,0),(1,0),(0,-1),(0,1)]
DIRS_DIAGONAL = [(-1,-1),(-1,1),(1,-1),(1,1)]
DIRS_KNIGHT   = [(-2,-1),(-2,1),(2,-1),(2,1),
                 (-1,-2),(-1,2),(1,-2),(1,2)]

KNIGHT_BLOCKERS = {
    (-2,-1):[(-1,0),(-1,-1)], (-2, 1):[(-1,0),(-1, 1)],
    ( 2,-1):[( 1,0),( 1,-1)], ( 2, 1):[( 1,0),( 1, 1)],
    (-1,-2):[(0,-1),(-1,-1)], (-1, 2):[(0, 1),(-1, 1)],
    ( 1,-2):[(0,-1),( 1,-1)], ( 1, 2):[(0, 1),( 1, 1)],
}

# ─────────────────────────────────────────────
#  БАЗА ДАННЫХ
# ─────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS grids (
        id SERIAL PRIMARY KEY,
        rows INTEGER NOT NULL,
        cols INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS cells (
        id SERIAL PRIMARY KEY,
        grid_id INTEGER REFERENCES grids(id) ON DELETE CASCADE,
        row INTEGER NOT NULL,
        col INTEGER NOT NULL,
        cell_type VARCHAR(20) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS path_results (
        id SERIAL PRIMARY KEY,
        grid_id INTEGER REFERENCES grids(id) ON DELETE CASCADE,
        found BOOLEAN NOT NULL,
        path_length REAL,
        path_cells TEXT,
        steps_count INTEGER,
        duration_ms REAL,
        saved_at TIMESTAMP DEFAULT NOW()
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

def save_grid(grid, rows, cols):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO grids (rows, cols) VALUES (%s,%s) RETURNING id", (rows, cols))
            grid_id = cur.fetchone()[0]
            data = [(grid_id, r, c, grid[r][c])
                    for r in range(rows) for c in range(cols)
                    if grid[r][c] != "empty"]
            if data:
                cur.executemany(
                    "INSERT INTO cells (grid_id,row,col,cell_type) VALUES (%s,%s,%s,%s)", data)
        conn.commit()
    return grid_id

def save_result(grid_id, found, path, steps, duration_ms):
    path_length = _path_cost(path) if found and path else None
    path_str    = ";".join(f"{r},{c}" for r,c in path) if path else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO path_results (grid_id,found,path_length,path_cells,steps_count,duration_ms) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (grid_id, found, path_length, path_str, steps, duration_ms))
        conn.commit()

def _path_cost(path):
    total = 0.0
    for i in range(1, len(path)):
        dr = abs(path[i][0]-path[i-1][0])
        dc = abs(path[i][1]-path[i-1][1])
        d  = dr+dc
        total += 1.0 if d==1 else (math.sqrt(2) if d==2 else math.sqrt(5))
    return round(total, 4)

# ─────────────────────────────────────────────
#  АЛГОРИТМ ЛИ
# ─────────────────────────────────────────────
def lee(grid, rows, cols, start, end, use_straight, use_diag, use_knight):
    INF  = float("inf")
    dist = [[INF]*cols for _ in range(rows)]
    prev = [[None]*cols for _ in range(rows)]
    dist[start[0]][start[1]] = 0
    queue = deque([start])
    wave_order, steps = [], 0

    while queue:
        r, c = queue.popleft()
        wave_order.append((r,c))
        steps += 1
        if (r,c) == end:
            break

        neighbours = []
        if use_straight:
            for dr,dc in DIRS_STRAIGHT: neighbours.append((dr,dc,1.0))
        if use_diag:
            for dr,dc in DIRS_DIAGONAL: neighbours.append((dr,dc,math.sqrt(2)))
        if use_knight:
            for dr,dc in DIRS_KNIGHT:   neighbours.append((dr,dc,math.sqrt(5)))

        for dr, dc, base_cost in neighbours:
            nr, nc = r+dr, c+dc
            if not (0<=nr<rows and 0<=nc<cols): continue
            cell = grid[nr][nc]
            if cell == "wall": continue
            if base_cost == math.sqrt(5):
                if any(grid[r+br][c+bc]=="wall"
                       for br,bc in KNIGHT_BLOCKERS.get((dr,dc),[])
                       if 0<=r+br<rows and 0<=c+bc<cols):
                    continue
            surf = SURFACES.get(cell, SURFACES["empty"])[1] or 1.0
            nd   = dist[r][c] + base_cost * surf
            if nd < dist[nr][nc]:
                dist[nr][nc] = nd
                prev[nr][nc] = (r,c)
                queue.append((nr,nc))

    if dist[end[0]][end[1]] == INF:
        return None, wave_order, steps

    path, cur = [], end
    while cur:
        path.append(cur); cur = prev[cur[0]][cur[1]]
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
        self.root.configure(bg=COLOR_BG)

        self.rows  = DEFAULT_ROWS
        self.cols  = DEFAULT_COLS
        self.grid  = [["empty"]*self.cols for _ in range(self.rows)]
        self.start = None
        self.end   = None

        self.use_straight = tk.BooleanVar(value=True)
        self.use_diag     = tk.BooleanVar(value=True)
        self.use_knight   = tk.BooleanVar(value=True)
        self.anim_speed   = tk.IntVar(value=6)
        self.mode_var     = tk.StringVar(value="wall")

        self._build_ui()
        self._draw_grid()

        try:
            init_db()
            self.db_ok = True
        except Exception as e:
            self.db_ok = False
            messagebox.showwarning("БД недоступна",
                f"PostgreSQL не подключён:\n{e}\n\nПрограмма работает без сохранения.")

    def _build_ui(self):
        # ── левая панель со скроллом ──────────────
        outer = tk.Frame(self.root, bg=COLOR_BG, width=250)
        outer.pack(side=tk.LEFT, fill=tk.Y)
        outer.pack_propagate(False)

        # canvas + scrollbar для прокрутки панели
        panel_canvas = tk.Canvas(outer, bg=COLOR_BG,
                                 highlightthickness=0, width=240)
        scrollbar = tk.Scrollbar(outer, orient="vertical",
                                 command=panel_canvas.yview)
        panel_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        panel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ctrl = tk.Frame(panel_canvas, bg=COLOR_BG, padx=12)
        ctrl_window = panel_canvas.create_window((0,0), window=ctrl, anchor="nw")

        def _on_frame_configure(e):
            panel_canvas.configure(scrollregion=panel_canvas.bbox("all"))
        ctrl.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(e):
            panel_canvas.itemconfig(ctrl_window, width=e.width)
        panel_canvas.bind("<Configure>", _on_canvas_configure)

        # прокрутка колёсиком мыши
        def _on_mousewheel(e):
            panel_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        panel_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── заголовок ──
        tk.Label(ctrl, text="Алгоритм Ли",
                 font=("Arial", 16, "bold"),
                 bg=COLOR_BG, fg="#2c3e50").pack(pady=(12,2))
        tk.Label(ctrl, text="Поиск кратчайшего пути в сетке",
                 font=("Arial", 9), bg=COLOR_BG, fg="#7f8c8d").pack(pady=(0,8))

        def section(text):
            tk.Frame(ctrl, bg="#bdc3c7", height=1).pack(fill="x", pady=(8,4))
            tk.Label(ctrl, text=text, bg=COLOR_BG,
                     font=("Arial", 11, "bold"), fg="#2c3e50").pack(anchor="w")

        # ── инструменты ──
        section("🖌  Инструмент")
        tools = [
            ("wall",  "#2c3e50", "🧱 Стена"),
            ("swamp", "#aed6f1", "🌿 Болото  ×2.0"),
            ("road",  "#a9dfbf", "🛤  Дорога  ×0.5"),
            ("sand",  "#fdebd0", "🏜  Песок   ×1.5"),
            ("start", COLOR_START, "🟢 Старт"),
            ("end",   COLOR_END,   "🔴 Финиш"),
            ("erase", "#ecf0f1",   "🧹 Ластик"),
        ]
        for val, color, label in tools:
            row = tk.Frame(ctrl, bg=COLOR_BG)
            row.pack(fill="x", pady=2)
            tk.Radiobutton(row, variable=self.mode_var, value=val,
                           bg=COLOR_BG, activebackground=COLOR_BG).pack(side="left")
            tk.Label(row, bg=color, width=2, height=1,
                     relief="solid", bd=1).pack(side="left", padx=5)
            tk.Label(row, text=label, bg=COLOR_BG,
                     font=("Arial", 11), fg="#2c3e50").pack(side="left")

        # ── типы шагов ──
        section("👣  Типы шагов")
        for var, label in [
            (self.use_straight, "↔  Прямые       (стоимость ×1)"),
            (self.use_diag,     "↗  Диагональ  (стоимость ×√2)"),
            (self.use_knight,   "♞  Конём        (стоимость ×√5)"),
        ]:
            tk.Checkbutton(ctrl, text=label, variable=var,
                           bg=COLOR_BG, font=("Arial", 10),
                           activebackground=COLOR_BG,
                           fg="#2c3e50").pack(anchor="w", pady=1)

        # ── скорость ──
        section("⚡  Скорость анимации")
        spd = tk.Frame(ctrl, bg=COLOR_BG)
        spd.pack(fill="x", pady=2)
        tk.Label(spd, text="Медленно", bg=COLOR_BG,
                 font=("Arial", 8), fg="#95a5a6").pack(side="left")
        tk.Scale(spd, from_=1, to=10, orient="horizontal",
                 variable=self.anim_speed, bg=COLOR_BG,
                 showvalue=False, highlightthickness=0,
                 troughcolor="#bdc3c7").pack(side="left", fill="x", expand=True)
        tk.Label(spd, text="Быстро", bg=COLOR_BG,
                 font=("Arial", 8), fg="#95a5a6").pack(side="left")

        # ── кнопки ──
        section("")
        btns = [
            ("▶  Найти путь",        "#27ae60", self._run),
            ("🔀  Случайная карта",  "#8e44ad", self._random_map),
            ("🗑  Очистить всё",     "#e74c3c", self._clear_all),
            ("💾  Сохранить в БД",   "#2980b9", self._save_to_db),
        ]
        for text, bg, cmd in btns:
            tk.Button(ctrl, text=text, bg=bg, fg="#ffffff",
                      font=("Arial", 11, "bold"),
                      relief="flat", bd=0, pady=7,
                      activebackground=bg, activeforeground="#ffffff",
                      cursor="hand2", command=cmd).pack(fill="x", pady=3)

        # ── результат ──
        section("📊  Результат")
        self.status_var = tk.StringVar(
            value="Поставь старт и финиш,\nзатем нажми «Найти путь»")
        tk.Label(ctrl, textvariable=self.status_var,
                 bg=COLOR_BG, wraplength=215,
                 justify="left", fg="#2c3e50",
                 font=("Arial", 10)).pack(anchor="w", pady=4)

        # ── легенда ──
        section("🗺  Легенда")
        legend = [
            (COLOR_START,          "Старт"),
            (COLOR_END,            "Финиш"),
            (SURFACES["wall"][0],  "Стена — непроходима"),
            (SURFACES["swamp"][0], "Болото — стоимость ×2"),
            (SURFACES["road"][0],  "Дорога — стоимость ×0.5"),
            (SURFACES["sand"][0],  "Песок — стоимость ×1.5"),
            (SURFACES["empty"][0], "Обычная — стоимость ×1"),
            (COLOR_WAVE,           "Волна поиска"),
            (COLOR_PATH,           "Найденный путь"),
        ]
        for color, label in legend:
            f = tk.Frame(ctrl, bg=COLOR_BG)
            f.pack(anchor="w", pady=2)
            tk.Label(f, bg=color, width=3, height=1,
                     relief="solid", bd=1).pack(side="left", padx=(0,8))
            tk.Label(f, text=label, bg=COLOR_BG,
                     font=("Arial", 9), fg="#2c3e50").pack(side="left")

        tk.Frame(ctrl, bg=COLOR_BG, height=20).pack()  # отступ снизу

        # ── канвас сетки ──
        cw = self.cols * CELL_SIZE + 1
        ch = self.rows * CELL_SIZE + 1
        canvas_frame = tk.Frame(self.root, bd=2, relief="groove", bg="#bdc3c7")
        canvas_frame.pack(side=tk.LEFT, padx=10, pady=10)
        self.canvas = tk.Canvas(canvas_frame, width=cw, height=ch,
                                bg=COLOR_GRID, cursor="crosshair",
                                highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>",  self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)

    # ── отрисовка ─────────────────────────────
    def _draw_grid(self):
        self.canvas.delete("all")
        self.rects = {}
        for r in range(self.rows):
            for c in range(self.cols):
                x1, y1 = c*CELL_SIZE, r*CELL_SIZE
                rect = self.canvas.create_rectangle(
                    x1, y1, x1+CELL_SIZE, y1+CELL_SIZE,
                    fill=self._cell_color(r,c), outline=COLOR_GRID, width=1)
                self.rects[(r,c)] = rect

    def _cell_color(self, r, c):
        if (r,c) == self.start: return COLOR_START
        if (r,c) == self.end:   return COLOR_END
        ct = self.grid[r][c]
        if ct == "wave": return COLOR_WAVE
        if ct == "path": return COLOR_PATH
        return SURFACES.get(ct, SURFACES["empty"])[0]

    def _update_cell(self, r, c):
        self.canvas.itemconfig(self.rects[(r,c)], fill=self._cell_color(r,c))

    # ── мышь ──────────────────────────────────
    def _on_click(self, e):
        r, c = e.y//CELL_SIZE, e.x//CELL_SIZE
        if 0<=r<self.rows and 0<=c<self.cols: self._apply_tool(r,c)

    def _on_drag(self, e):
        r, c = e.y//CELL_SIZE, e.x//CELL_SIZE
        if 0<=r<self.rows and 0<=c<self.cols: self._apply_tool(r,c)

    def _apply_tool(self, r, c):
        mode = self.mode_var.get()
        if mode == "start":
            old, self.start = self.start, (r,c)
            self.grid[r][c] = "empty"
            if old: self._update_cell(*old)
            self._update_cell(r,c)
        elif mode == "end":
            old, self.end = self.end, (r,c)
            self.grid[r][c] = "empty"
            if old: self._update_cell(*old)
            self._update_cell(r,c)
        elif mode == "erase":
            self.grid[r][c] = "empty"
            if (r,c)==self.start: self.start=None
            if (r,c)==self.end:   self.end=None
            self._update_cell(r,c)
        else:
            if (r,c) not in (self.start, self.end):
                self.grid[r][c] = mode
                self._update_cell(r,c)

    # ── кнопки ────────────────────────────────
    def _clear_all(self):
        self.start = self.end = None
        self.grid  = [["empty"]*self.cols for _ in range(self.rows)]
        self._draw_grid()
        self.status_var.set("Поставь старт и финиш,\nзатем нажми «Найти путь»")

    def _random_map(self):
        import random
        self._clear_all()
        pool = ["wall","wall","wall","swamp","swamp","road","sand"]
        for r in range(self.rows):
            for c in range(self.cols):
                if random.random() < 0.30:
                    self.grid[r][c] = random.choice(pool)
                    self._update_cell(r,c)
        self.status_var.set("Случайная карта готова.\nПоставь старт и финиш.")

    def _save_to_db(self):
        if not self.db_ok:
            messagebox.showwarning("БД", "PostgreSQL недоступен"); return
        try:
            gid = save_grid(self.grid, self.rows, self.cols)
            self.status_var.set(f"✅ Сохранено в БД\nID сетки: {gid}")
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e))

    # ── алгоритм ──────────────────────────────
    def _run(self):
        if not self.start or not self.end:
            messagebox.showinfo("Внимание", "Поставь старт 🟢 и финиш 🔴!"); return

        # сброс предыдущего запуска
        self.canvas.delete("path_marker")
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] in ("wave","path"):
                    self.grid[r][c] = "empty"
                    self._update_cell(r,c)

        self.status_var.set("🔍 Ищу путь…")
        self.root.update()

        t0 = time.time()
        path, wave_order, steps = lee(
            self.grid, self.rows, self.cols, self.start, self.end,
            self.use_straight.get(), self.use_diag.get(), self.use_knight.get())
        duration_ms = (time.time()-t0)*1000

        # анимация волны
        delay = max(1, 11-self.anim_speed.get())
        skip  = max(1, len(wave_order)//400)
        for i,(r,c) in enumerate(wave_order):
            if (r,c) in (self.start, self.end): continue
            if self.grid[r][c] == "empty":
                self.grid[r][c] = "wave"
                self._update_cell(r,c)
            if i%skip==0:
                self.root.update()
                self.root.after(delay)

        # рисуем путь — яркие квадраты поверх
        if path:
            for r,c in path:
                if (r,c) in (self.start, self.end): continue
                self.grid[r][c] = "path"
                x1 = c*CELL_SIZE + 3
                y1 = r*CELL_SIZE + 3
                x2 = x1 + CELL_SIZE - 6
                y2 = y1 + CELL_SIZE - 6
                self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill="#e74c3c", outline="#c0392b",
                    width=2, tags="path_marker")

            cost = _path_cost(path)
            self.status_var.set(
                f"✅ Путь найден!\n"
                f"─────────────────\n"
                f"📏 Длина:  {cost:.3f}\n"
                f"🔲 Клеток в пути: {len(path)}\n"
                f"🔍 Проверено: {steps}\n"
                f"⏱ Время: {duration_ms:.1f} мс"
            )
        else:
            self.status_var.set(
                "❌ Путь не найден!\n"
                "Попробуй убрать часть стен\n"
                "или включить другие типы шагов.")

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
