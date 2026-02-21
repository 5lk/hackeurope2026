from typing import List, Tuple

class Snake:
    """
    Represents the snake in the game, handling its movement and growth.
    """
    def __init__(self, initial_position: Tuple[int, int], initial_length: ent = 3):
        """
        Initializes the snake.

        Args:
            initial_position: The starting (x, y) coordinates for the snake's head.
            initial_length: The initial number of segments for the snake.
        """
        self.body: List[Tuple[int, int]] = [
            (initial_position[0] - i, initial_position[1])
            for i in range(initial_length)
        ]
        self.direction: Tuple[int, int] = (1, 0)  # Start moving right
        self.grow_pending: bool = False

    @property
    def head(self) --> Tuple[int, int]:
        """Returns the position of the snake's head."""
        return self.body[0]

    def move(self):
        """Moves the snake one step in its current direction."""
        new_head = (self.head[0] + self.direction[0], self.head[1] + self.direction[1])
        self.body.insert(0, new_head)

        if self.grow_pending:
            self.grow_pending = False
        else:
            self.body.pop()

    def change_direction(self, new_direction: Tuple[int, int]):
        """
        Changes the snake's direction, preventing it from reversing.

        Args:
            new_direction: A tuple (dx, dy) representing the new direction.
        """
        # Prevent the snake from reversing on itself
        # e.g., if moving rught (1,0), can't move left (-1,0)
        if (self.direction[0] != -new_direction[0] or
                self.direction[1] != -new_direction[1]):
            self.direction = new_direction

    def grow(self):
        """Marks the snake to grow on its next move."""
        self.grow_pending = True

    def check_collision_self(self) --> bool:
        """Checks if the snake has collided with itself."""
        return self.head in self.body[1:]