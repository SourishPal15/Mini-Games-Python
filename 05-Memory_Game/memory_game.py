import array
import math
import random
import sys
from dataclasses import dataclass

import pygame

WIDTH, HEIGHT = 1000, 680
FPS = 60

COLS, ROWS = 5, 4
PAIR_COUNT = 10
CARD_W, CARD_H = 104, 120
CARD_GAP = 14
BOARD_W = COLS * CARD_W + (COLS - 1) * CARD_GAP
BOARD_H = ROWS * CARD_H + (ROWS - 1) * CARD_GAP
BOARD_X = (WIDTH - BOARD_W) // 2
BOARD_Y = 100

FLIP_DURATION_MS = 260
RESOLVE_DELAY_MS = 450
MISMATCH_REVEAL_MS = 1000
GAME_OVER_DELAY_MS = 1900

MODE_COMPUTER = "computer"
MODE_PLAYER = "player"
DIFFICULTIES = ("Easy", "Medium", "Difficult")

PHASE_FIRST = "first_card"
PHASE_SECOND = "second_card"
PHASE_RESOLVE = "resolving"
PHASE_HIDE = "hiding"
PHASE_OVER = "game_over"

STATE_MENU = "menu"
STATE_SELECT = "select_difficulty"
STATE_DIFFICULTY = "difficulty"
STATE_INSTRUCTIONS = "instructions"
STATE_SOUND = "sound"
STATE_PLAYING = "playing"
STATE_RESULTS = "results"

TRANSITIONS = {
    STATE_MENU: {STATE_SELECT, STATE_DIFFICULTY, STATE_INSTRUCTIONS, STATE_SOUND, STATE_PLAYING},
    STATE_SELECT: {STATE_MENU, STATE_PLAYING},
    STATE_DIFFICULTY: {STATE_MENU},
    STATE_INSTRUCTIONS: {STATE_MENU},
    STATE_SOUND: {STATE_MENU},
    STATE_PLAYING: {STATE_MENU, STATE_RESULTS},
    STATE_RESULTS: {STATE_MENU, STATE_PLAYING},
}

WHITE = (255, 255, 255)
TEXT = (246, 248, 255)
MUTED = (186, 194, 232)
GOLD = (255, 208, 70)
GREEN = (96, 214, 140)
RED = (240, 90, 100)
DARK = (30, 34, 80)
P1_COLOR = (74, 160, 255)
P2_COLOR = (255, 132, 92)
BG_TOP = (28, 32, 92)
BG_BOTTOM = (86, 48, 128)
PANEL_FILL = (255, 255, 255, 28)
PANEL_BORDER = (255, 255, 255, 70)

COLOR_BLUE = (62, 128, 236)
COLOR_CORAL = (236, 104, 84)
COLOR_PURPLE = (144, 98, 222)
COLOR_TEAL = (40, 166, 166)
COLOR_AMBER = (214, 142, 34)
COLOR_ROSE = (184, 66, 92)
COLOR_SLATE = (92, 104, 160)
DIFFICULTY_COLORS = {"Easy": (70, 180, 120), "Medium": (232, 164, 50), "Difficult": (226, 86, 96)}

TITLE_COLORS = [
    (255, 208, 70),
    (255, 132, 92),
    (92, 200, 255),
    (150, 230, 140),
    (214, 150, 255),
    (255, 150, 200),
]
CONFETTI_COLORS = TITLE_COLORS + [WHITE]

RULES = [
    "The board has 20 cards arranged as 10 matching pairs.",
    "On your turn, flip two cards, one after the other.",
    "If both cards match, you score one point.",
    "A successful match lets you take another turn.",
    "If the cards do not match, they flip back after a short delay.",
    "A failed match passes the turn to your opponent.",
    "The game ends when all 10 pairs have been found.",
    "The player with the most pairs wins.",
]


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def mix(color_a, color_b, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(color_a[:3], color_b[:3]))


def ease_out_back(t):
    t = clamp(t, 0.0, 1.0)
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def ellipse_points(x, y, rx, ry, angle_deg, steps=28):
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    points = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        points.append((x + ex * cos_a - ey * sin_a, y + ex * sin_a + ey * cos_a))
    return points


def arc_points(cx, cy, radius, start_deg, end_deg, steps=24):
    points = []
    for i in range(steps + 1):
        angle = math.radians(lerp(start_deg, end_deg, i / steps))
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


class Pen:
    def __init__(self, surface, cx, cy, size):
        self.surface = surface
        self.cx = cx
        self.cy = cy
        self.u = size * 0.94 / 100.0

    def pt(self, x, y):
        return (self.cx + x * self.u, self.cy + y * self.u)

    def px(self, value):
        return max(1, int(round(value * self.u)))

    def circle(self, color, x, y, r, outline=None, ow=2):
        center = self.pt(x, y)
        radius = self.px(r)
        if color:
            pygame.draw.circle(self.surface, color, center, radius)
        if outline:
            pygame.draw.circle(self.surface, outline, center, radius, self.px(ow))

    def ellipse(self, color, x, y, w, h, outline=None, ow=2):
        rect = pygame.Rect(0, 0, self.px(w), self.px(h))
        cx, cy = self.pt(x, y)
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(self.surface, color, rect)
        if outline:
            pygame.draw.ellipse(self.surface, outline, rect, self.px(ow))

    def rotated_ellipse(self, color, x, y, rx, ry, angle, outline=None, ow=2):
        self.polygon(color, ellipse_points(x, y, rx, ry, angle), outline, ow)

    def polygon(self, color, points, outline=None, ow=2):
        pts = [self.pt(px, py) for px, py in points]
        pygame.draw.polygon(self.surface, color, pts)
        if outline:
            pygame.draw.polygon(self.surface, outline, pts, self.px(ow))

    def rect(self, color, x, y, w, h, radius=0, outline=None, ow=2):
        px, py = self.pt(x, y)
        rect = pygame.Rect(int(px), int(py), self.px(w), self.px(h))
        pygame.draw.rect(self.surface, color, rect, border_radius=self.px(radius) if radius else 0)
        if outline:
            pygame.draw.rect(
                self.surface, outline, rect, self.px(ow), border_radius=self.px(radius) if radius else 0
            )

    def line(self, color, start, end, w=3):
        pygame.draw.line(self.surface, color, self.pt(*start), self.pt(*end), self.px(w))

    def polyline(self, color, points, w=3):
        pygame.draw.lines(self.surface, color, False, [self.pt(px, py) for px, py in points], self.px(w))


def draw_apple(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    red, dark = (222, 52, 60), (150, 24, 36)
    circles = [(-13, 10, 30), (13, 10, 30), (0, 17, 28)]
    for x, y, r in circles:
        pen.circle(dark, x, y, r + 2.5)
    for x, y, r in circles:
        pen.circle(red, x, y, r)
    pen.ellipse((165, 25, 38), 0, -15, 16, 9)
    pen.line((105, 66, 38), (0, -15), (5, -37), 6)
    pen.polygon((86, 184, 84), [(5, -33), (14, -45), (30, -43), (26, -30), (12, -27)], (46, 124, 56), 2.5)
    pen.line((46, 124, 56), (8, -32), (24, -38), 1.5)
    pen.rotated_ellipse((246, 130, 130), -24, 4, 5, 12, 20)


def draw_banana(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    shift = -7
    outer = arc_points(0, -18, 52, 18, 162, 28)
    inner = arc_points(0, -34, 46, 162, 18, 28)
    shape = [(x, y + shift) for x, y in outer + inner]
    pen.polygon((250, 214, 60), shape, (190, 142, 18), 3.5)
    ridge = [(x, y + shift) for x, y in arc_points(0, -26, 49, 28, 152, 24)]
    pen.polyline((226, 178, 30), ridge, 2)
    glow = [(x, y + shift) for x, y in arc_points(0, -30, 47, 45, 135, 18)]
    pen.polyline((255, 240, 150), glow, 3)
    pen.circle((98, 62, 30), 46.6, -10.9 + shift, 5.5)
    pen.circle((98, 62, 30), -46.6, -10.9 + shift, 5.5)


def draw_orange(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    pen.circle((246, 146, 32), 0, 6, 38, (196, 98, 14), 3)
    pen.rotated_ellipse((255, 192, 96), -17, -6, 6, 13, 25)
    for x, y in [(10, 0), (18, 14), (2, 18), (-8, 28), (14, -12), (-2, -2), (24, 2), (-14, 16)]:
        pen.circle((214, 118, 20), x, y, 1.7)
    pen.polygon((86, 184, 84), [(2, -30), (12, -45), (30, -41), (24, -29), (10, -26)], (46, 124, 56), 2.5)
    pen.circle((96, 132, 46), 0, -30, 4.5)


def draw_strawberry(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    body, edge = (226, 42, 72), (150, 20, 46)
    pen.circle(edge, -14, -8, 29)
    pen.circle(edge, 14, -8, 29)
    pen.polygon(edge, [(-41, -5), (41, -5), (0, 48)])
    pen.circle(body, -14, -8, 26)
    pen.circle(body, 14, -8, 26)
    pen.polygon(body, [(-38, -4), (38, -4), (0, 44)])
    for x, y in [(-16, -2), (0, -4), (16, -2), (-22, 12), (-8, 10), (8, 10), (22, 12), (-13, 24), (3, 23), (14, 24), (0, 35)]:
        pen.ellipse((255, 232, 140), x, y, 5, 7)
    crown = [(-26, -26), (-14, -34), (-8, -44), (0, -34), (8, -44), (14, -34), (26, -26), (12, -22), (0, -16), (-12, -22)]
    pen.polygon((62, 164, 74), crown, (36, 112, 50), 2.5)
    pen.rect((52, 138, 62), -3, -52, 6, 12)


def draw_dog(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    ear, ear_edge = (122, 74, 44), (80, 46, 26)
    pen.rotated_ellipse(ear, -33, 4, 11, 24, 15, ear_edge, 2)
    pen.rotated_ellipse(ear, 33, 4, 11, 24, -15, ear_edge, 2)
    pen.circle((214, 168, 108), 0, 6, 34, (150, 106, 60), 2.5)
    pen.circle((158, 100, 56), 12, -4, 13)
    pen.ellipse((248, 228, 196), 0, 20, 40, 28)
    for x in (-12, 12):
        pen.circle((40, 30, 30), x, -2, 5)
        pen.circle(WHITE, x - 1.5, -3.5, 1.6)
    pen.ellipse((240, 110, 130), 0, 30, 10, 12)
    pen.ellipse((30, 24, 24), 0, 10, 16, 11)
    pen.line((90, 60, 40), (0, 15), (0, 22), 2.5)
    pen.line((90, 60, 40), (0, 22), (-8, 27), 2.5)
    pen.line((90, 60, 40), (0, 22), (8, 27), 2.5)


def draw_cat(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    fur, dark = (246, 168, 78), (200, 112, 38)
    for sign in (-1, 1):
        pen.polygon(fur, [(sign * 32, 0), (sign * 28, -42), (sign * 4, -24)], dark, 2.5)
        pen.polygon((248, 170, 176), [(sign * 27, -6), (sign * 26, -32), (sign * 12, -22)])
    pen.circle(fur, 0, 8, 33, dark, 2.5)
    pen.line(dark, (0, -22), (0, -11), 3)
    pen.line(dark, (-9, -20), (-7, -11), 3)
    pen.line(dark, (9, -20), (7, -11), 3)
    pen.ellipse((253, 230, 200), 0, 20, 26, 18)
    for x in (-13, 13):
        pen.ellipse((140, 210, 90), x, 4, 13, 15, (60, 100, 40), 1.5)
        pen.ellipse((20, 20, 20), x, 4, 4, 12)
    pen.polygon((240, 120, 140), [(-4, 13), (4, 13), (0, 18)])
    pen.line((90, 50, 30), (0, 18), (0, 21), 2)
    pen.line((90, 50, 30), (0, 21), (-6, 25), 2)
    pen.line((90, 50, 30), (0, 21), (6, 25), 2)
    for sign in (-1, 1):
        pen.line((90, 60, 40), (sign * 14, 16), (sign * 46, 10), 1.8)
        pen.line((90, 60, 40), (sign * 14, 20), (sign * 47, 20), 1.8)
        pen.line((90, 60, 40), (sign * 14, 24), (sign * 46, 30), 1.8)


def draw_rabbit(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    fur, edge, pink = (247, 247, 252), (160, 160, 184), (255, 176, 196)
    pen.rotated_ellipse(fur, -17, -26, 10, 24, -8, edge, 2.5)
    pen.rotated_ellipse(pink, -17, -24, 4.5, 17, -8)
    pen.rotated_ellipse(fur, 17, -26, 10, 24, 8, edge, 2.5)
    pen.rotated_ellipse(pink, 17, -24, 4.5, 17, 8)
    pen.circle(fur, 0, 18, 31, edge, 2.5)
    pen.circle((255, 214, 224), -18, 26, 6)
    pen.circle((255, 214, 224), 18, 26, 6)
    for x in (-11, 11):
        pen.circle((60, 40, 70), x, 12, 4.5)
        pen.circle(WHITE, x - 1.3, 10.7, 1.5)
    pen.polygon(pink, [(-4, 19), (4, 19), (0, 24)])
    pen.line((120, 90, 110), (0, 24), (0, 28), 2)
    pen.line((120, 90, 110), (0, 28), (-6, 32), 2)
    pen.line((120, 90, 110), (0, 28), (6, 32), 2)
    pen.rect(WHITE, -4, 30, 8, 9, 1.5, edge, 1.5)
    for sign in (-1, 1):
        pen.line((150, 150, 170), (sign * 14, 20), (sign * 40, 16), 1.5)
        pen.line((150, 150, 170), (sign * 14, 24), (sign * 40, 27), 1.5)


def draw_fish(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    orange, orange_edge = (255, 150, 60), (200, 100, 30)
    pen.polygon(orange, [(26, 0), (48, -22), (43, 0), (48, 22)], orange_edge, 2.5)
    pen.polygon(orange, [(-16, -20), (-2, -40), (14, -18)], orange_edge, 2.5)
    pen.polygon(orange, [(-8, 20), (2, 34), (14, 20)], orange_edge, 2.5)
    pen.ellipse((70, 170, 240), -6, 0, 76, 46, (30, 110, 180), 3)
    pen.ellipse((150, 215, 250), -6, 12, 56, 18)
    for dx in (4, 14, 24):
        half = 22 * math.sqrt(1 - (dx / 38.0) ** 2) - 4
        pen.line((40, 130, 210), (-6 + dx, -half), (-6 + dx, half), 2.5)
    pen.circle(WHITE, -24, -5, 7, (40, 40, 60), 1.5)
    pen.circle((30, 30, 50), -25.5, -5, 3.5)
    pen.polyline((30, 90, 150), [(-42, 6), (-37, 9), (-32, 7)], 2)
    pen.circle(None, -40, -31, 4, (150, 200, 240), 1.5)
    pen.circle(None, -46, -40, 3, (150, 200, 240), 1.5)


def draw_star(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    outer, inner = [], []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        radius_outer = 48 if i % 2 == 0 else 21
        radius_inner = 28 if i % 2 == 0 else 12
        outer.append((radius_outer * math.cos(angle), 4 + radius_outer * math.sin(angle)))
        inner.append((radius_inner * math.cos(angle), 4 + radius_inner * math.sin(angle)))
    pen.polygon((255, 212, 50), outer, (222, 140, 10), 3.5)
    pen.polygon((255, 232, 120), inner)
    for x in (-9, 9):
        pen.circle((70, 40, 10), x, 4, 3.2)
    pen.polyline((70, 40, 10), arc_points(0, 6, 10, 25, 155, 10), 2.2)
    pen.circle((255, 160, 100), -16, 11, 3.5)
    pen.circle((255, 160, 100), 16, 11, 3.5)


def draw_gift(surface, cx, cy, size):
    pen = Pen(surface, cx, cy, size)
    red, dark = (224, 58, 84), (170, 32, 58)
    gold, gold_dark = (255, 206, 64), (214, 150, 20)
    pen.rect(red, -34, -4, 68, 44, 3, dark, 2.5)
    pen.rect((240, 88, 112), -39, -18, 78, 20, 3, dark, 2.5)
    pen.rect(gold, -7, -4, 14, 44, 0, gold_dark, 2)
    pen.rect(gold, -7, -18, 14, 20, 0, gold_dark, 2)
    pen.rotated_ellipse(gold, -14, -28, 13, 8, -30, gold_dark, 2.5)
    pen.rotated_ellipse(gold, 14, -28, 13, 8, 30, gold_dark, 2.5)
    pen.circle(gold, 0, -24, 6, gold_dark, 2.5)


ILLUSTRATIONS = [
    ("Apple", draw_apple, (255, 229, 229), (224, 92, 100)),
    ("Banana", draw_banana, (255, 247, 204), (228, 184, 40)),
    ("Orange", draw_orange, (255, 236, 208), (240, 150, 50)),
    ("Strawberry", draw_strawberry, (255, 224, 238), (226, 70, 120)),
    ("Dog", draw_dog, (240, 230, 216), (160, 112, 70)),
    ("Cat", draw_cat, (236, 252, 214), (120, 180, 60)),
    ("Rabbit", draw_rabbit, (244, 236, 255), (160, 130, 214)),
    ("Fish", draw_fish, (206, 244, 244), (52, 166, 180)),
    ("Star", draw_star, (222, 228, 255), (110, 118, 220)),
    ("Gift Box", draw_gift, (216, 248, 230), (60, 184, 120)),
]


def render_illustration(draw_function, size, supersample=3):
    big = size * supersample
    surface = pygame.Surface((big, big), pygame.SRCALPHA)
    draw_function(surface, big / 2, big / 2, big)
    return pygame.transform.smoothscale(surface, (size, size))


@dataclass(frozen=True)
class AIProfile:
    capacity: int
    retention_turns: int
    forget_chance: float
    record_chance: float
    miss_pair_chance: float
    random_move_chance: float
    explore_preference: float
    avoid_repeats: bool
    first_delay: tuple
    second_delay: tuple
    description: str


AI_PROFILES = {
    "Easy": AIProfile(
        capacity=4,
        retention_turns=3,
        forget_chance=0.25,
        record_chance=0.8,
        miss_pair_chance=0.35,
        random_move_chance=0.3,
        explore_preference=0.5,
        avoid_repeats=False,
        first_delay=(1000, 1500),
        second_delay=(800, 1200),
        description="Short memory and plenty of guesses. A friendly opponent.",
    ),
    "Medium": AIProfile(
        capacity=10,
        retention_turns=8,
        forget_chance=0.07,
        record_chance=0.95,
        miss_pair_chance=0.1,
        random_move_chance=0.12,
        explore_preference=0.85,
        avoid_repeats=False,
        first_delay=(850, 1250),
        second_delay=(650, 1000),
        description="Remembers most cards and completes known pairs, with occasional slips.",
    ),
    "Difficult": AIProfile(
        capacity=20,
        retention_turns=1000,
        forget_chance=0.01,
        record_chance=1.0,
        miss_pair_chance=0.02,
        random_move_chance=0.02,
        explore_preference=1.0,
        avoid_repeats=True,
        first_delay=(600, 1000),
        second_delay=(500, 800),
        description="Near-perfect memory of every card revealed. Never peeks at hidden cards.",
    ),
}

AI_NOTES = [
    ("Easy", "Remembers only the last few cards it saw, forgets quickly, and often guesses at random."),
    ("Medium", "Remembers most cards for several turns and usually completes pairs it knows, with occasional slips."),
    ("Difficult", "Remembers nearly every card revealed and rarely slips, but never sees cards that were not flipped."),
]


@dataclass
class MemoryEntry:
    position: int
    identity: int
    observed: bool
    matched: bool
    last_seen_turn: int
    seen_order: int


class ComputerAI:
    def __init__(self, difficulty, rng=None):
        self.difficulty = difficulty
        self.profile = AI_PROFILES[difficulty]
        self.rng = rng or random.Random()
        self.memory = {}
        self.sequence = 0
        self.failed_guesses = set()
        self.planned_second = None

    def reset(self):
        self.memory = {}
        self.sequence = 0
        self.failed_guesses = set()
        self.planned_second = None

    def think_time(self, second):
        low, high = self.profile.second_delay if second else self.profile.first_delay
        return self.rng.randint(low, high)

    def observe(self, position, identity, turn):
        entry = self.memory.get(position)
        if entry is None and self.rng.random() > self.profile.record_chance:
            return
        self.sequence += 1
        if entry is None:
            self.memory[position] = MemoryEntry(position, identity, True, False, turn, self.sequence)
        else:
            entry.last_seen_turn = turn
            entry.seen_order = self.sequence
        self._enforce_capacity()

    def mark_matched(self, positions):
        for position in positions:
            entry = self.memory.get(position)
            if entry is not None:
                entry.matched = True
        self.failed_guesses = {pair for pair in self.failed_guesses if not (pair & set(positions))}
        self.planned_second = None

    def record_result(self, first, second, matched):
        if not matched:
            self.failed_guesses.add(frozenset((first, second)))

    def begin_turn(self, turn):
        for position in list(self.memory):
            entry = self.memory[position]
            expired = turn - entry.last_seen_turn > self.profile.retention_turns
            if entry.matched or expired or self.rng.random() < self.profile.forget_chance:
                del self.memory[position]
        self.planned_second = None

    def choose_first(self, available):
        available_set = set(available)
        pairs = self._known_pairs(available_set)
        if pairs and self.rng.random() >= self.profile.miss_pair_chance:
            first, second = self.rng.choice(pairs)
            self.planned_second = second.position
            return first.position
        self.planned_second = None
        return self._explore(available, None)

    def choose_second(self, first_position, first_identity, available):
        available_set = set(available)
        planned = self.planned_second
        self.planned_second = None
        if planned is not None and planned in available_set:
            return planned
        partner = None
        for entry in self._active_entries():
            if entry.identity == first_identity and entry.position in available_set:
                partner = entry
                break
        if partner is not None and self.rng.random() >= self.profile.miss_pair_chance:
            return partner.position
        return self._explore(available, first_position)

    def _active_entries(self):
        return [entry for entry in self.memory.values() if entry.observed and not entry.matched]

    def _known_pairs(self, available_set):
        by_identity = {}
        for entry in self._active_entries():
            if entry.position in available_set:
                by_identity.setdefault(entry.identity, []).append(entry)
        return [group[:2] for group in by_identity.values() if len(group) >= 2]

    def _explore(self, available, first_position):
        options = list(available)
        if self.rng.random() < self.profile.random_move_chance:
            return self.rng.choice(options)
        remembered = {entry.position for entry in self._active_entries()}
        unseen = [position for position in options if position not in remembered]
        pool = options
        if unseen and self.rng.random() < self.profile.explore_preference:
            pool = unseen
        if self.profile.avoid_repeats and first_position is not None:
            fresh = [p for p in pool if frozenset((first_position, p)) not in self.failed_guesses]
            if fresh:
                pool = fresh
        return self.rng.choice(pool)

    def _enforce_capacity(self):
        active = sorted(self._active_entries(), key=lambda entry: entry.seen_order)
        overflow = len(active) - self.profile.capacity
        for entry in active[: max(0, overflow)]:
            del self.memory[entry.position]


class Player:
    def __init__(self, name, color, is_computer):
        self.name = name
        self.color = color
        self.is_computer = is_computer
        self.score = 0


class Card:
    def __init__(self, index, identity, x, y):
        self.index = index
        self.identity = identity
        self.x = x
        self.y = y
        self.face_up = False
        self.matched = False
        self.flip = 0.0
        self.hover = 0.0
        self.pulse = 0.0
        self.shake = 0.0

    @property
    def center_x(self):
        return self.x + CARD_W / 2

    @property
    def center_y(self):
        return self.y + CARD_H / 2

    @property
    def selectable(self):
        return not self.face_up and not self.matched

    def contains(self, px, py):
        return self.x <= px < self.x + CARD_W and self.y <= py < self.y + CARD_H

    def update(self, dt, hovered):
        target = 1.0 if self.face_up else 0.0
        step = dt / FLIP_DURATION_MS
        if self.flip < target:
            self.flip = min(target, self.flip + step)
        elif self.flip > target:
            self.flip = max(target, self.flip - step)
        hover_target = 1.0 if hovered else 0.0
        self.hover += (hover_target - self.hover) * min(1.0, dt / 80.0)
        self.pulse = max(0.0, self.pulse - dt / 550.0)
        self.shake = max(0.0, self.shake - dt / 500.0)


class Game:
    def __init__(self, mode, difficulty="Medium", rng=None):
        self.mode = mode
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        if mode == MODE_COMPUTER:
            self.players = [Player("You", P1_COLOR, False), Player("Computer", P2_COLOR, True)]
            self.ai = ComputerAI(difficulty, random.Random(self.rng.random()))
        else:
            self.players = [Player("Player 1", P1_COLOR, False), Player("Player 2", P2_COLOR, False)]
            self.ai = None
        self.cards = []
        self.events = []
        self.new_round(0.0)

    def new_round(self, now):
        identities = list(range(PAIR_COUNT)) * 2
        self.rng.shuffle(identities)
        self.cards = []
        for index, identity in enumerate(identities):
            col, row = index % COLS, index // COLS
            x = BOARD_X + col * (CARD_W + CARD_GAP)
            y = BOARD_Y + row * (CARD_H + CARD_GAP)
            self.cards.append(Card(index, identity, x, y))
        for player in self.players:
            player.score = 0
        self.current = 0
        self.selected = []
        self.matched_identities = set()
        self.phase = PHASE_FIRST
        self.turn = 1
        self.timer_at = None
        self.ai_due_at = None
        self.moves_made = 0
        self.finished_at = None
        if self.ai is not None:
            self.ai.reset()
        self.events = [("turn", 0)]

    @property
    def current_player(self):
        return self.players[self.current]

    @property
    def matched_pairs(self):
        return len(self.matched_identities)

    @property
    def remaining_pairs(self):
        return PAIR_COUNT - self.matched_pairs

    @property
    def total_score(self):
        return sum(player.score for player in self.players)

    @property
    def finished(self):
        return self.phase == PHASE_OVER

    @property
    def accepting_human_input(self):
        return self.phase in (PHASE_FIRST, PHASE_SECOND) and not self.current_player.is_computer

    def result(self):
        if self.matched_pairs < PAIR_COUNT:
            return None
        first, second = self.players[0].score, self.players[1].score
        if first > second:
            return 0
        if second > first:
            return 1
        return -1

    def pop_events(self):
        events, self.events = self.events, []
        return events

    def available_positions(self):
        return [card.index for card in self.cards if card.selectable]

    def flip_card(self, index, now, by_computer=False):
        if self.phase not in (PHASE_FIRST, PHASE_SECOND):
            return False
        if self.current_player.is_computer != by_computer:
            return False
        if not isinstance(index, int) or not 0 <= index < len(self.cards):
            return False
        card = self.cards[index]
        if not card.selectable or index in self.selected or len(self.selected) >= 2:
            return False
        card.face_up = True
        self.selected.append(index)
        self.moves_made += 1
        self.events.append(("flip", index))
        if self.ai is not None:
            self.ai.observe(index, card.identity, self.turn)
        if len(self.selected) == 1:
            self.phase = PHASE_SECOND
            self._schedule_computer(now, True)
        else:
            self.phase = PHASE_RESOLVE
            self.timer_at = now + RESOLVE_DELAY_MS
            self.ai_due_at = None
        return True

    def update(self, now):
        if self.phase == PHASE_RESOLVE and now >= self.timer_at:
            self._resolve(now)
        elif self.phase == PHASE_HIDE and now >= self.timer_at:
            self._hide(now)
        elif self.phase in (PHASE_FIRST, PHASE_SECOND) and self.current_player.is_computer:
            if self.ai_due_at is not None and now >= self.ai_due_at:
                self.ai_due_at = None
                if self.phase == PHASE_FIRST:
                    self._computer_first(now)
                else:
                    self._computer_second(now)

    def _schedule_computer(self, now, second):
        if self.ai is not None and self.current_player.is_computer:
            self.ai_due_at = now + self.ai.think_time(second)
        else:
            self.ai_due_at = None

    def _computer_first(self, now):
        available = self.available_positions()
        if not available:
            return
        choice = self.ai.choose_first(available)
        if not self.flip_card(choice, now, True):
            if not self.flip_card(self.rng.choice(available), now, True):
                self.ai_due_at = now + 200

    def _computer_second(self, now):
        available = self.available_positions()
        if not available or not self.selected:
            return
        first_index = self.selected[0]
        first_identity = self.cards[first_index].identity
        choice = self.ai.choose_second(first_index, first_identity, available)
        if not self.flip_card(choice, now, True):
            if not self.flip_card(self.rng.choice(available), now, True):
                self.ai_due_at = now + 200

    def _resolve(self, now):
        first, second = (self.cards[i] for i in self.selected)
        is_match = first.identity == second.identity and first.identity not in self.matched_identities
        if self.ai is not None:
            self.ai.record_result(first.index, second.index, is_match)
        if is_match:
            self.matched_identities.add(first.identity)
            first.matched = True
            second.matched = True
            self.current_player.score += 1
            self.events.append(("match", first.index, second.index, self.current))
            if self.ai is not None:
                self.ai.mark_matched((first.index, second.index))
            self.selected = []
            self.timer_at = None
            if self.matched_pairs >= PAIR_COUNT:
                self.phase = PHASE_OVER
                self.finished_at = now
                self.events.append(("game_over",))
            else:
                self.phase = PHASE_FIRST
                self.events.append(("extra_turn", self.current))
                self._schedule_computer(now, False)
        else:
            self.events.append(("mismatch", first.index, second.index))
            self.phase = PHASE_HIDE
            self.timer_at = now + MISMATCH_REVEAL_MS

    def _hide(self, now):
        for index in self.selected:
            self.cards[index].face_up = False
        self.selected = []
        self.current = 1 - self.current
        self.turn += 1
        self.phase = PHASE_FIRST
        self.timer_at = None
        self.events.append(("turn", self.current))
        if self.ai is not None and self.current_player.is_computer:
            self.ai.begin_turn(self.turn)
        self._schedule_computer(now, False)


def synth_tone(rate, frequency, duration, volume=0.5, wave="sine", slide=None, attack=0.004, decay=3.0):
    count = max(1, int(rate * duration))
    attack_samples = max(1, int(rate * attack))
    fade_samples = max(1, int(count * 0.12))
    samples = []
    phase = 0.0
    for i in range(count):
        progress = i / count
        freq = frequency if slide is None else frequency + (slide - frequency) * progress
        phase += 2.0 * math.pi * freq / rate
        if wave == "triangle":
            value = (2.0 / math.pi) * math.asin(math.sin(phase))
        elif wave == "noise":
            value = random.uniform(-1.0, 1.0)
        else:
            value = math.sin(phase)
        envelope = min(1.0, i / attack_samples) * math.exp(-decay * progress) * min(1.0, (count - i) / fade_samples)
        samples.append(value * envelope * volume)
    return samples


def mix_tracks(tracks):
    length = max(len(track) for track in tracks)
    output = [0.0] * length
    for track in tracks:
        for i, value in enumerate(track):
            output[i] += value
    return output


def concat_tracks(tracks):
    output = []
    for track in tracks:
        output.extend(track)
    return output


class SoundManager:
    def __init__(self):
        self.available = False
        self.effects_enabled = True
        self.music_enabled = True
        self.volume = 0.6
        self.sounds = {}
        self.music = None
        self.music_channel = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            frequency, size, channels = pygame.mixer.get_init()
            if abs(size) != 16 or channels not in (1, 2):
                raise pygame.error("unsupported audio format")
            self.rate = frequency
            self.channels = channels
            self._build_sounds()
            pygame.mixer.set_reserved(1)
            self.music_channel = pygame.mixer.Channel(0)
            self.available = True
            self.set_volume(self.volume)
        except Exception:
            self.available = False
            self.sounds = {}
            self.music = None
            self.music_channel = None

    def _to_sound(self, samples):
        data = array.array("h")
        for value in samples:
            sample = int(clamp(value, -1.0, 1.0) * 32767)
            data.append(sample)
            if self.channels == 2:
                data.append(sample)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def _build_sounds(self):
        rate = self.rate
        flip = mix_tracks(
            [
                synth_tone(rate, 0, 0.05, 0.22, "noise", decay=6.0),
                synth_tone(rate, 900, 0.07, 0.28, "sine", slide=380, decay=4.0),
            ]
        )
        match = concat_tracks(
            [
                synth_tone(rate, 523.25, 0.1, 0.4, "triangle", decay=1.5),
                synth_tone(rate, 659.25, 0.1, 0.4, "triangle", decay=1.5),
                synth_tone(rate, 783.99, 0.1, 0.4, "triangle", decay=1.5),
                synth_tone(rate, 1046.5, 0.26, 0.4, "triangle", decay=2.5),
            ]
        )
        fail = concat_tracks(
            [
                synth_tone(rate, 392.0, 0.12, 0.34, "triangle", slide=340, decay=1.5),
                synth_tone(rate, 311.0, 0.22, 0.34, "triangle", slide=246, decay=2.5),
            ]
        )
        click = synth_tone(rate, 760, 0.07, 0.35, "sine", slide=1000, decay=3.5)
        fanfare = [523.25, 659.25, 783.99, 1046.5, 783.99, 1046.5]
        victory_notes = [synth_tone(rate, f, 0.14, 0.36, "triangle", decay=1.2) for f in fanfare]
        chord = mix_tracks(
            [synth_tone(rate, f, 0.7, 0.22, "triangle", decay=2.0) for f in (1046.5, 1318.5, 1568.0)]
        )
        self.sounds = {
            "flip": self._to_sound(flip),
            "match": self._to_sound(match),
            "fail": self._to_sound(fail),
            "click": self._to_sound(click),
            "victory": self._to_sound(concat_tracks(victory_notes + [chord])),
        }
        self.music = self._to_sound(self._build_music())

    def _build_music(self):
        rate = self.rate
        step = 0.36
        melody_notes = [659.25, 783.99, 880.0, 783.99, 659.25, 587.33, 523.25, 587.33,
                        659.25, 783.99, 659.25, 587.33, 523.25, 587.33, 659.25, None]
        melody = []
        for note in melody_notes:
            if note is None:
                melody.extend([0.0] * int(rate * step))
            else:
                melody.extend(synth_tone(rate, note, step, 0.15, "triangle", decay=2.2))
        bass = []
        for note in (130.81, 98.0, 110.0, 87.31):
            bass.extend(synth_tone(rate, note, step * 4, 0.16, "sine", decay=0.8))
        return mix_tracks([melody, bass])

    def play(self, name):
        if not self.available or not self.effects_enabled:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.stop()
            sound.play()
        except pygame.error:
            pass

    def set_volume(self, value):
        self.volume = clamp(value, 0.0, 1.0)
        if not self.available:
            return
        for sound in self.sounds.values():
            sound.set_volume(self.volume)
        if self.music is not None:
            self.music.set_volume(0.35 * self.volume)

    def set_effects_enabled(self, enabled):
        self.effects_enabled = enabled

    def toggle_effects(self):
        self.effects_enabled = not self.effects_enabled

    def toggle_music(self):
        self.music_enabled = not self.music_enabled
        self.sync_music()

    def start_music(self):
        self.sync_music()

    def sync_music(self):
        if not self.available or self.music_channel is None:
            return
        try:
            if self.music_enabled:
                if not self.music_channel.get_busy():
                    self.music_channel.play(self.music, loops=-1)
            else:
                self.music_channel.stop()
        except pygame.error:
            pass


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity", "shape", "angle", "spin")

    def __init__(self, x, y, vx, vy, life, color, size, gravity, shape, angle=0.0, spin=0.0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size
        self.gravity = gravity
        self.shape = shape
        self.angle = angle
        self.spin = spin


class AnimationManager:
    def __init__(self):
        self.particles = []
        self.texts = []
        self.banner = None

    def clear(self):
        self.particles = []
        self.texts = []
        self.banner = None

    def burst(self, x, y, color, count=22):
        for _ in range(count):
            angle = random.uniform(0.0, 2.0 * math.pi)
            speed = random.uniform(90.0, 300.0)
            tint = mix(color, WHITE, random.uniform(0.0, 0.55))
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed - 60.0,
                         random.uniform(0.5, 0.95), tint, random.uniform(3.0, 6.5), 420.0, "circle")
            )

    def confetti(self, count, spread_y=False):
        for _ in range(count):
            y = random.uniform(-HEIGHT * 0.5, -10.0) if spread_y else random.uniform(-30.0, -5.0)
            self.particles.append(
                Particle(random.uniform(0, WIDTH), y, random.uniform(-40.0, 40.0), random.uniform(90.0, 230.0),
                         random.uniform(3.0, 5.5), random.choice(CONFETTI_COLORS), random.uniform(5.0, 9.0), 30.0,
                         "paper", random.uniform(0.0, 6.28), random.uniform(-6.0, 6.0))
            )

    def float_text(self, text, x, y, color):
        self.texts.append({"text": text, "x": x, "y": y, "color": color, "life": 1.1})

    def show_banner(self, text, color):
        self.banner = {"text": text, "color": color, "age": 0.0, "duration": 1.5}

    def update(self, dt_ms):
        dt = dt_ms / 1000.0
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            if p.y < HEIGHT + 20:
                alive.append(p)
        self.particles = alive
        for item in self.texts:
            item["life"] -= dt
            item["y"] -= 60.0 * dt
        self.texts = [item for item in self.texts if item["life"] > 0.0]
        if self.banner is not None:
            self.banner["age"] += dt
            if self.banner["age"] >= self.banner["duration"]:
                self.banner = None

    def draw(self, surface, renderer):
        for p in self.particles:
            fade = clamp(p.life / p.max_life, 0.0, 1.0)
            if p.shape == "circle":
                radius = max(1, int(p.size * fade))
                pygame.draw.circle(surface, p.color, (int(p.x), int(p.y)), radius)
            else:
                half_w, half_h = p.size * 0.5, p.size * 0.9
                cos_a, sin_a = math.cos(p.angle), math.sin(p.angle)
                corners = []
                for cx, cy in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)):
                    corners.append((p.x + cx * cos_a - cy * sin_a, p.y + cx * sin_a + cy * cos_a))
                pygame.draw.polygon(surface, p.color, corners)
        for item in self.texts:
            image = renderer.text_surface(item["text"], 34, item["color"], True)
            image.set_alpha(int(255 * clamp(item["life"] / 0.4, 0.0, 1.0)))
            surface.blit(image, image.get_rect(center=(int(item["x"]), int(item["y"]))))
        if self.banner is not None:
            self._draw_banner(surface, renderer)

    def _draw_banner(self, surface, renderer):
        banner = self.banner
        label = renderer.text_surface(banner["text"], 24, WHITE, True)
        width, height = label.get_width() + 44, 40
        pill = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(pill, mix(banner["color"], DARK, 0.25), pill.get_rect(), border_radius=20)
        pygame.draw.rect(pill, mix(banner["color"], WHITE, 0.5), pill.get_rect(), 2, border_radius=20)
        pill.blit(label, label.get_rect(center=pill.get_rect().center))
        scale = ease_out_back(banner["age"] / 0.3)
        if abs(scale - 1.0) > 0.01:
            pill = pygame.transform.smoothscale(pill, (max(2, int(width * scale)), max(2, int(height * scale))))
        remaining = banner["duration"] - banner["age"]
        pill.set_alpha(int(255 * clamp(remaining / 0.3, 0.0, 1.0)))
        surface.blit(pill, pill.get_rect(center=(WIDTH // 2, 74)))


class FloatingBackground:
    def __init__(self):
        self.items = []
        for i in range(16):
            size = random.randint(30, 90)
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            kind = i % 3
            if kind == 0:
                pygame.draw.circle(surface, (255, 255, 255, 20), (size // 2, size // 2), size // 2)
            elif kind == 1:
                pygame.draw.rect(surface, (255, 255, 255, 16), surface.get_rect(), border_radius=size // 5)
                pygame.draw.rect(surface, (255, 255, 255, 34), surface.get_rect(), 2, border_radius=size // 5)
            else:
                pygame.draw.circle(surface, (255, 255, 255, 30), (size // 2, size // 2), size // 2, 3)
            self.items.append(
                {
                    "x": random.uniform(0, WIDTH),
                    "y": random.uniform(0, HEIGHT),
                    "size": size,
                    "speed": random.uniform(8.0, 26.0),
                    "sway": random.uniform(0.3, 1.0),
                    "phase": random.uniform(0.0, 6.28),
                    "surface": surface,
                }
            )

    def update(self, dt_ms):
        for item in self.items:
            item["y"] -= item["speed"] * dt_ms / 1000.0
            if item["y"] < -item["size"]:
                item["y"] = HEIGHT + item["size"]
                item["x"] = random.uniform(0, WIDTH)

    def draw(self, surface, time_s):
        for item in self.items:
            x = item["x"] + math.sin(time_s * item["sway"] + item["phase"]) * 18.0
            surface.blit(item["surface"], (int(x), int(item["y"])))


class Renderer:
    def __init__(self):
        self.fonts = {}
        self.panel_cache = {}
        self.shadow_cache = {}
        self.background = self._build_background()
        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.overlay.fill((8, 10, 30, 170))
        self.illustrations = {i: render_illustration(item[1], 84) for i, item in enumerate(ILLUSTRATIONS)}
        self.thumbnails = {i: render_illustration(item[1], 28) for i, item in enumerate(ILLUSTRATIONS)}
        self.star_icon = render_illustration(draw_star, 64)
        self.card_back = self._build_card_back()
        self.faces = {}
        for identity in range(PAIR_COUNT):
            for matched in (False, True):
                self.faces[(identity, matched)] = self._build_face(identity, matched)

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("segoeui,helveticaneue,arial,dejavusans", size, bold=bold)
        return self.fonts[key]

    def text_surface(self, string, size, color, bold=False):
        return self.font(size, bold).render(string, True, color)

    def text(self, surface, string, size, color, pos, anchor="center", bold=False, shadow=False):
        font = self.font(size, bold)
        image = font.render(string, True, color)
        rect = image.get_rect()
        setattr(rect, anchor, (int(pos[0]), int(pos[1])))
        if shadow:
            surface.blit(font.render(string, True, (10, 12, 40)), rect.move(2, 3))
        surface.blit(image, rect)
        return rect

    def wrap(self, string, size, max_width, bold=False):
        font = self.font(size, bold)
        lines, current = [], ""
        for word in string.split():
            trial = word if not current else current + " " + word
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def panel(self, surface, rect, fill=PANEL_FILL, border=PANEL_BORDER, radius=18):
        key = (rect.width, rect.height, fill, border, radius)
        image = self.panel_cache.get(key)
        if image is None:
            image = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(image, fill, image.get_rect(), border_radius=radius)
            if border:
                pygame.draw.rect(image, border, image.get_rect(), 2, border_radius=radius)
            self.panel_cache[key] = image
        surface.blit(image, rect.topleft)

    def shadow(self, surface, rect, radius=14, offset=(0, 6)):
        pad = 12
        key = (rect.width, rect.height, radius)
        image = self.shadow_cache.get(key)
        if image is None:
            image = pygame.Surface((rect.width + 2 * pad, rect.height + 2 * pad), pygame.SRCALPHA)
            for i in range(pad):
                grow = pad - i
                ring = pygame.Rect(pad - grow, pad - grow, rect.width + 2 * grow, rect.height + 2 * grow)
                pygame.draw.rect(image, (0, 0, 0, 6 + 4 * i), ring, border_radius=radius + grow)
            self.shadow_cache[key] = image
        surface.blit(image, (rect.x - pad + offset[0], rect.y - pad + offset[1]))

    def _build_background(self):
        surface = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            pygame.draw.line(surface, mix(BG_TOP, BG_BOTTOM, y / HEIGHT), (0, y), (WIDTH, y))
        return surface

    def _build_card_back(self):
        surface = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
        full = surface.get_rect()
        pygame.draw.rect(surface, (238, 240, 255), full, border_radius=14)
        inner = full.inflate(-10, -10)
        pygame.draw.rect(surface, (66, 78, 178), inner, border_radius=10)
        surface.set_clip(inner.inflate(-10, -10))
        for gx in range(-1, CARD_W // 16 + 2):
            for gy in range(-1, CARD_H // 16 + 2):
                cx = gx * 16 + (8 if gy % 2 else 0)
                cy = gy * 16
                pygame.draw.polygon(
                    surface, (92, 106, 210), [(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)]
                )
        surface.set_clip(None)
        pygame.draw.rect(surface, WHITE, inner, 2, border_radius=10)
        center = full.center
        pygame.draw.circle(surface, (36, 44, 120), (center[0], center[1] + 2), 27)
        pygame.draw.circle(surface, GOLD, center, 24)
        pygame.draw.circle(surface, (214, 150, 20), center, 24, 3)
        mark = self.font(40, True).render("?", True, (60, 44, 20))
        surface.blit(mark, mark.get_rect(center=center))
        return surface

    def _build_face(self, identity, matched):
        name, _, tint, border = ILLUSTRATIONS[identity]
        surface = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
        full = surface.get_rect()
        edge = GREEN if matched else border
        fill = mix(tint, (206, 255, 220), 0.4) if matched else tint
        pygame.draw.rect(surface, edge, full, border_radius=14)
        pygame.draw.rect(surface, fill, full.inflate(-8, -8), border_radius=11)
        art = self.illustrations[identity]
        surface.blit(art, art.get_rect(center=(full.centerx, 54)))
        label = self.font(15, True).render(name, True, mix(border, DARK, 0.45))
        surface.blit(label, label.get_rect(center=(full.centerx, CARD_H - 15)))
        return surface

    def draw_card(self, surface, card, time_s):
        progress = card.flip
        squeeze = abs(1.0 - 2.0 * progress)
        pop = 1.0 + 0.12 * math.sin(math.pi * (1.0 - card.pulse)) if card.pulse > 0.0 else 1.0
        width = max(2, int(CARD_W * squeeze * pop))
        height = int(CARD_H * pop)
        face_up = progress >= 0.5
        image = self.faces[(card.identity, card.matched)] if face_up else self.card_back
        if width != CARD_W or height != CARD_H:
            image = pygame.transform.smoothscale(image, (width, height))
        lift = card.hover * 6.0 + math.sin(math.pi * progress) * 12.0
        shake = math.sin(card.shake * 25.0) * 6.0 * card.shake
        rect = image.get_rect(center=(int(card.center_x + shake), int(card.center_y - lift)))
        self.shadow(surface, rect, 14, (0, int(6 + lift * 0.6)))
        surface.blit(image, rect)
        if card.shake > 0.0:
            pygame.draw.rect(surface, RED, rect, 4, border_radius=14)
        elif card.matched and progress >= 1.0:
            glow = 0.5 + 0.5 * math.sin(time_s * 3.0 + card.index)
            pygame.draw.rect(surface, mix(GOLD, WHITE, glow * 0.6), rect, 3, border_radius=14)
        elif card.hover > 0.05 and not face_up:
            pygame.draw.rect(surface, WHITE, rect, 3, border_radius=14)

    def draw_avatar(self, surface, center, radius, color, computer):
        cx, cy = center
        pygame.draw.circle(surface, color, center, radius)
        pygame.draw.circle(surface, mix(color, WHITE, 0.55), center, radius, 3)
        if computer:
            face = pygame.Rect(0, 0, int(radius * 1.1), int(radius * 0.8))
            face.center = (cx, cy + 3)
            pygame.draw.rect(surface, WHITE, face, border_radius=6)
            for dx in (-face.width // 4, face.width // 4):
                pygame.draw.circle(surface, color, (face.centerx + dx, face.centery), 4)
            pygame.draw.line(surface, WHITE, (cx, face.top), (cx, face.top - 7), 3)
            pygame.draw.circle(surface, WHITE, (cx, face.top - 8), 3)
        else:
            pygame.draw.circle(surface, WHITE, (cx, cy - 6), int(radius * 0.32))
            body = pygame.Rect(0, 0, int(radius * 1.0), int(radius * 0.7))
            body.midtop = (cx, cy + int(radius * 0.12))
            pygame.draw.ellipse(surface, WHITE, body)


class Button:
    def __init__(self, label, rect, action=None, color=COLOR_BLUE, font_size=26, label_fn=None, selected_fn=None):
        self.label = label
        self.rect = rect
        self.action = action
        self.color = color
        self.font_size = font_size
        self.label_fn = label_fn
        self.selected_fn = selected_fn
        self.hover = 0.0

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    def update(self, dt, mouse):
        target = 1.0 if self.rect.collidepoint(mouse) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt / 90.0)

    def draw(self, renderer, surface):
        label = self.label_fn() if self.label_fn else self.label
        selected = self.selected_fn() if self.selected_fn else False
        lift = int(round(3 * self.hover))
        body = self.rect.inflate(int(6 * self.hover), int(4 * self.hover)).move(0, -lift)
        renderer.shadow(surface, body, 14, (0, 5))
        pygame.draw.rect(surface, mix(self.color, WHITE, 0.16 * self.hover), body, border_radius=14)
        gloss = pygame.Rect(body.x + 4, body.y + 4, body.width - 8, max(2, body.height // 2 - 2))
        renderer.panel(surface, gloss, (255, 255, 255, 38), None, 11)
        border = GOLD if selected else mix(self.color, WHITE, 0.45)
        pygame.draw.rect(surface, border, body, 4 if selected else 2, border_radius=14)
        renderer.text(surface, label, self.font_size, WHITE, body.center, bold=True, shadow=True)
        if selected:
            cx, cy = body.right - 26, body.centery
            pygame.draw.circle(surface, GOLD, (cx, cy), 11)
            pygame.draw.lines(surface, DARK, False, [(cx - 5, cy), (cx - 1, cy + 4), (cx + 6, cy - 5)], 3)


class Slider:
    def __init__(self, rect, value):
        self.rect = rect
        self.value = value
        self.dragging = False

    def hit(self, pos):
        return self.rect.inflate(30, 34).collidepoint(pos)

    def set_from_x(self, x):
        self.value = clamp((x - self.rect.left) / self.rect.width, 0.0, 1.0)

    def draw(self, renderer, surface):
        track = self.rect
        pygame.draw.rect(surface, (40, 44, 104), track, border_radius=6)
        fill = pygame.Rect(track.left, track.top, int(track.width * self.value), track.height)
        if fill.width > 0:
            pygame.draw.rect(surface, GOLD, fill, border_radius=6)
        pygame.draw.rect(surface, mix(GOLD, WHITE, 0.5), track, 2, border_radius=6)
        knob = (int(track.left + track.width * self.value), track.centery)
        renderer.shadow(surface, pygame.Rect(knob[0] - 14, knob[1] - 14, 28, 28), 14, (0, 3))
        pygame.draw.circle(surface, WHITE, knob, 14)
        pygame.draw.circle(surface, GOLD, knob, 14, 4)


class App:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.renderer = Renderer()
        self.sound = SoundManager()
        self.anim = AnimationManager()
        self.background = FloatingBackground()
        self.running = True
        self.time = 0.0
        self.state = STATE_MENU
        self.buttons = []
        self.slider = None
        self.dialog = None
        self.game = None
        self.game_clock = 0.0
        self.difficulty = "Medium"
        self.confetti_timer = 0.0
        self.decor = []
        self.sound.start_music()
        self._build_state(STATE_MENU)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS), 50)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def quit(self):
        self.running = False

    def go(self, state):
        if state not in TRANSITIONS.get(self.state, ()):
            return False
        self.state = state
        self.dialog = None
        self.anim.clear()
        self._build_state(state)
        return True

    def start_game(self, mode, difficulty=None):
        if difficulty is not None:
            self.difficulty = difficulty
        if STATE_PLAYING not in TRANSITIONS.get(self.state, ()):
            return
        self.game = Game(mode, self.difficulty)
        self.game_clock = 0.0
        self.anim.clear()
        self.go(STATE_PLAYING)

    def set_difficulty(self, name):
        self.difficulty = name

    def toggle_effects(self):
        self.sound.toggle_effects()

    def toggle_music(self):
        self.sound.toggle_music()

    def _build_state(self, state):
        self.slider = None
        builders = {
            STATE_MENU: self._build_menu,
            STATE_SELECT: lambda: self._build_difficulty(True),
            STATE_DIFFICULTY: lambda: self._build_difficulty(False),
            STATE_INSTRUCTIONS: self._build_instructions,
            STATE_SOUND: self._build_sound,
            STATE_PLAYING: self._build_game,
            STATE_RESULTS: self._build_results,
        }
        builders[state]()

    def _back_button(self, top=596):
        rect = pygame.Rect(0, 0, 200, 50)
        rect.centerx = WIDTH // 2
        rect.top = top
        return Button("Back", rect, lambda: self.go(STATE_MENU), COLOR_SLATE, 24)

    def _build_menu(self):
        specs = [
            ("Play Against Computer", COLOR_BLUE, lambda: self.go(STATE_SELECT)),
            ("Play Against Player", COLOR_CORAL, lambda: self.start_game(MODE_PLAYER)),
            ("Difficulty", COLOR_PURPLE, lambda: self.go(STATE_DIFFICULTY)),
            ("Instructions", COLOR_TEAL, lambda: self.go(STATE_INSTRUCTIONS)),
            ("Sound Settings", COLOR_AMBER, lambda: self.go(STATE_SOUND)),
            ("Exit Game", COLOR_ROSE, self.quit),
        ]
        self.buttons = []
        for i, (label, color, action) in enumerate(specs):
            rect = pygame.Rect(0, 0, 380, 54)
            rect.centerx = WIDTH // 2
            rect.top = 214 + i * 66
            self.buttons.append(Button(label, rect, action, color))
        positions = [(36, 60), (116, 260), (WIDTH - 36 - CARD_W, 60), (WIDTH - 116 - CARD_W, 260)]
        self.decor = []
        for i, (x, y) in enumerate(positions):
            card = Card(i, random.randrange(PAIR_COUNT), x, y)
            self.decor.append({"card": card, "timer": random.uniform(600, 2400)})

    def _build_difficulty(self, starting):
        self.buttons = []
        for i, name in enumerate(DIFFICULTIES):
            rect = pygame.Rect(0, 0, 360, 56)
            rect.centerx = WIDTH // 2
            rect.top = 190 + i * 108
            if starting:
                action = lambda n=name: self.start_game(MODE_COMPUTER, n)
            else:
                action = lambda n=name: self.set_difficulty(n)
            self.buttons.append(
                Button(name, rect, action, DIFFICULTY_COLORS[name], 28, selected_fn=lambda n=name: self.difficulty == n)
            )
        self.buttons.append(self._back_button(596))

    def _build_instructions(self):
        rect = pygame.Rect(0, 0, 200, 50)
        rect.centerx = WIDTH // 2
        rect.top = 610
        self.buttons = [Button("Back", rect, lambda: self.go(STATE_MENU), COLOR_SLATE, 24)]

    def _build_sound(self):
        effects = pygame.Rect(0, 0, 420, 56)
        effects.centerx = WIDTH // 2
        effects.top = 160
        music = pygame.Rect(0, 0, 420, 56)
        music.centerx = WIDTH // 2
        music.top = 350
        self.buttons = [
            Button(
                "", effects, self.toggle_effects, COLOR_BLUE, 26,
                label_fn=lambda: "Sound Effects: " + ("ON" if self.sound.effects_enabled else "OFF"),
            ),
            Button(
                "", music, self.toggle_music, COLOR_PURPLE, 26,
                label_fn=lambda: "Background Music: " + ("ON" if self.sound.music_enabled else "OFF"),
            ),
            self._back_button(570),
        ]
        self.slider = Slider(pygame.Rect(WIDTH // 2 - 180, 295, 360, 10), self.sound.volume)

    def _build_game(self):
        self.buttons = [
            Button("Main Menu", pygame.Rect(16, 10, 130, 40), self.ask_leave, COLOR_SLATE, 20),
            Button("Restart", pygame.Rect(154, 10, 110, 40), self.ask_restart, COLOR_TEAL, 20),
            Button(
                "", pygame.Rect(WIDTH - 16 - 150, 10, 150, 40), self.toggle_effects, COLOR_AMBER, 20,
                label_fn=lambda: "Sound: " + ("ON" if self.sound.effects_enabled else "OFF"),
            ),
        ]
        self.confetti_timer = 0.0

    def _build_results(self):
        specs = [
            ("Play Again", COLOR_BLUE, self.play_again),
            ("Main Menu", COLOR_PURPLE, lambda: self.go(STATE_MENU)),
            ("Exit Game", COLOR_ROSE, self.quit),
        ]
        self.buttons = []
        for i, (label, color, action) in enumerate(specs):
            rect = pygame.Rect(0, 0, 220, 58)
            rect.centerx = WIDTH // 2 + (i - 1) * 240
            rect.top = 566
            self.buttons.append(Button(label, rect, action, color, 24))
        self.confetti_timer = 0.0

    def play_again(self):
        self.start_game(self.game.mode, self.game.difficulty)

    def _needs_confirmation(self):
        return self.game is not None and self.game.moves_made > 0 and not self.game.finished

    def ask_confirmation(self, text, on_yes):
        yes = Button("Yes", pygame.Rect(WIDTH // 2 - 170, HEIGHT // 2 + 28, 150, 50), None, COLOR_TEAL, 24)
        no = Button("No", pygame.Rect(WIDTH // 2 + 20, HEIGHT // 2 + 28, 150, 50), None, COLOR_ROSE, 24)
        yes.action = lambda: self._confirm(on_yes)
        no.action = self.close_dialog
        self.dialog = {"text": text, "buttons": [yes, no]}

    def _confirm(self, on_yes):
        self.dialog = None
        on_yes()

    def close_dialog(self):
        self.dialog = None

    def ask_restart(self):
        if self._needs_confirmation():
            self.ask_confirmation("Restart the current game?", self.restart_game)
        else:
            self.restart_game()

    def ask_leave(self):
        if self._needs_confirmation():
            self.ask_confirmation("Leave this game and return to the menu?", lambda: self.go(STATE_MENU))
        else:
            self.go(STATE_MENU)

    def restart_game(self):
        self.game.new_round(self.game_clock)
        self.anim.clear()

    def show_results(self):
        if self.go(STATE_RESULTS):
            self.sound.play("victory")
            self.anim.confetti(110, True)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            self.on_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.on_mouse_down(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            self.on_mouse_motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_mouse_up(event.pos)

    def on_key(self, key):
        if key != pygame.K_ESCAPE:
            return
        if self.dialog:
            self.close_dialog()
        elif self.state == STATE_PLAYING:
            self.ask_leave()
        elif self.state != STATE_MENU:
            self.go(STATE_MENU)

    def press(self, button):
        self.sound.play("click")
        if button.action:
            button.action()

    def on_mouse_down(self, pos):
        if self.dialog:
            for button in self.dialog["buttons"]:
                if button.hit(pos):
                    self.press(button)
                    return
            return
        for button in self.buttons:
            if button.hit(pos):
                self.press(button)
                return
        if self.state == STATE_SOUND and self.slider is not None and self.slider.hit(pos):
            self.slider.dragging = True
            self._apply_slider(pos)
        elif self.state == STATE_PLAYING and self.game.accepting_human_input:
            for card in self.game.cards:
                if card.contains(pos[0], pos[1]):
                    self.game.flip_card(card.index, self.game_clock)
                    break

    def on_mouse_motion(self, pos):
        if self.slider is not None and self.slider.dragging:
            self._apply_slider(pos)

    def on_mouse_up(self, pos):
        if self.slider is not None and self.slider.dragging:
            self.slider.dragging = False
            self._apply_slider(pos)
            self.sound.play("flip")

    def _apply_slider(self, pos):
        self.slider.set_from_x(pos[0])
        self.sound.set_volume(self.slider.value)

    def update(self, dt):
        self.time += dt / 1000.0
        mouse = pygame.mouse.get_pos()
        self.background.update(dt)
        idle = (-1000, -1000)
        for button in self.buttons:
            button.update(dt, idle if self.dialog else mouse)
        if self.dialog:
            for button in self.dialog["buttons"]:
                button.update(dt, mouse)
        if self.state == STATE_MENU:
            self._update_decor(dt)
        elif self.state == STATE_PLAYING:
            self._update_game(dt, mouse)
        elif self.state == STATE_RESULTS:
            self.confetti_timer += dt
            if self.confetti_timer >= 160:
                self.confetti_timer = 0.0
                self.anim.confetti(5)
        self.anim.update(dt)

    def _update_decor(self, dt):
        for item in self.decor:
            card = item["card"]
            item["timer"] -= dt
            if item["timer"] <= 0:
                if card.face_up:
                    card.face_up = False
                else:
                    card.identity = random.randrange(PAIR_COUNT)
                    card.face_up = True
                item["timer"] = random.uniform(1400, 3000)
            card.update(dt, False)

    def _update_game(self, dt, mouse):
        game = self.game
        if not self.dialog:
            self.game_clock += dt
            game.update(self.game_clock)
        for event in game.pop_events():
            self._handle_game_event(event)
        can_pick = game.accepting_human_input and not self.dialog
        for card in game.cards:
            hovered = can_pick and card.selectable and card.contains(mouse[0], mouse[1])
            card.update(dt, hovered)
        if game.finished and self.game_clock - game.finished_at >= GAME_OVER_DELAY_MS:
            self.show_results()

    def _turn_text(self, owner, again):
        game = self.game
        player = game.players[owner]
        if game.mode == MODE_COMPUTER:
            if owner == 0:
                return ("Match! Go again!" if again else "Your turn!"), player.color
            return ("Computer goes again" if again else "Computer's turn"), player.color
        return (f"{player.name} goes again!" if again else f"{player.name}'s turn!"), player.color

    def _handle_game_event(self, event):
        game = self.game
        kind = event[0]
        if kind == "flip":
            self.sound.play("flip")
        elif kind == "match":
            _, first, second, owner = event
            self.sound.play("match")
            color = game.players[owner].color
            for index in (first, second):
                card = game.cards[index]
                card.pulse = 1.0
                self.anim.burst(card.center_x, card.center_y, color)
            mid_x = (game.cards[first].center_x + game.cards[second].center_x) / 2
            mid_y = (game.cards[first].center_y + game.cards[second].center_y) / 2
            self.anim.float_text("+1", mid_x, mid_y, color)
        elif kind == "mismatch":
            self.sound.play("fail")
            game.cards[event[1]].shake = 1.0
            game.cards[event[2]].shake = 1.0
        elif kind == "turn":
            text, color = self._turn_text(event[1], False)
            self.anim.show_banner(text, color)
        elif kind == "extra_turn":
            text, color = self._turn_text(event[1], True)
            self.anim.show_banner(text, color)
        elif kind == "game_over":
            self.anim.confetti(60)

    def draw(self):
        self.screen.blit(self.renderer.background, (0, 0))
        self.background.draw(self.screen, self.time)
        if self.state == STATE_MENU:
            self._draw_menu()
        elif self.state in (STATE_SELECT, STATE_DIFFICULTY):
            self._draw_difficulty()
        elif self.state == STATE_INSTRUCTIONS:
            self._draw_instructions()
        elif self.state == STATE_SOUND:
            self._draw_sound()
        elif self.state == STATE_PLAYING:
            self._draw_game()
        elif self.state == STATE_RESULTS:
            self._draw_results()
        self._draw_buttons()
        self.anim.draw(self.screen, self.renderer)
        if self.dialog:
            self._draw_dialog()

    def _draw_buttons(self):
        for button in self.buttons:
            button.draw(self.renderer, self.screen)

    def _draw_title(self, text, center_y, size):
        r = self.renderer
        font = r.font(size, True)
        widths = [font.size(ch)[0] for ch in text]
        spacing = 3
        total = sum(widths) + spacing * (len(text) - 1)
        x = WIDTH / 2 - total / 2
        for i, (ch, width) in enumerate(zip(text, widths)):
            if ch != " ":
                bob = math.sin(self.time * 2.4 + i * 0.55) * 6
                color = TITLE_COLORS[i % len(TITLE_COLORS)]
                r.text(self.screen, ch, size, color, (x, center_y + bob), "midleft", True, True)
            x += width + spacing

    def _draw_menu(self):
        r = self.renderer
        for item in self.decor:
            r.draw_card(self.screen, item["card"], self.time)
        self._draw_title("MEMORY MATCH", 104, 72)
        r.text(self.screen, "Find all 10 pairs!", 24, MUTED, (WIDTH // 2, 164), bold=True)

    def _draw_difficulty(self):
        r = self.renderer
        starting = self.state == STATE_SELECT
        title = "Choose Difficulty" if starting else "Difficulty"
        r.text(self.screen, title, 48, WHITE, (WIDTH // 2, 80), bold=True, shadow=True)
        subtitle = "Pick your opponent to start the game" if starting else "Current: " + self.difficulty
        r.text(self.screen, subtitle, 22, MUTED, (WIDTH // 2, 132))
        for i, name in enumerate(DIFFICULTIES):
            button = self.buttons[i]
            r.text(self.screen, AI_PROFILES[name].description, 19, MUTED, (WIDTH // 2, button.rect.bottom + 22))

    def _draw_instructions(self):
        r = self.renderer
        panel = pygame.Rect(80, 40, 840, 550)
        r.panel(self.screen, panel)
        r.text(self.screen, "How to Play", 34, GOLD, (WIDTH // 2, 76), bold=True)
        y = 116
        for rule in RULES:
            pygame.draw.circle(self.screen, GOLD, (116, y), 5)
            r.text(self.screen, rule, 20, TEXT, (134, y), "midleft")
            y += 28
        r.text(self.screen, "Computer Difficulty", 28, GOLD, (WIDTH // 2, y + 24), bold=True)
        y += 62
        for name, description in AI_NOTES:
            r.text(self.screen, name, 21, DIFFICULTY_COLORS[name], (116, y), "topleft", True)
            for i, line in enumerate(r.wrap(description, 19, 650)):
                r.text(self.screen, line, 19, TEXT, (236, y + i * 24), "topleft")
            y += 56

    def _draw_sound(self):
        r = self.renderer
        r.text(self.screen, "Sound Settings", 48, WHITE, (WIDTH // 2, 84), bold=True, shadow=True)
        percent = int(round(self.sound.volume * 100))
        r.text(self.screen, f"Volume: {percent}%", 24, TEXT, (WIDTH // 2, 262), bold=True)
        self.slider.draw(r, self.screen)
        if self.sound.available:
            note, color = "Changes apply immediately.", MUTED
        else:
            note, color = "Audio is unavailable on this system, so the game will run silently.", RED
        r.text(self.screen, note, 20, color, (WIDTH // 2, 450))
        r.text(self.screen, "Release the slider to hear a preview.", 18, MUTED, (WIDTH // 2, 485))

    def _status_line(self):
        game = self.game
        player = game.current_player
        if game.phase == PHASE_OVER:
            return "All pairs found!", GOLD
        if game.phase == PHASE_RESOLVE:
            return "Checking the pair...", TEXT
        if game.phase == PHASE_HIDE:
            return "No match! Remember them...", MUTED
        if player.is_computer:
            if game.phase == PHASE_FIRST:
                return "Computer is thinking...", player.color
            return "Computer is picking...", player.color
        who = "Your turn" if game.mode == MODE_COMPUTER else player.name
        if game.phase == PHASE_FIRST:
            return f"{who}: pick a card", player.color
        return f"{who}: pick a second card", player.color

    def _draw_game(self):
        game = self.game
        r = self.renderer
        status, color = self._status_line()
        r.text(self.screen, status, 26, color, (WIDTH // 2, 30), bold=True, shadow=True)
        backdrop = pygame.Rect(BOARD_X - 10, BOARD_Y - 8, BOARD_W + 20, BOARD_H + 16)
        r.panel(self.screen, backdrop, (255, 255, 255, 18), PANEL_BORDER, 20)
        for card in game.cards:
            r.draw_card(self.screen, card, self.time)
        self._draw_player_panel(pygame.Rect(16, 100, 180, 250), 0)
        self._draw_player_panel(pygame.Rect(804, 100, 180, 250), 1)
        self._draw_progress_panel(pygame.Rect(16, 366, 180, 252))
        self._draw_info_panel(pygame.Rect(804, 366, 180, 252))

    def _draw_player_panel(self, rect, index):
        game = self.game
        r = self.renderer
        player = game.players[index]
        active = not game.finished and game.current == index
        r.panel(self.screen, rect)
        if active:
            glow = mix(player.color, WHITE, 0.25 + 0.25 * math.sin(self.time * 4.0))
            pygame.draw.rect(self.screen, glow, rect.inflate(6, 6), 4, border_radius=21)
        r.draw_avatar(self.screen, (rect.centerx, rect.top + 40), 26, player.color, player.is_computer)
        r.text(self.screen, player.name, 24, WHITE, (rect.centerx, rect.top + 86), bold=True)
        r.text(self.screen, str(player.score), 84, player.color, (rect.centerx, rect.top + 144), bold=True, shadow=True)
        r.text(self.screen, "pairs", 18, MUTED, (rect.centerx, rect.top + 192))
        tag = pygame.Rect(0, 0, 144, 30)
        tag.center = (rect.centerx, rect.bottom - 26)
        if active:
            pygame.draw.rect(self.screen, player.color, tag, border_radius=15)
            label = "THINKING..." if player.is_computer else "YOUR TURN"
            r.text(self.screen, label, 17, DARK, tag.center, bold=True)
        else:
            pygame.draw.rect(self.screen, mix(DARK, WHITE, 0.15), tag, border_radius=15)
            r.text(self.screen, "waiting", 17, MUTED, tag.center)

    def _draw_progress_panel(self, rect):
        game = self.game
        r = self.renderer
        r.panel(self.screen, rect)
        r.text(self.screen, "PAIRS FOUND", 16, MUTED, (rect.centerx, rect.top + 22), bold=True)
        r.text(self.screen, f"{game.matched_pairs} / {PAIR_COUNT}", 40, GOLD, (rect.centerx, rect.top + 58), bold=True)
        bar = pygame.Rect(rect.left + 16, rect.top + 88, rect.width - 32, 12)
        pygame.draw.rect(self.screen, (40, 44, 104), bar, border_radius=6)
        fill = pygame.Rect(bar.left, bar.top, int(bar.width * game.matched_pairs / PAIR_COUNT), bar.height)
        if fill.width > 0:
            pygame.draw.rect(self.screen, GREEN, fill, border_radius=6)
        r.text(self.screen, f"{game.remaining_pairs} remaining", 18, TEXT, (rect.centerx, rect.top + 120))
        x0 = rect.centerx - 80
        y0 = rect.top + 148
        for identity in range(PAIR_COUNT):
            col, row = identity % 5, identity // 5
            cell = pygame.Rect(x0 + col * 32, y0 + row * 38, 28, 28)
            if identity in game.matched_identities:
                self.screen.blit(r.thumbnails[identity], cell)
            else:
                pygame.draw.circle(self.screen, (66, 72, 140), cell.center, 6)

    def _draw_info_panel(self, rect):
        game = self.game
        r = self.renderer
        r.panel(self.screen, rect)
        r.text(self.screen, "GAME INFO", 16, MUTED, (rect.centerx, rect.top + 22), bold=True)
        if self.sound.available:
            sound_value, sound_color = ("ON" if self.sound.effects_enabled else "OFF"), TEXT
            music_value = "ON" if self.sound.music_enabled else "OFF"
        else:
            sound_value, sound_color, music_value = "N/A", RED, "N/A"
        mode = "vs Computer" if game.mode == MODE_COMPUTER else "2 Players"
        level = game.difficulty if game.mode == MODE_COMPUTER else "-"
        rows = [
            ("Mode", mode, TEXT),
            ("Level", level, DIFFICULTY_COLORS.get(level, TEXT)),
            ("Sound", sound_value, sound_color),
            ("Music", music_value, sound_color),
            ("Turn", str(game.turn), TEXT),
        ]
        y = rect.top + 64
        for key, value, color in rows:
            r.text(self.screen, key, 18, MUTED, (rect.left + 16, y), "midleft")
            r.text(self.screen, value, 18, color, (rect.right - 16, y), "midright", True)
            y += 32

    def _draw_results(self):
        game = self.game
        r = self.renderer
        result = game.result()
        if game.mode == MODE_COMPUTER:
            titles = {0: "You Win!", 1: "Computer Wins!", -1: "It's a Tie!"}
            messages = {
                0: "Brilliant memory! You out-remembered the computer.",
                1: "The computer got this one. Ready for a rematch?",
                -1: "Evenly matched! Try again to break the tie.",
            }
        else:
            titles = {0: "Player 1 Wins!", 1: "Player 2 Wins!", -1: "It's a Tie!"}
            messages = {
                0: "Great game! Player 1 has the sharper memory today.",
                1: "Great game! Player 2 has the sharper memory today.",
                -1: "Evenly matched! Time for a tie-breaker.",
            }
        title_color = GOLD if result == -1 else game.players[result].color
        bob = math.sin(self.time * 3.0) * 6
        r.text(self.screen, titles[result], 72, title_color, (WIDTH // 2, 100 + bob), bold=True, shadow=True)
        panel = pygame.Rect(170, 170, 660, 290)
        r.panel(self.screen, panel)
        for index, center_x in enumerate((330, 670)):
            player = game.players[index]
            if result == index or result == -1:
                self.screen.blit(r.star_icon, r.star_icon.get_rect(center=(center_x, 212)))
            r.text(self.screen, player.name, 30, WHITE, (center_x, 268), bold=True)
            r.text(self.screen, str(player.score), 96, player.color, (center_x, 340), bold=True, shadow=True)
            r.text(self.screen, "pairs", 20, MUTED, (center_x, 402))
        r.text(self.screen, "-", 60, MUTED, (WIDTH // 2, 340), bold=True)
        r.text(self.screen, f"Total matched pairs: {game.matched_pairs}/{PAIR_COUNT}", 22, TEXT, (WIDTH // 2, 438))
        r.text(self.screen, messages[result], 26, GOLD, (WIDTH // 2, 506), bold=True)

    def _draw_dialog(self):
        r = self.renderer
        self.screen.blit(r.overlay, (0, 0))
        panel = pygame.Rect(0, 0, 480, 210)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        r.shadow(self.screen, panel, 20, (0, 8))
        pygame.draw.rect(self.screen, (44, 50, 120), panel, border_radius=20)
        pygame.draw.rect(self.screen, mix(COLOR_SLATE, WHITE, 0.4), panel, 3, border_radius=20)
        r.text(self.screen, self.dialog["text"], 26, WHITE, (panel.centerx, panel.top + 62), bold=True)
        r.text(self.screen, "Your current progress will be lost.", 19, MUTED, (panel.centerx, panel.top + 98))
        for button in self.dialog["buttons"]:
            button.draw(r, self.screen)


def create_window():
    pygame.display.set_caption("Memory Match")
    try:
        return pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
    except pygame.error:
        return pygame.display.set_mode((WIDTH, HEIGHT))


def main():
    try:
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        if not pygame.display.get_init() or not pygame.font.get_init():
            raise pygame.error("display or font module failed to initialise")
        screen = create_window()
    except pygame.error as error:
        print(f"Unable to start Memory Match: {error}")
        pygame.quit()
        return 1
    try:
        App(screen).run()
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())