"""
Game Coordinator Service

Manages game lifecycle via gRPC server.

Legacy imports from process.py are commented out during gRPC refactoring (Phase 13).
They can be re-added if needed for backwards compatibility.
"""

# Legacy multiprocessing-based imports (Phase 8a - archived during gRPC migration)
# from .process import GameCoordinatorProcess, send_command
# __all__ = ['GameCoordinatorProcess', 'send_command']

__all__ = []
