# Handoff: arch-1

**Summary**: Here is a summary of the design artifacts for the Game State and Component Architecture.

### 1. Architecture/Design Artifacts

I will create a top-level `ARCH.md` file in the project root.

**`ARCH.md`**

-   **1. Overview**: Describes the core components (`Board`, `Snake`, `Food`) as the fundamental data structures for the game state. All game logic will operate on these components.
-   **2. Module Organization**:
    -   `game/common/types.py`: Defines shared, primitive data types used across all components, such as `Position` and `Direction`.
    -   `game/board.py`: Defines the `Board` component, responsible for game area boundaries.
    -   `game/snake.py`: Defines the `Snake` component, responsible for its own state, movement, and growth.
    -   `game/food.py`: Defines the `Food` component, representing a consumable item.
-   **3. Data Flow**: The main game loop (to be defined in a separate `game/engine.py` module) will hold instances of `Board`, `Snake`, and `Food`. On each tick, the engine will:
    1.  Query for user input to potentially change the snake's direction.
    2.  Call `snake.move()`.
    3.  Check for collisions:
        -   Snake head vs. Board boundaries.
        -   Snake head vs. Snake body.
        -   Snake head vs. Food position.
    4.  Update game state (e.g., call `snake.grow()` and generate new food on collision).
-   **4. Error Handling**: Invalid state transitions (e.g., moving the snake out of bounds, reversing direction) will raise exceptions (`ValueError`, `InvalidMoveError`) to be handled by the game engine.

---

### 2. Python Interfaces and Types

The following types and interfaces will be defined.

**File: `game/common/types.py`**

```python
from typing import NamedTuple
from enum import Enum, auto

class Position(NamedTuple):
    """Represents an (x, y) coordinate on the game board."""
    x: int
    y: int

class Direction(Enum):
    """Represents the four cardinal directions of movement."""
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
```

**File: `game/board.py`**

```python
from game.common.types import Position

class Board:
    """Defines the game area and its boundaries."""
    width: int
    height: int

    def __init__(self, width: int, height: int) -> None: ...

    def is_within_bounds(self, position: Position) -> bool:
        """Checks if a given position is within the board's dimensions."""
        ...
```

**File: `game/food.py`**

```python
from game.common.types import Position

class Food:
    """Represents a food item at a specific position."""
    position: Position

    def __init__(self, position: Position) -> None: ...
```

**File: `game/snake.py`**

```python
from collections.abc import Sequence
from game.common.types import Position, Direction

class Snake:
    """Represents the snake, its body, and its movement."""
    body: Sequence[Position]
    direction: Direction

    def __init__(self, initial_body: Sequence[Position], initial_direction: Direction) -> None: ...

    @property
    def head(self) -> Position:
        """Returns the position of the snake's head."""
        ...

    def move(self) -> None:
        """Updates the snake's body segments based on its current direction."""
        ...

    def grow(self) -> None:
        """Adds a new segment to the end of the snake's body."""
        ...

    def change_direction(self, new_direction: Direction) -> None:
        """
        Sets a new direction for the snake's next move.
        Raises InvalidMoveError if the new direction is opposite to the current one.
        """
        ...

    def check_self_collision(self) -> bool:
        """Checks if the snake's head has collided with its body."""
        ...
```

---

### 3. Module Contracts and Invariants

-   **`common.types`**:
    -   `Position` coordinates (`x`, `y`) must be non-negative integers.
-   **`board.Board`**:
    -   `width` and `height` must be positive integers upon initialization.
    -   The board's dimensions are immutable after creation.
-   **`snake.Snake`**:
    -   `body` must be a non-empty sequence of unique `Position`s.

## Artifacts
- output\ARCH.md

## Notes
- Architect instance completed (summary only).
