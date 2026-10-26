# Connect 4

A modern Connect 4 game built with Python and Pygame, featuring Player vs Player and Player vs Computer modes, multiple AI difficulty levels, smooth animations, sound effects, and background music.

## Features

* **Game Modes:** Play against a friend or the computer.
* **AI Difficulty:** Choose Easy, Medium, or Hard.
* **Customizable Settings:** Adjust audio, toggle animations, and switch between windowed and fullscreen modes.
* **Visual Effects:** Animated disc drops, winning highlights, and particle effects.
* **Audio:** Procedurally generated sound effects and background music.
* **Statistics:** Track wins, draws, total moves, and game duration.
* **Data Persistence:** Automatically saves settings and statistics.

## Requirements

* Python 3.x
* Pygame

## Installation and Usage

Install Pygame:

```bash
py -m pip install pygame
```

Run the game:

```bash
py connect4.py
```

Replace `connect4.py` with the name of your Python file if it differs.

## Controls

| Key                | Action            |
| ------------------ | ----------------- |
| Left / Right Arrow | Select a column   |
| Enter / Space      | Drop a disc       |
| Esc                | Pause the game    |
| R                  | Restart the game  |
| M                  | Toggle sound      |
| F11                | Toggle fullscreen |

You can also click a column to drop a disc.

## Technologies Used

* Python
* Pygame
* Minimax Algorithm
* Alpha-Beta Pruning
* JSON for persistent data storage

---
