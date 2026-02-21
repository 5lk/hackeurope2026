# Handoff: arch-2

**Summary**: Here is a summary of the design artifacts for the game loop and state management system.

### 1. Design Artifacts

I would create the following design documents:

*   **`ARCH.md` (Top-Level Architecture)**
    *   **Overview**: Describes the overall game architecture as a State-Driven Game Loop.
    *   **Core Components**:
        *   **Game Loop (`game.loop`)**: The central orchestrator responsible for timing, updating game logic, and rendering.
        *   **State Machine (`game.state`)**: Manages the high-level game states (`PLAYING`, `PAUSED`, `GAME_OVER`).
        *   **Game State (`game.state`)**: A data container holding all the information required to represent a single frame of the game (e.g., player position, score, enemies).
        *   **Scoring System (`game.scoring`)**: A dedicated service for managing and calculating the player's score.
    *   **Data Flow Diagram**: A diagram illustrating the flow of control and data:
        1.  `Game.run()` starts the loop.
        2.  Inside the loop, `Game.update()` is called with the time delta.
        3.  `Game.update()` checks the `StateMachine`'s current state.
        4.  Based on the state, it delegates updates to relevant systems (e.g., physics, input handling).
        5.  These systems modify a *copy* of the `GameState`.
        6.  The `ScoringSystem` updates the score within the new `GameState`.
        7.  The `Game` object replaces the old state with the new one.
        8.  `Game.render()` is called with the current `GameState` to draw the frame.

*   **`game/DESIGN.md` (Game Module Design)**
    *   **Module Responsibilities**: Details the specific roles of `game.loop`, `game.state`, and `game.scoring`.
    *   **API Contracts**: Defines the interfaces for `Game`, `StateMachine`, and `ScoringSystem`.
    *   **State Transitions**: A state transition table or diagram showing valid transitions between `GameStatus` enums (e.g., `PLAYING` -> `PAUSED`, `PLAYING` -> `GAME_OVER`, `GAME_OVER` -> `MAIN_MENU`).
    *   **Invariants**: Lists critical system rules, such as the immutability of `GameState` during a single update cycle and the non-negativity of the score.

### 2. Python Interfaces and Types

The following types and interfaces would be declared in `game/interfaces.py` or within their respective modules.

```python
# game/state/types.py
from enum import Enum, auto
from typing import Protocol
from dataclasses import dataclass

class GameStatus(Enum):
    """Enumeration for high-level game states."""
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    MAIN_MENU = auto()

@dataclass(frozen=True)
class GameState:
    """
    An immutable snapshot of all data needed to represent the game world at a point in time.
    Specific game entities (e.g., player, enemies) would be defined elsewhere.
    """
    score: int
    level: int
    # ... other game-specific state data (e.g., player_position, enemy_list)

class StateMachine(Protocol):
    """Manages transitions between game states."""

    @property
    def current_state(self) -> GameStatus:
        """Returns the current game state."""
        ...

    def transition_to(self, new_state: GameStatus) -> None:
        """
        Attempts to transition to a new state.
        Raises ValueError on an invalid transition.
        """
        ...

# game/scoring/types.py
class ScoringSystem(Protocol):
    """Defines the contract for score management."""

    def add_points(self, current_score: int, points: int) -> int:
        """
        Calculates a new score by adding points.
        Returns the new score.
        """
        ...

    def reset_score(self) -> int:
        """Returns the initial score value (e.g., 0)."""
        ...

# game/loop/types.py
class Game(Protocol):
    """
    The main game loop orchestrator.
    It owns the state machine and the current game state.
    """

    def run(self) -> None:
        """Starts and runs the main game loop until exit."""
        ...

    def update(self, delta_time: float) -> None:
        """
        Updates the game logic for a single frame based on the current state.
        This method is responsible for creating the next GameState.
        """
        ...

    def render(self) -> None:
        """
        Renders the current GameState to the display.
        This method is read-only with respect to GameState.

## Artifacts
- output\ARCH.md

## Notes
- Architect instance completed (summary only).
