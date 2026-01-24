# services/controller_manager/name_manager.py
"""
Human-readable controller name management.

Provides deterministic name generation from controller serial numbers
and persistent storage of custom names.
"""

import hashlib
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Default path, can be overridden by CONTROLLER_NAMES_FILE env var
DEFAULT_NAMES_FILE = "controller_names.txt"

ADJECTIVES = [
    "Red",
    "Blue",
    "Green",
    "Gold",
    "Silver",
    "Swift",
    "Brave",
    "Bold",
    "Fierce",
    "Mighty",
    "Noble",
    "Quiet",
    "Quick",
    "Calm",
    "Wild",
    "Wise",
]
NOUNS = [
    "Phoenix",
    "Dragon",
    "Tiger",
    "Wolf",
    "Eagle",
    "Falcon",
    "Lion",
    "Bear",
    "Hawk",
    "Raven",
    "Fox",
    "Panther",
    "Cobra",
    "Viper",
    "Storm",
    "Thunder",
]


class NameManager:
    """
    Manages human-readable names for controllers.

    Names are deterministically generated from serial numbers using a hash
    to select from adjective+noun word lists. Custom names can override
    the generated ones and are persisted to a text file.
    """

    def __init__(self, names_file: str | None = None):
        """
        Initialize the name manager.

        Args:
            names_file: Path to the file for persisting controller names.
                       If None, uses CONTROLLER_NAMES_FILE env var or default.
        """
        if names_file is None:
            names_file = os.environ.get("CONTROLLER_NAMES_FILE", DEFAULT_NAMES_FILE)
        self.names_file = names_file
        # Ensure parent directory exists
        names_path = Path(self.names_file)
        if names_path.parent != Path("."):
            names_path.parent.mkdir(parents=True, exist_ok=True)
        self._names: dict[str, str] = {}
        self._lock = threading.Lock()
        self._load_names()

    def _load_names(self) -> None:
        """Load names from the persistence file."""
        if not os.path.exists(self.names_file):
            return
        try:
            with open(self.names_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        serial, name = line.split("=", 1)
                        self._names[serial.strip()] = name.strip()
            logger.info(f"Loaded {len(self._names)} controller names from {self.names_file}")
        except Exception as e:
            logger.error(f"Error loading controller names: {e}")

    def _save_names(self) -> None:
        """Save names to the persistence file atomically."""
        try:
            temp = self.names_file + ".tmp"
            with open(temp, "w") as f:
                f.write("# Controller names (serial=name)\n")
                for serial, name in sorted(self._names.items()):
                    f.write(f"{serial}={name}\n")
            os.replace(temp, self.names_file)
            logger.debug(f"Saved {len(self._names)} controller names to {self.names_file}")
        except Exception as e:
            logger.error(f"Error saving controller names: {e}")

    def _generate_name(self, serial: str) -> str:
        """
        Generate a deterministic name from a serial number.

        Uses MD5 hash of serial to select adjective and noun indices,
        ensuring the same serial always gets the same name.

        Args:
            serial: Controller serial number.

        Returns:
            Generated name like "Blue Phoenix" or "Swift Tiger".
        """
        h = hashlib.md5(serial.encode()).hexdigest()
        adj_idx = int(h[:8], 16) % len(ADJECTIVES)
        noun_idx = int(h[8:16], 16) % len(NOUNS)
        return f"{ADJECTIVES[adj_idx]} {NOUNS[noun_idx]}"

    def get_name(self, serial: str) -> str:
        """
        Get the human-readable name for a controller.

        If no name exists, generates one deterministically and persists it.

        Args:
            serial: Controller serial number.

        Returns:
            Human-readable name for the controller.
        """
        with self._lock:
            if serial not in self._names:
                self._names[serial] = self._generate_name(serial)
                self._save_names()
                logger.info(f"Generated name for controller {serial}: {self._names[serial]}")
            return self._names[serial]

    def set_name(self, serial: str, name: str) -> bool:
        """
        Set a custom name for a controller.

        Args:
            serial: Controller serial number.
            name: Custom name to assign.

        Returns:
            True if the name was set successfully.
        """
        with self._lock:
            old_name = self._names.get(serial)
            self._names[serial] = name
            self._save_names()
            if old_name:
                logger.info(f"Renamed controller {serial}: {old_name} -> {name}")
            else:
                logger.info(f"Set name for controller {serial}: {name}")
            return True

    def get_all_names(self) -> dict[str, str]:
        """
        Get all controller names.

        Returns:
            Dict mapping serial numbers to names.
        """
        with self._lock:
            return dict(self._names)
