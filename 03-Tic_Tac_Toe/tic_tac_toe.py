"""
Tic Tac Toe - a polished desktop game built with Pygame.

Run:  python tic_tac_toe.py
Needs: pip install pygame
"""

import math
import random
import sys
from functools import lru_cache

import pygame

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
WIDTH, HEIGHT = 900, 700
FPS = 60

# Colors
BG_DARK = (21, 21, 21)          # #151515
WHITE = (255, 255, 255)
GREY = (189, 189, 189)          # #BDBDBD
X_COLOR = (33, 150, 243)        # #2196F3
O_COLOR = (244, 67, 54)         # #F44336
BG_X = (220, 238, 255)          # #DCEEFF  (X's turn)
BG_O = (255, 224, 224)          # #FFE0E0  (O's turn)
BG_DRAW = (236, 236, 236)
INK = (38, 50, 56)              # dark text on light backgrounds
GRID = (144, 164, 174)
HIGHLIGHT = (255, 193, 7)       # winning cells
HIGHLIGHT_LINE = (255, 143, 0)  # winning strike line
CONFETTI_COLORS = [(255, 82, 82), (255, 193, 7), (76, 175, 80), (33, 150, 243),
                   (171, 71, 188), (255, 112, 67), (0, 188, 212), (255, 64, 129)]

SYMBOL_COLOR = {"X": X_COLOR, "O": O_COLOR}
SYMBOL_BG = {"X": BG_X, "O": BG_O}

# Game states (one handler per state keeps the code free of nested ifs)
MENU, SYMBOL_SELECT, PLAYING, GAME_OVER = "menu", "symbol_select", "playing", "game_over"
MODE_COMPUTER, MODE_FRIEND = "computer", "friend"

# Board geometry
BOARD_SIZE = 420
CELL = BOARD_SIZE // 3
BOARD_LEFT = (WIDTH - BOARD_SIZE) // 2
BOARD_TOP = 150

RESULT_BUTTON_DELAY = 1.2   # seconds before Play Again / Main Menu appear
CONFETTI_DURATION = 2.5     # seconds of continuous confetti emission


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(a, b, t):
    return tuple(int(round(lerp(a[i], b[i], t))) for i in range(3))


def ease_out_back(t):
    """Easing with a slight overshoot - gives symbols a 'pop' when placed."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def other(symbol):
    return "O" if symbol == "X" else "X"


# --------------------------------------------------------------------------
# Game logic (pure functions, no Pygame involved)
# --------------------------------------------------------------------------
# All 8 winning lines as board indices:  0 1 2 / 3 4 5 / 6 7 8
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8),      # rows
         (0, 3, 6), (1, 4, 7), (2, 5, 8),      # columns
         (0, 4, 8), (2, 4, 6)]                 # diagonals


def check_winner(board):
    """Return (symbol, line) if somebody has three in a row, else None."""
    for a, b, c in LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a], (a, b, c)
    return None


def check_draw(board):
    """Board full and nobody has won."""
    return None not in board and check_winner(board) is None


@lru_cache(maxsize=None)
def minimax(board, turn, ai):
    """
    Score a position from the AI's point of view (board is a tuple).
    +ve = AI wins, -ve = AI loses, 0 = draw. Faster wins / slower losses
    score better because the score includes the number of empty cells.
    Results are cached, so the full game tree is only searched once.
    """
    result = check_winner(board)
    empties = board.count(None)
    if result:
        return (1 + empties) if result[0] == ai else -(1 + empties)
    if empties == 0:
        return 0

    scores = []
    for i, cell in enumerate(board):
        if cell is None:
            child = board[:i] + (turn,) + board[i + 1:]
            scores.append(minimax(child, other(turn), ai))
    return max(scores) if turn == ai else min(scores)


def best_move(board, ai):
    """
    Pick an optimal move for `ai`. Minimax automatically takes immediate wins
    and blocks the opponent's immediate wins, since those score best. Among
    equally good moves one is chosen at random so games vary.
    """
    board = tuple(board)
    scored = []
    for i, cell in enumerate(board):
        if cell is None:
            child = board[:i] + (ai,) + board[i + 1:]
            scored.append((minimax(child, other(ai), ai), i))
    top = max(score for score, _ in scored)
    return random.choice([i for score, i in scored if score == top])


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
@lru_cache(maxsize=256)
def symbol_surface(symbol, size):
    """Render an anti-aliased X or O (drawn at 2x then smoothscaled down)."""
    ss = 2
    side = size + size // 4 + 8
    big = pygame.Surface((side * ss, side * ss), pygame.SRCALPHA)
    cx = cy = side * ss // 2
    half = size * ss / 2
    thick = max(3, int(size * ss * 0.15))
    color = SYMBOL_COLOR[symbol]

    if symbol == "X":
        ends = [((cx - half, cy - half), (cx + half, cy + half)),
                ((cx + half, cy - half), (cx - half, cy + half))]
        for p, q in ends:
            pygame.draw.line(big, color, p, q, thick)
            for end in (p, q):  # rounded caps
                pygame.draw.circle(big, color, (int(end[0]), int(end[1])), thick // 2)
    else:
        pygame.draw.circle(big, color, (cx, cy), int(half), thick)

    return pygame.transform.smoothscale(big, (side, side))


def draw_symbol(surface, symbol, center, size, alpha=255):
    if size < 4:
        return
    img = symbol_surface(symbol, int(size))
    img.set_alpha(alpha)
    surface.blit(img, img.get_rect(center=center))


class Button:
    """Rounded button (or symbol card) with a smooth hover animation."""

    def __init__(self, rect, label="", symbol=None, base=(38, 38, 38),
                 hover_color=(62, 62, 62), text_color=WHITE, accent=(90, 90, 90)):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.symbol = symbol
        self.base = base
        self.hover_color = hover_color
        self.text_color = text_color
        self.accent = accent
        self.hover = 0.0   # 0 = idle, 1 = fully hovered

    def update(self, dt, mouse_pos, enabled=True):
        target = 1.0 if enabled and self.rect.collidepoint(mouse_pos) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    def draw(self, surface, font, alpha=255):
        grow = int(10 * self.hover)
        rect = self.rect.inflate(grow, grow // 2)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        body = layer.get_rect()
        pygame.draw.rect(layer, lerp_color(self.base, self.hover_color, self.hover),
                         body, border_radius=18)
        pygame.draw.rect(layer, lerp_color((60, 60, 60), self.accent, self.hover),
                         body, width=3, border_radius=18)
        if self.symbol:
            draw_symbol(layer, self.symbol, body.center, int(120 * (1 + 0.1 * self.hover)))
        else:
            text = font.render(self.label, True, self.text_color)
            layer.blit(text, text.get_rect(center=body.center))
        layer.set_alpha(alpha)
        surface.blit(layer, rect)


# --------------------------------------------------------------------------
# Confetti
# --------------------------------------------------------------------------
class Confetto:
    """One falling paper piece. Motion is driven by delta time."""

    def __init__(self, burst):
        self.x = random.uniform(0, WIDTH)
        self.y = random.uniform(-260, -10) if burst else random.uniform(-40, -10)
        self.vy = random.uniform(120, 320)                  # different speeds
        self.sway = random.uniform(20, 70)
        self.sway_speed = random.uniform(2, 5)
        self.phase = random.uniform(0, math.tau)
        self.w = random.uniform(6, 12)                      # different sizes
        self.h = random.uniform(10, 18)
        self.spin = random.uniform(-6, 6)
        self.angle = random.uniform(0, math.tau)
        self.color = random.choice(CONFETTI_COLORS)
        self.age = 0.0

    def update(self, dt):
        self.age += dt
        self.y += self.vy * dt
        self.x += math.cos(self.age * self.sway_speed + self.phase) * self.sway * dt
        self.angle += self.spin * dt

    def draw(self, surface):
        # Squash the width with |cos| so pieces look like they flutter in 3D
        hw = self.w / 2 * max(0.2, abs(math.cos(self.angle)))
        hh = self.h / 2
        tilt = math.sin(self.age * self.sway_speed + self.phase) * 0.6
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        points = [(self.x + px * cos_t - py * sin_t, self.y + px * sin_t + py * cos_t)
                  for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        pygame.draw.polygon(surface, self.color, points)


class ConfettiSystem:
    def __init__(self):
        self.pieces = []
        self.emit_time = 0.0
        self.spawn_accumulator = 0.0

    def start(self):
        self.pieces = [Confetto(burst=True) for _ in range(120)]
        self.emit_time = CONFETTI_DURATION
        self.spawn_accumulator = 0.0

    def clear(self):
        self.pieces = []
        self.emit_time = 0.0

    def update(self, dt):
        if self.emit_time > 0:                    # keep a gentle stream going
            self.emit_time -= dt
            self.spawn_accumulator += dt * 60
            while self.spawn_accumulator >= 1:
                self.spawn_accumulator -= 1
                self.pieces.append(Confetto(burst=False))
        for piece in self.pieces:
            piece.update(dt)
        self.pieces = [p for p in self.pieces if p.y < HEIGHT + 30]

    def draw(self, surface):
        for piece in self.pieces:
            piece.draw(surface)


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Tic Tac Toe")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        names = "segoeui,helveticaneue,helvetica,arial,dejavusans"
        self.font_title = pygame.font.SysFont(names, 92, bold=True)
        self.font_header = pygame.font.SysFont(names, 54, bold=True)
        self.font_result = pygame.font.SysFont(names, 68, bold=True)
        self.font_turn = pygame.font.SysFont(names, 40, bold=True)
        self.font_button = pygame.font.SysFont(names, 30, bold=True)
        self.font_small = pygame.font.SysFont(names, 22)

        self.confetti = ConfettiSystem()
        self.bg = BG_DARK
        self.state = MENU
        self.mode = None
        self.player_symbol = None   # human (vs computer) or Player 1 (vs friend)
        self.build_buttons()
        self.reset_game()

    # ---- setup -----------------------------------------------------------
    def build_buttons(self):
        cx = WIDTH // 2
        w, h = 420, 72
        self.btn_computer = Button((cx - w // 2, 290, w, h), "PLAY WITH COMPUTER")
        self.btn_friend = Button((cx - w // 2, 380, w, h), "PLAY AGAINST FRIEND")
        self.btn_exit = Button((cx - w // 2, 470, w, h), "EXIT",
                               hover_color=(90, 36, 36), accent=O_COLOR)
        self.menu_buttons = [self.btn_computer, self.btn_friend, self.btn_exit]

        self.btn_pick_x = Button((cx - 290, 250, 240, 240), symbol="X", accent=X_COLOR,
                                 base=(34, 34, 34), hover_color=(48, 48, 48))
        self.btn_pick_o = Button((cx + 50, 250, 240, 240), symbol="O", accent=O_COLOR,
                                 base=(34, 34, 34), hover_color=(48, 48, 48))
        self.btn_back = Button((cx - 100, 570, 200, 54), "BACK")
        self.symbol_buttons = [self.btn_pick_x, self.btn_pick_o, self.btn_back]

        # Buttons on the light result screen use dark styling
        dark = dict(base=INK, hover_color=(69, 90, 100), accent=INK)
        self.btn_again = Button((cx - 270, 612, 250, 56), "PLAY AGAIN", **dark)
        self.btn_main = Button((cx + 20, 612, 250, 56), "MAIN MENU", **dark)
        self.result_buttons = [self.btn_again, self.btn_main]

    def reset_game(self):
        """Completely clear everything belonging to the previous game."""
        self.board = [None] * 9
        self.current = "X"              # X always moves first
        self.winner = None
        self.win_line = None
        self.pop = [1.0] * 9            # per-cell placement animation progress
        self.invalid_cell = None
        self.invalid_timer = 0.0
        self.ai_timer = 0.0
        self.result_time = 0.0
        self.confetti.clear()

    def start_game(self, symbol):
        self.reset_game()
        self.player_symbol = symbol
        self.state = PLAYING
        self.begin_turn()

    def go_to_menu(self):
        self.reset_game()
        self.mode = None
        self.player_symbol = None
        self.state = MENU

    def quit(self):
        pygame.quit()
        sys.exit()

    # ---- turn logic --------------------------------------------------------
    @property
    def computer_symbol(self):
        return other(self.player_symbol) if self.mode == MODE_COMPUTER else None

    def is_computer_turn(self):
        return (self.state == PLAYING and self.mode == MODE_COMPUTER
                and self.current == self.computer_symbol)

    def begin_turn(self):
        if self.is_computer_turn():
            self.ai_timer = random.uniform(0.4, 0.7)   # non-blocking "thinking" delay

    def place_move(self, index):
        """Try to place the current symbol. Returns False if the move is illegal."""
        if self.state != PLAYING or self.board[index] is not None:
            return False

        self.board[index] = self.current
        self.pop[index] = 0.0

        result = check_winner(self.board)
        if result:
            self.winner, self.win_line = result
            self.end_game(celebrate=True)
        elif check_draw(self.board):
            self.end_game(celebrate=False)
        else:
            self.current = other(self.current)
            self.begin_turn()
        return True

    def end_game(self, celebrate):
        self.state = GAME_OVER
        self.result_time = 0.0
        if celebrate:
            self.confetti.start()

    def computer_move(self):
        self.place_move(best_move(self.board, self.computer_symbol))

    def cell_at(self, pos):
        """Map a mouse position to a board index, or None if outside the board."""
        x, y = pos
        if not (BOARD_LEFT <= x < BOARD_LEFT + BOARD_SIZE and
                BOARD_TOP <= y < BOARD_TOP + BOARD_SIZE):
            return None
        col = (x - BOARD_LEFT) // CELL
        row = (y - BOARD_TOP) // CELL
        return row * 3 + col

    def cell_rect(self, index):
        row, col = divmod(index, 3)
        return pygame.Rect(BOARD_LEFT + col * CELL, BOARD_TOP + row * CELL, CELL, CELL)

    # ---- text --------------------------------------------------------------
    def turn_text(self):
        if self.mode == MODE_COMPUTER:
            who = "Your" if self.current == self.player_symbol else "Computer's"
        else:
            number = 1 if self.current == self.player_symbol else 2
            who = f"Player {number}'s"
        return f"{who} Turn — {self.current}"

    def result_text(self):
        if self.winner is None:
            return "DRAW!"
        if self.mode == MODE_COMPUTER:
            return "YOU WON!" if self.winner == self.player_symbol else "Computer won!"
        number = 1 if self.winner == self.player_symbol else 2
        return f"Player {number} ({self.winner}) won!"

    # ---- input (mouse handling, one handler per state) -----------------------
    def on_click(self, pos):
        handlers = {MENU: self.click_menu, SYMBOL_SELECT: self.click_symbol_select,
                    PLAYING: self.click_playing, GAME_OVER: self.click_game_over}
        handlers[self.state](pos)

    def click_menu(self, pos):
        if self.btn_computer.hit(pos):
            self.mode, self.state = MODE_COMPUTER, SYMBOL_SELECT
        elif self.btn_friend.hit(pos):
            self.mode, self.state = MODE_FRIEND, SYMBOL_SELECT
        elif self.btn_exit.hit(pos):
            self.quit()

    def click_symbol_select(self, pos):
        if self.btn_pick_x.hit(pos):
            self.start_game("X")
        elif self.btn_pick_o.hit(pos):
            self.start_game("O")
        elif self.btn_back.hit(pos):
            self.go_to_menu()

    def click_playing(self, pos):
        self.handle_board_click(pos)

    def handle_board_click(self, pos):
        if self.is_computer_turn():            # ignore clicks while the AI "thinks"
            return
        index = self.cell_at(pos)
        if index is None:                      # clicked outside the board
            return
        if not self.place_move(index):         # occupied cell: no change, flash red
            self.invalid_cell, self.invalid_timer = index, 0.35

    def click_game_over(self, pos):
        if self.result_time < RESULT_BUTTON_DELAY:
            return
        if self.btn_again.hit(pos):
            self.reset_game()
            self.state = SYMBOL_SELECT         # same mode, choose X/O again
        elif self.btn_main.hit(pos):
            self.go_to_menu()

    def on_escape(self):
        if self.state == MENU:
            self.quit()
        else:
            self.go_to_menu()

    # ---- update ------------------------------------------------------------
    def target_background(self):
        if self.state in (MENU, SYMBOL_SELECT):
            return BG_DARK
        if self.state == PLAYING:
            return SYMBOL_BG[self.current]
        return SYMBOL_BG[self.winner] if self.winner else BG_DRAW

    def update(self, dt):
        mouse = pygame.mouse.get_pos()

        # Smoothly fade the background toward the colour for the current state
        target = self.target_background()
        self.bg = lerp_color(self.bg, target, 1 - math.exp(-dt * 12))
        if max(abs(self.bg[i] - target[i]) for i in range(3)) <= 2:
            self.bg = target

        if self.state == MENU:
            for b in self.menu_buttons:
                b.update(dt, mouse)
        elif self.state == SYMBOL_SELECT:
            for b in self.symbol_buttons:
                b.update(dt, mouse)
        elif self.state == PLAYING:
            if self.is_computer_turn():
                self.ai_timer -= dt
                if self.ai_timer <= 0:
                    self.computer_move()
        elif self.state == GAME_OVER:
            self.result_time += dt
            for b in self.result_buttons:
                b.update(dt, mouse, enabled=self.result_time >= RESULT_BUTTON_DELAY)

        # Animations that run in every state
        self.pop = [min(1.0, p + dt / 0.3) for p in self.pop]
        self.invalid_timer = max(0.0, self.invalid_timer - dt)
        self.confetti.update(dt)

    # ---- drawing -----------------------------------------------------------
    def draw_text(self, text, font, color, center):
        surf = font.render(text, True, color)
        self.screen.blit(surf, surf.get_rect(center=center))

    def draw(self):
        self.screen.fill(self.bg)
        {MENU: self.draw_main_menu, SYMBOL_SELECT: self.draw_symbol_selection,
         PLAYING: self.draw_game, GAME_OVER: self.draw_game_over}[self.state]()

    def draw_main_menu(self):
        self.draw_text("TIC TAC TOE", self.font_title, WHITE, (WIDTH // 2, 150))
        pygame.draw.rect(self.screen, X_COLOR, (WIDTH // 2 - 60, 212, 60, 6), border_radius=3)
        pygame.draw.rect(self.screen, O_COLOR, (WIDTH // 2, 212, 60, 6), border_radius=3)
        self.draw_text("Three in a row wins", self.font_small, GREY, (WIDTH // 2, 245))
        for b in self.menu_buttons:
            b.draw(self.screen, self.font_button)

    def draw_symbol_selection(self):
        self.draw_text("CHOOSE YOUR SYMBOL", self.font_header, WHITE, (WIDTH // 2, 120))
        subtitle = ("You are playing against the computer" if self.mode == MODE_COMPUTER
                    else "Player 1, pick your symbol")
        self.draw_text(subtitle, self.font_small, GREY, (WIDTH // 2, 180))
        for b in self.symbol_buttons:
            b.draw(self.screen, self.font_button)
        self.draw_text("X always goes first", self.font_small, GREY, (WIDTH // 2, 525))

    def draw_board(self):
        mouse = pygame.mouse.get_pos()

        # Panel with a soft shadow
        panel = pygame.Rect(BOARD_LEFT, BOARD_TOP, BOARD_SIZE, BOARD_SIZE).inflate(36, 36)
        pygame.draw.rect(self.screen, lerp_color(self.bg, (0, 0, 0), 0.12),
                         panel.move(0, 6), border_radius=28)
        pygame.draw.rect(self.screen, WHITE, panel, border_radius=28)

        # Pulsing highlight under the winning cells
        if self.win_line:
            pulse = 0.5 + 0.5 * math.sin(self.result_time * 6)
            for i in self.win_line:
                layer = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                pygame.draw.rect(layer, (*HIGHLIGHT, int(90 + 110 * pulse)),
                                 layer.get_rect().inflate(-12, -12), border_radius=14)
                self.screen.blit(layer, self.cell_rect(i))

        # Hover ghost preview on empty cells (only when it is the human's turn)
        hovered = self.cell_at(mouse)
        if (self.state == PLAYING and not self.is_computer_turn()
                and hovered is not None and self.board[hovered] is None):
            rect = self.cell_rect(hovered)
            pygame.draw.rect(self.screen, (240, 244, 247), rect.inflate(-12, -12), border_radius=14)
            draw_symbol(self.screen, self.current, rect.center, int(CELL * 0.58), alpha=70)

        # Red flash for an invalid (occupied-cell) click
        if self.invalid_cell is not None and self.invalid_timer > 0:
            layer = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            pygame.draw.rect(layer, (*O_COLOR, int(150 * self.invalid_timer / 0.35)),
                             layer.get_rect().inflate(-12, -12), border_radius=14)
            self.screen.blit(layer, self.cell_rect(self.invalid_cell))

        # Grid lines
        inset = 16
        for k in (1, 2):
            v = BOARD_LEFT + k * CELL
            h = BOARD_TOP + k * CELL
            pygame.draw.line(self.screen, GRID, (v, BOARD_TOP + inset),
                             (v, BOARD_TOP + BOARD_SIZE - inset), 6)
            pygame.draw.line(self.screen, GRID, (BOARD_LEFT + inset, h),
                             (BOARD_LEFT + BOARD_SIZE - inset, h), 6)

        # Symbols, with a scale + fade-in animation when placed
        for i, symbol in enumerate(self.board):
            if symbol is None:
                continue
            progress = self.pop[i]
            size = int(CELL * 0.58 * ease_out_back(progress))
            draw_symbol(self.screen, symbol, self.cell_rect(i).center, size,
                        alpha=int(255 * min(1.0, progress * 2.5)))

        # Strike line through the winning combination (grows in)
        if self.win_line:
            start = self.cell_rect(self.win_line[0]).center
            end = self.cell_rect(self.win_line[2]).center
            grow = min(1.0, self.result_time / 0.4)
            tip = (lerp(start[0], end[0], grow), lerp(start[1], end[1], grow))
            pygame.draw.line(self.screen, HIGHLIGHT_LINE, start, tip, 9)
            pygame.draw.circle(self.screen, HIGHLIGHT_LINE, start, 4)
            pygame.draw.circle(self.screen, HIGHLIGHT_LINE, tip, 4)

    def draw_game(self):
        self.draw_text(self.turn_text(), self.font_turn,
                       SYMBOL_COLOR[self.current], (WIDTH // 2, 75))
        self.draw_board()
        self.draw_text("Press ESC for the main menu", self.font_small,
                       GRID, (WIDTH // 2, 660))

    def draw_game_over(self):
        self.draw_board()
        self.confetti.draw(self.screen)   # drawn before the text so it never covers it

        # Result message with a pop-in animation
        color = SYMBOL_COLOR[self.winner] if self.winner else INK
        text = self.font_result.render(self.result_text(), True, color)
        scale = max(0.05, ease_out_back(min(1.0, self.result_time / 0.5)))
        size = (max(1, int(text.get_width() * scale)), max(1, int(text.get_height() * scale)))
        text = pygame.transform.smoothscale(text, size)
        self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 72)))

        # Buttons fade in after a short delay
        fade = (self.result_time - RESULT_BUTTON_DELAY) / 0.4
        if fade > 0:
            for b in self.result_buttons:
                b.draw(self.screen, self.font_button, alpha=int(255 * min(1.0, fade)))

    # ---- main loop ---------------------------------------------------------
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)   # delta time in seconds
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.on_click(event.pos)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.on_escape()
            self.update(dt)
            self.draw()
            pygame.display.flip()


if __name__ == "__main__":
    Game().run()