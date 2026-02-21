# Architecture

**Task**: Define the Bird Component Contract (`arch-1.3`)

## Summary
This document specifies the design contract for the Bird component. It defines the component's state, properties, methods, and physics-related behavior, including its response to gravity and user-initiated flapping.

## File Plan
- components/bird/DESIGN.md

## File Plan Notes
- This design assumes the existence of common game development types: `Vector2D` for position and velocity, `Rect` for hitboxes, and `Surface` for drawing contexts.
- The physics model is a simplified 2D simulation with constant downward gravity and an instantaneous upward impulse on flap.
- The specific values for gravity, flap impulse, and rotation limits are considered configuration details, not part of this core contract.

## Module Contracts
### components.bird.Bird
**Responsibilities**
- Maintain the bird's physical state, including position, velocity, and rotation.
- Update its state over time based on physics rules (gravity).
- Provide an interface to apply an upward impulse (flap).
- Expose a hitbox for collision detection purposes.
- Provide an interface to render the bird onto a given surface.
**Inputs**
- Initial state on construction (e.g., starting position).
- `update(deltaTime: float)`: A method to advance the bird's state by a time delta.
- `draw(surface: Surface)`: A method to render the bird's current state.
- `flap()`: A method to trigger an upward velocity impulse.
**Outputs**
- Public properties for `position: Vector2D`, `velocity: Vector2D`, and `hitbox: Rect`.
- A visual representation of the bird rendered on the provided `Surface` during the `draw` call.
**Invariants**
- The bird is always subject to a constant downward acceleration (gravity) during each `update` call.
- The `flap()` method applies an immediate, fixed-magnitude upward change to the bird's vertical velocity.
- The bird's `hitbox` must always be synchronized with its current `position`.
- The bird's rotation is a function of its vertical velocity.
**Error Modes**
- This component does not define specific error handling. It is expected that inputs like `deltaTime` are valid. Invalid inputs may result in undefined behavior.
