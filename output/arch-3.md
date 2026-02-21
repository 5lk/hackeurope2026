# Handoff: arch-3

**Summary**: An architecture and design specification for the rendering and input handling interfaces.

### 1. Architecture/Design Artifacts

I will create the following design documents:

*   **`ARCH.md` (Update)**:
    *   Add sections for the `Renderer` and `InputHandler` components.
    *   Define them as abstract interfaces that decouple the core game logic from the presentation layer (e.g., Pygame, Curses).
    *   Illustrate the data flow: `InputHandler` -> `GameEngine` -> `GameState` -> `Renderer`.

*   **`src/renderer/DESIGN.md`**:
    *   **Purpose**: To define the contract for any system that can render the game's state.
    *   **Responsibilities**: Initialize a display surface, render a given `GameState` object, and clean up resources.
    *   **Contract**: The renderer is a "write-only" system from the game engine's perspective. It reads the `GameState` but never modifies it.

*   **`src/input_handler/DESIGN.md`**:
    *   **Purpose**: To define the contract for capturing and translating user input into game commands.
    *   **Responsibilities**: Poll for user actions (e.g., key presses) and convert them into a discrete set of `UserCommand`s for the game engine to process.
    *   **Contract**: The input handler must provide a non-blocking or time-bounded method to fetch the next command, ensuring the game loop does not stall.

### 2. Python Interfaces and Types

I will declare the following abstract classes, enums, and type aliases. These definitions would reside in `src/renderer/api.py` and `src/input_handler/api.py`.

*(Note: The `GameState` type is assumed to be defined elsewhere, e.g., in `src/game_model/types.py`)*

#### **`src/input_handler/api.py`**

```python
# src/input_handler/api.py
from enum import Enum, auto
from typing import Optional, Protocol

class UserCommand(Enum):
    """Discrete user commands that the game engine can process."""
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    QUIT = auto()
    PAUSE = auto()

class InputHandler(Protocol):
    """
    An interface for a system that captures and provides user input.
    """
    def get_next_command(self) -> Optional[UserCommand]:
        """
        Polls for and returns the next user command.

        This method should be non-blocking or have a minimal timeout.
        Returns:
            A UserCommand if one is available, otherwise None.
        """
        ...
```

#### **`src/renderer/api.py`**

```python
# src/renderer/api.py
from typing import Protocol
# from src.game_model.types import GameState # Assumed to exist

class Renderer(Protocol):
    """
    An interface for a system that can render the game state.
    """
    def setup(self, width: int, height: int) -> None:
        """
        Initializes the rendering context, such as a window or terminal screen.
        
        Args:
            width: The width of the game grid.

## Artifacts
- output\ARCH.md

## Notes
- Architect instance completed (summary only).
