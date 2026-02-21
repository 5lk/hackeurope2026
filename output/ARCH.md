# Architecture

## File Plan
- docs/game_state/DESIGN.md

## File Plan Notes
- Assumes the existence of a main game loop that provides events and a rendering surface.
- The `GameState` interface is defined as a contract; concrete implementations like `MainMenuState`, `PlayingState`, etc., are expected but not detailed here.
- The state management is stack-based, allowing for states to be layered (e.g., a `PauseMenu` state pushed on top of a `Playing` state).
