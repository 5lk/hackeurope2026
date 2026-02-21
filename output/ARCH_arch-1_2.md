# Architecture

**Task**: Architect the Core Game Loop (`arch-1.2`)

## Summary
This architecture defines the core game loop, which orchestrates the main phases of the game: input processing, state updates, and rendering. The design centers on a `GameLoop` class that drives the execution flow and a `Game` class that manages the overall application lifecycle and the active `GameState`. The loop operates on a frame-by-frame basis, calculating delta time to ensure frame-rate independent updates. Responsibilities are delegated to the current `GameState`, which encapsulates the logic for a specific part of the game (e.g., menu, gameplay).

## File Plan
- docs/core/GAME_LOOP_ARCH.md

## File Plan Notes
- This design assumes the existence of a `GameState` abstract base class or interface that all game states (e.g., `MainMenuState`, `GameplayState`) will implement.
- The specific implementations for input handling, rendering, and timing (clock) are considered external dependencies with defined interfaces.
- The `Game` class is assumed to manage a stack of `GameState` objects to handle state transitions like pausing.

## Module Contracts
### game.Game
**Responsibilities**
- Own and manage the main `GameLoop` instance.
- Manage the active `GameState` (e.g., via a state stack).
- Initialize and shut down core engine subsystems (e.g., window, renderer).
- Serve as the primary entry point to start and stop the game.
**Inputs**
- Initial `GameState` to begin execution.
- Game configuration data (e.g., window dimensions, title).
**Outputs**
- Orchestrates the application lifecycle, resulting in a running game window.
**Invariants**
- A valid `GameLoop` instance must exist for the duration of the game's execution.
- There must always be at least one active `GameState` while the loop is running.
**Error Modes**
- Failure to initialize a required subsystem (e.g., graphics context) must result in a clean shutdown.
- Attempting to run without an initial `GameState` must raise an error.

### game.loop.GameLoop
**Responsibilities**
- Continuously execute the main loop cycle until a stop condition is met.
- Measure and provide delta time for each frame update.
- Invoke the methods of the active `GameState` in the correct sequence: process input, update logic, render.
- Maintain the running status of the loop.
**Inputs**
- A reference to the `Game` or a `GameStateManager` to access the current `GameState`.
- A timing utility (e.g., a `Clock` object) to calculate delta time.
**Outputs**
- Delegates calls to the active `GameState`'s `handle_input`, `update`, and `render` methods each frame.
**Invariants**
- The execution order per frame must be: input processing, then state update, then rendering.
- Delta time passed to the `update` method must be a non-negative float representing the time elapsed since the previous frame.
**Error Modes**
- If the active `GameState` becomes null during execution, the loop must terminate gracefully.
- Failure of the underlying timing mechanism should be handled or reported.

### game.state.GameState (Interface)
**Responsibilities**
- Encapsulate the logic, data, and presentation for a specific screen or state of the game.
- Implement the `handle_input` method to process user input.
- Implement the `update` method to advance the game simulation for one frame.
- Implement the `render` method to draw the current state to the screen.
**Inputs**
- `handle_input`: A collection of current input events.
- `update`: Delta time (float) for time-based calculations.
- `render`: A rendering target or context to draw upon.
**Outputs**
- The `update` method may signal a request for a state change (e.g., push, pop, switch) to the `Game` object.
**Invariants**
- A `GameState` must be fully initialized before it can be made active in the `GameLoop`.
**Error Modes**
- Errors occurring within a state's methods should be handled internally or propagated to the main `Game` object.
