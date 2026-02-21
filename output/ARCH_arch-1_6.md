# Architecture

**Task**: Define the Rendering Abstraction Layer (`arch-1.6`)

## Summary
This design specifies a rendering abstraction layer that decouples game logic from the Pygame library. It introduces a `Drawable` protocol for any game object that needs to be drawn, and a `Renderer` class responsible for managing the display surface and orchestrating the rendering of all `Drawable` objects each frame.

## File Plan
- rendering/DESIGN.md

## File Plan Notes
- This design assumes a main game loop will instantiate the `Renderer` and pass it a list of `Drawable` objects to render in each frame.
- The `Drawable` protocol is defined as a structural type (typing.Protocol) rather than a nominal one (abc.ABC), allowing for flexible implementation by game objects like `Bird` and `Pipe` without requiring inheritance.
- Specific asset loading (e.g., images for sprites) is considered an implementation detail of concrete `Drawable` classes and is not part of this abstraction layer design.

## Module Contracts
### flappy.rendering.interfaces
**Responsibilities**
- Define a contract for any object that can be drawn on the screen.
- Provide the necessary data for a `Renderer` to draw the object onto a Pygame surface.
**Inputs**
- A Pygame `Surface` to draw onto.
**Outputs**
- The object is drawn onto the provided surface. This is a side-effect; there is no return value.
**Invariants**
- A `Drawable` object must always have a valid visual representation (e.g., a loaded `pygame.Surface`) and a position (`pygame.Rect`).
**Error Modes**
- Implementations should handle missing assets gracefully, for example by drawing a placeholder shape, and should not raise exceptions during the draw call.

### flappy.rendering.renderer
**Responsibilities**
- Initialize and manage the main Pygame display window and surface.
- Clear the display at the beginning of each frame.
- Iterate through a sequence of `Drawable` objects and instruct each to draw itself.
- Update the display to present the completed frame to the user.
**Inputs**
- Configuration on initialization (e.g., screen width, height, caption).
- An iterable of `Drawable` objects for each frame to be rendered.
**Outputs**
- Visual output to the user's screen.
**Invariants**
- The Pygame display must be successfully initialized before any rendering methods are called.
- The collection of `Drawable` objects is treated as read-only during a single render pass.
**Error Modes**
- Failure to initialize Pygame or the display window should raise a `RuntimeError` on construction.
- Receiving an object in the render list that does not conform to the `Drawable` protocol should raise a `TypeError`.
