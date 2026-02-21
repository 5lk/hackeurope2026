from typing import Tuple

class Board:
    """
    Represents the game board.

    Attributes:
        width (int): The width of the board.
        height (int): The height of the board.
    """

    def __init__(self, width: int, height: int):
        """
        Initializes the Board with a given width and height.

        Args:
            width (int): The width of the game board.
            height (int): The height of the game board.
        """
        if not isinstance(width, int) or not isinstance(height, int):
            raise TypeError("Width and height must be integers.")
        if width <= 0 or height <= 0:
            raise ValueError("Width and height must be positive.")

        self.width = width
        self.height = height

    @property
    def size(self) -> Tuple[int, int]:
        """
        Returns the size of the board as a tuple (width, height).

        Returns:
            Tuple[int, int]: The width and height of the board.
        """
        return (self.width, self.height)

    def is_within_bounds(self, position: Tuple[int, int]) -> bool:
        """
        Checks if a given position is within the board boundaries.

        Args:
            position (Tuple[int, int]): The (x, y) coordinates to check.

        Returns:
            bool: True if the position is within bounds, False otherwise.
        """
        x, y = position
        return 0 <= x < self.width and 0 <= y < self.height
