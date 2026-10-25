# Snake Game

A classic Snake game built with Python and Pygame, featuring a grass-themed board, smooth animations, sound effects, customizable snake colors, and increasing difficulty.

## Features

* Eat apples to earn points and grow longer.
* Choose from nine snake colors.
* Increasing speed and levels as you collect apples.
* Pause, resume, restart, and return to the main menu.
* Wall and self-collision detection, plus a board-completion victory condition.
* Animated effects and procedurally generated graphics and sounds.
* Persistent high score saved locally in `snake_highscore.txt`.

## Requirements

* Python 3.10 or newer
* Pygame **or** Pygame Community Edition (Pygame-CE)

## Setup and Run

1. Install Python from [python.org](https://www.python.org/downloads/).

2. Open a terminal in the project folder.

3. **(Recommended)** Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install Pygame:

   ```powershell
   python -m pip install pygame
   ```

5. Run the game:

   ```powershell
   python snake.py
   ```

### If Pygame Does Not Work

Try Pygame-CE in the same environment. Avoid installing both packages together:

```powershell
python -m pip uninstall pygame
python -m pip install pygame-ce
python snake.py
```

Both packages use `import pygame`, so no source-code change is needed. If you have interpreter issues in VS Code, make sure the selected Python interpreter is the same one where you installed the package.

## Controls

| Action                  | Controls                        |
| ----------------------- | ------------------------------- |
| Move                    | `WASD` or arrow keys            |
| Pause / Resume          | `P` or `Esc`                    |
| Navigate menus          | `WASD` or arrow keys            |
| Select menu option      | `Enter`, `Space`, or left-click |
| Restart after game over | `R`                             |
| Return to main menu     | `M`                             |

## Project Files

* `snake.py` — Main game code.
* `snake_highscore.txt` — Created automatically to store the high score.

No external images, fonts, or audio files are required.

## Possible Future Improvements

* Difficulty settings and adjustable game speed.
* Audio and visual settings.
* Additional themes and game modes.
* A leaderboard and detailed statistics.

## Conclusion

This project brings the classic Snake experience together with modern visuals, responsive controls, and progressive gameplay in a self-contained Python game. Clone the project, install the dependency, and enjoy playing—or build on it with your own improvements.
