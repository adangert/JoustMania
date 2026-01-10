"""
Settings Service

Manages settings as a separate process with pub/sub pattern.

Supports both:
- Legacy Queue-based IPC (process.py)
- gRPC (server.py, settings_pb2, settings_pb2_grpc)
"""

# gRPC exports (always available)
try:
    from . import settings_pb2, settings_pb2_grpc

    _grpc_available = True
except ImportError:
    _grpc_available = False

# Legacy Queue-based exports (optional - requires psmove)
try:
    from .process import SETTINGS_SCHEMA, SettingsProcess, send_command

    _queue_available = True
except ImportError:
    _queue_available = False
    SettingsProcess = None
    send_command = None
    SETTINGS_SCHEMA = None

__all__ = [
    "settings_pb2",
    "settings_pb2_grpc",
    "SettingsProcess",
    "send_command",
    "SETTINGS_SCHEMA",
]
