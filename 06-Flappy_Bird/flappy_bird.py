import argparse
import json
import math
import os
import random
import sys
from array import array

import pygame

WIDTH = 800
HEIGHT = 600
FPS = 60
GROUND_HEIGHT = 80
GROUND_Y = HEIGHT - GROUND_HEIGHT
GROUND_PERIOD = 32

BIRD_X = 200
BIRD_RADIUS = 13
HOVER_Y = 270
GRAVITY = 1500.0
FLAP_VELOCITY = -460.0
MAX_FALL_SPEED = 800.0

PIPE_WIDTH = 68
CAP_WIDTH = 84
CAP_HEIGHT = 30
CAP_OVERHANG = (CAP_WIDTH - PIPE_WIDTH) // 2
PIPE_SPACING = 320
SPAWN_X = WIDTH + 30
MAX_GAP_SHIFT = 125
EDGE_MARGIN = 70

BASE_SPEED = 180.0
SPEED_GAIN = 0.04
SECRET_SPEED = 230.0
GAP_START = 180.0
GAP_MIN = 150.0
GAP_SHRINK = 0.03
SECRET_GAP = 135.0

EASTER_SCORE = 999
FINAL_SCORE = 1000
EASTER_SWAP = 2.0
EASTER_END = 3.4
GAMEOVER_LOCK = 0.75
VICTORY_FADE = 0.9
VICTORY_LOCK = 1.8
SHAKE_TIME = 0.3
MAX_PARTICLES = 380

STATE_MENU = "menu"
STATE_HOWTO = "howto"
STATE_READY = "ready"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_EASTER = "easter"
STATE_SECRET = "secret"
STATE_GAMEOVER = "gameover"
STATE_VICTORY = "victory"

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
SKY = (140, 210, 240)
DARK = (60, 45, 25)
YELLOW = (255, 220, 50)
ORANGE = (247, 160, 40)
BTN_FACE = (247, 160, 40)
BTN_HOVER = (255, 205, 80)
BTN_BORDER = (110, 62, 18)
BTN_SHADOW = (80, 45, 12)
BIRD_BODY = (255, 215, 50)
BIRD_OUTLINE = (120, 75, 10)
GOLD_RAY = (255, 246, 190)
CONFETTI_COLORS = [
    (255, 80, 80),
    (255, 190, 40),
    (90, 220, 90),
    (80, 170, 255),
    (200, 100, 255),
    (255, 120, 200),
    (255, 255, 255),
]
EASTER_COLORS = [(255, 240, 90), (120, 255, 240), (255, 130, 230), (255, 255, 255)]
SECRET_TITLE_COLORS = [(255, 120, 240), (120, 255, 240)]

FOCUS_LOST = getattr(pygame, "WINDOWFOCUSLOST", None)


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def ease_in_out(t):
    return t * t * (3.0 - 2.0 * t)


def fade_in(t, start, duration):
    return int(255 * clamp((t - start) / duration, 0.0, 1.0))


def circle_hits_rect(cx, cy, radius, rx, ry, rw, rh):
    nearest_x = clamp(cx, rx, rx + rw)
    nearest_y = clamp(cy, ry, ry + rh)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx * dx + dy * dy < radius * radius


def get_save_path():
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    return os.path.join(base, "flappy_best.json")


def load_best(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return 0
    value = data.get("best") if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return int(clamp(value, 0, FINAL_SCORE))


def save_best(path, value):
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump({"best": int(value)}, handle)
        os.replace(temp_path, path)
    except OSError:
        pass


def note(start, freq, dur, vol, wave="sine", decay=1.0):
    return (start, freq, freq, dur, vol, wave, decay)


def build_sound_layers():
    sounds = {}
    sounds["flap"] = (0.1, [(0.0, 520.0, 900.0, 0.09, 0.30, "sine", 1.3)])
    sounds["point"] = (
        0.26,
        [
            note(0.0, 988.0, 0.07, 0.13, "square", 0.8),
            note(0.07, 1319.0, 0.17, 0.13, "square", 1.3),
        ],
    )
    sounds["hit"] = (
        0.34,
        [
            (0.0, 0.0, 0.0, 0.12, 0.30, "noise", 2.0),
            (0.0, 240.0, 70.0, 0.30, 0.25, "square", 1.6),
        ],
    )
    sounds["click"] = (0.05, [(0.0, 760.0, 520.0, 0.035, 0.22, "sine", 1.0)])

    easter = [(0.0, 70.0, 160.0, 0.9, 0.30, "triangle", 0.6)]
    arpeggio = [523.25, 659.25, 783.99, 1046.5, 1318.5, 1568.0]
    for index, freq in enumerate(arpeggio):
        start = 0.1 + 0.11 * index
        easter.append(note(start, freq, 0.22, 0.14, "square", 1.4))
        easter.append(note(start, freq * 0.5, 0.22, 0.14, "triangle", 1.2))
    for freq in (523.25, 659.25, 783.99, 1046.5, 1568.0):
        easter.append(note(0.85, freq, 1.3, 0.11, "triangle", 1.1))
        easter.append(note(0.85, freq, 1.0, 0.04, "square", 1.3))
    easter.append((0.85, 1500.0, 3000.0, 0.9, 0.06, "sine", 1.5))
    sounds["easter"] = (2.3, easter)

    victory = []
    melody = [
        (0.00, 523.25, 0.12),
        (0.14, 523.25, 0.12),
        (0.28, 523.25, 0.12),
        (0.42, 523.25, 0.34),
        (0.80, 415.30, 0.34),
        (1.16, 466.16, 0.34),
        (1.52, 523.25, 0.16),
        (1.72, 466.16, 0.12),
        (1.88, 523.25, 0.95),
    ]
    for start, freq, dur in melody:
        victory.append(note(start, freq, dur, 0.13, "square", 0.9))
        victory.append(note(start, freq * 0.5, dur, 0.18, "triangle", 0.9))
    for freq in (659.25, 783.99, 1046.5):
        victory.append(note(1.88, freq, 1.3, 0.10, "triangle", 1.1))
    for index in range(8):
        victory.append(note(1.9 + 0.08 * index, 2000.0 + 150.0 * index, 0.2, 0.06, "sine", 1.5))
    sounds["victory"] = (3.3, victory)
    return sounds


def synthesize(length, layers, rate, channels):
    total = int(length * rate)
    mix = [0.0] * total
    two_pi = 2.0 * math.pi
    attack = max(1, int(0.004 * rate))
    for start, f0, f1, dur, vol, wave, decay in layers:
        first = int(start * rate)
        count = int(dur * rate)
        phase = 0.0
        for i in range(count):
            index = first + i
            if index >= total:
                break
            t = i / count
            phase += (f0 + (f1 - f0) * t) / rate
            cycle = phase % 1.0
            if wave == "sine":
                value = math.sin(two_pi * cycle)
            elif wave == "square":
                value = 1.0 if cycle < 0.5 else -1.0
            elif wave == "triangle":
                value = 4.0 * abs(cycle - 0.5) - 1.0
            else:
                value = random.uniform(-1.0, 1.0)
            envelope = min(1.0, i / attack) * (1.0 - t) ** decay
            mix[index] += value * vol * envelope
    data = array("h")
    for value in mix:
        sample = int(clamp(value, -1.0, 1.0) * 30000)
        for _ in range(channels):
            data.append(sample)
    return pygame.mixer.Sound(buffer=data.tobytes())


class Audio:
    def __init__(self):
        self.enabled = True
        self.available = False
        self.sounds = {}
        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init(22050, -16, 1, 512)
            except pygame.error:
                return
        init = pygame.mixer.get_init()
        if init is None:
            return
        try:
            rate, fmt, channels = init
            if fmt != -16:
                return
            for name, (length, layers) in build_sound_layers().items():
                self.sounds[name] = synthesize(length, layers, rate, channels)
            self.available = True
        except Exception:
            self.sounds = {}
            self.available = False

    def play(self, name):
        if not (self.enabled and self.available):
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.play()
        except pygame.error:
            pass

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled and self.available:
            try:
                pygame.mixer.stop()
            except pygame.error:
                pass
        return self.enabled


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "rot", "vrot", "kind")

    def __init__(self, x, y, vx, vy, life, color, size, kind):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size
        self.kind = kind
        self.rot = random.uniform(0.0, math.tau)
        self.vrot = random.uniform(-9.0, 9.0)


class Bird:
    WING_SEQUENCE = (1, 0, 1, 2)

    def __init__(self):
        self.reset(BIRD_X, HOVER_Y)

    def reset(self, x, y):
        self.x = x
        self.y = y
        self.vel = 0.0
        self.angle = 0.0
        self.flap_timer = 0.0
        self.wing_phase = 0.0
        self.idle = False

    def flap(self):
        self.vel = FLAP_VELOCITY
        self.flap_timer = 0.28

    def step(self, dt):
        self.vel = min(self.vel + GRAVITY * dt, MAX_FALL_SPEED)
        self.y += self.vel * dt

    def animate(self, dt, idle_speed=0.0):
        target = clamp(-self.vel * 0.075, -85.0, 28.0)
        self.angle += (target - self.angle) * min(1.0, dt * 14.0)
        self.idle = idle_speed > 0.0
        if self.flap_timer > 0.0:
            self.flap_timer = max(0.0, self.flap_timer - dt)
            self.wing_phase += dt * 26.0
        else:
            self.wing_phase += dt * idle_speed

    def wing_frame(self):
        if self.flap_timer <= 0.0 and not self.idle:
            return 1
        return self.WING_SEQUENCE[int(self.wing_phase) % 4]


class Pipe:
    __slots__ = ("x", "gap_center", "gap", "scored")

    def __init__(self, x, gap_center, gap):
        self.x = x
        self.gap_center = gap_center
        self.gap = gap
        self.scored = False

    def gap_top(self):
        return self.gap_center - self.gap / 2.0

    def gap_bottom(self):
        return self.gap_center + self.gap / 2.0


class Button:
    def __init__(self, label, center, action, size=(280, 52), silent=False):
        self.label = label
        self.action = action
        self.silent = silent
        self.rect = pygame.Rect(0, 0, size[0], size[1])
        self.rect.center = center

    def text(self):
        return self.label() if callable(self.label) else self.label


def make_gradient(top, bottom):
    surface = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(lerp(top[i], bottom[i], t)) for i in range(3))
        pygame.draw.line(surface, color, (0, y), (WIDTH, y))
    return surface


def build_secret_background():
    surface = make_gradient((8, 8, 40), (70, 20, 110))
    cx = WIDTH // 2
    radius = 120
    top_y = GROUND_Y - radius
    for y in range(top_y, GROUND_Y):
        dy = GROUND_Y - y
        half = int(math.sqrt(max(0, radius * radius - dy * dy)))
        t = (y - top_y) / radius
        color = (
            int(lerp(160, 110, t)),
            int(lerp(50, 30, t)),
            int(lerp(120, 140, t)),
        )
        pygame.draw.line(surface, color, (cx - half, y), (cx + half, y))
    for k in range(1, 6):
        y = GROUND_Y - 16 * k
        for dy in range(k):
            row = surface.get_at((0, y + dy))[:3]
            pygame.draw.line(surface, row, (cx - radius, y + dy), (cx + radius, y + dy))
    return surface


def build_ground(dirt, edge, grass, stripe, dash_a, dash_b):
    width = WIDTH + GROUND_PERIOD
    surface = pygame.Surface((width, GROUND_HEIGHT))
    surface.fill(dirt)
    pygame.draw.rect(surface, grass, (0, 3, width, 17))
    for x in range(-GROUND_PERIOD, width + GROUND_PERIOD, GROUND_PERIOD):
        pygame.draw.polygon(surface, stripe, [(x + 14, 3), (x + 30, 3), (x + 16, 20), (x, 20)])
    pygame.draw.rect(surface, edge, (0, 0, width, 3))
    pygame.draw.rect(surface, edge, (0, 20, width, 3))
    for x in range(0, width, GROUND_PERIOD):
        pygame.draw.rect(surface, dash_a, (x + 6, 38, 14, 5))
        pygame.draw.rect(surface, dash_b, (x + 20, 58, 9, 5))
    return surface


def build_secret_ground():
    width = WIDTH + GROUND_PERIOD
    surface = pygame.Surface((width, GROUND_HEIGHT))
    surface.fill((22, 8, 50))
    for x in range(-GROUND_PERIOD, width + 2 * GROUND_PERIOD, GROUND_PERIOD):
        pygame.draw.line(surface, (120, 50, 200), (x, 3), (x - 28, GROUND_HEIGHT), 2)
    for y in (24, 46, 68):
        pygame.draw.line(surface, (80, 35, 150), (0, y), (width, y), 2)
    pygame.draw.rect(surface, (170, 40, 150), (0, 3, width, 3))
    pygame.draw.rect(surface, (255, 70, 210), (0, 0, width, 3))
    return surface


def build_pipe_art(base, light, dark, outline):
    body = pygame.Surface((PIPE_WIDTH, HEIGHT))
    body.fill(outline)
    body.fill(base, (3, 0, PIPE_WIDTH - 6, HEIGHT))
    body.fill(light, (8, 0, 9, HEIGHT))
    body.fill(dark, (PIPE_WIDTH - 18, 0, 12, HEIGHT))
    cap = pygame.Surface((CAP_WIDTH, CAP_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(cap, outline, (0, 0, CAP_WIDTH, CAP_HEIGHT), border_radius=5)
    pygame.draw.rect(cap, base, (3, 3, CAP_WIDTH - 6, CAP_HEIGHT - 6), border_radius=3)
    cap.fill(light, (10, 4, 10, CAP_HEIGHT - 8))
    cap.fill(dark, (CAP_WIDTH - 24, 4, 14, CAP_HEIGHT - 8))
    return body.convert(), cap.convert_alpha()


def build_bird_frames(glow_color):
    size = 76
    c = size // 2
    wing_rects = [(c - 20, c - 11, 22, 13), (c - 20, c - 3, 22, 13), (c - 20, c + 4, 22, 13)]
    frames = []
    for wing in range(3):
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        if glow_color is not None:
            for radius, alpha in ((36, 28), (31, 46), (26, 70)):
                layer = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(layer, tuple(glow_color) + (alpha,), (c, c), radius)
                surface.blit(layer, (0, 0))
        body = pygame.Rect(0, 0, 40, 32)
        body.center = (c, c)
        tail = [(c - 19, c - 4), (c - 30, c - 11), (c - 27, c + 1), (c - 30, c + 8), (c - 19, c + 5)]
        if glow_color is not None:
            pygame.draw.ellipse(surface, glow_color, body.inflate(9, 9))
        pygame.draw.polygon(surface, BIRD_OUTLINE, tail)
        pygame.draw.ellipse(surface, BIRD_OUTLINE, body.inflate(5, 5))
        pygame.draw.polygon(surface, (240, 170, 30), tail)
        pygame.draw.ellipse(surface, BIRD_BODY, body)
        pygame.draw.ellipse(surface, (255, 240, 160), pygame.Rect(c - 4, c + 3, 24, 12))
        wing_rect = pygame.Rect(wing_rects[wing])
        pygame.draw.ellipse(surface, (255, 236, 130), wing_rect)
        pygame.draw.ellipse(surface, (200, 140, 20), wing_rect, 2)
        pygame.draw.circle(surface, BIRD_OUTLINE, (c + 10, c - 7), 9)
        pygame.draw.circle(surface, WHITE, (c + 10, c - 7), 8)
        pygame.draw.circle(surface, BLACK, (c + 12, c - 7), 3)
        upper = [(c + 17, c - 3), (c + 30, c + 2), (c + 17, c + 4)]
        lower = [(c + 17, c + 4), (c + 27, c + 7), (c + 17, c + 11)]
        pygame.draw.polygon(surface, (255, 130, 30), upper)
        pygame.draw.polygon(surface, (235, 100, 20), lower)
        pygame.draw.polygon(surface, (160, 70, 10), upper, 1)
        pygame.draw.polygon(surface, (160, 70, 10), lower, 1)
        frames.append(surface.convert_alpha())
    return frames


def build_panel(size, fill, border):
    surface = pygame.Surface(size, pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, border, rect, border_radius=22)
    pygame.draw.rect(surface, fill, rect.inflate(-8, -8), border_radius=18)
    return surface.convert_alpha()


class Game:
    def __init__(self, start_score=0):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Flappy Bird")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.canvas = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.overlay_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.gold_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.clock = pygame.time.Clock()
        self.fonts = {}
        self.text_cache = {}
        self.bird_cache = {}
        self.audio = Audio()
        self.start_score = start_score
        self.persist = start_score == 0
        self.save_path = get_save_path()
        self.best = load_best(self.save_path)
        self.build_assets()
        self.bird = Bird()
        self.particles = []
        self.buttons = []
        self.focus = 0
        self.running = True
        self.time = 0.0
        self.scroll = 0.0
        self.fade = 0.0
        self.flash = 0.0
        self.shake = 0.0
        self.ui_lock = 0.0
        self.paused_from = STATE_PLAYING
        self.state = STATE_MENU
        self.easter_t = 0.0
        self.easter_swapped = False
        self.easter_bird_y = HOVER_Y
        self.spark_acc = 0.0
        self.go_t = 0.0
        self.victory_t = 0.0
        self.victory_from = (BIRD_X, HOVER_Y)
        self.confetti_acc = 0.0
        self.reset_run()
        self.set_state(STATE_MENU)

    def build_assets(self):
        self.backgrounds = {
            "normal": self.solid_background(SKY),
            "secret": build_secret_background().convert(),
            "gold": make_gradient((255, 238, 150), (255, 186, 62)).convert(),
        }
        self.grounds = {
            "normal": build_ground(
                (222, 216, 149), (68, 130, 36), (140, 210, 70), (115, 190, 50), (200, 190, 120), (200, 190, 120)
            ).convert(),
            "secret": build_secret_ground().convert(),
            "gold": build_ground(
                (235, 185, 60), (150, 95, 10), (255, 224, 100), (255, 200, 50), (215, 160, 40), (215, 160, 40)
            ).convert(),
        }
        self.pipe_art = {
            "normal": build_pipe_art((115, 190, 45), (170, 225, 95), (75, 150, 30), (45, 85, 25)),
            "secret": build_pipe_art((70, 230, 110), (190, 255, 210), (25, 150, 80), (5, 50, 40)),
        }
        self.bird_frames = {
            "normal": build_bird_frames(None),
            "secret": build_bird_frames((90, 255, 255)),
            "gold": build_bird_frames((255, 240, 150)),
        }
        rng = random.Random(7)
        self.stars = [
            (rng.uniform(0, WIDTH), rng.uniform(10, GROUND_Y - 40), rng.choice((1, 2, 2, 3)), rng.uniform(0, 6.28))
            for _ in range(55)
        ]
        self.panel_gameover = build_panel((380, 520), (255, 246, 214, 238), (120, 70, 20, 255))
        self.panel_howto = build_panel((700, 390), (255, 246, 214, 238), (120, 70, 20, 255))

    def solid_background(self, color):
        surface = pygame.Surface((WIDTH, HEIGHT))
        surface.fill(color)
        return surface.convert()

    def get_font(self, size):
        font = self.fonts.get(size)
        if font is None:
            font = pygame.font.SysFont("verdana,arial,dejavusans", size, bold=True)
            self.fonts[size] = font
        return font

    def render_text(self, content, size, color, outline, thick):
        key = (content, size, color, outline, thick)
        surface = self.text_cache.get(key)
        if surface is None:
            font = self.get_font(size)
            base = font.render(content, True, color)
            if outline is None:
                surface = base.convert_alpha()
            else:
                w, h = base.get_size()
                surface = pygame.Surface((w + 2 * thick, h + 2 * thick), pygame.SRCALPHA)
                edge = font.render(content, True, outline)
                for dx in range(-thick, thick + 1):
                    for dy in range(-thick, thick + 1):
                        if dx * dx + dy * dy <= thick * thick + 1:
                            surface.blit(edge, (thick + dx, thick + dy))
                surface.blit(base, (thick, thick))
            if len(self.text_cache) > 600:
                self.text_cache.clear()
            self.text_cache[key] = surface
        return surface

    def text(self, content, size, color, pos, anchor="center", outline=DARK, thick=2,
             alpha=255, scale=1.0, max_width=WIDTH - 40):
        surface = self.render_text(content, size, color, outline, thick)
        w, h = surface.get_size()
        factor = scale
        if w * factor > max_width:
            factor = max_width / w
        if abs(factor - 1.0) > 0.01:
            surface = pygame.transform.smoothscale(surface, (max(1, int(w * factor)), max(1, int(h * factor))))
        rect = surface.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        if alpha < 255:
            surface.set_alpha(max(0, int(alpha)))
            self.canvas.blit(surface, rect)
            surface.set_alpha(255)
        else:
            self.canvas.blit(surface, rect)

    def draw_overlay(self, target, color, alpha):
        if alpha <= 0:
            return
        self.overlay_surface.fill(color)
        self.overlay_surface.set_alpha(min(255, int(alpha)))
        target.blit(self.overlay_surface, (0, 0))

    def reset_run(self):
        self.score = self.start_score
        self.bird.reset(BIRD_X, HOVER_Y)
        self.pipes = []
        self.theme = "normal"
        self.easter_done = False
        self.easter_swapped = False
        self.victory_done = False
        self.hit_played = False
        self.secret_wait = False
        self.new_best = False
        self.particles = []
        self.flash = 0.0
        self.shake = 0.0

    def set_state(self, new_state):
        self.state = new_state
        self.focus = 0
        self.buttons = self.build_buttons(new_state)
        if new_state in (STATE_MENU, STATE_HOWTO, STATE_READY):
            self.fade = 1.0

    def sound_label(self):
        return "Sound: ON" if self.audio.enabled else "Sound: OFF"

    def build_buttons(self, state):
        cx = WIDTH // 2
        if state == STATE_MENU:
            return [
                Button("Play", (cx, 255), self.start_game),
                Button("How to Play", (cx, 319), lambda: self.set_state(STATE_HOWTO)),
                Button(self.sound_label, (cx, 383), self.toggle_sound, silent=True),
                Button("Exit", (cx, 447), self.quit_game),
            ]
        if state == STATE_HOWTO:
            return [Button("Back", (cx, 485), self.to_menu, size=(220, 50))]
        if state == STATE_PAUSED:
            return [
                Button("Resume", (cx, 290), self.resume, size=(260, 50)),
                Button("Restart", (cx, 352), self.start_game, size=(260, 50)),
                Button("Main Menu", (cx, 414), self.to_menu, size=(260, 50)),
            ]
        if state == STATE_GAMEOVER:
            return [
                Button("Play Again", (cx, 405), self.start_game, size=(260, 48)),
                Button("Main Menu", (cx, 463), self.to_menu, size=(260, 48)),
                Button("Exit", (cx, 521), self.quit_game, size=(260, 48)),
            ]
        if state == STATE_VICTORY:
            return [
                Button("Play Again", (cx, 395), self.start_game, size=(260, 48)),
                Button("Main Menu", (cx, 453), self.to_menu, size=(260, 48)),
                Button("Exit", (cx, 511), self.quit_game, size=(260, 48)),
            ]
        return []

    def quit_game(self):
        self.running = False

    def toggle_sound(self):
        if self.audio.toggle():
            self.audio.play("click")

    def to_menu(self):
        self.theme = "normal"
        self.particles = []
        self.flash = 0.0
        self.shake = 0.0
        self.set_state(STATE_MENU)

    def start_game(self):
        self.reset_run()
        self.set_state(STATE_READY)
        self.ui_lock = 0.2

    def begin_play(self):
        if self.ui_lock > 0.0:
            return
        self.set_state(STATE_PLAYING)
        self.bird.flap()
        self.audio.play("flap")

    def pause(self):
        if self.state not in (STATE_PLAYING, STATE_SECRET):
            return
        self.paused_from = self.state
        self.set_state(STATE_PAUSED)

    def resume(self):
        self.set_state(self.paused_from)
        self.ui_lock = 0.15

    def try_flap(self):
        if self.ui_lock > 0.0:
            return
        if self.state == STATE_SECRET and self.secret_wait:
            self.secret_wait = False
        self.bird.flap()
        self.audio.play("flap")

    def current_speed(self):
        if self.theme == "secret":
            return SECRET_SPEED
        return BASE_SPEED + SPEED_GAIN * min(self.score, FINAL_SCORE - 1)

    def current_gap(self):
        if self.theme == "secret":
            return SECRET_GAP
        return max(GAP_MIN, GAP_START - GAP_SHRINK * self.score)

    def spawn_pipe(self):
        gap = self.current_gap()
        low = EDGE_MARGIN + gap / 2.0
        high = GROUND_Y - EDGE_MARGIN - gap / 2.0
        if self.pipes:
            previous = self.pipes[-1].gap_center
            center = random.uniform(max(low, previous - MAX_GAP_SHIFT), min(high, previous + MAX_GAP_SHIFT))
        else:
            center = random.uniform(low + 20.0, high - 20.0)
        self.pipes.append(Pipe(SPAWN_X, center, gap))

    def check_collision(self):
        bx = self.bird.x
        by = self.bird.y
        r = BIRD_RADIUS
        if by + r >= GROUND_Y or by - r <= 0:
            return True
        for pipe in self.pipes:
            if pipe.x - CAP_OVERHANG > bx + r or pipe.x + PIPE_WIDTH + CAP_OVERHANG < bx - r:
                continue
            top = pipe.gap_top()
            bottom = pipe.gap_bottom()
            if circle_hits_rect(bx, by, r, pipe.x, -200, PIPE_WIDTH, top - CAP_HEIGHT + 200):
                return True
            if circle_hits_rect(bx, by, r, pipe.x - CAP_OVERHANG, top - CAP_HEIGHT, CAP_WIDTH, CAP_HEIGHT):
                return True
            if circle_hits_rect(bx, by, r, pipe.x - CAP_OVERHANG, bottom, CAP_WIDTH, CAP_HEIGHT):
                return True
            if circle_hits_rect(bx, by, r, pipe.x, bottom + CAP_HEIGHT, PIPE_WIDTH, GROUND_Y):
                return True
        return False

    def add_point(self):
        if self.victory_done or self.score >= FINAL_SCORE:
            return
        self.score += 1
        if self.score >= FINAL_SCORE:
            self.score = FINAL_SCORE
            self.start_victory()
        elif self.score == EASTER_SCORE and not self.easter_done:
            self.start_easter()
        else:
            self.audio.play("point")

    def start_easter(self):
        self.easter_done = True
        self.easter_t = 0.0
        self.easter_swapped = False
        self.spark_acc = 0.0
        self.bird.vel = 0.0
        self.audio.play("easter")
        self.set_state(STATE_EASTER)

    def start_victory(self):
        self.victory_done = True
        self.victory_t = 0.0
        self.victory_from = (self.bird.x, self.bird.y)
        self.confetti_acc = 0.0
        if self.score > self.best:
            self.best = self.score
            if self.persist:
                save_best(self.save_path, self.best)
        self.particles = []
        self.flash = 1.0
        self.audio.play("victory")
        self.set_state(STATE_VICTORY)
        self.ui_lock = VICTORY_LOCK
        for _ in range(90):
            self.emit_confetti(0, HEIGHT * 0.62, random.uniform(160, 460), -random.uniform(250, 520))
            self.emit_confetti(WIDTH, HEIGHT * 0.62, -random.uniform(160, 460), -random.uniform(250, 520))

    def die(self):
        if self.state not in (STATE_PLAYING, STATE_SECRET):
            return
        self.bird.vel = max(self.bird.vel, 0.0)
        if not self.hit_played:
            self.hit_played = True
            self.audio.play("hit")
        if self.score > self.best:
            self.best = self.score
            self.new_best = True
            if self.persist:
                save_best(self.save_path, self.best)
        self.go_t = 0.0
        self.flash = 0.8
        self.shake = SHAKE_TIME
        self.set_state(STATE_GAMEOVER)
        self.ui_lock = GAMEOVER_LOCK

    def emit_confetti(self, x, y, vx, vy):
        if len(self.particles) >= MAX_PARTICLES:
            return
        color = random.choice(CONFETTI_COLORS)
        self.particles.append(Particle(x, y, vx, vy, random.uniform(5.0, 8.0), color, random.uniform(5.0, 9.0), "confetti"))

    def emit_sparks(self, x, y, count, speed_low, speed_high, colors):
        for _ in range(count):
            if len(self.particles) >= MAX_PARTICLES:
                return
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(speed_low, speed_high)
            self.particles.append(
                Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                         random.uniform(0.5, 1.2), random.choice(colors), random.uniform(3.0, 6.5), "spark")
            )

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if FOCUS_LOST is not None and event.type == FOCUS_LOST:
            self.pause()
            return
        state = self.state
        if state in (STATE_PLAYING, STATE_SECRET):
            self.handle_play_event(event)
        elif state == STATE_READY:
            self.handle_ready_event(event)
        elif state == STATE_EASTER:
            return
        else:
            self.handle_menu_event(event)

    def handle_play_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                self.pause()
            elif event.key in (pygame.K_SPACE, pygame.K_UP):
                self.try_flap()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.try_flap()

    def handle_ready_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.to_menu()
            elif event.key in (pygame.K_SPACE, pygame.K_UP):
                self.begin_play()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.begin_play()

    def activate(self, index):
        if not 0 <= index < len(self.buttons):
            return
        button = self.buttons[index]
        if not button.silent:
            self.audio.play("click")
        button.action()

    def handle_menu_event(self, event):
        state = self.state
        if event.type == pygame.KEYDOWN:
            if state == STATE_PAUSED and event.key in (pygame.K_ESCAPE, pygame.K_p):
                self.resume()
                return
            if self.ui_lock > 0.0:
                return
            if event.key == pygame.K_ESCAPE and state in (STATE_HOWTO, STATE_GAMEOVER, STATE_VICTORY):
                self.to_menu()
            elif event.key in (pygame.K_UP, pygame.K_w) and self.buttons:
                self.focus = (self.focus - 1) % len(self.buttons)
            elif event.key in (pygame.K_DOWN, pygame.K_s) and self.buttons:
                self.focus = (self.focus + 1) % len(self.buttons)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.activate(self.focus)
        elif event.type == pygame.MOUSEMOTION:
            if self.ui_lock > 0.0:
                return
            for index, button in enumerate(self.buttons):
                if button.rect.collidepoint(event.pos):
                    self.focus = index
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.ui_lock > 0.0:
                return
            for index, button in enumerate(self.buttons):
                if button.rect.collidepoint(event.pos):
                    self.focus = index
                    self.activate(index)
                    break

    def update(self, dt):
        state = self.state
        if state != STATE_PAUSED:
            self.time += dt
            self.update_effects(dt)
        self.ui_lock = max(0.0, self.ui_lock - dt)
        self.fade = max(0.0, self.fade - dt * 3.0)
        if state == STATE_MENU:
            self.scroll += 90.0 * dt
        elif state == STATE_HOWTO:
            self.scroll += 90.0 * dt
        elif state == STATE_READY:
            self.update_hover(dt)
            self.scroll += self.current_speed() * dt
        elif state in (STATE_PLAYING, STATE_SECRET):
            self.update_play(dt)
        elif state == STATE_EASTER:
            self.update_easter(dt)
        elif state == STATE_GAMEOVER:
            self.update_gameover(dt)
        elif state == STATE_VICTORY:
            self.update_victory(dt)

    def update_effects(self, dt):
        self.flash = max(0.0, self.flash - dt * 3.0)
        self.shake = max(0.0, self.shake - dt)
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0 or p.y > HEIGHT + 20:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.vrot * dt
            if p.kind == "confetti":
                p.vy = min(p.vy + 260.0 * dt, 230.0)
                p.vx -= p.vx * 0.8 * dt
                p.x += math.sin(p.rot) * 25.0 * dt
            else:
                p.vx -= p.vx * 1.5 * dt
                p.vy -= p.vy * 1.5 * dt
            alive.append(p)
        self.particles = alive

    def update_hover(self, dt):
        self.bird.y = HOVER_Y + math.sin(self.time * 5.0) * 7.0
        self.bird.vel = 0.0
        self.bird.animate(dt, 9.0)

    def update_play(self, dt):
        speed = self.current_speed()
        self.scroll += speed * dt
        if self.state == STATE_SECRET and self.secret_wait:
            self.update_hover(dt)
            return
        self.bird.step(dt)
        self.bird.animate(dt)
        for pipe in self.pipes:
            pipe.x -= speed * dt
        if not self.pipes or self.pipes[-1].x <= SPAWN_X - PIPE_SPACING:
            self.spawn_pipe()
        while self.pipes and self.pipes[0].x + PIPE_WIDTH + CAP_OVERHANG < 0:
            self.pipes.pop(0)
        if self.check_collision():
            self.die()
            return
        for pipe in self.pipes:
            if not pipe.scored and pipe.x + PIPE_WIDTH < self.bird.x:
                pipe.scored = True
                self.add_point()
                if self.state not in (STATE_PLAYING, STATE_SECRET):
                    return

    def update_easter(self, dt):
        self.easter_t += dt
        t = self.easter_t
        bird = self.bird
        bird.vel = 0.0
        bird.animate(dt, 7.0)
        if t < EASTER_SWAP:
            self.spark_acc += dt * 70.0
            while self.spark_acc >= 1.0:
                self.spark_acc -= 1.0
                self.emit_sparks(WIDTH / 2, 255, 1, 90.0, 280.0, EASTER_COLORS)
        if not self.easter_swapped and t >= EASTER_SWAP:
            self.easter_swapped = True
            self.theme = "secret"
            self.pipes = []
            self.flash = 1.0
            self.easter_bird_y = bird.y
            self.emit_sparks(WIDTH / 2, 255, 60, 150.0, 480.0, EASTER_COLORS)
        if self.easter_swapped:
            p = clamp((t - EASTER_SWAP) / (EASTER_END - EASTER_SWAP - 0.3), 0.0, 1.0)
            bird.y = lerp(self.easter_bird_y, HOVER_Y, ease_in_out(p))
        if t >= EASTER_END:
            bird.y = HOVER_Y
            bird.vel = 0.0
            self.secret_wait = True
            self.set_state(STATE_SECRET)
            self.ui_lock = 0.3

    def update_gameover(self, dt):
        self.go_t += dt
        bird = self.bird
        if bird.y + BIRD_RADIUS < GROUND_Y:
            bird.step(dt)
            if bird.y + BIRD_RADIUS >= GROUND_Y:
                bird.y = GROUND_Y - BIRD_RADIUS
                bird.vel = 0.0
            bird.angle += (-90.0 - bird.angle) * min(1.0, dt * 8.0)
        else:
            bird.angle += (-90.0 - bird.angle) * min(1.0, dt * 8.0)

    def update_victory(self, dt):
        self.victory_t += dt
        self.scroll += 60.0 * dt
        self.confetti_acc += dt * 140.0
        while self.confetti_acc >= 1.0:
            self.confetti_acc -= 1.0
            self.emit_confetti(random.uniform(0, WIDTH), -10, random.uniform(-40, 40), random.uniform(80, 180))

    def draw(self):
        state = self.state
        if state == STATE_MENU:
            self.draw_menu()
        elif state == STATE_HOWTO:
            self.draw_howto()
        elif state == STATE_READY:
            self.draw_scene()
            self.draw_ready_prompt()
        elif state in (STATE_PLAYING, STATE_SECRET):
            self.draw_scene()
            if state == STATE_SECRET and self.secret_wait:
                self.draw_ready_prompt()
        elif state == STATE_PAUSED:
            self.draw_paused()
        elif state == STATE_EASTER:
            self.draw_easter()
        elif state == STATE_GAMEOVER:
            self.draw_gameover()
        elif state == STATE_VICTORY:
            self.draw_victory()
        self.present()

    def present(self):
        ox = 0
        oy = 0
        if self.shake > 0.0:
            amp = int(1 + 6 * self.shake / SHAKE_TIME)
            ox = random.randint(-amp, amp)
            oy = random.randint(-amp, amp)
            self.screen.fill(BLACK)
        self.screen.blit(self.canvas, (ox, oy))
        if self.fade > 0.0:
            self.draw_overlay(self.screen, (20, 40, 70), 255 * self.fade * 0.8)
        if self.flash > 0.0:
            self.draw_overlay(self.screen, WHITE, 210 * self.flash)
        pygame.display.flip()

    def draw_bird(self, x, y, angle, frame, kind):
        key = (kind, frame, int(round(angle)))
        image = self.bird_cache.get(key)
        if image is None:
            image = pygame.transform.rotate(self.bird_frames[kind][frame], key[2])
            self.bird_cache[key] = image
        self.canvas.blit(image, image.get_rect(center=(int(x), int(y))))

    def draw_stars(self):
        for sx, sy, size, phase in self.stars:
            x = (sx - self.time * 6.0 * size) % WIDTH
            level = int(140 + 115 * math.sin(self.time * 2.5 + phase))
            color = (level, level, min(255, level + 40))
            pygame.draw.rect(self.canvas, color, (int(x), int(sy), size, size))

    def draw_pipes(self, theme):
        art_key = "secret" if theme == "secret" else "normal"
        body, cap = self.pipe_art[art_key]
        canvas = self.canvas
        for pipe in self.pipes:
            x = int(pipe.x)
            top = int(pipe.gap_top())
            bottom = int(pipe.gap_bottom())
            top_height = top - CAP_HEIGHT
            if top_height > 0:
                canvas.blit(body, (x, 0), (0, 0, PIPE_WIDTH, top_height))
            canvas.blit(cap, (x - CAP_OVERHANG, top - CAP_HEIGHT))
            bottom_y = bottom + CAP_HEIGHT
            bottom_height = GROUND_Y - bottom_y
            if bottom_height > 0:
                canvas.blit(body, (x, bottom_y), (0, 0, PIPE_WIDTH, bottom_height))
            canvas.blit(cap, (x - CAP_OVERHANG, bottom))
            if theme == "secret":
                level = int(190 + 65 * math.sin(self.time * 5.0 + pipe.x * 0.03))
                color = (level, 255, level)
                if top_height > 0:
                    pygame.draw.rect(canvas, color, (x - 1, -4, PIPE_WIDTH + 2, top_height + 4), 2)
                if bottom_height > 0:
                    pygame.draw.rect(canvas, color, (x - 1, bottom_y, PIPE_WIDTH + 2, bottom_height), 2)
                pygame.draw.rect(canvas, color, (x - CAP_OVERHANG - 1, top - CAP_HEIGHT - 1, CAP_WIDTH + 2, CAP_HEIGHT + 2), 2, border_radius=6)
                pygame.draw.rect(canvas, color, (x - CAP_OVERHANG - 1, bottom - 1, CAP_WIDTH + 2, CAP_HEIGHT + 2), 2, border_radius=6)

    def draw_particles(self):
        canvas = self.canvas
        for p in self.particles:
            if p.kind == "confetti":
                w = max(1, int(p.size * abs(math.cos(p.rot))))
                h = int(p.size * 1.4)
                pygame.draw.rect(canvas, p.color, (int(p.x - w / 2), int(p.y - h / 2), w, h))
            else:
                radius = max(1, int(p.size * p.life / p.max_life))
                pygame.draw.circle(canvas, p.color, (int(p.x), int(p.y)), radius)

    def draw_scene(self, hud=True, show_bird=True):
        theme = self.theme
        canvas = self.canvas
        canvas.blit(self.backgrounds[theme], (0, 0))
        if theme == "secret":
            self.draw_stars()
        self.draw_pipes(theme)
        canvas.blit(self.grounds[theme], (-(int(self.scroll) % GROUND_PERIOD), GROUND_Y))
        if show_bird:
            bird = self.bird
            if theme == "secret":
                level = int(170 + 85 * math.sin(self.time * 6.0))
                radius = int(24 + 3 * math.sin(self.time * 6.0))
                pygame.draw.circle(canvas, (level, 255, 255), (int(bird.x), int(bird.y)), radius, 2)
            self.draw_bird(bird.x, bird.y, bird.angle, bird.wing_frame(), theme)
        self.draw_particles()
        if hud:
            self.draw_hud()

    def draw_hud(self):
        secret = self.theme == "secret"
        edge = (70, 0, 110) if secret else (50, 40, 30)
        self.text(str(self.score), 72, WHITE, (WIDTH // 2, 52), outline=edge, thick=4)
        self.text("BEST: " + str(self.best), 22, WHITE, (16, 14), anchor="topleft", outline=edge, thick=2)
        if secret:
            color = SECRET_TITLE_COLORS[int(self.time * 3) % 2]
            self.text("THE 999 CHALLENGE", 30, color, (WIDTH // 2, 112), outline=(60, 0, 90), thick=3)

    def draw_ready_prompt(self):
        secret = self.theme == "secret"
        edge = (70, 0, 110) if secret else (50, 40, 30)
        self.text("GET READY!", 56, YELLOW, (WIDTH // 2, 175), outline=edge, thick=4)
        alpha = 170 + 85 * math.sin(self.time * 5.0)
        self.text("Press SPACE, UP ARROW or click to flap", 24, WHITE, (WIDTH // 2, 345), outline=edge, thick=2, alpha=alpha)

    def draw_button(self, button, focused):
        rect = button.rect
        face = BTN_HOVER if focused else BTN_FACE
        pygame.draw.rect(self.canvas, BTN_SHADOW, rect.move(0, 5), border_radius=14)
        top = rect.move(0, -2) if focused else rect
        pygame.draw.rect(self.canvas, BTN_BORDER, top, border_radius=14)
        pygame.draw.rect(self.canvas, face, top.inflate(-6, -6), border_radius=11)
        pygame.draw.rect(self.canvas, (255, 235, 170), (top.x + 12, top.y + 6, top.width - 24, 4), border_radius=2)
        self.text(button.text(), 26, WHITE, top.center, outline=BTN_BORDER, thick=2, max_width=rect.width - 24)

    def draw_buttons(self):
        for index, button in enumerate(self.buttons):
            self.draw_button(button, index == self.focus)

    def draw_menu(self):
        canvas = self.canvas
        canvas.blit(self.backgrounds["normal"], (0, 0))
        canvas.blit(self.grounds["normal"], (-(int(self.scroll) % GROUND_PERIOD), GROUND_Y))
        title_y = 85 + math.sin(self.time * 2.5) * 5
        self.text("FLAPPY BIRD", 76, YELLOW, (WIDTH // 2, title_y), outline=(110, 60, 10), thick=5)
        frame = Bird.WING_SEQUENCE[int(self.time * 9) % 4]
        self.draw_bird(WIDTH // 2, 168 + math.sin(self.time * 3.0) * 9, math.sin(self.time * 3.0) * 8, frame, "normal")
        self.draw_buttons()
        self.text("BEST SCORE: " + str(self.best), 26, WHITE, (WIDTH // 2, 565), outline=(60, 50, 20), thick=2)

    def draw_howto(self):
        canvas = self.canvas
        canvas.blit(self.backgrounds["normal"], (0, 0))
        canvas.blit(self.grounds["normal"], (-(int(self.scroll) % GROUND_PERIOD), GROUND_Y))
        canvas.blit(self.panel_howto, (50, 50))
        self.text("HOW TO PLAY", 40, (230, 90, 30), (WIDTH // 2, 98), outline=(90, 40, 10), thick=3)
        lines = [
            "Press SPACE or the UP ARROW to flap.",
            "You can also click the left mouse button to flap.",
            "Each successfully passed pipe pair earns 1 point.",
            "Avoid hitting pipes, the ground, or the ceiling.",
            "Reach 1000 points to complete the game.",
            "A secret event awaits you at 999 points!",
        ]
        for index, line in enumerate(lines):
            y = 170 + index * 46
            pygame.draw.circle(canvas, ORANGE, (92, y), 7)
            pygame.draw.circle(canvas, BTN_BORDER, (92, y), 7, 2)
            self.text(line, 21, (70, 45, 20), (112, y), anchor="midleft", outline=None, max_width=610)
        self.draw_buttons()

    def draw_paused(self):
        self.draw_scene()
        self.draw_overlay(self.canvas, BLACK, 150)
        self.text("PAUSED", 76, WHITE, (WIDTH // 2, 190), outline=DARK, thick=4)
        self.draw_buttons()
        self.text("Press ESC or P to resume", 20, WHITE, (WIDTH // 2, 490), outline=DARK, thick=2)

    def draw_easter(self):
        t = self.easter_t
        self.draw_scene(hud=False)
        if t < 0.8:
            alpha = 190 * t / 0.8
        elif t < EASTER_SWAP:
            alpha = 190
        else:
            alpha = 190 * max(0.0, 1.0 - (t - EASTER_SWAP) / (EASTER_END - EASTER_SWAP - 0.2))
        self.draw_overlay(self.canvas, (15, 0, 35), alpha)
        self.draw_particles()
        self.draw_hud()
        if t < 2.7:
            if t < 0.7:
                scale = max(0.05, ease_out_back(t / 0.7))
            else:
                scale = 1.0 + 0.04 * math.sin((t - 0.7) * 9.0)
            text_alpha = 255 if t < 2.3 else 255 * (2.7 - t) / 0.4
            color = EASTER_COLORS[int(t * 8) % 4]
            self.text("SECRET LEVEL", 76, color, (WIDTH // 2, 215), outline=(60, 0, 90), thick=5, alpha=text_alpha, scale=scale, max_width=760)
            self.text("UNLOCKED!", 76, color, (WIDTH // 2, 295), outline=(60, 0, 90), thick=5, alpha=text_alpha, scale=scale, max_width=760)

    def draw_gameover(self):
        self.draw_scene()
        ov = clamp((self.go_t - 0.35) / 0.4, 0.0, 1.0)
        self.draw_overlay(self.canvas, BLACK, 150 * ov)
        if ov <= 0.0:
            return
        alpha = int(255 * ov)
        self.panel_gameover.set_alpha(alpha)
        self.canvas.blit(self.panel_gameover, (210, 40))
        self.panel_gameover.set_alpha(255)
        brown = (110, 70, 30)
        self.text("GAME OVER", 48, (255, 90, 50), (WIDTH // 2, 100), outline=(90, 30, 10), thick=3, alpha=alpha, max_width=330)
        self.text("SCORE", 22, brown, (WIDTH // 2, 158), outline=None, alpha=alpha)
        self.text(str(self.score), 56, WHITE, (WIDTH // 2, 202), outline=(90, 50, 20), thick=3, alpha=alpha)
        self.text("BEST", 22, brown, (WIDTH // 2, 260), outline=None, alpha=alpha)
        self.text(str(self.best), 44, WHITE, (WIDTH // 2, 300), outline=(90, 50, 20), thick=3, alpha=alpha)
        if self.new_best:
            pulse = 1.0 + 0.06 * math.sin(self.time * 8.0)
            self.text("NEW BEST!", 26, (255, 140, 0), (WIDTH // 2, 343), outline=(90, 50, 20), thick=2, alpha=alpha, scale=pulse)
        if self.go_t >= GAMEOVER_LOCK:
            self.draw_buttons()

    def draw_victory(self):
        vt = self.victory_t
        canvas = self.canvas
        if vt < VICTORY_FADE:
            self.draw_scene(hud=False, show_bird=False)
            self.draw_gold_background(self.gold_surface)
            self.gold_surface.set_alpha(int(255 * vt / VICTORY_FADE))
            canvas.blit(self.gold_surface, (0, 0))
            self.gold_surface.set_alpha(255)
        else:
            self.draw_gold_background(canvas)
        progress = ease_in_out(clamp(vt / VICTORY_FADE, 0.0, 1.0))
        bird_x = lerp(self.victory_from[0], WIDTH / 2, progress)
        bird_y = lerp(self.victory_from[1], 195.0, progress)
        if vt >= VICTORY_FADE:
            bird_y = 195.0 + math.sin(self.time * 3.0) * 6.0
        angle = lerp(self.bird.angle, math.sin(self.time * 3.0) * 6.0, progress)
        frame = Bird.WING_SEQUENCE[int(self.time * 10) % 4]
        self.draw_bird(bird_x, bird_y, angle, frame, "gold")
        for i in range(6):
            a = self.time * 1.2 + i * math.tau / 6
            sx = bird_x + math.cos(a) * 62
            sy = bird_y + math.sin(a) * 40
            r = 5 + 2 * math.sin(self.time * 6.0 + i)
            points = [
                (sx, sy - r * 1.6), (sx + r * 0.4, sy - r * 0.4), (sx + r * 1.6, sy), (sx + r * 0.4, sy + r * 0.4),
                (sx, sy + r * 1.6), (sx - r * 0.4, sy + r * 0.4), (sx - r * 1.6, sy), (sx - r * 0.4, sy - r * 0.4),
            ]
            pygame.draw.polygon(canvas, WHITE, points)
        self.draw_particles()
        if vt < VICTORY_FADE:
            return
        brown = (140, 70, 0)
        pulse = 1.0 + 0.03 * math.sin(self.time * 4.0)
        self.text("CONGRATULATIONS!", 56, WHITE, (WIDTH // 2, 62), outline=brown, thick=4, alpha=fade_in(vt, 0.9, 0.4), scale=pulse, max_width=740)
        self.text("YOU DID IT!", 44, WHITE, (WIDTH // 2, 122), outline=brown, thick=4, alpha=fade_in(vt, 1.2, 0.4))
        self.text("FINAL SCORE: 1000 / 1000", 38, WHITE, (WIDTH // 2, 272), outline=brown, thick=3, alpha=fade_in(vt, 1.5, 0.4), max_width=740)
        self.text("YOU HAVE MASTERED FLAPPY BIRD!", 28, (120, 55, 0), (WIDTH // 2, 322), outline=None, alpha=fade_in(vt, 1.7, 0.4), max_width=740)
        if vt >= VICTORY_LOCK:
            self.draw_buttons()

    def draw_gold_background(self, target):
        target.blit(self.backgrounds["gold"], (0, 0))
        cx = WIDTH // 2
        cy = 200
        base = self.time * 0.25
        count = 14
        step = math.tau / count
        for i in range(count):
            a = base + i * step
            p1 = (cx + math.cos(a) * 1000, cy + math.sin(a) * 1000)
            p2 = (cx + math.cos(a + step * 0.5) * 1000, cy + math.sin(a + step * 0.5) * 1000)
            pygame.draw.polygon(target, GOLD_RAY, [(cx, cy), p1, p2])
        target.blit(self.grounds["gold"], (-(int(self.scroll) % GROUND_PERIOD), GROUND_Y))

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1.0 / 30.0)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
        pygame.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Flappy Bird - The Ultimate Edition")
    parser.add_argument(
        "--start-score",
        type=int,
        default=0,
        help="practice mode: begin every run at this score (0-998) to try the 999 secret level quickly; best score is not saved",
    )
    args = parser.parse_args()
    return int(clamp(args.start_score, 0, EASTER_SCORE - 1))


def main():
    start_score = parse_args()
    game = Game(start_score)
    game.run()
    sys.exit()


if __name__ == "__main__":
    main()