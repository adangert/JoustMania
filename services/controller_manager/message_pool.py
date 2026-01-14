"""
Message pool for reusable protobuf messages.

Extracted from server.py to reduce file size (Phase 18 - Task 3).
"""

import threading
from collections import deque


class MessagePool:
    """Pool of reusable protobuf messages."""

    def __init__(self, message_class, pool_size=10):
        """Initialize message pool with pre-allocated messages."""
        self.pool = deque([message_class() for _ in range(pool_size)])
        self.message_class = message_class
        self.lock = threading.Lock()

    def get(self):
        """Get a message from pool or create new if empty."""
        with self.lock:
            if self.pool:
                msg = self.pool.popleft()
                msg.Clear()
                return msg
        # Pool empty, create new message
        return self.message_class()

    def return_msg(self, msg):
        """Return message to pool for reuse."""
        with self.lock:
            self.pool.append(msg)
