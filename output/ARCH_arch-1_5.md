# Architecture

**Task**: Design the Collision Detection System (`arch-1.5`)

## Summary
This document outlines the design for a collision detection system. The system is centered around a `CollisionSystem` module that processes a list of objects conforming to a `Collidable` interface. Game entities like `Bird` and `Pipe` will implement this interface by providing a geometric bounding box. The `CollisionSystem` checks for overlaps between these boxes and with world boundaries. Upon detection, it generates and dispatches `CollisionEvent` data objects to be handled by the main game state manager, triggering game-over conditions.

## File Plan
- docs/designs/collision_system.md

## File Plan Notes
- Assumes a main game loop or `GameState` manager is responsible for invoking the `CollisionSystem` each frame.
- Assumes game objects like `Bird` and `Pipe` have a position and size that can be used to derive a rectangular bounding box (`Rect`).
- Assumes the existence of an event bus or a direct notification mechanism for the `GameState` to receive `CollisionEvent`s.
- The design uses simple Axis-Aligned Bounding Box (AABB) collision detection for performance. More complex collision geometry is out of scope.

## Module Contracts
### game.interfaces.collidable
**Responsibilities**
- Define the contract for any game object that can be checked for collisions.
- Provide a method to retrieve the object's geometric representation for collision checks.
**Outputs**
- A geometric shape, specifically a `Rect` (rectangle), representing the object's current bounding box.
**Invariants**
- The returned `Rect` must accurately reflect the object's current position and dimensions.
**Error Modes**
- Not applicable for a pure interface definition.

### game.systems.collision
**Responsibilities**
- Accept a list of all `Collidable` objects for a given frame.
- Check for collisions between designated objects (e.g., `Bird` vs. `Pipe`).
- Check for collisions between the `Bird` and world boundaries (e.g., ground, ceiling).
- Generate a `CollisionEvent` for each detected collision.
**Inputs**
- A list of `Collidable` objects.
- World boundary definitions (e.g., ground y-coordinate).
**Outputs**
- A list of `CollisionEvent` objects to be processed by the game state manager.
**Invariants**
- The system must not modify the state of the input objects.
- Collision checks are performed once per invocation, typically once per game frame.
**Error Modes**
- Handles an empty list of collidables by returning an empty list of events.
- Logs a warning or raises an error if an object in the input list does not conform to the `Collidable` interface.

### game.entities.bird
**Responsibilities**
- Implement the `Collidable` interface.
- Provide its current bounding box based on its position and size.
**Outputs**
- A `Rect` object for the `get_bounding_box()` method.
**Invariants**
- The bounding box must be kept consistent with the bird's internal state (position).

### game.entities.pipe
**Responsibilities**
- Implement the `Collidable` interface.
- Provide bounding boxes for its physical parts (top and bottom pipe sections).
**Outputs**
- A `Rect` object for the `get_bounding_box()` method. A single `Pipe` entity may represent a pair of pipes and thus expose multiple collidable components.
**Invariants**
- The bounding box must be kept consistent with the pipe's internal state (position).

### game.events.collision_event
**Responsibilities**
- Act as a data structure to represent a collision event.
- Hold references to the two entities that have collided.
**Inputs**
- Two `Collidable` objects involved in the collision.
**Outputs**
- An immutable data object containing the collided entities.
**Invariants**
- An event must always reference exactly two distinct collidable entities or one entity and a boundary type (e.g., 'ground').
**Error Modes**
- Instantiation fails if not provided with the required collision participants.
