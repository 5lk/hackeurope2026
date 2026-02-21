# Architecture

**Task**: Design the Input Handling System (`arch-1.7`)

## Summary
This design outlines an event-driven input handling system. The `InputHandler` module is responsible for capturing raw Pygame events, translating them into abstract `GameCommand` objects, and placing them on a queue. The main `Game` module consumes these commands from the queue during its update loop and dispatches them to the relevant game logic, decoupling input processing from game state management.

## File Plan
- src/input/DESIGN.md

## File Plan Notes
- This design assumes a central game loop within the `Game` module that drives the entire process.
- The specific mapping of physical keys (e.g., Spacebar) to `GameCommand` types (e.g., `BirdFlap`) is considered external configuration and is not part of this contract.
- The design uses a command queue for communication between the `InputHandler` and the `Game` module. An alternative could be a pub/sub event bus, but a simple queue is sufficient for this scope.

## Module Contracts
### input.handler
**Responsibilities**
- Poll the underlying framework (Pygame) for raw user input events.
- Map raw input events (e.g., `pygame.KEYDOWN`, `pygame.MOUSEBUTTONDOWN`) to abstract, game-specific `GameCommand` objects.
- Provide a mechanism to retrieve the generated commands for a single frame or update cycle.
**Inputs**
- A stream of `pygame.event.Event` objects.
- A configuration defining the mapping from raw Pygame events to `GameCommand` types.
**Outputs**
- A collection (e.g., a list or queue) of `GameCommand` instances generated since the last poll.
**Invariants**
- The handler is decoupled from game logic and has no knowledge of command subscribers or their effects.
- The handler is stateless between polling cycles.
- Unconfigured or irrelevant input events are ignored.
**Error Modes**
- Initialization failure if the event-to-command mapping configuration is missing or invalid.

### game
**Responsibilities**
- Define the set of possible `GameCommand` types (e.g., `StartGame`, `BirdFlap`, `QuitGame`).
- Instantiate and own the `InputHandler` instance.
- In each game loop iteration, retrieve and process all pending `GameCommand`s from the `InputHandler`.
- Dispatch each `GameCommand` to the appropriate game system or state machine.
- Act as the sole consumer of the commands produced by the `InputHandler`.
**Inputs**
- A collection of `GameCommand` objects for the current frame.
**Outputs**
- Game state changes, such as updating player position, changing the game scene, or modifying game variables.
**Invariants**
- All user-initiated changes to the game state must originate from a `GameCommand`.
- Commands are processed in the order they are received from the `InputHandler`.
**Error Modes**
- A `GameCommand` is received that is not applicable to the current game state (e.g., `BirdFlap` while in the main menu). Such commands should be ignored.
