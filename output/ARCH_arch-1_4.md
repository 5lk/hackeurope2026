# Architecture

**Task**: Define the Pipe Component and Spawning Logic (`arch-1.4`)

## Summary
This design specifies the contracts for the `Pipe` and `PipeManager` components. The `Pipe` component is a data structure representing a pair of obstacles with defined physical properties and hitboxes. The `PipeManager` is responsible for the entire lifecycle of these pipes, including spawning them at regular intervals, updating their positions as they move across the screen, and removing them once they are no longer visible. This separation of concerns allows the `Pipe` to be a simple data object while the `PipeManager` encapsulates the complex game logic for obstacle management.

## File Plan
- game/obstacles/DESIGN.md

## File Plan Notes
- This design assumes a 2D coordinate system where the origin (0,0) is at the top-left of the screen.
- It is assumed that a game loop will call an `update` method on the `PipeManager` instance on each frame, providing the elapsed time (delta time).
- The design presumes the existence of a `Rectangle` or similar geometric primitive type for defining hitboxes.
- The `PipeManager` will need access to game world constants, such as screen width and height, for its logic.

## Module Contracts
### game.obstacles.pipe
**Responsibilities**
- Represent a single pair of vertical pipes (top and bottom) as a single entity.
- Store the state of the pipe pair, including its x-position, the y-position of the gap's center, gap size, and pipe width.
- Provide access to the collision boundaries (hitboxes) for both the top and bottom pipes.
- Maintain a state indicating whether the player has successfully passed this pipe pair.
**Inputs**
- Initial configuration upon creation: x-position, center y-position of the gap, gap size, and pipe width.
**Outputs**
- A data structure containing the pipe's current state (position, dimensions).
- A pair of `Rectangle` objects representing the hitboxes for the top and bottom pipes.
**Invariants**
- The top and bottom pipes are always vertically aligned along the same x-axis.
- The vertical distance between the top and bottom pipe (the gap) is constant throughout the pipe's lifetime.
- The pipe's x-position is monotonically decreasing as it moves from right to left across the screen.
**Error Modes**
- Instantiation with invalid parameters (e.g., negative gap size, gap larger than screen height) should raise a `ValueError`.

### game.obstacles.pipe_manager
**Responsibilities**
- Manage a collection of active `Pipe` instances.
- Spawn new `Pipe` instances at a configured horizontal interval off-screen to the right.
- Randomize the vertical position of the gap for newly spawned pipes within a configured range.
- Update the position of all managed pipes each frame, moving them horizontally to the left.
- Remove `Pipe` instances from the collection once they have moved off-screen to the left.
- Provide a way to retrieve all active pipes for collision detection and rendering.
- Detect when the player has successfully passed a pipe and signal a score increase.
**Inputs**
- Delta time: The time elapsed since the last frame, used for position updates.
- Game world configuration: Screen width, screen height, pipe movement speed.
- Pipe spawning configuration: Horizontal distance between pipes, vertical gap size, range for the gap's center y-position.
- Player's current position, used for scoring logic.
**Outputs**
- A collection of all active `Pipe` instances.
- A signal or event indicating that the player's score should be incremented.
**Invariants**
- Pipes are always spawned to the right of the visible screen area.
- Pipes are always removed after they have moved completely past the left of the visible screen area.
- The collection of pipes remains sorted by their x-position.
- The horizontal distance between newly spawned pipes is consistent.
**Error Modes**
- If initialized with invalid configuration (e.g., spawn distance less than zero), the manager should raise a `ValueError`.
- The manager must function correctly when the collection of active pipes is empty.
