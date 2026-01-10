"""
Game Coordinator Service

Manages game lifecycle as a separate process.
"""

from .process import GameCoordinatorProcess, send_command

__all__ = ['GameCoordinatorProcess', 'send_command']
