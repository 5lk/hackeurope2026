import random
from typing import Tuple

class Food:
    """Represents the food in the Snake game."""

    def __init__(self, board_width: nt, board_height: nt, block_size: int):
        """
Initializes the Food object.

        Args:
            board_width (int): The width of the game board.
            board_height (int): The height of the game board.
            block_size (int): The size of a single block/grid cell.
        """
        self.board_width = board_width
        self.board_height = board_height
        self.block_size = block_size
        self.position = self._generate_random_position()

    def _generate_random_position(self) -> Tuple[int, int]:
        """Generates a random position for the food on the board."""
        x = random.randrange(0, self.board_width - self.block_size, self.block_size)
        y = random.randrange(0, self.board_height - self.block_size, self.block_size)
        return (x, y)

    def respawn(self) -> None:
        """Moves the food to a new random position."""
        self.position = self._generate_random_position()
