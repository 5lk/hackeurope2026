# Architecture

**Task**: Define the UI and Scoring System Contract (`arch-1.8`)

## Summary
This design specifies the contracts for the `ScoreManager` and `UISystem` modules. The `ScoreManager` is responsible for the logic of tracking, incrementing, and storing the player's score. The `UISystem` is responsible for rendering the score and game-over information. Communication is event-driven, with the `ScoreManager` emitting signals that the `UISystem` consumes to update the display, ensuring a clean separation of concerns between game logic and presentation.

## File Plan
- docs/ui_scoring_design.md

## File Plan Notes
- This design assumes an event-driven architecture where modules can publish and subscribe to signals or events (e.g., `ScoreIncrementEvent`, `GameStateChangeEvent`).
- The specific rendering implementation for the UI is out of scope for this design and is left to the `UISystem`'s internal implementation.
- Persistence of the high score (e.g., saving to a file) is a responsibility of the `ScoreManager` but the mechanism is not detailed here.

## Module Contracts
### ScoreManager
**Responsibilities**
- Track the player's current score as an integer.
- Increment the score when a scoring event occurs (e.g., player passes a pipe).
- Reset the current score at the start of a new game.
- Maintain and update the high score.
- Notify listeners when the score or high score changes.
**Inputs**
- A signal to increment the score (e.g., `on_pipe_cleared`).
- A signal indicating the start of a new game to reset the score (e.g., `on_game_start`).
- A signal indicating the end of a game to finalize the score and check for a new high score (e.g., `on_game_over`).
**Outputs**
- A `score_updated` signal containing the new score value.
- A `high_score_updated` signal containing the new high score value.
- A queryable interface to get the current score and high score.
**Invariants**
- The score must always be a non-negative integer.
- The high score must be greater than or equal to any score achieved in a completed game session.
**Error Modes**
- The system should gracefully handle multiple score increment events that might occur in the same frame, processing them sequentially.

### UISystem
**Responsibilities**
- Display the current score during gameplay.
- Display the game-over screen upon game completion.
- Render the final score and the current high score on the game-over screen.
- Manage the visibility of UI elements based on the current game state.
**Inputs**
- Listens for the `score_updated` signal from `ScoreManager` to update the score display.
- Listens for the `high_score_updated` signal from `ScoreManager` to update the high score display.
- A `game_state_changed` signal (e.g., to 'playing', 'game_over') to control the visibility of UI elements like the in-game score HUD and the game-over screen.
**Outputs**
- Visual rendering of the score on the screen.
- Visual rendering of the game-over screen, including final score and high score.
**Invariants**
- The displayed score must accurately reflect the last value received from the `score_updated` signal.
- The game-over screen must only be visible when the game state is 'game_over'.
- The in-game score display should only be visible when the game state is 'playing'.
**Error Modes**
- If UI assets (e.g., fonts, images) fail to load, the system should not crash the application. It may log an error and fail to display the relevant UI element.
