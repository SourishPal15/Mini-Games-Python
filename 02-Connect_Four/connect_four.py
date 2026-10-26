import json
import math
import os
import random
import sys
import threading
import time
from array import array

try:
    import pygame
except ImportError:
    print("Pygame is not installed. Install it with: py -m pip install pygame")
    sys.exit(1)

WIDTH, HEIGHT = 1000, 720
FPS = 60
ROWS, COLS = 6, 7
CELL = 76
PAD = 20
HOLE_R = 32
DISC_R = 33
GRAVITY = 2600.0
FADE_TIME = 0.16
BOARD_RECT = pygame.Rect((WIDTH - (COLS * CELL + 2 * PAD)) // 2, 200, COLS * CELL + 2 * PAD, ROWS * CELL + 2 * PAD)
DROP_Y = BOARD_RECT.y - 42
try:
    DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connect4_data.json")
except NameError:
    DATA_PATH = os.path.join(os.getcwd(), "connect4_data.json")

WHITE = (244, 247, 255)
MUTED = (158, 170, 210)
GOLD = (255, 214, 80)
PANEL = (24, 32, 74)
PANEL_EDGE = (70, 92, 170)
PLAYER_COLOR = {1: (228, 54, 66), 2: (250, 204, 38)}
PLAYER_COLOR_NAME = {1: "Red", 2: "Yellow"}
BUTTON_COLORS = {
    "normal": ((48, 64, 132), (78, 108, 206)),
    "primary": ((36, 150, 96), (58, 198, 128)),
    "danger": ((184, 54, 68), (230, 84, 98)),
}
DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_TEXT = {
    "easy": "Mostly random, with the occasional smart move.",
    "medium": "Takes wins, blocks threats and avoids blunders.",
    "hard": "Searches many moves ahead with minimax.",
}
MODE_TEXT = {"pvp": "Player vs Player", "pvc": "Player vs Computer"}
DEMO_MENU = [3, 2, 3, 2, 3, 4, 3]
DEMO_HOW = [0, 1, 1, 2, 3, 2, 2, 3, 4, 3, 3]

DEFAULT_SETTINGS = {
    "master": 0.8,
    "sfx": 0.8,
    "music": 0.5,
    "sfx_on": True,
    "music_on": True,
    "fullscreen": False,
    "animations": True,
    "mode": "pvp",
    "difficulty": "medium",
    "color": 1,
}

A = None


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)), int(lerp(c1[2], c2[2], t)))


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    return "%02d:%02d" % (m, s)


def col_x(c):
    return BOARD_RECT.x + PAD + CELL // 2 + c * CELL


def row_y(r):
    return BOARD_RECT.y + PAD + CELL // 2 + r * CELL


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean_settings(data):
    out = dict(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return out
    for key in ("master", "sfx", "music"):
        v = data.get(key)
        if is_number(v):
            out[key] = clamp(float(v), 0.0, 1.0)
    for key in ("sfx_on", "music_on", "fullscreen", "animations"):
        v = data.get(key)
        if isinstance(v, bool):
            out[key] = v
    if data.get("mode") in MODE_TEXT:
        out["mode"] = data["mode"]
    if data.get("difficulty") in DIFFICULTIES:
        out["difficulty"] = data["difficulty"]
    if data.get("color") in (1, 2) and not isinstance(data.get("color"), bool):
        out["color"] = data["color"]
    return out


class Stats:
    INT_KEYS = ("games", "p1_wins", "p2_wins", "human_wins", "computer_wins", "draws", "total_moves")

    def __init__(self, data=None):
        self.reset()
        if isinstance(data, dict):
            self.load(data)

    def reset(self):
        for key in self.INT_KEYS:
            setattr(self, key, 0)
        self.total_time = 0.0
        self.diff_games = {"easy": 0, "medium": 0, "hard": 0}

    def load(self, data):
        for key in self.INT_KEYS:
            v = data.get(key)
            if is_number(v) and v >= 0:
                setattr(self, key, int(v))
        v = data.get("total_time")
        if is_number(v) and v >= 0:
            self.total_time = float(v)
        dg = data.get("diff_games")
        if isinstance(dg, dict):
            for key in DIFFICULTIES:
                v = dg.get(key)
                if is_number(v) and v >= 0:
                    self.diff_games[key] = int(v)

    def to_dict(self):
        out = {key: getattr(self, key) for key in self.INT_KEYS}
        out["total_time"] = round(self.total_time, 2)
        out["diff_games"] = dict(self.diff_games)
        return out

    def record(self, mode, diff, winner, human, duration, moves):
        self.games += 1
        self.total_time += duration
        self.total_moves += moves
        if mode == "pvc" and diff in self.diff_games:
            self.diff_games[diff] += 1
        if winner == 0:
            self.draws += 1
        elif mode == "pvp":
            if winner == 1:
                self.p1_wins += 1
            else:
                self.p2_wins += 1
        elif winner == human:
            self.human_wins += 1
        else:
            self.computer_wins += 1

    def average(self):
        return self.total_time / self.games if self.games else 0.0


class Storage:
    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, settings, stats):
        payload = {"settings": settings, "stats": stats.to_dict()}
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.path)
        except (OSError, TypeError, ValueError):
            pass


class Board:
    def __init__(self):
        self.grid = [[0] * COLS for _ in range(ROWS)]

    def drop_row(self, c):
        if not isinstance(c, int) or not 0 <= c < COLS:
            return None
        for r in range(ROWS - 1, -1, -1):
            if self.grid[r][c] == 0:
                return r
        return None

    def place(self, c, p):
        r = self.drop_row(c)
        if r is None:
            return None
        self.grid[r][c] = p
        return r

    def full(self):
        return all(self.grid[0][c] != 0 for c in range(COLS))

    def check_win(self, r, c, p):
        cells = set()
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            line = [(r, c)]
            for sign in (1, -1):
                rr, cc = r + dr * sign, c + dc * sign
                while 0 <= rr < ROWS and 0 <= cc < COLS and self.grid[rr][cc] == p:
                    line.append((rr, cc))
                    rr += dr * sign
                    cc += dc * sign
            if len(line) >= 4:
                cells.update(line)
        return sorted(cells)


def build_windows():
    wins = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                er, ec = r + 3 * dr, c + 3 * dc
                if 0 <= er < ROWS and 0 <= ec < COLS:
                    wins.append(tuple((r + i * dr) * COLS + c + i * dc for i in range(4)))
    return wins


WINDOWS = build_windows()
CELL_WINDOWS = [[w for w in WINDOWS if idx in w] for idx in range(ROWS * COLS)]
ORDER = [3, 2, 4, 1, 5, 0, 6]
INF = 10 ** 9
WIN_SCORE = 100000


class Timeout(Exception):
    pass


class Engine:
    def __init__(self, grid, me, limit=1.0, max_depth=8):
        self.g = [v for row in grid for v in row]
        self.h = [sum(1 for r in range(ROWS) if self.g[r * COLS + c]) for c in range(COLS)]
        self.count = sum(self.h)
        self.me = me
        self.max_depth = max_depth
        self.deadline = time.perf_counter() + limit
        self.nodes = 0

    def legal(self):
        return [c for c in ORDER if self.h[c] < ROWS]

    def place(self, c, p):
        idx = (ROWS - 1 - self.h[c]) * COLS + c
        self.g[idx] = p
        self.h[c] += 1
        self.count += 1
        return idx

    def undo(self, c):
        self.h[c] -= 1
        self.count -= 1
        self.g[(ROWS - 1 - self.h[c]) * COLS + c] = 0

    def wins_at(self, idx, p):
        g = self.g
        for w in CELL_WINDOWS[idx]:
            if g[w[0]] == p and g[w[1]] == p and g[w[2]] == p and g[w[3]] == p:
                return True
        return False

    def find_win(self, p):
        for c in self.legal():
            idx = self.place(c, p)
            won = self.wins_at(idx, p)
            self.undo(c)
            if won:
                return c
        return None

    def playable(self, i):
        return i >= (ROWS - 1) * COLS or self.g[i + COLS] != 0

    def evaluate(self, p):
        g = self.g
        o = 3 - p
        score = 0
        for r in range(ROWS):
            v = g[r * COLS + 3]
            if v == p:
                score += 4
            elif v == o:
                score -= 4
        for w in WINDOWS:
            mine = theirs = 0
            empty = -1
            for i in w:
                v = g[i]
                if v == p:
                    mine += 1
                elif v == o:
                    theirs += 1
                else:
                    empty = i
            if mine and theirs:
                continue
            if mine == 3:
                score += 45 if self.playable(empty) else 14
            elif mine == 2:
                score += 4
            elif theirs == 3:
                score -= 50 if self.playable(empty) else 16
            elif theirs == 2:
                score -= 4
        return score

    def search(self, depth, alpha, beta, p):
        self.nodes += 1
        if self.nodes & 255 == 0 and time.perf_counter() > self.deadline:
            raise Timeout()
        if self.count == ROWS * COLS:
            return 0
        if depth == 0:
            return self.evaluate(p)
        best = -INF
        for c in ORDER:
            if self.h[c] >= ROWS:
                continue
            idx = self.place(c, p)
            if self.wins_at(idx, p):
                self.undo(c)
                return WIN_SCORE + depth
            v = -self.search(depth - 1, -beta, -alpha, 3 - p)
            self.undo(c)
            if v > best:
                best = v
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return best

    def choose(self):
        legal = self.legal()
        if not legal:
            return None
        me = self.me
        opp = 3 - me
        win = self.find_win(me)
        if win is not None:
            return win
        block = self.find_win(opp)
        if block is not None:
            return block
        best = legal[0]
        try:
            for depth in range(2, self.max_depth + 1):
                order = [best] + [c for c in legal if c != best]
                cur = None
                cur_v = -INF
                alpha = -INF
                for c in order:
                    self.place(c, me)
                    v = -self.search(depth - 1, -INF, -alpha, opp)
                    self.undo(c)
                    if v > cur_v:
                        cur_v = v
                        cur = c
                    if v > alpha:
                        alpha = v
                best = cur
                if cur_v >= WIN_SCORE:
                    break
        except Timeout:
            pass
        return best


def easy_move(grid, me):
    e = Engine(grid, me, 1.0, 1)
    legal = e.legal()
    if not legal:
        return None
    win = e.find_win(me)
    if win is not None and random.random() < 0.55:
        return win
    block = e.find_win(3 - me)
    if block is not None and random.random() < 0.45:
        return block
    weights = [1 + (3 - abs(c - 3)) for c in legal]
    return random.choices(legal, weights)[0]


def medium_move(grid, me):
    e = Engine(grid, me, 1.0, 1)
    legal = e.legal()
    if not legal:
        return None
    opp = 3 - me
    win = e.find_win(me)
    if win is not None:
        return win
    block = e.find_win(opp)
    if block is not None:
        return block
    safe = []
    for c in legal:
        e.place(c, me)
        bad = False
        if e.h[c] < ROWS:
            idx = e.place(c, opp)
            bad = e.wins_at(idx, opp)
            e.undo(c)
        e.undo(c)
        if not bad:
            safe.append(c)
    pool = safe or legal
    best = pool[0]
    best_score = -INF
    for c in pool:
        e.place(c, me)
        score = e.evaluate(me) + random.uniform(0, 8)
        e.undo(c)
        if score > best_score:
            best_score = score
            best = c
    return best


def hard_move(grid, me):
    return Engine(grid, me, 1.1, 9).choose()


def compute_ai(grid, me, difficulty):
    if difficulty == "easy":
        return easy_move(grid, me)
    if difficulty == "medium":
        return medium_move(grid, me)
    return hard_move(grid, me)


WAITING = object()


class AIWorker:
    def __init__(self):
        self.token = 0
        self.result = None
        self.lock = threading.Lock()

    def request(self, grid, me, difficulty):
        with self.lock:
            self.token += 1
            token = self.token
            self.result = None
        snapshot = [row[:] for row in grid]
        thread = threading.Thread(target=self.run, args=(token, snapshot, me, difficulty), daemon=True)
        thread.start()
        return token

    def run(self, token, grid, me, difficulty):
        try:
            col = compute_ai(grid, me, difficulty)
        except Exception:
            legal = [c for c in ORDER if grid[0][c] == 0]
            col = legal[0] if legal else None
        with self.lock:
            if token == self.token:
                self.result = (token, col)

    def take(self, token):
        with self.lock:
            if self.result is not None and self.result[0] == token:
                col = self.result[1]
                self.result = None
                return col
        return WAITING

    def cancel(self):
        with self.lock:
            self.token += 1
            self.result = None


def make_background():
    s = pygame.Surface((WIDTH, HEIGHT))
    top = (10, 15, 40)
    bottom = (32, 38, 90)
    for y in range(HEIGHT):
        pygame.draw.line(s, lerp_color(top, bottom, y / HEIGHT), (0, y), (WIDTH, y))
    return s.convert()


def make_disc(color, radius):
    k = 3
    R = radius * k
    big = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
    dark = lerp_color(color, (0, 0, 0), 0.45)
    light = lerp_color(color, (255, 255, 255), 0.35)
    steps = 22
    for i in range(steps):
        t = i / (steps - 1)
        r = max(1, int(R * (1 - 0.78 * t)))
        off = int(R * 0.22 * t)
        pygame.draw.circle(big, lerp_color(dark, light, t ** 0.8), (R - off, R - off), r)
    pygame.draw.circle(big, lerp_color(color, dark, 0.5), (R, R), int(R * 0.66), max(2, int(R * 0.07)))
    hl = pygame.Surface((int(R * 0.9), int(R * 0.55)), pygame.SRCALPHA)
    pygame.draw.ellipse(hl, (255, 255, 255, 90), hl.get_rect())
    big.blit(hl, (int(R * 0.28), int(R * 0.14)))
    return pygame.transform.smoothscale(big, (radius * 2, radius * 2))


def make_shadow(w, h, radius, spread, alpha):
    s = pygame.Surface((w + 2 * spread, h + 2 * spread), pygame.SRCALPHA)
    for i in range(spread):
        a = int(alpha * ((i + 1) / spread) ** 2)
        rect = pygame.Rect(i, i, w + 2 * (spread - i), h + 2 * (spread - i))
        pygame.draw.rect(s, (0, 0, 0, a), rect, border_radius=radius + spread - i)
    return s


def make_board(cell, pad, corner, hole, rim):
    w = COLS * cell + 2 * pad
    h = ROWS * cell + 2 * pad
    grad = pygame.Surface((w, h))
    top = (50, 118, 245)
    bottom = (22, 56, 168)
    for y in range(h):
        pygame.draw.line(grad, lerp_color(top, bottom, y / h), (0, y), (w, y))
    surf = grad.convert_alpha()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=corner)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    for r in range(ROWS):
        for c in range(COLS):
            cx = pad + cell // 2 + c * cell
            cy = pad + cell // 2 + r * cell
            pygame.draw.circle(surf, (14, 40, 128), (cx, cy), rim)
            pygame.draw.circle(surf, (0, 0, 0, 0), (cx, cy), hole)
    pygame.draw.rect(surf, (128, 178, 255), (0, 0, w, h), 3, border_radius=corner)
    return surf


def make_glow():
    size = DISC_R + 16
    surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
    for i in range(14):
        a = int(230 * (1 - i / 14) ** 2)
        pygame.draw.circle(surf, (255, 255, 255, a), (size, size), DISC_R + 2 + i, 2)
    return surf


def make_flash():
    surf = pygame.Surface((DISC_R * 2, DISC_R * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (255, 255, 255, 255), (DISC_R, DISC_R), DISC_R)
    return surf


class Assets:
    def __init__(self):
        self.fonts = {}
        self.texts = {}
        self.discs = {}
        self.shadows = {}
        self.boards = {}
        self.misc = {}
        self.background = make_background()
        self.glow = make_glow()
        self.flash = make_flash()
        self.dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.dim.fill((4, 6, 20, 160))
        self.black = pygame.Surface((WIDTH, HEIGHT))
        self.black.fill((0, 0, 0))

    def font(self, size, bold=False):
        key = (size, bold)
        f = self.fonts.get(key)
        if f is None:
            try:
                f = pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", size, bold=bold)
            except Exception:
                f = pygame.font.Font(None, int(size * 1.3))
            self.fonts[key] = f
        return f

    def text(self, string, size, color, bold=False):
        key = (string, size, color, bold)
        img = self.texts.get(key)
        if img is None:
            if len(self.texts) > 700:
                self.texts.clear()
            img = self.font(size, bold).render(string, True, color)
            self.texts[key] = img
        return img

    def disc(self, color, radius):
        key = (color, radius)
        d = self.discs.get(key)
        if d is None:
            d = make_disc(color, radius)
            self.discs[key] = d
        return d

    def ghost(self, color):
        key = ("ghost", color)
        d = self.misc.get(key)
        if d is None:
            d = self.disc(color, DISC_R).copy()
            d.set_alpha(95)
            self.misc[key] = d
        return d

    def bgdisc(self, color, radius):
        key = ("bg", color, radius)
        d = self.misc.get(key)
        if d is None:
            d = self.disc(color, radius).copy()
            d.set_alpha(44)
            self.misc[key] = d
        return d

    def shadow(self, w, h, radius, spread, alpha):
        key = (w, h, radius, spread, alpha)
        s = self.shadows.get(key)
        if s is None:
            s = make_shadow(w, h, radius, spread, alpha)
            self.shadows[key] = s
        return s

    def board_surface(self, cell, pad, corner, hole, rim):
        key = (cell, pad, corner, hole, rim)
        s = self.boards.get(key)
        if s is None:
            s = make_board(cell, pad, corner, hole, rim)
            self.boards[key] = s
        return s

    def column(self, kind):
        key = ("column", kind)
        s = self.misc.get(key)
        if s is None:
            s = pygame.Surface((CELL, BOARD_RECT.h - 12), pygame.SRCALPHA)
            color = (255, 70, 70, 255) if kind == "red" else (255, 255, 255, 255)
            pygame.draw.rect(s, color, s.get_rect(), border_radius=18)
            self.misc[key] = s
        return s

    def gloss(self, w, h, radius):
        key = ("gloss", w, h, radius)
        s = self.misc.get(key)
        if s is None:
            s = pygame.Surface((w, max(1, h // 2)), pygame.SRCALPHA)
            pygame.draw.rect(s, (255, 255, 255, 30), s.get_rect(), border_top_left_radius=radius, border_top_right_radius=radius)
            self.misc[key] = s
        return s


def draw_text(surf, string, size, color, pos, anchor="center", bold=False, shadow=False):
    img = A.text(string, size, color, bold)
    rect = img.get_rect(**{anchor: pos})
    if shadow:
        surf.blit(A.text(string, size, (6, 8, 26), bold), rect.move(2, 3))
    surf.blit(img, rect)
    return rect


def draw_panel(surf, rect, fill=PANEL, edge=PANEL_EDGE, width=2, radius=16):
    surf.blit(A.shadow(rect.w, rect.h, radius, 10, 90), (rect.x - 10, rect.y - 10 + 6))
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    pygame.draw.rect(surf, edge, rect, width, border_radius=radius)


def wrap_text(text, font, width):
    lines = []
    cur = ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if font.size(test)[0] <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Audio:
    def __init__(self, settings):
        self.s = settings
        self.ok = False
        self.sounds = {}
        self.channel = None
        self.music_bytes = None
        self.music_started = False
        self.last_volume = -1.0
        self.sr = 44100
        self.channels = 2
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            info = pygame.mixer.get_init()
        except pygame.error:
            return
        if not info or info[1] != -16 or info[2] not in (1, 2):
            return
        self.sr = info[0]
        self.channels = info[2]
        try:
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(1)
            self.channel = pygame.mixer.Channel(0)
            self.build_sfx()
        except pygame.error:
            return
        self.ok = True
        threading.Thread(target=self.build_music, daemon=True).start()

    def pack(self, data, peak):
        top = max(abs(x) for x in data) if data else 0.0
        scale = peak * 32767.0 / top if top > 1e-9 else 0.0
        mono = array("h", [int(x * scale) for x in data])
        if self.channels == 2:
            st = array("h", [0]) * (len(mono) * 2)
            st[0::2] = mono
            st[1::2] = mono
            return st.tobytes()
        return mono.tobytes()

    def tone(self, notes, harm=(1.0,), peak=0.4):
        sr = self.sr
        data = []
        phase = 0.0
        for f0, f1, dur, gain in notes:
            n = int(sr * dur)
            for i in range(n):
                t = i / n
                phase += 6.283185307 * (f0 + (f1 - f0) * t) / sr
                env = min(1.0, i / (sr * 0.005)) * (1 - t) ** 1.2
                v = 0.0
                for k, a in enumerate(harm):
                    v += a * math.sin(phase * (k + 1))
                data.append(v * env * gain)
        return pygame.mixer.Sound(buffer=self.pack(data, peak))

    def build_sfx(self):
        t = self.tone
        self.sounds["hover"] = t([(980, 980, 0.035, 1.0)], peak=0.10)
        self.sounds["click"] = t([(560, 560, 0.04, 1.0), (840, 840, 0.06, 1.0)], peak=0.22)
        self.sounds["drop"] = t([(720, 340, 0.17, 1.0)], (1.0, 0.2), peak=0.26)
        self.sounds["land"] = t([(170, 70, 0.14, 1.0)], (1.0, 0.5, 0.2), peak=0.40)
        self.sounds["invalid"] = t([(210, 150, 0.14, 1.0)], (1.0, 0.0, 0.5, 0.0, 0.25), peak=0.24)
        self.sounds["turn"] = t([(660, 660, 0.05, 1.0), (880, 880, 0.07, 1.0)], peak=0.18)
        self.sounds["win_line"] = t([(523, 523, 0.07, 1.0), (659, 659, 0.07, 1.0), (784, 784, 0.07, 1.0), (1047, 1047, 0.12, 1.0)], (1.0, 0.3), peak=0.30)
        self.sounds["fanfare"] = t([(523, 523, 0.13, 1.0), (523, 523, 0.13, 1.0), (659, 659, 0.13, 1.0), (784, 784, 0.15, 1.0), (1047, 1047, 0.5, 1.0)], (1.0, 0.4, 0.15), peak=0.32)
        self.sounds["draw"] = t([(440, 392, 0.18, 1.0), (330, 247, 0.34, 1.0)], (1.0, 0.2), peak=0.28)
        self.sounds["pause"] = t([(620, 400, 0.11, 1.0)], peak=0.22)
        self.sounds["resume"] = t([(400, 620, 0.11, 1.0)], peak=0.22)
        self.sounds["transition"] = t([(280, 620, 0.1, 1.0)], peak=0.16)

    def build_music(self):
        try:
            sr = self.sr
            step = 0.25
            total = int(sr * step * 32)
            buf = [0.0] * total
            chords = [
                (220.0, 261.63, 329.63),
                (174.61, 220.0, 261.63),
                (261.63, 329.63, 392.0),
                (196.0, 246.94, 293.66),
            ]
            pattern = [0, 1, 2, 1, 0, 1, 2, 1]
            cache = {}

            def wave(freq, dur, decay, harm):
                key = (freq, dur, decay)
                w = cache.get(key)
                if w is None:
                    n = int(sr * dur)
                    w = []
                    for i in range(n):
                        tt = i / n
                        env = min(1.0, i / (sr * 0.012)) * math.exp(-decay * tt)
                        ph = 6.283185307 * freq * i / sr
                        v = 0.0
                        for k, a in enumerate(harm):
                            v += a * math.sin(ph * (k + 1))
                        w.append(v * env)
                    cache[key] = w
                return w

            for ci, chord in enumerate(chords):
                for j in range(8):
                    w = wave(chord[pattern[j]] * 2, 0.6, 4.5, (1.0, 0.25))
                    start = int((ci * 8 + j) * step * sr)
                    for i, v in enumerate(w):
                        buf[(start + i) % total] += v * 0.5
                bass = wave(chord[0] / 2, 2.0, 1.4, (1.0, 0.3))
                start = int(ci * 8 * step * sr)
                for i, v in enumerate(bass):
                    buf[(start + i) % total] += v * 0.7
            self.music_bytes = self.pack(buf, 0.22)
        except Exception:
            self.music_bytes = None

    def play(self, name):
        if not self.ok or not self.s["sfx_on"]:
            return
        snd = self.sounds.get(name)
        vol = self.s["master"] * self.s["sfx"]
        if snd is None or vol <= 0.001:
            return
        try:
            snd.set_volume(vol)
            snd.play()
        except pygame.error:
            pass

    def stop_sfx(self):
        if not self.ok:
            return
        for snd in self.sounds.values():
            try:
                snd.stop()
            except pygame.error:
                pass

    def update(self):
        if not self.ok:
            return
        try:
            if self.music_bytes and not self.music_started:
                snd = pygame.mixer.Sound(buffer=self.music_bytes)
                self.channel.play(snd, loops=-1)
                self.music_started = True
                self.music_bytes = None
                self.last_volume = -1.0
            if self.music_started:
                vol = self.s["master"] * self.s["music"] if self.s["music_on"] else 0.0
                if abs(vol - self.last_volume) > 0.001:
                    self.channel.set_volume(vol)
                    self.last_volume = vol
        except pygame.error:
            self.music_started = True

    def shutdown(self):
        try:
            pygame.mixer.stop()
            pygame.mixer.quit()
        except pygame.error:
            pass


class Particles:
    MAX = 220

    def __init__(self):
        self.items = []

    def clear(self):
        self.items = []

    def burst(self, x, y, colors, n, speed=380.0):
        for _ in range(n):
            if len(self.items) >= self.MAX:
                return
            a = random.uniform(0, 6.2832)
            sp = random.uniform(speed * 0.3, speed)
            life = random.uniform(0.6, 1.3)
            self.items.append([x, y, math.cos(a) * sp, math.sin(a) * sp - 120, life, random.choice(colors), random.uniform(3, 6), 700.0])

    def confetti(self, n, colors):
        for _ in range(n):
            if len(self.items) >= self.MAX:
                return
            self.items.append([random.uniform(0, WIDTH), -8.0, random.uniform(-50, 50), random.uniform(60, 160), random.uniform(1.6, 2.6), random.choice(colors), random.uniform(3, 6), 110.0])

    def update(self, dt):
        keep = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0 or p[1] > HEIGHT + 20:
                continue
            p[3] += p[7] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            keep.append(p)
        self.items = keep

    def draw(self, surf):
        for p in self.items:
            r = max(1, int(p[6] * min(1.0, p[4] / 0.5)))
            pygame.draw.circle(surf, p[5], (int(p[0]), int(p[1])), r)


class MiniBoard:
    def __init__(self, seq, cell):
        self.seq = seq
        self.cell = cell
        self.pad = max(8, cell // 4)
        self.hole = int(cell * 0.42)
        self.reset()

    def reset(self):
        self.board = Board()
        self.index = 0
        self.player = 1
        self.drop = None
        self.wait = 0.8
        self.win = []
        self.hold = 0.0

    def apply(self, col):
        row = self.board.place(col, self.player)
        if row is not None:
            cells = self.board.check_win(row, col, self.player)
            if cells:
                self.win = cells
            self.player = 3 - self.player
        self.index += 1

    def update(self, dt, animate):
        if not animate:
            while not self.win and self.index < len(self.seq):
                self.apply(self.seq[self.index])
            return
        if self.win or self.index >= len(self.seq):
            self.hold += dt
            if self.hold > 2.6:
                self.reset()
            return
        if self.drop:
            d = self.drop
            d["vy"] += 1800.0 * dt
            d["y"] += d["vy"] * dt
            if d["y"] >= d["target"]:
                self.drop = None
                self.apply(d["col"])
                self.wait = 0.55
            return
        self.wait -= dt
        if self.wait <= 0:
            col = self.seq[self.index]
            row = self.board.drop_row(col)
            if row is None:
                self.index += 1
                return
            self.drop = {
                "col": col,
                "player": self.player,
                "y": -float(self.cell),
                "vy": 0.0,
                "target": self.pad + self.cell // 2 + row * self.cell,
            }

    def draw(self, surf, topleft, t, animate):
        x0, y0 = topleft
        cell = self.cell
        pad = self.pad
        board = A.board_surface(cell, pad, 14, self.hole, self.hole + 3)
        w, h = board.get_size()
        surf.blit(A.shadow(w, h, 14, 12, 110), (x0 - 12, y0 - 12 + 8))
        pygame.draw.rect(surf, (12, 16, 40), (x0, y0, w, h), border_radius=14)
        radius = self.hole + 1
        for r in range(ROWS):
            for c in range(COLS):
                v = self.board.grid[r][c]
                if v:
                    surf.blit(A.disc(PLAYER_COLOR[v], radius), (x0 + pad + cell // 2 + c * cell - radius, y0 + pad + cell // 2 + r * cell - radius))
        if self.drop:
            d = self.drop
            surf.blit(A.disc(PLAYER_COLOR[d["player"]], radius), (x0 + pad + cell // 2 + d["col"] * cell - radius, int(y0 + d["y"]) - radius))
        surf.blit(board, (x0, y0))
        if self.win:
            pulse = 0.5 + 0.5 * math.sin(t * 7) if animate else 1.0
            color = lerp_color(GOLD, WHITE, pulse)
            for r, c in self.win:
                pygame.draw.circle(surf, color, (x0 + pad + cell // 2 + c * cell, y0 + pad + cell // 2 + r * cell), self.hole + 2, 3)


class Button:
    def __init__(self, rect, label, action, kind="normal", selected=None, delay=0.0, size=22):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.kind = kind
        self.selected = selected
        self.size = size
        self.hover = 0.0
        self.pressed = False
        self.age = -delay

    def text(self):
        return self.label() if callable(self.label) else self.label

    def update(self, dt, focused):
        self.hover += ((1.0 if focused else 0.0) - self.hover) * min(1.0, dt * 16)
        self.age += dt

    def handle(self, e, app):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.pressed = True
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.pressed:
            self.pressed = False
            if self.rect.collidepoint(e.pos):
                app.audio.play("click")
                self.action()
            return True
        return False

    def draw(self, surf, focused, anim):
        if anim and self.age < 0:
            return
        off = 0
        if anim and self.age < 0.28:
            off = int((1 - ease_out(self.age / 0.28)) * 50)
        rect = self.rect.move(off, 2 if self.pressed else 0).inflate(int(self.hover * 8), int(self.hover * 4))
        base, hov = BUTTON_COLORS[self.kind]
        color = lerp_color(base, hov, self.hover)
        surf.blit(A.shadow(rect.w, rect.h, 14, 8, 90), (rect.x - 8, rect.y - 8 + 5))
        pygame.draw.rect(surf, color, rect, border_radius=14)
        surf.blit(A.gloss(rect.w, rect.h, 14), rect.topleft)
        pygame.draw.rect(surf, lerp_color(color, (255, 255, 255), 0.3), rect, 2, border_radius=14)
        if self.selected and self.selected():
            pygame.draw.rect(surf, GOLD, rect.inflate(6, 6), 3, border_radius=17)
        draw_text(surf, self.text(), self.size, WHITE, rect.center, "center", True)


class Slider:
    def __init__(self, rect, label, get, set_value, on_release=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.get = get
        self.set_value = set_value
        self.on_release = on_release
        self.track = pygame.Rect(self.rect.x + 150, self.rect.centery - 4, self.rect.w - 150 - 64, 8)
        self.drag = False
        self.hover = 0.0
        self.age = 1.0

    def update(self, dt, focused):
        self.hover += ((1.0 if focused else 0.0) - self.hover) * min(1.0, dt * 16)

    def set_from(self, x):
        self.set_value(clamp((x - self.track.x) / self.track.w, 0.0, 1.0))

    def nudge(self, d):
        self.set_value(clamp(self.get() + d, 0.0, 1.0))
        if self.on_release:
            self.on_release()

    def handle(self, e, app):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.drag = True
            self.set_from(e.pos[0])
            return True
        if e.type == pygame.MOUSEMOTION and self.drag:
            self.set_from(e.pos[0])
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            self.drag = False
            if self.on_release:
                self.on_release()
            return True
        return False

    def draw(self, surf, focused, anim):
        r = self.rect
        draw_text(surf, self.label, 20, WHITE, (r.x, r.centery), "midleft")
        tr = self.track
        pygame.draw.rect(surf, (36, 46, 100), tr, border_radius=5)
        v = self.get()
        fill = pygame.Rect(tr.x, tr.y, int(tr.w * v), tr.h)
        if fill.w > 0:
            pygame.draw.rect(surf, (88, 158, 255), fill, border_radius=5)
        kx = tr.x + int(tr.w * v)
        pygame.draw.circle(surf, (10, 14, 40), (kx, tr.centery + 2), 12)
        pygame.draw.circle(surf, WHITE, (kx, tr.centery), 12 if (focused or self.drag) else 10)
        draw_text(surf, "%d%%" % int(round(v * 100)), 18, MUTED, (r.right, r.centery), "midright")
        if focused:
            pygame.draw.rect(surf, (90, 120, 210), r.inflate(14, 0), 2, border_radius=12)


class Match:
    def __init__(self, app):
        self.app = app
        s = app.settings
        self.mode = s["mode"]
        self.diff = s["difficulty"]
        self.human = s["color"] if self.mode == "pvc" else 0
        self.reset()

    def reset(self):
        self.app.worker.cancel()
        self.board = Board()
        self.player = 1
        self.moves = 0
        self.elapsed = 0.0
        self.status = "playing"
        self.winner = 0
        self.win_cells = []
        self.anim = None
        self.pending = None
        self.paused = False
        self.sel = 3
        self.thinking = False
        self.ai_token = 0
        self.ai_timer = 0.0
        self.ai_ready = False
        self.ai_col = None
        self.recorded = False
        self.over_t = 0.0
        self.fanfare_t = None
        self.celebrate = 0.0
        self.flash = {}

    def label(self, p):
        if self.mode == "pvc":
            return "You" if p == self.human else "Computer"
        return "Player %d" % p

    def is_ai_turn(self):
        return self.mode == "pvc" and self.player != self.human

    def can_human_move(self):
        return self.status == "playing" and not self.paused and self.anim is None and not self.is_ai_turn()

    def set_paused(self, value):
        if self.status != "playing" or self.paused == value:
            return
        self.paused = value
        self.app.audio.play("pause" if value else "resume")

    def human_drop(self, col):
        if not self.can_human_move():
            return
        if self.board.drop_row(col) is None:
            self.flash[col] = 0.45
            self.app.audio.play("invalid")
            return
        self.place(col)

    def place(self, col):
        if self.status != "playing" or self.anim is not None:
            return False
        player = self.player
        row = self.board.place(col, player)
        if row is None:
            return False
        self.moves += 1
        cells = self.board.check_win(row, col, player)
        if cells:
            self.pending = ("win", cells)
        elif self.board.full():
            self.pending = ("draw", None)
        else:
            self.pending = None
        self.anim = {"col": col, "row": row, "player": player, "y": float(DROP_Y), "vy": 0.0, "bounces": 0, "target": float(row_y(row))}
        self.app.audio.play("drop")
        if not self.app.settings["animations"]:
            self.app.audio.play("land")
            self.finish_move()
        return True

    def step_anim(self, dt):
        a = self.anim
        a["vy"] += GRAVITY * dt
        a["y"] += a["vy"] * dt
        if a["y"] >= a["target"]:
            a["y"] = a["target"]
            if a["bounces"] == 0:
                self.app.audio.play("land")
            if a["bounces"] < 2 and a["vy"] > 220:
                a["vy"] = -a["vy"] * 0.32
                a["bounces"] += 1
            else:
                self.finish_move()

    def finish_move(self):
        a = self.anim
        self.anim = None
        pending = self.pending
        self.pending = None
        if pending and pending[0] == "win":
            self.status = "won"
            self.winner = a["player"]
            self.win_cells = pending[1]
            self.over_t = 0.0
            self.record()
            self.app.audio.play("win_line")
            self.fanfare_t = 0.4
            self.celebrate = 2.4
            if self.app.settings["animations"]:
                colors = [PLAYER_COLOR[self.winner], WHITE, GOLD]
                for r, c in self.win_cells:
                    self.app.particles.burst(col_x(c), row_y(r), colors, 10)
        elif pending and pending[0] == "draw":
            self.status = "draw"
            self.over_t = 0.0
            self.record()
            self.app.audio.play("draw")
        else:
            self.player = 3 - self.player
            if self.mode == "pvp" or not self.is_ai_turn():
                self.app.audio.play("turn")

    def record(self):
        if self.recorded:
            return
        self.recorded = True
        winner = self.winner if self.status == "won" else 0
        self.app.stats.record(self.mode, self.diff, winner, self.human, self.elapsed, self.moves)
        self.app.save()

    def update(self, dt):
        for key in list(self.flash):
            self.flash[key] -= dt
            if self.flash[key] <= 0:
                del self.flash[key]
        if self.status != "playing":
            self.over_t += dt
            if self.fanfare_t is not None:
                self.fanfare_t -= dt
                if self.fanfare_t <= 0:
                    self.fanfare_t = None
                    self.app.audio.play("fanfare")
            if self.celebrate > 0:
                self.celebrate -= dt
                if self.app.settings["animations"]:
                    self.app.particles.confetti(2, [PLAYER_COLOR[self.winner], WHITE, GOLD, (90, 170, 255)])
            return
        if self.paused:
            return
        self.elapsed += dt
        if self.anim is not None:
            self.step_anim(dt)
            return
        if self.is_ai_turn():
            self.run_ai(dt)

    def run_ai(self, dt):
        worker = self.app.worker
        if not self.thinking:
            self.thinking = True
            self.ai_timer = 0.0
            self.ai_ready = False
            self.ai_col = None
            self.ai_token = worker.request(self.board.grid, self.player, self.diff)
            return
        self.ai_timer += dt
        if not self.ai_ready:
            res = worker.take(self.ai_token)
            if res is not WAITING:
                self.ai_ready = True
                self.ai_col = res
        minimum = {"easy": 0.5, "medium": 0.6, "hard": 0.7}.get(self.diff, 0.6)
        if self.ai_ready and self.ai_timer >= minimum:
            col = self.ai_col
            self.thinking = False
            self.ai_ready = False
            self.ai_col = None
            if col is None or self.board.drop_row(col) is None:
                legal = [c for c in range(COLS) if self.board.drop_row(c) is not None]
                if not legal:
                    return
                col = random.choice(legal)
            self.place(col)


class App:
    def __init__(self):
        global A
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("Connect 4")
        self.store = Storage(DATA_PATH)
        data = self.store.load()
        self.settings = clean_settings(data.get("settings"))
        self.stats = Stats(data.get("stats"))
        self.screen = None
        self.apply_display()
        A = Assets()
        self.audio = Audio(self.settings)
        self.particles = Particles()
        self.worker = AIWorker()
        self.clock = pygame.time.Clock()
        self.state = "menu"
        self.match = None
        self.widgets = []
        self.widget_key = None
        self.focus = -1
        self.modal = None
        self.modal_widgets = []
        self.fade = None
        self.time = 0.0
        self.running = True
        self.block_until = 0.0
        self.last_focus = -1
        self.settings_return = "menu"
        self.menu_demo = MiniBoard(DEMO_MENU, 46)
        self.how_demo = MiniBoard(DEMO_HOW, 40)
        self.bg_discs = []
        for i in range(12):
            self.bg_discs.append({
                "x": random.uniform(0, WIDTH),
                "y": random.uniform(0, HEIGHT),
                "r": random.choice((24, 34, 46, 58)),
                "color": PLAYER_COLOR[1 + i % 2],
                "speed": random.uniform(12, 34),
                "phase": random.uniform(0, 6.28),
            })

    def save(self):
        self.store.save(self.settings, self.stats)

    def apply_display(self):
        flags = pygame.SCALED
        if self.settings["fullscreen"]:
            flags |= pygame.FULLSCREEN
        try:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        except pygame.error:
            self.settings["fullscreen"] = False
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

    def toggle_fullscreen(self):
        self.settings["fullscreen"] = not self.settings["fullscreen"]
        self.apply_display()
        self.save()

    def toggle_sfx(self):
        self.settings["sfx_on"] = not self.settings["sfx_on"]
        if not self.settings["sfx_on"]:
            self.audio.stop_sfx()
        else:
            self.audio.play("click")
        self.save()

    def set_setting(self, key, value):
        self.settings[key] = value

    def cycle_mode(self):
        self.settings["mode"] = "pvc" if self.settings["mode"] == "pvp" else "pvp"
        self.save()

    def cycle_difficulty(self):
        i = DIFFICULTIES.index(self.settings["difficulty"])
        self.settings["difficulty"] = DIFFICULTIES[(i + 1) % 3]
        self.save()

    def cycle_color(self):
        self.settings["color"] = 2 if self.settings["color"] == 1 else 1
        self.save()

    def toggle_animations(self):
        self.settings["animations"] = not self.settings["animations"]
        if not self.settings["animations"]:
            self.particles.clear()
        self.save()

    def toggle_setting(self, key):
        self.settings[key] = not self.settings[key]
        if key == "sfx_on" and not self.settings[key]:
            self.audio.stop_sfx()
        self.save()

    def pick(self, key, value):
        self.settings[key] = value
        self.save()

    def goto(self, state, callback=None):
        if self.fade:
            return
        if not self.settings["animations"]:
            self.switch(state, callback)
            return
        self.fade = {"phase": "out", "t": 0.0, "state": state, "cb": callback}

    def switch(self, state, callback):
        if callback:
            callback()
        self.state = state
        self.modal = None
        self.modal_widgets = []
        self.widget_key = None
        self.focus = -1
        self.audio.play("transition")

    def new_match(self):
        self.match = Match(self)
        self.particles.clear()
        self.block_until = time.perf_counter() + 0.25

    def end_match(self):
        self.worker.cancel()
        self.match = None
        self.particles.clear()

    def start_game(self):
        self.goto("game", self.new_match)

    def go_menu(self):
        self.goto("menu", self.end_match if self.match else None)

    def open_settings(self, ret):
        self.settings_return = ret
        self.goto("settings")

    def close_settings(self):
        self.save()
        self.goto(self.settings_return)

    def restart_now(self):
        self.match.reset()
        self.particles.clear()
        self.block_until = time.perf_counter() + 0.25

    def confirm_restart(self):
        m = self.match
        if m and m.moves > 0 and m.status == "playing":
            self.ask("Restart game?", "The current game will be lost.", self.restart_now)
        elif m:
            self.restart_now()

    def leave_game(self):
        m = self.match
        if m and m.moves > 0 and m.status == "playing":
            self.ask("Return to main menu?", "The current game will be lost.", self.go_menu)
        else:
            self.go_menu()

    def pause_game(self):
        if self.match:
            self.match.set_paused(True)

    def resume_game(self):
        if self.match:
            self.match.set_paused(False)
            self.block_until = time.perf_counter() + 0.25

    def ask(self, title, text, on_yes):
        self.modal = {"title": title, "text": text, "yes": on_yes}
        self.modal_widgets = [
            Button((310, 392, 180, 44), "Yes", lambda: self.answer(True), "danger", size=20),
            Button((510, 392, 180, 44), "No", lambda: self.answer(False), "normal", size=20),
        ]
        self.focus = 1

    def answer(self, yes):
        cb = self.modal["yes"] if self.modal else None
        self.modal = None
        self.modal_widgets = []
        self.focus = -1
        self.block_until = time.perf_counter() + 0.25
        if yes and cb:
            cb()

    def reset_stats(self):
        self.stats.reset()
        self.save()

    def quit_app(self):
        self.running = False

    def overlay(self):
        m = self.match
        if self.state != "game" or not m:
            return None
        if m.paused:
            return "pause"
        if m.status != "playing":
            return "over"
        return None

    def active_widgets(self):
        return self.modal_widgets if self.modal else self.widgets

    def sync_widgets(self):
        key = (self.state, self.overlay())
        if key != self.widget_key:
            self.widget_key = key
            self.widgets = self.build_widgets()
            self.focus = self.hit_index(pygame.mouse.get_pos())

    def hit_index(self, pos):
        for i, w in enumerate(self.active_widgets()):
            if w.rect.collidepoint(pos):
                return i
        return -1

    def build_widgets(self):
        st = self.state
        out = []
        cx = WIDTH // 2

        def btn(x, y, w, h, label, action, kind="normal", selected=None, size=22):
            out.append(Button((x, y, w, h), label, action, kind, selected, delay=len(out) * 0.04, size=size))

        if st == "menu":
            x, w, h = 130, 320, 52
            items = [
                ("Play", self.start_game, "primary"),
                (lambda: "Game Mode: " + ("2 Players" if self.settings["mode"] == "pvp" else "vs Computer"), lambda: self.goto("mode"), "normal"),
                (lambda: "Difficulty: " + self.settings["difficulty"].capitalize(), lambda: self.goto("difficulty"), "normal"),
                ("Statistics", lambda: self.goto("stats"), "normal"),
                ("Settings", lambda: self.open_settings("menu"), "normal"),
                ("How to Play", lambda: self.goto("howto"), "normal"),
                ("Exit", self.quit_app, "danger"),
            ]
            for i, (label, action, kind) in enumerate(items):
                btn(x, 190 + i * 64, w, h, label, action, kind)
        elif st == "mode":
            btn(cx - 190, 190, 380, 56, "Player vs Player", lambda: self.pick("mode", "pvp"), selected=lambda: self.settings["mode"] == "pvp")
            btn(cx - 190, 262, 380, 56, "Player vs Computer", lambda: self.pick("mode", "pvc"), selected=lambda: self.settings["mode"] == "pvc")
            btn(cx - 190, 390, 180, 52, "Play as Red", lambda: self.pick("color", 1), selected=lambda: self.settings["color"] == 1, size=20)
            btn(cx + 10, 390, 180, 52, "Play as Yellow", lambda: self.pick("color", 2), selected=lambda: self.settings["color"] == 2, size=20)
            btn(cx - 120, 540, 240, 52, "Back", lambda: self.goto("menu"))
        elif st == "difficulty":
            for i, d in enumerate(DIFFICULTIES):
                btn(180, 190 + i * 76, 240, 56, d.capitalize(), (lambda dd=d: self.pick("difficulty", dd)), selected=(lambda dd=d: self.settings["difficulty"] == dd))
            btn(cx - 120, 480, 240, 52, "Back", lambda: self.goto("menu"))
        elif st == "stats":
            btn(cx - 260, 590, 240, 52, "Reset Statistics", lambda: self.ask("Reset statistics?", "All recorded results will be erased.", self.reset_stats), "danger")
            btn(cx + 20, 590, 240, 52, "Back", lambda: self.goto("menu"))
        elif st == "howto":
            btn(cx - 120, 630, 240, 50, "Back", lambda: self.goto("menu"))
        elif st == "settings":
            lx, rx, w = 60, 530, 410

            def slider(y, label, key, test):
                out.append(Slider((lx, y, w, 46), label, lambda: self.settings[key], lambda v: self.set_setting(key, v), lambda: self.slider_release(test)))

            slider(160, "Master volume", "master", True)
            slider(222, "Effects volume", "sfx", True)
            slider(284, "Music volume", "music", False)
            btn(lx, 350, w, 46, lambda: "Sound effects: " + ("On" if self.settings["sfx_on"] else "Off"), lambda: self.toggle_setting("sfx_on"), size=20)
            btn(lx, 412, w, 46, lambda: "Background music: " + ("On" if self.settings["music_on"] else "Off"), lambda: self.toggle_setting("music_on"), size=20)
            btn(rx, 160, w, 46, lambda: "Display: " + ("Fullscreen" if self.settings["fullscreen"] else "Windowed"), self.toggle_fullscreen, size=20)
            btn(rx, 222, w, 46, lambda: "Animations: " + ("On" if self.settings["animations"] else "Off"), self.toggle_animations, size=20)
            btn(rx, 330, w, 46, lambda: "Default mode: " + MODE_TEXT[self.settings["mode"]], self.cycle_mode, size=20)
            btn(rx, 392, w, 46, lambda: "Default difficulty: " + self.settings["difficulty"].capitalize(), self.cycle_difficulty, size=20)
            btn(rx, 454, w, 46, lambda: "Your color vs computer: " + PLAYER_COLOR_NAME[self.settings["color"]], self.cycle_color, size=20)
            btn(rx, 516, w, 46, "Reset statistics", lambda: self.ask("Reset statistics?", "All recorded results will be erased.", self.reset_stats), "danger", size=20)
            btn(cx - 120, 630, 240, 50, "Back", self.close_settings)
        elif st == "game":
            ov = self.overlay()
            if ov == "pause":
                x = cx - 130
                btn(x, 262, 260, 52, "Resume", self.resume_game, "primary")
                btn(x, 328, 260, 52, "Restart Game", self.confirm_restart)
                btn(x, 394, 260, 52, "Settings", lambda: self.open_settings("game"))
                btn(x, 460, 260, 52, "Main Menu", self.leave_game, "danger")
            elif ov == "over":
                btn(280, 98, 210, 40, "Play Again", self.restart_now, "primary", size=20)
                btn(510, 98, 210, 40, "Main Menu", self.go_menu, "normal", size=20)
            else:
                x0 = 199
                btn(x0, 14, 140, 40, "Restart", self.confirm_restart, size=18)
                btn(x0 + 154, 14, 140, 40, "Pause", self.pause_game, size=18)
                btn(x0 + 308, 14, 140, 40, lambda: "Sound: " + ("On" if self.settings["sfx_on"] else "Off"), self.toggle_sfx, size=18)
                btn(x0 + 462, 14, 140, 40, "Main Menu", self.leave_game, size=18)
        return out

    def slider_release(self, test):
        self.save()
        if test:
            self.audio.play("land")

    def col_at(self, pos):
        x, y = pos
        left = BOARD_RECT.x + PAD
        if y < 70 or x < left or x >= left + COLS * CELL:
            return None
        return (x - left) // CELL

    def move_focus(self, d):
        widgets = self.active_widgets()
        n = len(widgets)
        if not n:
            return
        if self.focus < 0:
            self.focus = 0 if d > 0 else n - 1
        else:
            self.focus = (self.focus + d) % n
        self.audio.play("hover")

    def activate_focus(self):
        widgets = self.active_widgets()
        if 0 <= self.focus < len(widgets):
            w = widgets[self.focus]
            if isinstance(w, Button):
                self.audio.play("click")
                w.action()
                return True
        return False

    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if self.fade:
            return
        if e.type == pygame.KEYDOWN:
            self.on_key(e)
            return
        if e.type == pygame.MOUSEMOTION:
            idx = self.hit_index(e.pos)
            if idx != self.focus and not any(isinstance(w, Slider) and w.drag for w in self.active_widgets()):
                if idx >= 0:
                    self.audio.play("hover")
                self.focus = idx
            if self.state == "game" and not self.modal and self.overlay() is None:
                col = self.col_at(e.pos)
                if col is not None and self.match:
                    self.match.sel = col
        if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            for w in list(self.active_widgets()):
                if w.handle(e, self):
                    return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.state == "game" and not self.modal and self.overlay() is None and self.match:
                if time.perf_counter() >= self.block_until:
                    col = self.col_at(e.pos)
                    if col is not None:
                        self.match.sel = col
                        self.match.human_drop(col)

    def on_key(self, e):
        k = e.key
        enter = k in (pygame.K_RETURN, pygame.K_KP_ENTER)
        if self.modal:
            if k == pygame.K_y:
                self.answer(True)
            elif k in (pygame.K_n, pygame.K_ESCAPE):
                self.answer(False)
            elif k in (pygame.K_LEFT, pygame.K_UP):
                self.move_focus(-1)
            elif k in (pygame.K_RIGHT, pygame.K_DOWN):
                self.move_focus(1)
            elif enter or k == pygame.K_SPACE:
                self.activate_focus()
            return
        if k == pygame.K_m:
            self.toggle_sfx()
            return
        if self.state == "game":
            self.game_key(k, enter)
            return
        if k == pygame.K_ESCAPE:
            if self.state == "settings":
                self.close_settings()
            elif self.state != "menu":
                self.goto("menu")
            return
        if k == pygame.K_UP:
            self.move_focus(-1)
        elif k == pygame.K_DOWN:
            self.move_focus(1)
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            widgets = self.active_widgets()
            if 0 <= self.focus < len(widgets) and isinstance(widgets[self.focus], Slider):
                widgets[self.focus].nudge(0.05 if k == pygame.K_RIGHT else -0.05)
        elif enter or k == pygame.K_SPACE:
            self.activate_focus()

    def game_key(self, k, enter):
        m = self.match
        if not m:
            return
        ov = self.overlay()
        if ov == "pause":
            if k == pygame.K_ESCAPE:
                self.resume_game()
            elif k == pygame.K_UP:
                self.move_focus(-1)
            elif k == pygame.K_DOWN:
                self.move_focus(1)
            elif enter or k == pygame.K_SPACE:
                if not self.activate_focus():
                    self.resume_game()
            return
        if ov == "over":
            if k == pygame.K_ESCAPE:
                self.go_menu()
            elif (enter or k in (pygame.K_SPACE, pygame.K_r)) and m.over_t > 0.6:
                self.restart_now()
            return
        if k == pygame.K_ESCAPE:
            self.pause_game()
        elif k == pygame.K_LEFT:
            if m.sel > 0:
                m.sel -= 1
                self.audio.play("hover")
        elif k == pygame.K_RIGHT:
            if m.sel < COLS - 1:
                m.sel += 1
                self.audio.play("hover")
        elif enter or k == pygame.K_SPACE:
            if time.perf_counter() >= self.block_until:
                m.human_drop(m.sel)
        elif k == pygame.K_r:
            self.confirm_restart()

    def update(self, dt):
        self.time += dt
        anim = self.settings["animations"]
        self.audio.update()
        if self.fade:
            f = self.fade
            f["t"] += dt
            if f["t"] >= FADE_TIME:
                if f["phase"] == "out":
                    self.switch(f["state"], f["cb"])
                    f["phase"] = "in"
                    f["t"] = 0.0
                else:
                    self.fade = None
        self.sync_widgets()
        for i, w in enumerate(self.active_widgets()):
            w.update(dt, i == self.focus)
        if anim:
            for d in self.bg_discs:
                d["y"] -= d["speed"] * dt
                d["x"] += math.sin(self.time * 0.5 + d["phase"]) * 12 * dt
                if d["y"] < -d["r"] * 2:
                    d["y"] = HEIGHT + d["r"] * 2
                    d["x"] = random.uniform(0, WIDTH)
        if self.state == "menu":
            self.menu_demo.update(dt, anim)
        elif self.state == "howto":
            self.how_demo.update(dt, anim)
        elif self.state == "game" and self.match and not self.modal:
            self.match.update(dt)
        self.particles.update(dt)

    def draw(self):
        s = self.screen
        s.blit(A.background, (0, 0))
        anim = self.settings["animations"]
        for d in self.bg_discs:
            img = A.bgdisc(d["color"], d["r"])
            s.blit(img, (int(d["x"]) - d["r"], int(d["y"]) - d["r"]))
        st = self.state
        if st == "menu":
            self.draw_menu()
        elif st == "mode":
            self.draw_mode()
        elif st == "difficulty":
            self.draw_difficulty()
        elif st == "stats":
            self.draw_stats()
        elif st == "settings":
            self.draw_settings()
        elif st == "howto":
            self.draw_howto()
        elif st == "game" and self.match:
            self.draw_game()
        if not self.modal:
            self.draw_widgets(self.widgets, anim)
        self.particles.draw(s)
        if self.modal:
            self.draw_modal()
        if self.fade:
            f = self.fade
            amount = f["t"] / FADE_TIME
            alpha = amount if f["phase"] == "out" else 1.0 - amount
            A.black.set_alpha(int(255 * clamp(alpha, 0.0, 1.0)))
            s.blit(A.black, (0, 0))
        pygame.display.flip()

    def draw_widgets(self, widgets, anim):
        for i, w in enumerate(widgets):
            w.draw(self.screen, i == self.focus, anim)

    def title(self, text):
        draw_text(self.screen, text, 48, WHITE, (WIDTH // 2, 70), "center", True, True)

    def draw_menu(self):
        s = self.screen
        anim = self.settings["animations"]
        bob = int(math.sin(self.time * 1.6) * 4) if anim else 0
        fw = A.font(84, True).size("CONNECT")[0]
        dd = 96
        x0 = (WIDTH - (fw + 24 + dd)) // 2
        y = 72 + bob
        draw_text(s, "CONNECT", 84, WHITE, (x0, y), "midleft", True, True)
        cx = x0 + fw + 24 + dd // 2
        s.blit(A.disc(PLAYER_COLOR[1], dd // 2), (cx - dd // 2, y - dd // 2))
        draw_text(s, "4", 64, WHITE, (cx, y), "center", True, True)
        draw_text(s, "Drop. Connect. Win.", 22, MUTED, (WIDTH // 2, 134))
        self.menu_demo.draw(s, (557, 250), self.time, anim)

    def draw_mode(self):
        s = self.screen
        self.title("Game Mode")
        text = "Red always moves first." if self.settings["mode"] == "pvp" else "Choose your color. The computer plays the other one."
        draw_text(s, text, 20, MUTED, (WIDTH // 2, 345))
        draw_text(s, "Your color (Player vs Computer)", 18, MUTED, (WIDTH // 2, 372))

    def draw_difficulty(self):
        s = self.screen
        self.title("Difficulty")
        draw_text(s, "Applies to Player vs Computer games.", 20, MUTED, (WIDTH // 2, 125))
        for i, d in enumerate(DIFFICULTIES):
            draw_text(s, DIFFICULTY_TEXT[d], 20, WHITE if self.settings["difficulty"] == d else MUTED, (460, 218 + i * 76), "midleft")

    def draw_stats(self):
        s = self.screen
        self.title("Statistics")
        st = self.stats
        cards = [
            ("Games played", str(st.games)),
            ("Player 1 wins (2-player)", str(st.p1_wins)),
            ("Player 2 wins (2-player)", str(st.p2_wins)),
            ("Human wins vs computer", str(st.human_wins)),
            ("Computer wins vs human", str(st.computer_wins)),
            ("Draws", str(st.draws)),
            ("Total moves played", str(st.total_moves)),
            ("Average game duration", fmt_time(st.average())),
            ("Computer games by level", "E %d  M %d  H %d" % (st.diff_games["easy"], st.diff_games["medium"], st.diff_games["hard"])),
        ]
        for i, (label, value) in enumerate(cards):
            rect = pygame.Rect(60 + (i % 3) * 300, 130 + (i // 3) * 140, 280, 120)
            draw_panel(s, rect)
            draw_text(s, label, 17, MUTED, (rect.centerx, rect.y + 30))
            draw_text(s, value, 34 if len(value) < 12 else 28, WHITE, (rect.centerx, rect.y + 76), "center", True)

    def draw_settings(self):
        s = self.screen
        self.title("Settings")
        for label, x, y in (("AUDIO", 60, 130), ("DISPLAY", 530, 130), ("GAMEPLAY", 530, 300)):
            draw_text(s, label, 18, GOLD, (x, y), "midleft", True)
            pygame.draw.line(s, PANEL_EDGE, (x, y + 16), (x + 410, y + 16), 2)

    def draw_howto(self):
        s = self.screen
        self.title("How to Play")
        sections = [
            ("Objective", "Connect four discs of your color in a row - horizontally, vertically or diagonally - before your opponent does."),
            ("Dropping a disc", "Click a column, or use the Left and Right arrows with Enter or Space. The disc falls to the lowest free slot."),
            ("Game modes", "Player vs Player: two people share this computer, Red goes first. Player vs Computer: pick your color and face the computer."),
            ("Difficulty", "Easy mostly plays randomly. Medium takes wins, blocks threats and avoids blunders. Hard looks many moves ahead with minimax and alpha-beta pruning."),
            ("Controls", "Esc pauses, R restarts (with confirmation), M toggles sound, F11 toggles fullscreen. Settings are in the main menu and the pause menu."),
        ]
        y = 120
        body = A.font(17)
        for head, text in sections:
            draw_text(s, head, 20, GOLD, (60, y), "topleft", True)
            y += 28
            for line in wrap_text(text, body, 540):
                draw_text(s, line, 17, WHITE, (60, y), "topleft")
                y += 22
            y += 12
        self.how_demo.draw(s, (655, 250), self.time, self.settings["animations"])

    def status_info(self):
        m = self.match
        if m.paused:
            return "Paused", WHITE
        if m.status == "won":
            lab = m.label(m.winner)
            return "%s %s!" % (lab, "win" if lab == "You" else "wins"), PLAYER_COLOR[m.winner]
        if m.status == "draw":
            return "It's a draw!", WHITE
        if m.is_ai_turn():
            return "Computer is thinking", PLAYER_COLOR[m.player]
        lab = m.label(m.player)
        turn = "Your turn" if lab == "You" else "%s's turn" % lab
        return "%s (%s)" % (turn, PLAYER_COLOR_NAME[m.player]), PLAYER_COLOR[m.player]

    def draw_card(self, rect, p):
        m = self.match
        s = self.screen
        anim = self.settings["animations"]
        active = m.status == "playing" and m.player == p and not m.paused
        winner = m.status == "won" and m.winner == p
        pc = PLAYER_COLOR[p]
        edge = pc if (active or winner) else PANEL_EDGE
        draw_panel(s, rect, edge=edge, width=3 if (active or winner) else 2)
        if active and anim:
            pulse = 0.5 + 0.5 * math.sin(self.time * 5)
            pygame.draw.circle(s, lerp_color(PANEL, pc, 0.25 + 0.35 * pulse), (rect.centerx, rect.y + 48), 34)
        s.blit(A.disc(pc, 28), (rect.centerx - 28, rect.y + 20))
        draw_text(s, m.label(p), 22, WHITE, (rect.centerx, rect.y + 98), "center", True)
        draw_text(s, PLAYER_COLOR_NAME[p] + " discs", 16, MUTED, (rect.centerx, rect.y + 122))
        tag = ""
        if winner:
            tag = "WINNER"
        elif active:
            tag = "THINKING" if m.is_ai_turn() else "TO MOVE"
        if tag:
            draw_text(s, tag, 16, pc, (rect.centerx, rect.y + 146), "center", True)

    def draw_info_card(self, rect, head, value, size=34):
        draw_panel(self.screen, rect)
        draw_text(self.screen, head, 15, MUTED, (rect.centerx, rect.y + 22), "center", True)
        draw_text(self.screen, value, size, WHITE, (rect.centerx, rect.y + 54), "center", True)

    def draw_game(self):
        s = self.screen
        m = self.match
        t = self.time
        anim = self.settings["animations"]
        left = pygame.Rect(16, 180, 182, 170)
        right = pygame.Rect(802, 180, 182, 170)
        self.draw_card(left, 1)
        self.draw_card(right, 2)
        self.draw_info_card(pygame.Rect(16, 366, 182, 80), "TIME", fmt_time(m.elapsed))
        self.draw_info_card(pygame.Rect(802, 366, 182, 80), "MOVES", str(m.moves))
        mode_rect = pygame.Rect(16, 462, 182, 100)
        draw_panel(s, mode_rect)
        draw_text(s, "GAME MODE", 15, MUTED, (mode_rect.centerx, mode_rect.y + 22), "center", True)
        draw_text(s, MODE_TEXT[m.mode], 17, WHITE, (mode_rect.centerx, mode_rect.y + 52), "center", True)
        if m.mode == "pvc":
            draw_text(s, "Level: " + m.diff.capitalize(), 16, GOLD, (mode_rect.centerx, mode_rect.y + 78))
        keys_rect = pygame.Rect(802, 462, 182, 100)
        draw_panel(s, keys_rect)
        draw_text(s, "CONTROLS", 15, MUTED, (keys_rect.centerx, keys_rect.y + 22), "center", True)
        for i, line in enumerate(("Left / Right: select", "Enter / Space: drop", "Esc: pause")):
            draw_text(s, line, 14, WHITE, (keys_rect.centerx, keys_rect.y + 46 + i * 20))
        ov = self.overlay()
        if ov != "over":
            text, color = self.status_info()
            if m.is_ai_turn() and m.status == "playing" and not m.paused:
                full = A.font(28, True).size("Computer is thinking...")[0]
                dots = "." * (int(t * 3) % 4) if anim else "..."
                draw_text(s, "Computer is thinking" + dots, 28, color, (WIDTH // 2 - full // 2, 98), "midleft", True)
            else:
                draw_text(s, text, 28, color, (WIDTH // 2, 98), "center", True)
        s.blit(A.shadow(BOARD_RECT.w, BOARD_RECT.h, 28, 18, 120), (BOARD_RECT.x - 18, BOARD_RECT.y - 18 + 12))
        pygame.draw.rect(s, (12, 16, 40), BOARD_RECT, border_radius=28)
        a = m.anim
        for r in range(ROWS):
            for c in range(COLS):
                v = m.board.grid[r][c]
                if v and not (a and a["row"] == r and a["col"] == c):
                    s.blit(A.disc(PLAYER_COLOR[v], DISC_R), (col_x(c) - DISC_R, row_y(r) - DISC_R))
        if a:
            s.blit(A.disc(PLAYER_COLOR[a["player"]], DISC_R), (col_x(a["col"]) - DISC_R, int(a["y"]) - DISC_R))
        human_turn = m.can_human_move() and not self.modal
        full_col = False
        if human_turn:
            c = m.sel
            row = m.board.drop_row(c)
            pc = PLAYER_COLOR[m.player]
            if row is not None:
                s.blit(A.ghost(pc), (col_x(c) - DISC_R, row_y(row) - DISC_R))
                bob = int(math.sin(t * 5) * 3) if anim else 0
                s.blit(A.disc(pc, DISC_R), (col_x(c) - DISC_R, DROP_Y - DISC_R + bob))
            else:
                full_col = True
                x = col_x(c)
                pygame.draw.line(s, (255, 90, 90), (x - 14, DROP_Y - 14), (x + 14, DROP_Y + 14), 6)
                pygame.draw.line(s, (255, 90, 90), (x - 14, DROP_Y + 14), (x + 14, DROP_Y - 14), 6)
        elif m.status == "playing" and m.is_ai_turn() and not m.paused:
            for i in range(3):
                bounce = abs(math.sin(t * 5 + i * 0.7)) * 10 if anim else 0
                pygame.draw.circle(s, PLAYER_COLOR[m.player], (WIDTH // 2 - 30 + i * 30, int(DROP_Y - bounce)), 9)
        s.blit(A.board_surface(CELL, PAD, 28, HOLE_R, HOLE_R + 4), BOARD_RECT.topleft)
        if human_turn:
            overlay = A.column("red" if full_col else "white")
            alpha = 40 + (int(14 * math.sin(t * 4)) if anim else 0)
            overlay.set_alpha(alpha)
            s.blit(overlay, (col_x(m.sel) - CELL // 2, BOARD_RECT.y + 6))
        for col, tm in m.flash.items():
            overlay = A.column("red")
            overlay.set_alpha(int(150 * tm / 0.45))
            s.blit(overlay, (col_x(col) - CELL // 2, BOARD_RECT.y + 6))
        if m.status == "won":
            pulse = 0.5 + 0.5 * math.sin(t * 7) if anim else 1.0
            A.glow.set_alpha(int(110 + 145 * pulse))
            A.flash.set_alpha(int(30 + 70 * pulse))
            gw = A.glow.get_width() // 2
            for r, c in m.win_cells:
                s.blit(A.glow, (col_x(c) - gw, row_y(r) - gw))
                s.blit(A.flash, (col_x(c) - DISC_R, row_y(r) - DISC_R))
        if ov == "pause":
            s.blit(A.dim, (0, 0))
            panel = pygame.Rect(WIDTH // 2 - 170, 160, 340, 400)
            draw_panel(s, panel, edge=GOLD, width=3)
            draw_text(s, "PAUSED", 46, WHITE, (WIDTH // 2, 214), "center", True, True)
            draw_text(s, "Time %s - Moves %d" % (fmt_time(m.elapsed), m.moves), 17, MUTED, (WIDTH // 2, 246))
        elif ov == "over":
            self.draw_over_panel()

    def draw_over_panel(self):
        s = self.screen
        m = self.match
        rect = pygame.Rect(250, 8, 500, 140)
        if m.status == "won":
            lab = m.label(m.winner)
            title = "%s %s!" % (lab, "win" if lab == "You" else "wins")
            color = PLAYER_COLOR[m.winner]
            sub = "%s connected four - %d moves - %s" % (PLAYER_COLOR_NAME[m.winner], m.moves, fmt_time(m.elapsed))
            edge = color
        else:
            title = "It's a draw!"
            color = WHITE
            sub = "The board is full - %d moves - %s" % (m.moves, fmt_time(m.elapsed))
            edge = MUTED
        draw_panel(s, rect, edge=edge, width=3)
        if m.status == "won":
            s.blit(A.disc(color, 20), (rect.x + 24, rect.y + 20))
            s.blit(A.disc(color, 20), (rect.right - 64, rect.y + 20))
        draw_text(s, title, 40, color, (rect.centerx, rect.y + 38), "center", True, True)
        draw_text(s, sub, 18, MUTED, (rect.centerx, rect.y + 74))

    def draw_modal(self):
        s = self.screen
        s.blit(A.dim, (0, 0))
        rect = pygame.Rect(280, 250, 440, 210)
        draw_panel(s, rect, edge=GOLD, width=3)
        draw_text(s, self.modal["title"], 28, WHITE, (rect.centerx, rect.y + 42), "center", True)
        for i, line in enumerate(wrap_text(self.modal["text"], A.font(18), 380)):
            draw_text(s, line, 18, MUTED, (rect.centerx, rect.y + 90 + i * 24))
        self.draw_widgets(self.modal_widgets, self.settings["animations"])

    def run(self):
        try:
            while self.running:
                dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
                for e in pygame.event.get():
                    self.handle_event(e)
                self.update(dt)
                self.draw()
        finally:
            self.save()
            self.worker.cancel()
            self.audio.shutdown()
            pygame.quit()


def main():
    App().run()


if __name__ == "__main__":
    main()