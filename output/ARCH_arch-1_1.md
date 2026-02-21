# Architecture

**Task**: Design the Game State Machine (`arch-1.1`)

## Summary
This design outlines a state machine pattern for managing game flow. The `Game` class acts as the context, managing a stack of `GameState` objects. Each `GameState` (e.g., MainMenu, Playing) is a self-contained module responsible for its own event handling, logic updates, and rendering. Transitions between states are managed explicitly by the `Game` class in response to requests from the active state.

## File Plan
- docs/game_state/DESIGN.md

## File Plan Notes
- Assumes the existence of a main game loop that provides events and a rendering surface.
- The `GameState` interface is defined as a contract; concrete implementations like `MainMenuState`, `PlayingState`, etc., are expected but not detailed here.
- The state management is stack-based, allowing for states to be layered (e.g., a `PauseMenu` state pushed on top of a `Playing` state).

## Module Contracts
### game.state.GameState
**Responsibilities**
- Define the contract for all individual game states (e.g., MainMenu, Playing).
- Handle user input and system events relevant to the state.
- Update the state's internal logic based on elapsed time.
- Render the state's visual representation to a given surface.
- Manage its own lifecycle through `on_enter` and `on_exit` hooks, used for setup and teardown.
**Inputs**
- `event`: An object representing a user or system event (e.g., key press, mouse move).
- `dt`: A float representing the time delta since the last update.
- `surface`: A rendering target object for drawing operations.
- `game_context`: A reference to the main `Game` object to request state changes.
**Outputs**
- Requests to the `Game` context to push, pop, or change states.
- Visual output rendered to the provided surface.
**Invariants**
- A `GameState` must not directly modify the global state stack; it must request changes through the `Game` context.
- A `GameState` should be self-contained and not rely on the internal state of other `GameState` implementations.
**Error Modes**
- Failure during initialization should be caught by the `Game` class, preventing the state from being pushed onto the stack.
- Unhandled exceptions during `update` or `draw` should be caught by the main game loop, logged, and potentially trigger a transition to a safe state (e.g., `MainMenu` or an error screen).

### game.Game
**Responsibilities**
- Initialize and manage the main game window and rendering context.
- Maintain a stack of `GameState` instances.
- Run the main game loop, which polls for events, calls `update` and `draw` on the active state, and manages the frame rate.
- Dispatch events to the active (top-most) `GameState`.
- Execute state transitions (push, pop, change) as requested by `GameState` instances.
**Inputs**
- An initial `GameState` to start the game with.
- System-level events from the underlying windowing/event library.
**Outputs**
- A rendered game window on the user's display.
- Clean exit of the application when the state stack is empty or a quit event is received.
**Invariants**
- The state stack must never be empty while the main loop is running. If a pop operation would result in an empty stack, the game must exit.
- Only the state at the top of the stack receives `update` and `handle_event` calls.
- Drawing may involve iterating through multiple states on the stack if transparency or overlay effects are desired (e.g., drawing the `Playing` state underneath the `Paused` state).
**Error Modes**
- Attempting to pop from an empty stack should result in a clean shutdown of the game.
- If a `GameState` fails to be instantiated, the transition request should be denied and an error logged.
