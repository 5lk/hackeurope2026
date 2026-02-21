# Handoff: arch-1

**Summary**: Architect lead completed 8 subtasks for Define Game Architecture and Components.

## Artifacts
- output\ARCH_arch-1_3.md
- output\components\bird\DESIGN.md
- output\ARCH_arch-1_8.md
- output\docs\ui_scoring_design.md
- output\ARCH_arch-1_4.md
- output\game\obstacles\DESIGN.md
- output\ARCH_arch-1_2.md
- output\docs\core\GAME_LOOP_ARCH.md
- output\ARCH_arch-1_6.md
- output\rendering\DESIGN.md
- output\ARCH_arch-1_5.md
- output\docs\designs\collision_system.md
- output\ARCH_arch-1_7.md
- output\src\input\DESIGN.md
- output\ARCH_arch-1_1.md
- output\docs\game_state\DESIGN.md

## Notes
- Subtask arch-1.3: This document specifies the design contract for the Bird component. It defines the component's state, properties, methods, and physics-related behavior, including its response to gravity and user-initiated flapping.
- Subtask arch-1.8: This design specifies the contracts for the `ScoreManager` and `UISystem` modules. The `ScoreManager` is responsible for the logic of tracking, incrementing, and storing the player's score. The `UISystem` is responsible for rendering the score and game-over information. Communication is event-driven, with the `ScoreManager` emitting signals that the `UISystem` consumes to update the display, ensuring a clean separation of concerns between game logic and presentation.
- Subtask arch-1.4: This design specifies the contracts for the `Pipe` and `PipeManager` components. The `Pipe` component is a data structure representing a pair of obstacles with defined physical properties and hitboxes. The `PipeManager` is responsible for the entire lifecycle of these pipes, including spawning them at regular intervals, updating their positions as they move across the screen, and removing them once they are no longer visible. This separation of concerns allows the `Pipe` to be a simple data object while the `PipeManager` encapsulates the complex game logic for obstacle management.
- Subtask arch-1.2: This architecture defines the core game loop, which orchestrates the main phases of the game: input processing, state updates, and rendering. The design centers on a `GameLoop` class that drives the execution flow and a `Game` class that manages the overall application lifecycle and the active `GameState`. The loop operates on a frame-by-frame basis, calculating delta time to ensure frame-rate independent updates. Responsibilities are delegated to the current `GameState`, which encapsulates the logic for a specific part of the game (e.g., menu, gameplay).
- Subtask arch-1.6: This design specifies a rendering abstraction layer that decouples game logic from the Pygame library. It introduces a `Drawable` protocol for any game object that needs to be drawn, and a `Renderer` class responsible for managing the display surface and orchestrating the rendering of all `Drawable` objects each frame.
- Subtask arch-1.5: This document outlines the design for a collision detection system. The system is centered around a `CollisionSystem` module that processes a list of objects conforming to a `Collidable` interface. Game entities like `Bird` and `Pipe` will implement this interface by providing a geometric bounding box. The `CollisionSystem` checks for overlaps between these boxes and with world boundaries. Upon detection, it generates and dispatches `CollisionEvent` data objects to be handled by the main game state manager, triggering game-over conditions.
- Subtask arch-1.7: This design outlines an event-driven input handling system. The `InputHandler` module is responsible for capturing raw Pygame events, translating them into abstract `GameCommand` objects, and placing them on a queue. The main `Game` module consumes these commands from the queue during its update loop and dispatches them to the relevant game logic, decoupling input processing from game state management.
- Subtask arch-1.1: This design outlines a state machine pattern for managing game flow. The `Game` class acts as the context, managing a stack of `GameState` objects. Each `GameState` (e.g., MainMenu, Playing) is a self-contained module responsible for its own event handling, logic updates, and rendering. Transitions between states are managed explicitly by the `Game` class in response to requests from the active state.
