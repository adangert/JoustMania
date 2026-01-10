"""
Controller Manager Service

Manages Move controller lifecycle via gRPC server.

Legacy imports from process.py are commented out during gRPC refactoring (Phase 13).
They can be re-added if needed for backwards compatibility.
"""

# Legacy multiprocessing-based imports (Phase 8a - archived during gRPC migration)
# from .process import ControllerManagerProcess, send_command
# __all__ = ['ControllerManagerProcess', 'send_command']

__all__ = []
