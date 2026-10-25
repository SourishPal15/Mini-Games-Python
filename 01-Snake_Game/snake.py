import array
import math
import os
import random
import sys
import pygame

WIDTH = 900
HEIGHT = 700
FPS = 60
CELL = 30
COLS = 28
ROWS = 20
TOTAL_CELLS = COLS * ROWS
BOARD_X = 30
BOARD_Y = 80
BOARD_WIDTH = COLS * CELL
BOARD_HEIGHT = ROWS * CELL
BOARD_RECT = pygame.Rect(BOARD_X, BOARD_Y, BOARD_WIDTH, BOARD_HEIGHT)

SCORE_PER_APPLE = 10
START_DELAY_MS = 160
MIN_DELAY_MS = 70
DELAY_STEP_MS = 10
APPLES_PER_LEVEL = 5
START_GRACE_MS = 600
MAX_FRAME_MS = 50
GROW_EFFECT_MS = 320
BANNER_MS = 1000
APPLE_POP_MS = 220
FADE_SECONDS = 0.3
BACK_FOCUS = 9

HIGH_SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snake_highscore.txt")

FOREST_GREEN = (22, 88, 44)
DEEP_GREEN = (12, 56, 28)
LEAF_GREEN = (60, 140, 70)
LIGHT_GREEN = (110, 200, 90)
MENU_GRASS = (152, 210, 112)
GAME_GRASS = (140, 200, 100)
BOARD_LIGHT = (168, 222, 120)
BOARD_DARK = (156, 212, 108)
CREAM = (240, 252, 232)
SOFT_GREEN = (190, 235, 170)
WHITE = (255, 255, 255)
GOLD = (255, 205, 40)
SHADOW_GREEN = (20, 70, 36)
BURST_COLORS = [(220, 40, 40), (255, 120, 100), (255, 230, 120), (120, 200, 60)]

UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

KEY_DIRECTIONS = {
    pygame.K_UP: UP,
    pygame.K_w: UP,
    pygame.K_DOWN: DOWN,
    pygame.K_s: DOWN,
    pygame.K_LEFT: LEFT,
    pygame.K_a: LEFT,
    pygame.K_RIGHT: RIGHT,
    pygame.K_d: RIGHT,
}
NAV_PREVIOUS = (pygame.K_UP, pygame.K_LEFT, pygame.K_w, pygame.K_a)
NAV_NEXT = (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_s, pygame.K_d)
CONFIRM_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
FOCUS_LOST_EVENT = getattr(pygame, "WINDOWFOCUSLOST", -1)

SNAKE_COLORS = [
    ("Blue", (45, 110, 230), (15, 50, 130)),
    ("Green", (34, 150, 60), (10, 70, 28)),
    ("Red", (215, 45, 45), (110, 15, 20)),
    ("Yellow", (250, 215, 40), (140, 105, 0)),
    ("Pink", (245, 120, 185), (150, 40, 100)),
    ("White", (250, 250, 250), (60, 60, 60)),
    ("Black", (28, 28, 28), (120, 120, 120)),
    ("Orange", (250, 150, 30), (140, 70, 0)),
    ("Purple", (140, 70, 200), (70, 25, 110)),
]


def mix(color_a, color_b, amount):
    return tuple(int(a + (b - a) * amount) for a, b in zip(color_a, color_b))


def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, "r", encoding="utf-8") as score_file:
            return max(0, int(score_file.read().strip()))
    except FileNotFoundError:
        save_high_score(0)
        return 0
    except (OSError, ValueError):
        return 0


def save_high_score(score):
    try:
        with open(HIGH_SCORE_FILE, "w", encoding="utf-8") as score_file:
            score_file.write(str(score))
    except OSError:
        pass


def load_font(size):
    return pygame.font.SysFont("segoeui,arial,verdana,dejavusans", size, bold=True)


class TextCache:
    def __init__(self):
        self.items = {}

    def get(self, font, text, color):
        key = (id(font), text, color)
        image = self.items.get(key)
        if image is None:
            if len(self.items) > 400:
                self.items.clear()
            image = font.render(text, True, color)
            self.items[key] = image
        return image


TEXT = TextCache()


def draw_text(surface, font, text, color, center=None, topleft=None, midleft=None, midright=None, shadow=None):
    image = TEXT.get(font, text, color)
    rect = image.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    elif midleft is not None:
        rect.midleft = midleft
    elif midright is not None:
        rect.midright = midright
    if shadow is not None:
        surface.blit(TEXT.get(font, text, shadow), rect.move(2, 3))
    surface.blit(image, rect)
    return rect


def build_tone(sequence, settings, volume=0.25):
    sample_rate, _, channels = settings
    samples = array.array("h")
    for frequency, duration_ms in sequence:
        count = int(sample_rate * duration_ms / 1000)
        attack = sample_rate * 0.005 + 1
        release = sample_rate * 0.02 + 1
        for index in range(count):
            fade = min(1.0, index / attack, (count - index) / release)
            value = int(32767 * volume * fade * math.sin(2 * math.pi * frequency * index / sample_rate))
            for _ in range(channels):
                samples.append(value)
    return pygame.mixer.Sound(buffer=samples.tobytes())


class Sounds:
    def __init__(self):
        self.effects = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            settings = pygame.mixer.get_init()
            if settings and settings[1] == -16:
                self.effects = {
                    "eat": build_tone([(660, 60), (880, 90)], settings),
                    "click": build_tone([(520, 45)], settings),
                    "game_over": build_tone([(330, 150), (262, 150), (196, 320)], settings),
                    "victory": build_tone([(523, 110), (659, 110), (784, 110), (1046, 280)], settings),
                }
        except (pygame.error, ValueError, TypeError, OSError):
            self.effects = {}

    def play(self, name):
        sound = self.effects.get(name)
        if sound is not None:
            try:
                sound.play()
            except pygame.error:
                pass


def scatter_patches(surface, rng, count, base):
    width, height = surface.get_size()
    for _ in range(count):
        shift = rng.randint(-6, 6)
        color = (base[0] + shift, base[1] + shift, base[2] + shift)
        rect = pygame.Rect(rng.randrange(width), rng.randrange(height), rng.randint(40, 110), rng.randint(20, 60))
        pygame.draw.ellipse(surface, color, rect)


def scatter_grass(surface, rng, count, dark, light):
    width, height = surface.get_size()
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        color = dark if rng.random() < 0.6 else light
        blade = rng.randint(3, 6)
        pygame.draw.line(surface, color, (x, y), (x - 2, y - blade), 1)
        pygame.draw.line(surface, color, (x, y), (x, y - blade - 1), 1)
        pygame.draw.line(surface, color, (x, y), (x + 2, y - blade), 1)


def build_grass(size, base, seed):
    rng = random.Random(seed)
    surface = pygame.Surface(size)
    surface.fill(base)
    area = size[0] * size[1]
    scatter_patches(surface, rng, area // 4000, base)
    scatter_grass(surface, rng, area // 1400, mix(base, (0, 70, 0), 0.3), mix(base, WHITE, 0.25))
    return surface


def build_game_background():
    surface = build_grass((WIDTH, HEIGHT), GAME_GRASS, 2)
    pygame.draw.rect(surface, mix(GAME_GRASS, DEEP_GREEN, 0.45), BOARD_RECT.inflate(14, 14).move(4, 6), border_radius=8)
    board = pygame.Surface((BOARD_WIDTH, BOARD_HEIGHT))
    for grid_y in range(ROWS):
        for grid_x in range(COLS):
            color = BOARD_LIGHT if (grid_x + grid_y) % 2 == 0 else BOARD_DARK
            board.fill(color, (grid_x * CELL, grid_y * CELL, CELL, CELL))
    rng = random.Random(3)
    scatter_grass(board, rng, BOARD_WIDTH * BOARD_HEIGHT // 1800, mix(BOARD_LIGHT, (0, 70, 0), 0.3), mix(BOARD_LIGHT, WHITE, 0.3))
    surface.blit(board, BOARD_RECT.topleft)
    pygame.draw.rect(surface, DEEP_GREEN, BOARD_RECT.inflate(10, 10), width=5, border_radius=4)
    panel = pygame.Rect(30, 10, 840, 60)
    pygame.draw.rect(surface, SHADOW_GREEN, panel.move(0, 4), border_radius=16)
    pygame.draw.rect(surface, FOREST_GREEN, panel, border_radius=16)
    pygame.draw.rect(surface, DEEP_GREEN, panel, width=3, border_radius=16)
    return surface


def draw_eyes(surface, center, direction, cell):
    dx, dy = direction
    forward = cell * 0.17
    side = cell * 0.22
    radius = max(3, cell // 7)
    for sign in (-1, 1):
        eye_x = int(center[0] + dx * forward - dy * side * sign)
        eye_y = int(center[1] + dy * forward + dx * side * sign)
        pygame.draw.circle(surface, (25, 25, 25), (eye_x, eye_y), radius + 1)
        pygame.draw.circle(surface, WHITE, (eye_x, eye_y), radius)
        pygame.draw.circle(surface, (15, 15, 15), (eye_x + dx * 1, eye_y + dy * 1), max(1, radius // 2))


def draw_snake(surface, cells, direction, palette, origin, cell):
    body_color, outline_color = palette
    stripe_color = mix(body_color, outline_color, 0.2)
    border = max(2, cell // 14)
    inset = max(1, cell // 30)
    origin_x, origin_y = origin
    for index in range(len(cells) - 1, 0, -1):
        grid_x, grid_y = cells[index]
        outer = pygame.Rect(origin_x + grid_x * cell, origin_y + grid_y * cell, cell, cell).inflate(-2 * inset, -2 * inset)
        inner = outer.inflate(-2 * border, -2 * border)
        color = body_color if index % 2 == 1 else stripe_color
        pygame.draw.rect(surface, outline_color, outer, border_radius=cell // 3)
        pygame.draw.rect(surface, color, inner, border_radius=max(2, cell // 4))
    head_x, head_y = cells[0]
    head_outer = pygame.Rect(origin_x + head_x * cell, origin_y + head_y * cell, cell, cell)
    head_inner = head_outer.inflate(-2 * border, -2 * border)
    pygame.draw.rect(surface, outline_color, head_outer, border_radius=cell * 2 // 5)
    pygame.draw.rect(surface, body_color, head_inner, border_radius=cell // 3)
    draw_eyes(surface, head_outer.center, direction, cell)


def draw_apple(surface, center, radius, scale=1.0):
    center_x, center_y = center
    size = max(2, int(radius * scale))
    pygame.draw.circle(surface, (130, 15, 20), (center_x, center_y + 1), size + 1)
    pygame.draw.circle(surface, (205, 35, 40), (center_x, center_y), size)
    pygame.draw.circle(surface, (232, 72, 64), (center_x - size // 4, center_y - size // 4), max(2, size * 2 // 3))
    highlight = pygame.Rect(center_x - int(size * 0.6), center_y - int(size * 0.65), max(2, int(size * 0.45)), max(2, int(size * 0.3)))
    pygame.draw.ellipse(surface, (255, 220, 210), highlight)
    top = center_y - size
    pygame.draw.line(surface, (110, 70, 30), (center_x, top + 2), (center_x + int(2 * scale), top - int(5 * scale)), 3)
    leaf = [(2, -2), (6, -8), (13, -6), (8, 0)]
    points = [(center_x + int(px * scale), top + int(py * scale)) for px, py in leaf]
    pygame.draw.polygon(surface, (70, 180, 65), points)
    pygame.draw.polygon(surface, (30, 110, 40), points, 1)


class Button:
    def __init__(self, text, center, size=(320, 64)):
        self.text = text
        self.rect = pygame.Rect(0, 0, size[0], size[1])
        self.rect.center = center
        self.hover = 0.0

    def update(self, active, seconds):
        target = 1.0 if active else 0.0
        self.hover += (target - self.hover) * min(1.0, seconds * 14)

    def draw(self, surface, font):
        grow = int(10 * self.hover)
        rect = self.rect.inflate(grow, grow // 2)
        pygame.draw.rect(surface, SHADOW_GREEN, rect.move(0, 5), border_radius=18)
        pygame.draw.rect(surface, mix(LEAF_GREEN, LIGHT_GREEN, self.hover), rect, border_radius=18)
        pygame.draw.rect(surface, mix(DEEP_GREEN, WHITE, self.hover), rect, width=3, border_radius=18)
        draw_text(surface, font, self.text, WHITE, center=rect.center, shadow=DEEP_GREEN)


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.sounds = Sounds()
        self.fonts = {
            "title": load_font(80),
            "heading": load_font(60),
            "banner": load_font(44),
            "large": load_font(36),
            "medium": load_font(30),
            "value": load_font(28),
            "small": load_font(20),
            "label": load_font(15),
        }
        self.menu_background = build_grass((WIDTH, HEIGHT), MENU_GRASS, 1)
        self.game_background = build_game_background()
        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.overlay.fill((8, 32, 18, 150))
        self.fade_surface = pygame.Surface((WIDTH, HEIGHT))
        self.fade_surface.fill((0, 0, 0))
        self.high_score = load_high_score()
        self.color_index = 1
        self.color_focus = self.color_index
        self.state = "menu"
        self.focus = 0
        self.input_lock = 0.0
        self.fade = 0.0
        self.elapsed = 0
        self.buttons = {
            "menu": [
                Button("Start Game", (450, 285)),
                Button("Choose Snake Color", (450, 370)),
                Button("Exit", (450, 455)),
            ],
            "paused": [
                Button("Resume", (320, 445), (230, 58)),
                Button("Main Menu", (580, 445), (230, 58)),
            ],
            "game_over": [
                Button("Restart", (320, 460), (230, 58)),
                Button("Main Menu", (580, 460), (230, 58)),
            ],
            "victory": [
                Button("New Game", (320, 460), (230, 58)),
                Button("Main Menu", (580, 460), (230, 58)),
            ],
        }
        self.actions = {
            "menu": [self.start_game, self.open_colors, self.quit_game],
            "paused": [self.resume, self.go_menu],
            "game_over": [self.start_game, self.go_menu],
            "victory": [self.start_game, self.go_menu],
        }
        self.back_button = Button("Back", (450, 565), (220, 56))
        self.color_cards = []
        for index in range(len(SNAKE_COLORS)):
            row, column = divmod(index, 3)
            self.color_cards.append(pygame.Rect(111 + column * 234, 190 + row * 106, 210, 92))
        self.reset_round()

    def level(self):
        return self.apples_eaten // APPLES_PER_LEVEL + 1

    def current_delay(self):
        return max(MIN_DELAY_MS, START_DELAY_MS - (self.level() - 1) * DELAY_STEP_MS)

    def palette(self):
        return SNAKE_COLORS[self.color_index][1:]

    def reset_round(self):
        start_x = COLS // 2
        start_y = ROWS // 2
        self.snake = [(start_x, start_y), (start_x - 1, start_y), (start_x - 2, start_y)]
        self.direction = RIGHT
        self.direction_queue = []
        self.score = 0
        self.apples_eaten = 0
        self.move_timer = -START_GRACE_MS
        self.particles = []
        self.grow_timer = 0
        self.banner_timer = 0
        self.banner_text = ""
        self.food_age = 0
        self.new_record = False
        self.round_start_high = self.high_score
        self.food = None
        self.spawn_food()

    def spawn_food(self):
        occupied = set(self.snake)
        free_cells = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in occupied]
        if not free_cells:
            self.food = None
            return False
        self.food = random.choice(free_cells)
        self.food_age = 0
        return True

    def change_state(self, state, lock=0.2, fade=False):
        self.state = state
        self.input_lock = lock
        self.fade = 1.0 if fade else 0.0
        self.focus = 0
        for button in self.buttons.get(state, []):
            button.hover = 0.0
        self.back_button.hover = 0.0
        position = pygame.mouse.get_pos()
        for index, button in enumerate(self.buttons.get(state, [])):
            if button.rect.collidepoint(position):
                self.focus = index
        if state == "colors":
            self.color_focus = self.color_index

    def start_game(self):
        self.reset_round()
        self.change_state("playing", lock=0.0, fade=True)

    def open_colors(self):
        self.change_state("colors")

    def go_menu(self):
        self.change_state("menu", fade=True)

    def quit_game(self):
        self.running = False

    def pause(self):
        self.change_state("paused", lock=0.0)

    def resume(self):
        self.change_state("playing", lock=0.0)

    def finish_round(self, state, sound):
        self.new_record = self.score > 0 and self.score > self.round_start_high
        self.sounds.play(sound)
        self.change_state(state, lock=0.5)

    def end_game(self):
        self.finish_round("game_over", "game_over")

    def win_game(self):
        self.finish_round("victory", "victory")

    def select_color(self, index):
        self.color_index = index
        self.sounds.play("click")

    def activate(self, index):
        self.sounds.play("click")
        self.actions[self.state][index]()

    def queue_direction(self, direction):
        reference = self.direction_queue[-1] if self.direction_queue else self.direction
        if direction == reference:
            return
        if direction[0] == -reference[0] and direction[1] == -reference[1]:
            return
        if len(self.direction_queue) >= 2:
            return
        self.direction_queue.append(direction)

    def step(self):
        if self.direction_queue:
            self.direction = self.direction_queue.pop(0)
        head_x, head_y = self.snake[0]
        new_head = (head_x + self.direction[0], head_y + self.direction[1])
        if not (0 <= new_head[0] < COLS and 0 <= new_head[1] < ROWS):
            self.end_game()
            return
        eating = new_head == self.food
        blocking = self.snake if eating else self.snake[:-1]
        if new_head in blocking:
            self.end_game()
            return
        self.snake.insert(0, new_head)
        if not eating:
            self.snake.pop()
            return
        self.eat_apple()

    def eat_apple(self):
        previous_level = self.level()
        self.score += SCORE_PER_APPLE
        self.apples_eaten += 1
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)
        self.spawn_burst(self.food)
        self.grow_timer = GROW_EFFECT_MS
        if self.level() > previous_level:
            self.banner_text = "LEVEL " + str(self.level())
            self.banner_timer = BANNER_MS
        self.sounds.play("eat")
        if len(self.snake) >= TOTAL_CELLS:
            self.food = None
            self.win_game()
            return
        self.spawn_food()

    def spawn_burst(self, cell):
        center_x = BOARD_X + cell[0] * CELL + CELL // 2
        center_y = BOARD_Y + cell[1] * CELL + CELL // 2
        for _ in range(14):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60, 190)
            life = random.uniform(350, 650)
            self.particles.append([center_x, center_y, math.cos(angle) * speed, math.sin(angle) * speed, life, life, random.choice(BURST_COLORS)])

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == FOCUS_LOST_EVENT:
            if self.state == "playing":
                self.pause()
        elif self.state == "playing":
            self.handle_playing_event(event)
        elif self.state == "colors":
            self.handle_colors_event(event)
        else:
            self.handle_button_event(event)

    def handle_playing_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_p, pygame.K_ESCAPE):
            self.pause()
        elif event.key in KEY_DIRECTIONS:
            self.queue_direction(KEY_DIRECTIONS[event.key])

    def handle_button_event(self, event):
        buttons = self.buttons[self.state]
        if event.type == pygame.MOUSEMOTION:
            for index, button in enumerate(buttons):
                if button.rect.collidepoint(event.pos):
                    self.focus = index
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.input_lock > 0:
                return
            for index, button in enumerate(buttons):
                if button.rect.collidepoint(event.pos):
                    self.activate(index)
                    break
        elif event.type == pygame.KEYDOWN:
            if event.key in NAV_PREVIOUS:
                self.focus = (self.focus - 1) % len(buttons)
            elif event.key in NAV_NEXT:
                self.focus = (self.focus + 1) % len(buttons)
            elif event.key in CONFIRM_KEYS:
                if self.input_lock <= 0:
                    self.activate(self.focus)
            elif event.key == pygame.K_ESCAPE:
                self.handle_escape()
            else:
                self.handle_shortcut(event.key)

    def handle_escape(self):
        if self.state == "paused":
            self.resume()
        elif self.state in ("game_over", "victory") and self.input_lock <= 0:
            self.go_menu()

    def handle_shortcut(self, key):
        if self.state == "paused":
            if key == pygame.K_p:
                self.resume()
            elif key == pygame.K_m:
                self.go_menu()
        elif self.state in ("game_over", "victory") and self.input_lock <= 0:
            if key == pygame.K_r:
                self.start_game()
            elif key == pygame.K_m:
                self.go_menu()

    def color_card_at(self, position):
        for index, rect in enumerate(self.color_cards):
            if rect.collidepoint(position):
                return index
        return None

    def handle_colors_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            index = self.color_card_at(event.pos)
            if index is not None:
                self.color_focus = index
            elif self.back_button.rect.collidepoint(event.pos):
                self.color_focus = BACK_FOCUS
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.input_lock > 0:
                return
            index = self.color_card_at(event.pos)
            if index is not None:
                self.color_focus = index
                self.select_color(index)
            elif self.back_button.rect.collidepoint(event.pos):
                self.sounds.play("click")
                self.go_menu()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.go_menu()
            elif event.key in CONFIRM_KEYS:
                if self.input_lock <= 0:
                    if self.color_focus == BACK_FOCUS:
                        self.sounds.play("click")
                        self.go_menu()
                    else:
                        self.select_color(self.color_focus)
            elif event.key in NAV_PREVIOUS or event.key in NAV_NEXT:
                self.move_color_focus(event.key)

    def move_color_focus(self, key):
        focus = self.color_focus
        if focus == BACK_FOCUS:
            if key in (pygame.K_UP, pygame.K_w):
                self.color_focus = 7
            return
        row, column = divmod(focus, 3)
        go_back = False
        if key in (pygame.K_LEFT, pygame.K_a):
            column = (column - 1) % 3
        elif key in (pygame.K_RIGHT, pygame.K_d):
            column = (column + 1) % 3
        elif key in (pygame.K_UP, pygame.K_w):
            row = (row - 1) % 3
        elif key in (pygame.K_DOWN, pygame.K_s):
            if row == 2:
                go_back = True
            else:
                row += 1
        self.color_focus = BACK_FOCUS if go_back else row * 3 + column

    def update(self, dt_ms):
        seconds = dt_ms / 1000
        self.elapsed += dt_ms
        self.input_lock = max(0.0, self.input_lock - seconds)
        self.fade = max(0.0, self.fade - seconds / FADE_SECONDS)
        self.update_buttons(seconds)
        if self.state in ("playing", "game_over", "victory"):
            self.update_effects(dt_ms)
        if self.state == "playing":
            self.move_timer += dt_ms
            delay = self.current_delay()
            if self.move_timer >= delay:
                self.move_timer -= delay
                self.step()

    def update_buttons(self, seconds):
        if self.state == "colors":
            self.back_button.update(self.color_focus == BACK_FOCUS, seconds)
            return
        for index, button in enumerate(self.buttons.get(self.state, [])):
            button.update(index == self.focus, seconds)

    def update_effects(self, dt_ms):
        seconds = dt_ms / 1000
        self.food_age += dt_ms
        self.grow_timer = max(0, self.grow_timer - dt_ms)
        self.banner_timer = max(0, self.banner_timer - dt_ms)
        for particle in self.particles:
            particle[0] += particle[2] * seconds
            particle[1] += particle[3] * seconds
            particle[4] -= dt_ms
        self.particles = [particle for particle in self.particles if particle[4] > 0]

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "colors":
            self.draw_colors()
        else:
            self.draw_game()
            if self.state == "paused":
                self.draw_pause()
            elif self.state == "game_over":
                self.draw_result("GAME OVER", (255, 120, 105), "R: Restart    M / Esc: Main Menu    Enter: Select")
            elif self.state == "victory":
                self.draw_result("YOU WIN!", GOLD, "R: New Game    M / Esc: Main Menu    Enter: Select")
        if self.fade > 0:
            self.fade_surface.set_alpha(int(255 * self.fade))
            self.screen.blit(self.fade_surface, (0, 0))
        pygame.display.flip()

    def draw_banner(self, rect, text, font):
        pygame.draw.rect(self.screen, SHADOW_GREEN, rect.move(0, 6), border_radius=30)
        pygame.draw.rect(self.screen, FOREST_GREEN, rect, border_radius=30)
        pygame.draw.rect(self.screen, DEEP_GREEN, rect, width=5, border_radius=30)
        draw_text(self.screen, font, text, CREAM, center=(rect.centerx, rect.centery), shadow=DEEP_GREEN)

    def draw_menu(self):
        self.screen.blit(self.menu_background, (0, 0))
        banner = pygame.Rect(150, 40, 600, 165)
        pygame.draw.rect(self.screen, SHADOW_GREEN, banner.move(0, 6), border_radius=30)
        pygame.draw.rect(self.screen, FOREST_GREEN, banner, border_radius=30)
        pygame.draw.rect(self.screen, DEEP_GREEN, banner, width=5, border_radius=30)
        draw_text(self.screen, self.fonts["title"], "SNAKE GAME", CREAM, center=(450, 100), shadow=DEEP_GREEN)
        draw_text(self.screen, self.fonts["small"], "Eat apples. Grow longer. Stay alive.", SOFT_GREEN, center=(450, 170))
        for button in self.buttons["menu"]:
            button.draw(self.screen, self.fonts["medium"])
        self.draw_menu_snake()
        draw_text(self.screen, self.fonts["small"], "Click a button, or use Up / Down and Enter", DEEP_GREEN, center=(450, 668))

    def draw_menu_snake(self):
        body_color, outline_color = self.palette()
        time = self.elapsed / 1000
        count = 22
        points = []
        for index in range(count):
            x = 190 + index * 19
            y = 590 + math.sin(index * 0.5 - time * 3) * 16
            points.append((int(x), int(y), int(5 + index * 0.4)))
        for x, y, radius in points:
            pygame.draw.circle(self.screen, outline_color, (x, y), radius + 2)
        for x, y, radius in points:
            pygame.draw.circle(self.screen, body_color, (x, y), radius)
        head_x, head_y, _ = points[-1]
        draw_eyes(self.screen, (head_x, head_y), RIGHT, 28)
        apple_y = 590 + int(math.sin(time * 4) * 3)
        draw_apple(self.screen, (head_x + 75, apple_y), 16)

    def draw_colors(self):
        self.screen.blit(self.menu_background, (0, 0))
        self.draw_banner(pygame.Rect(150, 30, 600, 90), "CHOOSE SNAKE COLOR", self.fonts["banner"])
        preview_cells = [(5, 0), (4, 0), (3, 0), (2, 0), (1, 0), (0, 0)]
        draw_snake(self.screen, preview_cells, RIGHT, self.palette(), (372, 135), 26)
        draw_apple(self.screen, (590, 149), 10)
        for index in range(len(SNAKE_COLORS)):
            self.draw_color_card(index)
        self.back_button.draw(self.screen, self.fonts["medium"])

    def draw_color_card(self, index):
        name, body_color, outline_color = SNAKE_COLORS[index]
        rect = self.color_cards[index]
        focused = index == self.color_focus
        selected = index == self.color_index
        pygame.draw.rect(self.screen, SHADOW_GREEN, rect.move(0, 5), border_radius=16)
        pygame.draw.rect(self.screen, (252, 255, 246) if focused else (226, 244, 214), rect, border_radius=16)
        if selected:
            pygame.draw.rect(self.screen, GOLD, rect, width=5, border_radius=16)
        elif focused:
            pygame.draw.rect(self.screen, FOREST_GREEN, rect, width=4, border_radius=16)
        else:
            pygame.draw.rect(self.screen, (90, 150, 100), rect, width=2, border_radius=16)
        swatch_center = (rect.x + 52, rect.centery)
        pygame.draw.circle(self.screen, outline_color, swatch_center, 28)
        pygame.draw.circle(self.screen, body_color, swatch_center, 24)
        draw_text(self.screen, self.fonts["medium"], name, DEEP_GREEN, midleft=(rect.x + 98, rect.centery))
        if selected:
            badge = (rect.right - 24, rect.y + 24)
            pygame.draw.circle(self.screen, FOREST_GREEN, badge, 14)
            pygame.draw.lines(self.screen, WHITE, False, [(badge[0] - 6, badge[1]), (badge[0] - 2, badge[1] + 5), (badge[0] + 6, badge[1] - 5)], 3)

    def draw_game(self):
        self.screen.blit(self.game_background, (0, 0))
        self.draw_hud()
        if self.food is not None:
            scale = min(1.0, 0.4 + 0.6 * self.food_age / APPLE_POP_MS)
            food_x = BOARD_X + self.food[0] * CELL + CELL // 2
            food_y = BOARD_Y + self.food[1] * CELL + CELL // 2 + 2
            draw_apple(self.screen, (food_x, food_y), 11, scale)
        draw_snake(self.screen, self.snake, self.direction, self.palette(), (BOARD_X, BOARD_Y), CELL)
        self.screen.set_clip(BOARD_RECT)
        if self.grow_timer > 0:
            progress = 1 - self.grow_timer / GROW_EFFECT_MS
            head_x = BOARD_X + self.snake[0][0] * CELL + CELL // 2
            head_y = BOARD_Y + self.snake[0][1] * CELL + CELL // 2
            ring_radius = int(CELL * 0.5 + progress * CELL * 0.6)
            ring_width = int(3 * (1 - progress)) + 1
            pygame.draw.circle(self.screen, mix(WHITE, BOARD_LIGHT, progress), (head_x, head_y), ring_radius, ring_width)
        for particle in self.particles:
            radius = max(1, int(1 + 4 * particle[4] / particle[5]))
            pygame.draw.circle(self.screen, particle[6], (int(particle[0]), int(particle[1])), radius)
        if self.banner_timer > 0:
            rise = int(20 * (1 - self.banner_timer / BANNER_MS))
            draw_text(self.screen, self.fonts["large"], self.banner_text, (255, 240, 120), center=(BOARD_RECT.centerx, BOARD_Y + 50 - rise), shadow=DEEP_GREEN)
        self.screen.set_clip(None)

    def draw_hud(self):
        name, body_color, outline_color = SNAKE_COLORS[self.color_index]
        stats = [
            ("SCORE", str(self.score), 56),
            ("BEST", str(self.high_score), 200),
            ("LEVEL", str(self.level()), 340),
            ("LENGTH", str(len(self.snake)), 450),
        ]
        for label, value, x in stats:
            draw_text(self.screen, self.fonts["label"], label, SOFT_GREEN, topleft=(x, 16))
            draw_text(self.screen, self.fonts["value"], value, WHITE, topleft=(x, 31))
        draw_text(self.screen, self.fonts["label"], "SNAKE", SOFT_GREEN, topleft=(600, 16))
        pygame.draw.circle(self.screen, outline_color, (612, 49), 11)
        pygame.draw.circle(self.screen, body_color, (612, 49), 8)
        draw_text(self.screen, self.fonts["value"], name, WHITE, midleft=(632, 49))
        draw_text(self.screen, self.fonts["small"], "P / Esc: Pause", SOFT_GREEN, midright=(850, 41))

    def draw_panel(self, rect, heading, heading_color):
        self.screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(self.screen, DEEP_GREEN, rect.move(0, 8), border_radius=28)
        pygame.draw.rect(self.screen, FOREST_GREEN, rect, border_radius=28)
        pygame.draw.rect(self.screen, SOFT_GREEN, rect, width=3, border_radius=28)
        draw_text(self.screen, self.fonts["heading"], heading, heading_color, center=(rect.centerx, rect.y + 62), shadow=DEEP_GREEN)

    def draw_pause(self):
        rect = pygame.Rect(0, 0, 520, 300)
        rect.center = (450, 350)
        self.draw_panel(rect, "PAUSED", CREAM)
        draw_text(self.screen, self.fonts["medium"], "Press P or Esc to resume", WHITE, center=(450, 325))
        draw_text(self.screen, self.fonts["small"], "Press M for the main menu", SOFT_GREEN, center=(450, 365))
        for button in self.buttons["paused"]:
            button.draw(self.screen, self.fonts["medium"])

    def draw_result(self, heading, heading_color, instructions):
        rect = pygame.Rect(0, 0, 520, 380)
        rect.center = (450, 350)
        self.draw_panel(rect, heading, heading_color)
        draw_text(self.screen, self.fonts["large"], "Score: " + str(self.score), WHITE, center=(450, 285))
        draw_text(self.screen, self.fonts["medium"], "High Score: " + str(self.high_score), SOFT_GREEN, center=(450, 335))
        if self.new_record:
            draw_text(self.screen, self.fonts["medium"], "NEW HIGH SCORE!", GOLD, center=(450, 383), shadow=DEEP_GREEN)
        for button in self.buttons[self.state]:
            button.draw(self.screen, self.fonts["medium"])
        draw_text(self.screen, self.fonts["small"], instructions, SOFT_GREEN, center=(450, 515))

    def run(self):
        while self.running:
            dt_ms = self.clock.tick(FPS)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(min(dt_ms, MAX_FRAME_MS))
            self.draw()


def main():
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Snake Game")
    game = Game(screen)
    game.run()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()