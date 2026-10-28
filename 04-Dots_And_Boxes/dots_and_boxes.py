import array
import math
import random
import sys
import threading
import time
from functools import lru_cache

import pygame

BG = (30, 30, 34)
PANEL = (40, 40, 46)
PANEL_LIGHT = (52, 52, 60)
PANEL_HOVER = (68, 68, 80)
BORDER = (72, 72, 84)
BORDER_LIGHT = (160, 160, 178)
TEXT = (236, 236, 242)
MUTED = (146, 146, 158)
DOT_COLOR = (214, 214, 222)
GUIDE = (52, 52, 60)
GUIDE_BRIGHT = (96, 96, 108)
RED = (255, 75, 85)
BLUE = (65, 145, 255)
RED_LIGHT = (255, 140, 148)
BLUE_LIGHT = (130, 188, 255)
RED_DARK = (92, 36, 44)
BLUE_DARK = (28, 56, 98)

PLAYER_COLOR = {1: RED, 2: BLUE}
PLAYER_LIGHT = {1: RED_LIGHT, 2: BLUE_LIGHT}
PLAYER_DARK = {1: RED_DARK, 2: BLUE_DARK}
PLAYER_TAG = {1: "RED", 2: "BLUE"}
BOARD_SIZES = (("Small", 3), ("Medium", 4), ("Large", 5))
LEVELS = (
    ("Easy", "Relaxed play, great for beginners"),
    ("Medium", "Solid tactics, but still makes mistakes"),
    ("Hard", "Deep search with chain strategy"),
)
MIN_WIDTH = 720
MIN_HEIGHT = 540
HARD_TIME_LIMIT = 0.6
HARD_ROLLOUTS = 4
INFINITY = 10 ** 6


def clamp(value, low, high):
    return max(low, min(high, value))


def mix(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def wrap_text(font, text, max_width):
    lines = []
    current = ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class Topology:
    def __init__(self, n):
        self.n = n
        self.box_count = n * n
        self.h_count = (n + 1) * n
        self.line_count = self.h_count + n * (n + 1)
        self.line_boxes = [[] for _ in range(self.line_count)]
        self.line_info = [None] * self.line_count
        self.box_lines = []
        for r in range(n + 1):
            for c in range(n):
                i = r * n + c
                self.line_info[i] = (0, r, c)
                if r > 0:
                    self.line_boxes[i].append((r - 1) * n + c)
                if r < n:
                    self.line_boxes[i].append(r * n + c)
        for r in range(n):
            for c in range(n + 1):
                i = self.h_count + r * (n + 1) + c
                self.line_info[i] = (1, r, c)
                if c > 0:
                    self.line_boxes[i].append(r * n + c - 1)
                if c < n:
                    self.line_boxes[i].append(r * n + c)
        for r in range(n):
            for c in range(n):
                self.box_lines.append(
                    (
                        r * n + c,
                        (r + 1) * n + c,
                        self.h_count + r * (n + 1) + c,
                        self.h_count + r * (n + 1) + c + 1,
                    )
                )


TOPOLOGIES = {}


def get_topology(n):
    if n not in TOPOLOGIES:
        TOPOLOGIES[n] = Topology(n)
    return TOPOLOGIES[n]


class Position:
    def __init__(self, n):
        self.topo = get_topology(n)
        self.drawn = [False] * self.topo.line_count
        self.counts = [0] * self.topo.box_count
        self.mask = 0
        self.remaining = self.topo.box_count

    def clone(self):
        copy = Position.__new__(Position)
        copy.topo = self.topo
        copy.drawn = self.drawn[:]
        copy.counts = self.counts[:]
        copy.mask = self.mask
        copy.remaining = self.remaining
        return copy

    def apply(self, i):
        self.drawn[i] = True
        self.mask |= 1 << i
        done = 0
        for b in self.topo.line_boxes[i]:
            self.counts[b] += 1
            if self.counts[b] == 4:
                done += 1
        self.remaining -= done
        return done

    def undo(self, i, done):
        self.drawn[i] = False
        self.mask &= ~(1 << i)
        for b in self.topo.line_boxes[i]:
            self.counts[b] -= 1
        self.remaining += done

    def free_lines(self):
        return [i for i in range(self.topo.line_count) if not self.drawn[i]]

    def capture_lines(self):
        result = []
        for b in range(self.topo.box_count):
            if self.counts[b] == 3:
                for line in self.topo.box_lines[b]:
                    if not self.drawn[line]:
                        if line not in result:
                            result.append(line)
                        break
        return result

    def is_safe(self, i):
        for b in self.topo.line_boxes[i]:
            if self.counts[b] >= 2:
                return False
        return True

    def sacrifice(self, i):
        total = 0
        for b in self.topo.line_boxes[i]:
            if self.counts[b] == 2:
                total += 1
        return total


class Board(Position):
    def __init__(self, n):
        super().__init__(n)
        self.line_owner = [0] * self.topo.line_count
        self.box_owner = [0] * self.topo.box_count
        self.scores = [0, 0, 0]

    def play(self, i, player):
        self.line_owner[i] = player
        self.apply(i)
        done = []
        for b in self.topo.line_boxes[i]:
            if self.counts[b] == 4:
                self.box_owner[b] = player
                done.append(b)
        self.scores[player] += len(done)
        return done

    def completed(self):
        return self.topo.box_count - self.remaining


@lru_cache(maxsize=None)
def endgame_value(chains, loops):
    if not chains and not loops:
        return 0
    best = -INFINITY
    tried = set()
    for index, size in enumerate(chains):
        if ("c", size) in tried:
            continue
        tried.add(("c", size))
        rest = chains[:index] + chains[index + 1:]
        after = endgame_value(rest, loops)
        if size <= 2:
            value = -size - after
        else:
            value = min(-size - after, 4 - size + after)
        best = max(best, value)
    for index, size in enumerate(loops):
        if ("l", size) in tried:
            continue
        tried.add(("l", size))
        rest = loops[:index] + loops[index + 1:]
        after = endgame_value(chains, rest)
        value = min(-size - after, 8 - size + after)
        best = max(best, value)
    return best


def endgame_eval(pos):
    topo = pos.topo
    counts = pos.counts
    drawn = pos.drawn
    seen = [False] * topo.box_count
    chains = []
    loops = []
    for start in range(topo.box_count):
        if counts[start] != 2 or seen[start]:
            continue
        seen[start] = True
        stack = [start]
        nodes = 0
        links = set()
        while stack:
            x = stack.pop()
            nodes += 1
            for line in topo.box_lines[x]:
                if drawn[line]:
                    continue
                for y in topo.line_boxes[line]:
                    if y != x and counts[y] == 2:
                        links.add(line)
                        if not seen[y]:
                            seen[y] = True
                            stack.append(y)
        if len(links) >= nodes and nodes >= 4:
            loops.append(nodes)
        else:
            chains.append(nodes)
    return endgame_value(tuple(sorted(chains)), tuple(sorted(loops)))


def greedy_gain(pos):
    taken = 0
    trail = []
    while True:
        lines = pos.capture_lines()
        if not lines:
            break
        i = lines[0]
        k = pos.apply(i)
        taken += k
        trail.append((i, k))
    for i, k in reversed(trail):
        pos.undo(i, k)
    return taken


def easy_move(pos, rng):
    captures = pos.capture_lines()
    if captures and rng.random() < 0.92:
        return rng.choice(captures)
    free = pos.free_lines()
    safe = [i for i in free if pos.is_safe(i)]
    if safe and rng.random() < 0.85:
        return rng.choice(safe)
    if not safe and rng.random() < 0.6:
        least = min(pos.sacrifice(i) for i in free)
        return rng.choice([i for i in free if pos.sacrifice(i) == least])
    return rng.choice(free)


def medium_move(pos, rng):
    captures = pos.capture_lines()
    if captures:
        best_gain = -1
        best_lines = []
        for i in captures:
            k = pos.apply(i)
            pos.undo(i, k)
            if k > best_gain:
                best_gain = k
                best_lines = [i]
            elif k == best_gain:
                best_lines.append(i)
        return rng.choice(best_lines)
    free = pos.free_lines()
    scored = []
    for i in free:
        k = pos.apply(i)
        gain = greedy_gain(pos)
        bonus = 0.0
        if gain == 0:
            safe_after = 0
            for j in free:
                if j != i and not pos.drawn[j] and pos.is_safe(j):
                    safe_after += 1
            if safe_after % 2 == 0:
                bonus = 0.3
        pos.undo(i, k)
        scored.append((-gain + bonus + rng.random() * 0.05, i))
    scored.sort(reverse=True)
    if len(scored) > 1 and rng.random() < 0.12:
        return rng.choice(scored[:3])[1]
    return scored[0][1]


class SearchTimeout(Exception):
    pass


class HardSearch:
    def __init__(self, pos, rng, limit):
        self.pos = pos.clone()
        self.rng = rng
        self.deadline = time.perf_counter() + limit
        self.table = {}
        self.nodes = 0

    def candidates(self, depth):
        pos = self.pos
        topo = pos.topo
        captures = pos.capture_lines()
        if captures:
            moves = list(captures)
            if depth > 0:
                for b in range(topo.box_count):
                    if pos.counts[b] != 3:
                        continue
                    missing = None
                    for line in topo.box_lines[b]:
                        if not pos.drawn[line]:
                            missing = line
                            break
                    for other in topo.line_boxes[missing]:
                        if other != b and pos.counts[other] == 2:
                            for line in topo.box_lines[other]:
                                if not pos.drawn[line] and line != missing and line not in moves:
                                    moves.append(line)
            return moves
        free = pos.free_lines()
        safe = [i for i in free if pos.is_safe(i)]
        if not safe:
            return sorted(free, key=pos.sacrifice)
        if len(safe) <= 10:
            small = [i for i in free if i not in safe and pos.sacrifice(i) <= 2]
            return safe + sorted(small, key=pos.sacrifice)
        return safe

    def evaluate(self):
        pos = self.pos
        free = pos.free_lines()
        if not any(pos.is_safe(i) for i in free):
            return endgame_eval(pos)
        total = 0.0
        for _ in range(HARD_ROLLOUTS):
            order = free[:]
            self.rng.shuffle(order)
            applied = []
            for i in order:
                if pos.is_safe(i):
                    pos.apply(i)
                    applied.append(i)
            value = endgame_eval(pos)
            if len(applied) % 2 == 1:
                value = -value
            for i in reversed(applied):
                pos.undo(i, 0)
            total += value
        return total / HARD_ROLLOUTS

    def negamax(self, depth, alpha, beta):
        pos = self.pos
        if pos.remaining == 0:
            return 0
        self.nodes += 1
        if self.nodes % 128 == 0 and time.perf_counter() > self.deadline:
            raise SearchTimeout()
        key = pos.mask
        entry = self.table.get(key)
        if entry is not None and entry[0] >= depth:
            stored_flag, stored_value = entry[1], entry[2]
            if stored_flag == 0:
                return stored_value
            if stored_flag == 1 and stored_value >= beta:
                return stored_value
            if stored_flag == 2 and stored_value <= alpha:
                return stored_value
        if depth <= 0 and not pos.capture_lines():
            return self.evaluate()
        original_alpha = alpha
        best = -INFINITY
        for i in self.candidates(depth):
            k = pos.apply(i)
            if k:
                value = k + self.negamax(depth, alpha - k, beta - k)
            else:
                value = -self.negamax(depth - 1, -beta, -alpha)
            pos.undo(i, k)
            if value > best:
                best = value
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        if best <= original_alpha:
            flag = 2
        elif best >= beta:
            flag = 1
        else:
            flag = 0
        self.table[key] = (depth, flag, best)
        return best

    def search(self):
        pos = self.pos
        captures = set(pos.capture_lines())
        moves = self.candidates(99)
        self.rng.shuffle(moves)
        moves.sort(key=lambda i: -1 if i in captures else pos.sacrifice(i))
        best_move = moves[0]
        free_count = len(pos.free_lines())
        try:
            for depth in range(1, free_count + 1):
                alpha = -INFINITY
                current_best = None
                current_value = -INFINITY
                ordered = [best_move] + [i for i in moves if i != best_move]
                for i in ordered:
                    k = pos.apply(i)
                    if k:
                        value = k + self.negamax(depth, alpha - k, INFINITY - k)
                    else:
                        value = -self.negamax(depth - 1, -INFINITY, -alpha)
                    pos.undo(i, k)
                    if value > current_value:
                        current_value = value
                        current_best = i
                    if current_value > alpha:
                        alpha = current_value
                best_move = current_best
        except SearchTimeout:
            pass
        return best_move


def choose_move(pos, level, rng):
    if level == "Easy":
        return easy_move(pos, rng)
    if level == "Medium":
        return medium_move(pos, rng)
    return HardSearch(pos, rng, HARD_TIME_LIMIT).search()


class Sfx:
    def __init__(self):
        self.enabled = True
        self.ready = False
        self.sounds = {}
        self.rate = 44100
        self.channels = 1
        try:
            info = pygame.mixer.get_init()
            if not info:
                pygame.mixer.init(44100, -16, 1, 512)
                info = pygame.mixer.get_init()
            if info and abs(info[1]) == 16:
                self.rate = info[0]
                self.channels = info[2]
                self.build()
                self.ready = True
        except Exception:
            self.ready = False
            self.sounds = {}

    def tone(self, notes, volume=0.33):
        data = array.array("h")
        for note in notes:
            freq, duration, amp = note[0], note[1], note[2]
            shape = note[3] if len(note) > 3 else "sine"
            count = max(1, int(self.rate * duration))
            attack = max(1, int(self.rate * 0.003))
            for k in range(count):
                t = k / self.rate
                envelope = min(1.0, k / attack) * (1.0 - k / count) ** 1.6
                phase = 2 * math.pi * freq * t
                if shape == "soft":
                    wave = 0.75 * math.sin(phase) + 0.25 * math.sin(2 * phase)
                elif shape == "square":
                    wave = 0.5 if math.sin(phase) >= 0 else -0.5
                else:
                    wave = math.sin(phase)
                value = int(32767 * volume * amp * envelope * wave)
                for _ in range(self.channels):
                    data.append(value)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def build(self):
        self.sounds = {
            "click": self.tone([(1000, 0.035, 0.5)]),
            "hover": self.tone([(1500, 0.02, 0.18)]),
            "select": self.tone([(700, 0.05, 0.5), (940, 0.08, 0.5)]),
            "line": self.tone([(780, 0.045, 0.6, "soft")]),
            "box": self.tone([(1047, 0.07, 0.6, "soft"), (1319, 0.14, 0.6, "soft")]),
            "extra": self.tone([(880, 0.07, 0.5, "soft"), (1175, 0.11, 0.5, "soft")]),
            "turn": self.tone([(520, 0.08, 0.3, "soft")]),
            "win": self.tone(
                [(523, 0.11, 0.6, "soft"), (659, 0.11, 0.6, "soft"), (784, 0.11, 0.6, "soft"), (1047, 0.34, 0.6, "soft")]
            ),
            "lose": self.tone(
                [(392, 0.16, 0.55, "soft"), (349, 0.16, 0.55, "soft"), (294, 0.16, 0.55, "soft"), (220, 0.36, 0.55, "soft")]
            ),
            "draw": self.tone([(494, 0.14, 0.5, "soft"), (392, 0.28, 0.5, "soft")]),
            "restart": self.tone([(330, 0.06, 0.5), (495, 0.06, 0.5), (660, 0.1, 0.5)]),
            "invalid": self.tone([(170, 0.12, 0.5, "square")], 0.2),
        }

    def play(self, name):
        if self.enabled and self.ready:
            sound = self.sounds.get(name)
            if sound is not None:
                try:
                    sound.play()
                except Exception:
                    pass


class Fonts:
    def __init__(self):
        self.cache = {}

    def get(self, size, bold=True):
        key = (int(size), bold)
        if key not in self.cache:
            self.cache[key] = pygame.font.SysFont("segoeui,arial,helvetica", int(size), bold=bold)
        return self.cache[key]


def round_rect(surface, color, rect, radius, alpha=255, width=0):
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    if alpha >= 255:
        pygame.draw.rect(surface, color, rect, width, border_radius=radius)
    else:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (color[0], color[1], color[2], int(alpha)), layer.get_rect(), width, border_radius=radius)
        surface.blit(layer, rect.topleft)


def glow(surface, color, rect, radius, layers=7, step=2, strength=110):
    rect = pygame.Rect(rect)
    pad = layers * step + 2
    layer = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
    for i in range(1, layers + 1):
        grow = i * step
        alpha = int(strength * (1 - i / (layers + 1)) ** 2)
        ring = pygame.Rect(pad - grow, pad - grow, rect.w + grow * 2, rect.h + grow * 2)
        pygame.draw.rect(layer, (color[0], color[1], color[2], alpha), ring, step + 1, border_radius=radius + grow)
    surface.blit(layer, (rect.x - pad, rect.y - pad))


class Game:
    def __init__(self, n, mode, level):
        self.n = n
        self.mode = mode
        self.level = level
        self.board = Board(n)
        self.current = 1
        self.paused = False
        self.over = False
        self.over_at = 0
        self.result_shown = False
        self.winner = 0
        self.moves = 0
        self.line_anim = {}
        self.box_anim = {}
        self.ai_job = None

    def names(self):
        if self.mode == "computer":
            return {1: "You", 2: "Computer"}
        return {1: "Player 1", 2: "Player 2"}

    def human_turn(self):
        return self.mode == "friend" or self.current == 1


class App:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Dots & Boxes")
        self.screen = pygame.display.set_mode((1000, 720), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.sfx = Sfx()
        self.fonts = Fonts()
        self.scene = "menu"
        self.board_size = 4
        self.last_config = None
        self.game = None
        self.hit_list = []
        self.hover_amount = {}
        self.hover_now = None
        self.hover_prev = None
        self.mouse = (0, 0)
        self.fade = 1.0
        self.running = True
        self.now = 0
        self.dt = 0.016
        self.s = 1.0
        self.locked = False
        self.sound_queue = []
        self.settings_origin = "menu"
        self.dialog = None
        self.confetti = []

    def run(self):
        while self.running:
            self.dt = min(self.clock.tick(60) / 1000.0, 0.05)
            self.now = pygame.time.get_ticks()
            self.screen = pygame.display.get_surface()
            width, height = self.screen.get_size()
            self.s = clamp(min(width / 1000.0, height / 720.0), 0.6, 1.7)
            self.mouse = pygame.mouse.get_pos()
            self.handle_events()
            self.update()
            self.draw()
            pygame.display.flip()
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                width, height = event.size
                if width < MIN_WIDTH or height < MIN_HEIGHT:
                    pygame.display.set_mode((max(width, MIN_WIDTH), max(height, MIN_HEIGHT)), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                self.on_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.on_click(event.pos)

    def on_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.dialog is not None:
                self.dialog = None
            elif self.scene == "game":
                self.toggle_pause()
            elif self.scene == "settings":
                self.settings_back()
            elif self.scene in ("difficulty", "rules"):
                self.set_scene("menu")
        elif event.key == pygame.K_p and self.scene == "game" and self.dialog is None:
            self.toggle_pause()

    def on_click(self, pos):
        for rect, action, sound in reversed(self.hit_list):
            if rect.collidepoint(pos):
                self.sfx.play(sound)
                action()
                return
        if self.scene == "game" and self.game is not None and not self.overlay_active():
            self.game_click(pos)

    def overlay_active(self):
        g = self.game
        return self.dialog is not None or g is None or g.paused or g.over

    def set_scene(self, name):
        self.scene = name
        self.fade = 1.0
        self.dialog = None

    def queue_sound(self, name, delay_ms):
        self.sound_queue.append((self.now + delay_ms, name))

    def confirm(self, title, text, yes_label, on_yes):
        self.dialog = {"title": title, "text": text, "yes": yes_label, "on_yes": on_yes}

    def close_dialog(self):
        self.dialog = None

    def new_game(self, mode, level, size):
        self.game = Game(size, mode, level)
        self.last_config = (mode, level)
        self.confetti = []
        self.sound_queue = []
        self.set_scene("game")

    def start_computer(self, level):
        self.new_game("computer", level, self.board_size)

    def start_friend(self):
        self.new_game("friend", None, self.board_size)

    def in_progress(self):
        g = self.game
        return g is not None and g.moves > 0 and not g.over

    def restart(self, size=None):
        if not self.last_config:
            return
        if size is None:
            size = self.game.n if self.game is not None else self.board_size
        self.sfx.play("restart")
        self.new_game(self.last_config[0], self.last_config[1], size)

    def request_restart(self, size=None):
        if self.in_progress():
            self.confirm(
                "Restart Game?",
                "Your progress in this game will be lost.",
                "Restart",
                lambda: self.restart(size),
            )
        else:
            self.restart(size)

    def to_menu(self):
        self.game = None
        self.confetti = []
        self.set_scene("menu")

    def request_menu(self):
        if self.in_progress():
            self.confirm(
                "Leave Game?",
                "The current game will be lost if you return to the main menu.",
                "Main Menu",
                self.to_menu,
            )
        else:
            self.to_menu()

    def go_difficulty(self):
        self.game = None
        self.set_scene("difficulty")

    def open_settings(self, origin):
        self.settings_origin = origin
        self.set_scene("settings")

    def settings_back(self):
        if self.settings_origin == "game" and self.game is not None:
            self.set_scene("game")
            self.delay_ai()
        else:
            self.set_scene("menu")

    def set_board_size(self, size):
        self.board_size = size

    def toggle_sound(self):
        self.sfx.enabled = not self.sfx.enabled
        if self.sfx.enabled:
            self.sfx.play("click")

    def toggle_pause(self):
        g = self.game
        if g is None or g.over:
            return
        g.paused = not g.paused
        if not g.paused:
            self.delay_ai()

    def delay_ai(self):
        g = self.game
        if g is not None and g.ai_job is not None:
            g.ai_job["ready_at"] = max(g.ai_job["ready_at"], self.now + 350)

    def quit_game(self):
        self.running = False

    def layout_game(self):
        width, height = self.screen.get_size()
        s = self.s
        n = self.game.n
        margin = int(22 * s)
        top = pygame.Rect(margin, margin, width - 2 * margin, int(100 * s))
        bar_h = int(50 * s)
        bar = pygame.Rect(margin, height - margin - bar_h, width - 2 * margin, bar_h)
        gap = int(14 * s)
        area = pygame.Rect(margin, top.bottom + gap, width - 2 * margin, bar.top - gap - (top.bottom + gap))
        pad = int(28 * s)
        cell = min((area.w - 2 * pad) / n, (area.h - 2 * pad) / n)
        cell = clamp(cell, 24, 150 * s)
        ox = area.centerx - cell * n / 2
        oy = area.centery - cell * n / 2
        return {"top": top, "bar": bar, "ox": ox, "oy": oy, "cell": cell, "pad": pad}

    def line_at(self, pos, lay):
        n = self.game.n
        topo = self.game.board.topo
        ox, oy, cell = lay["ox"], lay["oy"], lay["cell"]
        mx, my = pos
        fx = (mx - ox) / cell
        fy = (my - oy) / cell
        best = None
        best_dist = cell * 0.3
        r = int(round(fy))
        c = int(math.floor(fx))
        if 0 <= r <= n and 0 <= c < n:
            x0 = ox + c * cell
            x1 = x0 + cell
            y = oy + r * cell
            dx = max(x0 - mx, 0, mx - x1)
            dist = math.hypot(dx, my - y)
            if dist < best_dist:
                best_dist = dist
                best = r * n + c
        c2 = int(round(fx))
        r2 = int(math.floor(fy))
        if 0 <= c2 <= n and 0 <= r2 < n:
            y0 = oy + r2 * cell
            y1 = y0 + cell
            x = ox + c2 * cell
            dy = max(y0 - my, 0, my - y1)
            dist = math.hypot(mx - x, dy)
            if dist < best_dist:
                best = topo.h_count + r2 * (n + 1) + c2
        return best

    def game_click(self, pos):
        g = self.game
        if not g.human_turn():
            return
        lay = self.layout_game()
        i = self.line_at(pos, lay)
        if i is None:
            return
        if g.board.drawn[i]:
            self.sfx.play("invalid")
            return
        self.apply_move(i)

    def apply_move(self, i):
        g = self.game
        if g.over or g.board.drawn[i]:
            return
        player = g.current
        done = g.board.play(i, player)
        g.moves += 1
        g.line_anim[i] = self.now
        self.sfx.play("line")
        if done:
            for b in done:
                g.box_anim[b] = self.now
            self.queue_sound("box", 60)
            if g.board.remaining == 0:
                self.finish_game()
            else:
                self.queue_sound("extra", 260)
        else:
            g.current = 3 - player
            self.queue_sound("turn", 110)

    def finish_game(self):
        g = self.game
        g.over = True
        g.over_at = self.now
        s1, s2 = g.board.scores[1], g.board.scores[2]
        g.winner = 1 if s1 > s2 else 2 if s2 > s1 else 0
        if g.winner == 0:
            name = "draw"
        elif g.mode == "computer":
            name = "win" if g.winner == 1 else "lose"
        else:
            name = "win"
        self.queue_sound(name, 800)

    def start_ai(self):
        g = self.game
        snapshot = g.board.clone()
        level = g.level
        holder = {"move": None, "done": False}

        def work():
            try:
                holder["move"] = choose_move(snapshot, level, random.Random())
            except Exception:
                holder["move"] = None
            holder["done"] = True

        threading.Thread(target=work, daemon=True).start()
        g.ai_job = {"holder": holder, "ready_at": self.now + random.randint(300, 700)}

    def spawn_confetti(self):
        g = self.game
        if g.winner == 0 or (g.mode == "computer" and g.winner == 2):
            return
        width, height = self.screen.get_size()
        colors = [PLAYER_COLOR[g.winner], PLAYER_LIGHT[g.winner], (240, 240, 246)]
        self.confetti = [
            {
                "x": random.uniform(0, width),
                "y": random.uniform(-height * 0.8, 0),
                "vx": random.uniform(-30, 30),
                "vy": random.uniform(90, 200),
                "size": random.randint(4, 8),
                "color": random.choice(colors),
                "phase": random.uniform(0, 6.28),
            }
            for _ in range(70)
        ]

    def update(self):
        due = [item for item in self.sound_queue if item[0] <= self.now]
        if due:
            self.sound_queue = [item for item in self.sound_queue if item[0] > self.now]
            for _, name in due:
                self.sfx.play(name)
        g = self.game
        if self.scene != "game" or g is None:
            return
        if g.over:
            if not g.result_shown and self.now - g.over_at > 900:
                g.result_shown = True
                self.spawn_confetti()
            return
        if g.paused or self.dialog is not None:
            return
        if g.mode == "computer" and g.current == 2:
            if g.ai_job is None:
                self.start_ai()
            else:
                job = g.ai_job
                if job["holder"]["done"] and self.now >= job["ready_at"]:
                    move = job["holder"]["move"]
                    g.ai_job = None
                    if move is None or g.board.drawn[move]:
                        move = random.choice(g.board.free_lines())
                    self.apply_move(move)

    def font(self, size, bold=True):
        return self.fonts.get(max(8, int(size * self.s)), bold)

    def text(self, content, size, color, pos, anchor="center", bold=True):
        surface = self.font(size, bold).render(content, True, color)
        rect = surface.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        self.screen.blit(surface, rect)
        return rect

    def button(self, key, rect, label, action, sound="click", enabled=True, size=22, selected=False, sub=None):
        rect = pygame.Rect(rect)
        s = self.s
        active = enabled and not self.locked
        hovered = active and rect.collidepoint(self.mouse)
        amount = self.hover_amount.get(key, 0.0)
        amount += ((1.0 if hovered else 0.0) - amount) * min(1.0, self.dt * 14)
        self.hover_amount[key] = amount
        if hovered:
            self.hover_now = key
        shown = rect.inflate(int(8 * amount * s), int(4 * amount * s))
        fill = mix(PANEL_LIGHT, PANEL_HOVER, amount)
        border = mix(BORDER, BORDER_LIGHT, amount)
        color = mix(TEXT, (255, 255, 255), amount)
        if selected:
            fill = mix((76, 76, 94), (92, 92, 112), amount)
            border = (208, 208, 222)
        if not enabled:
            fill = PANEL
            border = (56, 56, 64)
            color = (104, 104, 114)
        radius = int(12 * s)
        round_rect(self.screen, fill, shown, radius)
        round_rect(self.screen, border, shown, radius, width=2)
        if sub:
            self.text(label, size, color, (shown.centerx, shown.centery - 9 * s))
            self.text(sub, size * 0.62, MUTED if enabled else color, (shown.centerx, shown.centery + 14 * s), bold=False)
        else:
            self.text(label, size, color, shown.center)
        if active:
            self.hit_list.append((rect, action, sound))

    def backdrop(self):
        width, height = self.screen.get_size()
        step = int(64 * self.s)
        radius = max(2, int(3 * self.s))
        for x in range(step // 2, width, step):
            for y in range(step // 2, height, step):
                pygame.draw.circle(self.screen, (44, 44, 50), (x, y), radius)

    def title_logo(self, y, size):
        parts = [("DOTS", RED), (" & ", MUTED), ("BOXES", BLUE)]
        font = self.font(size)
        surfaces = [font.render(p[0], True, p[1]) for p in parts]
        total = sum(sf.get_width() for sf in surfaces)
        x = self.screen.get_width() // 2 - total // 2
        for sf in surfaces:
            self.screen.blit(sf, (x, int(y - sf.get_height() / 2)))
            x += sf.get_width()

    def heading(self, content, y):
        self.text(content, 46, TEXT, (self.screen.get_width() // 2, y))

    def draw(self):
        self.screen.fill(BG)
        self.hit_list = []
        self.hover_now = None
        self.locked = self.dialog is not None
        if self.scene == "menu":
            self.draw_menu()
        elif self.scene == "difficulty":
            self.draw_difficulty()
        elif self.scene == "rules":
            self.draw_rules()
        elif self.scene == "settings":
            self.draw_settings()
        elif self.scene == "game" and self.game is not None:
            self.draw_game()
        if self.dialog is not None:
            self.draw_dialog()
        if self.hover_now != self.hover_prev:
            if self.hover_now is not None:
                self.sfx.play("hover")
            self.hover_prev = self.hover_now
        if self.fade > 0:
            width, height = self.screen.get_size()
            veil = pygame.Surface((width, height), pygame.SRCALPHA)
            veil.fill((BG[0], BG[1], BG[2], int(255 * clamp(self.fade, 0, 1))))
            self.screen.blit(veil, (0, 0))
            self.fade -= self.dt * 4.0

    def draw_menu(self):
        width, height = self.screen.get_size()
        s = self.s
        self.backdrop()
        self.title_logo(height * 0.19, 76)
        self.text("Connect the dots. Claim the boxes.", 20, MUTED, (width / 2, height * 0.19 + 58 * s), bold=False)
        bw, bh, gap = int(380 * s), int(56 * s), int(16 * s)
        y0 = int(height * 0.36)
        items = (
            ("Play Against Computer", lambda: self.set_scene("difficulty")),
            ("Play Against Friend", self.start_friend),
            ("Game Rules", lambda: self.set_scene("rules")),
            ("Settings", lambda: self.open_settings("menu")),
            ("Exit Game", self.quit_game),
        )
        for index, (label, action) in enumerate(items):
            rect = pygame.Rect(0, 0, bw, bh)
            rect.midtop = (width // 2, y0 + index * (bh + gap))
            self.button("menu_" + label, rect, label, action, sound="select")

    def draw_difficulty(self):
        width, height = self.screen.get_size()
        s = self.s
        self.backdrop()
        self.heading("SELECT DIFFICULTY", height * 0.15)
        size_label = [name for name, value in BOARD_SIZES if value == self.board_size][0]
        self.text(
            "Board: %s (%d × %d boxes)" % (size_label, self.board_size, self.board_size),
            18,
            MUTED,
            (width / 2, height * 0.15 + 46 * s),
            bold=False,
        )
        bw, bh, gap = int(440 * s), int(72 * s), int(16 * s)
        y0 = int(height * 0.32)
        for index, (level, description) in enumerate(LEVELS):
            rect = pygame.Rect(0, 0, bw, bh)
            rect.midtop = (width // 2, y0 + index * (bh + gap))
            self.button("level_" + level, rect, level, lambda lv=level: self.start_computer(lv), sound="select", size=26, sub=description)
        back = pygame.Rect(0, 0, int(240 * s), int(50 * s))
        back.midtop = (width // 2, y0 + 3 * (bh + gap) + int(10 * s))
        self.button("level_back", back, "Back", lambda: self.set_scene("menu"))

    def mini_box(self, cx, cy, size, sides, filled):
        s = self.s
        half = size / 2
        points = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
        thickness = max(4, int(6 * s))
        if filled:
            inner = pygame.Rect(0, 0, int(size - thickness * 2), int(size - thickness * 2))
            inner.center = (int(cx), int(cy))
            round_rect(self.screen, RED_DARK, inner, int(6 * s))
            self.text("1", 26, RED_LIGHT, (cx, cy))
        for k in range(4):
            a = (int(points[k][0]), int(points[k][1]))
            b = (int(points[(k + 1) % 4][0]), int(points[(k + 1) % 4][1]))
            if k < sides:
                pygame.draw.line(self.screen, RED, a, b, thickness)
            else:
                pygame.draw.line(self.screen, GUIDE_BRIGHT, a, b, 2)
        for p in points:
            pygame.draw.circle(self.screen, DOT_COLOR, (int(p[0]), int(p[1])), max(4, int(6 * s)))

    def draw_rules(self):
        width, height = self.screen.get_size()
        s = self.s
        self.backdrop()
        self.heading("GAME RULES", int(46 * s))
        back = pygame.Rect(0, 0, int(240 * s), int(50 * s))
        back.midbottom = (width // 2, height - int(20 * s))
        panel = pygame.Rect(0, 0, int(min(900 * s, width - 40 * s)), 0)
        panel.top = int(88 * s)
        panel.height = back.top - int(14 * s) - panel.top
        panel.centerx = width // 2
        round_rect(self.screen, PANEL, panel, int(18 * s))
        round_rect(self.screen, BORDER, panel, int(18 * s), width=2)
        rules = (
            "Players take turns drawing a line between two adjacent dots.",
            "A line can only connect two horizontally or vertically adjacent dots, never diagonally.",
            "Completing all four sides of a box earns one point.",
            "A player who completes a box gets another turn.",
            "Multiple boxes can be completed with a single line.",
            "The game ends when all boxes are completed.",
            "The player with the most boxes wins.",
        )
        font = self.font(19, False)
        text_x = panel.x + int(62 * s)
        max_w = panel.w - int(100 * s)
        y = panel.top + int(26 * s)
        line_h = int(25 * s)
        for number, rule in enumerate(rules, 1):
            lines = wrap_text(font, rule, max_w)
            pygame.draw.circle(self.screen, PANEL_HOVER, (panel.x + int(34 * s), y + int(11 * s)), int(14 * s))
            self.text(str(number), 16, TEXT, (panel.x + int(34 * s), y + int(11 * s)))
            for line in lines:
                self.text(line, 19, TEXT, (text_x, y + int(11 * s)), anchor="midleft", bold=False)
                y += line_h
            y += int(9 * s)
        area_top = y + int(6 * s)
        area_h = panel.bottom - area_top - int(10 * s)
        box_size = clamp(min(area_h - 40 * s, 90 * s), 40, 100 * s)
        cy = area_top + (area_h - 24 * s) / 2
        self.mini_box(panel.centerx - panel.w * 0.2, cy, box_size, 3, False)
        self.mini_box(panel.centerx + panel.w * 0.2, cy, box_size, 4, True)
        self.text("Incomplete box", 17, MUTED, (panel.centerx - panel.w * 0.2, cy + box_size / 2 + 22 * s), bold=False)
        self.text("Completed box", 17, MUTED, (panel.centerx + panel.w * 0.2, cy + box_size / 2 + 22 * s), bold=False)
        self.button("rules_back", back, "Back", lambda: self.set_scene("menu"))

    def draw_settings(self):
        width, height = self.screen.get_size()
        s = self.s
        self.backdrop()
        self.heading("SETTINGS", height * 0.1)
        pw = int(min(640 * s, width - 40 * s))
        left = width // 2 - pw // 2
        y = int(height * 0.19)
        row_h = int(52 * s)
        self.text("Sound Effects", 24, TEXT, (left, y + row_h // 2), anchor="midleft")
        toggle = pygame.Rect(0, 0, int(150 * s), row_h)
        toggle.midright = (left + pw, y + row_h // 2)
        self.button("set_sound", toggle, "ON" if self.sfx.enabled else "OFF", self.toggle_sound, selected=self.sfx.enabled)
        y += row_h + int(26 * s)
        self.text("Board Size", 24, TEXT, (left, y + int(12 * s)), anchor="midleft")
        y += int(34 * s)
        gap = int(12 * s)
        bw = (pw - 2 * gap) // 3
        for index, (name, value) in enumerate(BOARD_SIZES):
            rect = pygame.Rect(left + index * (bw + gap), y, bw, int(62 * s))
            self.button(
                "set_size_" + name,
                rect,
                name,
                lambda v=value: self.set_board_size(v),
                sound="select",
                size=21,
                selected=self.board_size == value,
                sub="%d × %d boxes" % (value, value),
            )
        y += int(62 * s) + int(12 * s)
        self.text("Board size applies when a new game begins.", 16, MUTED, (width / 2, y + int(8 * s)), bold=False)
        y += int(34 * s)
        bh = int(52 * s)
        bgap = int(12 * s)
        restart = pygame.Rect(left, y, pw, bh)
        self.button(
            "set_restart",
            restart,
            "Restart Game",
            lambda: self.request_restart(self.board_size),
            enabled=self.last_config is not None,
        )
        y += bh + bgap
        if self.settings_origin == "game" and self.game is not None:
            self.button("set_back", pygame.Rect(left, y, pw, bh), "Back to Game", self.settings_back)
            y += bh + bgap
        self.button("set_menu", pygame.Rect(left, y, pw, bh), "Return to Main Menu", self.request_menu)

    def draw_game(self):
        g = self.game
        lay = self.layout_game()
        base_locked = self.dialog is not None or g.paused or g.over
        self.locked = base_locked
        self.draw_scoreboard(lay["top"])
        self.draw_board(lay)
        self.draw_controls(lay)
        if g.paused and not g.over:
            self.locked = self.dialog is not None
            self.draw_pause()
        if g.over and g.result_shown:
            self.locked = self.dialog is not None
            self.draw_result()

    def draw_scoreboard(self, rect):
        g = self.game
        s = self.s
        center_w = int(250 * s)
        gap = int(12 * s)
        card_w = (rect.w - center_w - 2 * gap) // 2
        cards = {
            1: pygame.Rect(rect.x, rect.y, card_w, rect.h),
            2: pygame.Rect(rect.right - card_w, rect.y, card_w, rect.h),
        }
        names = g.names()
        for player, card in cards.items():
            active = g.current == player and not g.over
            color = PLAYER_COLOR[player]
            light = PLAYER_LIGHT[player]
            if active:
                glow(self.screen, light, card, int(14 * s))
                round_rect(self.screen, mix(PANEL, PLAYER_DARK[player], 0.6), card, int(14 * s))
                round_rect(self.screen, light, card, int(14 * s), width=3)
            else:
                round_rect(self.screen, PANEL, card, int(14 * s))
                round_rect(self.screen, BORDER, card, int(14 * s), width=2)
            name_color = light if active else color
            self.text(names[player], 24, name_color, (card.x + int(18 * s), card.centery - int(15 * s)), anchor="midleft")
            self.text(PLAYER_TAG[player], 14, MUTED if not active else light, (card.x + int(18 * s), card.centery + int(17 * s)), anchor="midleft")
            self.text(str(g.board.scores[player]), 52, name_color, (card.right - int(22 * s), card.centery), anchor="midright")
        mid = pygame.Rect(cards[1].right + gap, rect.y, center_w, rect.h)
        pill = pygame.Rect(0, 0, center_w, int(44 * s))
        pill.midtop = (mid.centerx, mid.y + int(4 * s))
        if g.over:
            label = "GAME OVER"
            fill = PANEL_LIGHT
            edge = BORDER_LIGHT
            color = TEXT
        elif g.paused:
            label = "PAUSED"
            fill = PANEL_LIGHT
            edge = BORDER_LIGHT
            color = TEXT
        else:
            if g.mode == "computer":
                label = "YOUR TURN" if g.current == 1 else "COMPUTER'S TURN"
            else:
                label = PLAYER_TAG[g.current] + "'S TURN"
            fill = mix(PANEL, PLAYER_DARK[g.current], 0.6)
            edge = PLAYER_LIGHT[g.current]
            color = PLAYER_LIGHT[g.current]
            glow(self.screen, edge, pill, int(12 * s), layers=5, strength=80)
        round_rect(self.screen, fill, pill, int(12 * s))
        round_rect(self.screen, edge, pill, int(12 * s), width=2)
        self.text(label, 21, color, pill.center)
        total = g.board.topo.box_count
        self.text("Completed %d / %d boxes" % (g.board.completed(), total), 17, MUTED, (mid.centerx, pill.bottom + int(24 * s)), bold=False)

    def draw_board(self, lay):
        g = self.game
        b = g.board
        topo = b.topo
        n = g.n
        s = self.s
        now = self.now
        ox, oy, cell, pad = lay["ox"], lay["oy"], lay["cell"], lay["pad"]
        panel = pygame.Rect(int(ox - pad), int(oy - pad), int(cell * n + 2 * pad), int(cell * n + 2 * pad))
        round_rect(self.screen, PANEL, panel, int(18 * s))
        round_rect(self.screen, BORDER, panel, int(18 * s), width=2)
        thickness = max(4, int(cell * 0.085))
        letters = {1: "Y", 2: "C"} if g.mode == "computer" else {1: "1", 2: "2"}
        for index in range(topo.box_count):
            owner = b.box_owner[index]
            if not owner:
                continue
            r, c = divmod(index, n)
            elapsed = now - g.box_anim.get(index, now - 10000)
            t = ease_out(elapsed / 380.0)
            full = cell - thickness * 2
            size = max(2, int(full * t))
            box = pygame.Rect(0, 0, size, size)
            box.center = (int(ox + (c + 0.5) * cell), int(oy + (r + 0.5) * cell))
            round_rect(self.screen, PLAYER_DARK[owner], box, int(8 * s))
            round_rect(self.screen, PLAYER_COLOR[owner], box, int(8 * s), alpha=110, width=2)
            if t > 0.6:
                self.text(letters[owner], cell * 0.34 / s, PLAYER_COLOR[owner], box.center)
            if elapsed < 450:
                p = elapsed / 450.0
                ring = box.inflate(int(26 * p * s), int(26 * p * s))
                round_rect(self.screen, PLAYER_LIGHT[owner], ring, int(10 * s), alpha=int(170 * (1 - p)), width=3)
        for i in range(topo.line_count):
            if not b.drawn[i]:
                p1, p2 = self.line_points(i, ox, oy, cell)
                pygame.draw.line(self.screen, GUIDE, p1, p2, 2)
        if not self.overlay_active() and g.human_turn():
            i = self.line_at(self.mouse, lay)
            if i is not None and not b.drawn[i]:
                p1, p2 = self.line_points(i, ox, oy, cell)
                preview = mix(PANEL, PLAYER_COLOR[g.current], 0.55)
                pygame.draw.line(self.screen, preview, p1, p2, thickness)
                pygame.draw.circle(self.screen, preview, p1, thickness // 2)
                pygame.draw.circle(self.screen, preview, p2, thickness // 2)
        for i in range(topo.line_count):
            if not b.drawn[i]:
                continue
            owner = b.line_owner[i]
            elapsed = now - g.line_anim.get(i, now - 10000)
            t = ease_out(elapsed / 170.0)
            p1, p2 = self.line_points(i, ox, oy, cell)
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            a = (int(mid[0] + (p1[0] - mid[0]) * t), int(mid[1] + (p1[1] - mid[1]) * t))
            c2 = (int(mid[0] + (p2[0] - mid[0]) * t), int(mid[1] + (p2[1] - mid[1]) * t))
            color = mix((255, 255, 255), PLAYER_COLOR[owner], elapsed / 380.0)
            pygame.draw.line(self.screen, color, a, c2, thickness)
            pygame.draw.circle(self.screen, color, a, thickness // 2)
            pygame.draw.circle(self.screen, color, c2, thickness // 2)
        radius = max(4, int(cell * 0.075))
        for r in range(n + 1):
            for c in range(n + 1):
                pygame.draw.circle(self.screen, DOT_COLOR, (int(ox + c * cell), int(oy + r * cell)), radius)

    def line_points(self, i, ox, oy, cell):
        kind, r, c = self.game.board.topo.line_info[i]
        if kind == 0:
            return (int(ox + c * cell), int(oy + r * cell)), (int(ox + (c + 1) * cell), int(oy + r * cell))
        return (int(ox + c * cell), int(oy + r * cell)), (int(ox + c * cell), int(oy + (r + 1) * cell))

    def draw_controls(self, lay):
        g = self.game
        bar = lay["bar"]
        s = self.s
        gap = int(12 * s)
        bw = min(int(200 * s), (bar.w - 3 * gap) // 4)
        x = bar.centerx - (4 * bw + 3 * gap) // 2
        items = (
            ("ctl_restart", "Restart", lambda: self.request_restart()),
            ("ctl_pause", "Resume" if g.paused else "Pause", self.toggle_pause),
            ("ctl_menu", "Main Menu", self.request_menu),
            ("ctl_sound", "Sound: On" if self.sfx.enabled else "Sound: Off", self.toggle_sound),
        )
        for index, (key, label, action) in enumerate(items):
            rect = pygame.Rect(x + index * (bw + gap), bar.y, bw, bar.h)
            self.button(key, rect, label, action, size=19)

    def draw_pause(self):
        width, height = self.screen.get_size()
        s = self.s
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((10, 10, 14, 185))
        self.screen.blit(dim, (0, 0))
        panel = pygame.Rect(0, 0, int(440 * s), int(380 * s))
        panel.center = (width // 2, height // 2)
        round_rect(self.screen, PANEL, panel, int(18 * s))
        round_rect(self.screen, BORDER_LIGHT, panel, int(18 * s), width=2)
        self.text("PAUSED", 52, TEXT, (panel.centerx, panel.top + int(62 * s)))
        bw, bh, gap = int(320 * s), int(52 * s), int(14 * s)
        y = panel.top + int(120 * s)
        items = (
            ("pause_resume", "Resume", self.toggle_pause),
            ("pause_settings", "Settings", lambda: self.open_settings("game")),
            ("pause_menu", "Main Menu", self.request_menu),
        )
        for index, (key, label, action) in enumerate(items):
            rect = pygame.Rect(0, 0, bw, bh)
            rect.midtop = (panel.centerx, y + index * (bh + gap))
            self.button(key, rect, label, action)

    def draw_result(self):
        g = self.game
        width, height = self.screen.get_size()
        s = self.s
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((10, 10, 14, 175))
        self.screen.blit(dim, (0, 0))
        names = g.names()
        if g.winner == 0:
            title = "IT'S A DRAW"
            accent = TEXT
        else:
            accent = PLAYER_LIGHT[g.winner]
            if g.mode == "computer":
                title = "YOU WIN!" if g.winner == 1 else "COMPUTER WINS"
            else:
                title = "%s WINS!" % names[g.winner].upper()
        buttons = [("res_again", "Play Again", self.restart)]
        if g.mode == "computer":
            buttons.append(("res_diff", "Change Difficulty", self.go_difficulty))
        buttons.append(("res_menu", "Main Menu", self.to_menu))
        buttons.append(("res_exit", "Exit Game", self.quit_game))
        bh = int(46 * s)
        bgap = int(10 * s)
        panel = pygame.Rect(0, 0, int(520 * s), int(250 * s) + len(buttons) * (bh + bgap) + int(24 * s))
        panel.center = (width // 2, height // 2)
        glow(self.screen, accent, panel, int(18 * s), strength=90)
        round_rect(self.screen, PANEL, panel, int(18 * s))
        round_rect(self.screen, accent, panel, int(18 * s), width=3)
        pulse = 1 + 0.04 * math.sin(self.now / 260.0)
        self.text(title, 42 * pulse, accent, (panel.centerx, panel.top + int(50 * s)))
        for player, offset in ((1, -120), (2, 120)):
            cx = panel.centerx + int(offset * s)
            self.text(names[player], 22, PLAYER_COLOR[player], (cx, panel.top + int(108 * s)))
            self.text(str(g.board.scores[player]), 64, PLAYER_LIGHT[player], (cx, panel.top + int(158 * s)))
            self.text("boxes captured", 15, MUTED, (cx, panel.top + int(208 * s)), bold=False)
        y = panel.top + int(244 * s)
        for index, (key, label, action) in enumerate(buttons):
            rect = pygame.Rect(0, 0, int(340 * s), bh)
            rect.midtop = (panel.centerx, y + index * (bh + bgap))
            self.button(key, rect, label, action, size=20)
        self.draw_confetti()

    def draw_confetti(self):
        width, height = self.screen.get_size()
        alive = []
        for piece in self.confetti:
            piece["y"] += piece["vy"] * self.dt
            piece["x"] += piece["vx"] * self.dt + math.sin(self.now / 300.0 + piece["phase"]) * 0.6
            if piece["y"] < height + 10:
                alive.append(piece)
                if piece["y"] > -10:
                    size = piece["size"]
                    pygame.draw.rect(self.screen, piece["color"], (int(piece["x"]), int(piece["y"]), size, size + 3))
        self.confetti = alive

    def draw_dialog(self):
        width, height = self.screen.get_size()
        s = self.s
        self.locked = False
        self.hit_list = []
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((10, 10, 14, 170))
        self.screen.blit(dim, (0, 0))
        panel = pygame.Rect(0, 0, int(480 * s), int(230 * s))
        panel.center = (width // 2, height // 2)
        round_rect(self.screen, PANEL, panel, int(16 * s))
        round_rect(self.screen, BORDER_LIGHT, panel, int(16 * s), width=2)
        self.text(self.dialog["title"], 30, TEXT, (panel.centerx, panel.top + int(44 * s)))
        font = self.font(18, False)
        y = panel.top + int(88 * s)
        for line in wrap_text(font, self.dialog["text"], panel.w - int(60 * s)):
            self.text(line, 18, MUTED, (panel.centerx, y), bold=False)
            y += int(24 * s)
        bw, bh, gap = int(180 * s), int(46 * s), int(16 * s)
        yes_rect = pygame.Rect(panel.centerx - gap // 2 - bw, panel.bottom - int(30 * s) - bh, bw, bh)
        no_rect = pygame.Rect(panel.centerx + gap // 2, yes_rect.y, bw, bh)
        on_yes = self.dialog["on_yes"]

        def accept():
            self.close_dialog()
            on_yes()

        self.button("dlg_yes", yes_rect, self.dialog["yes"], accept, size=19)
        self.button("dlg_no", no_rect, "Cancel", self.close_dialog, size=19)


def main():
    app = App()
    app.run()
    sys.exit()


if __name__ == "__main__":
    main()