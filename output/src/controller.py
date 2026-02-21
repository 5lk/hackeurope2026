import pygame
from .model import Direction, Snake

class InputHandler:
    """Handles user input for the game."""

    def handle_input(self, snake: Snake) -> bool:
        """
        Processes keyboard events to control the snake and handle game exit.

        Args:
            snake: The Snake object to control.

        Returns:
            False if the game should quit, True otherwise.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                return False
            if event.type == pygame.KEYPDOWN:
                if event.key == pygame.K_UP or event.key == pygame.K_w:
                    snake.change_direction(Direction.UP)
                elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                    snake.change_direction(Direction.DOWN)
                elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                    snake.change_direction(Direction.LEFT)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                    snake.change_direction(Direction.RIGHT)
        return True
