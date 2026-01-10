"""
JoustMania Core Common Module

Backward compatibility layer - re-exports from core.types and adds psmove-specific utilities.
This module has psmove dependencies and should only be used by controller_manager.
"""

import logging
import time
from enum import Flag

import psmove

# Re-export everything from types for backward compatibility
from .types import *

logger = logging.getLogger(__name__)


def get_move(serial: str, move_num: int) -> psmove.PSMove | None:
    """Get PSMove controller by serial number."""
    time.sleep(0.02)
    move = psmove.PSMove(move_num)
    time.sleep(0.05)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                print("returning " + str(move.get_serial()))
                return move
        return None
    return move


# PSMove-specific Button mapping (overrides the generic one from types)
class Button(Flag):
    """Controller buttons with actual PSMove constants."""

    NONE = 0

    TRIANGLE = psmove.Btn_TRIANGLE
    CIRCLE = psmove.Btn_CIRCLE
    CROSS = psmove.Btn_CROSS
    SQUARE = psmove.Btn_SQUARE

    SELECT = psmove.Btn_SELECT
    START = psmove.Btn_START

    SYNC = psmove.Btn_PS
    MIDDLE = psmove.Btn_MOVE
    TRIGGER = psmove.Btn_T

    SHAPES = TRIANGLE | CIRCLE | CROSS | SQUARE
    UPDATE = SELECT | START


all_shapes = [Button.TRIANGLE, Button.CIRCLE, Button.CROSS, Button.SQUARE]


# Battery levels with actual PSMove constants
battery_levels = {
    psmove.Batt_MIN: "Low",
    psmove.Batt_20Percent: "20%",
    psmove.Batt_40Percent: "40%",
    psmove.Batt_60Percent: "60%",
    psmove.Batt_80Percent: "80%",
    psmove.Batt_MAX: "100%",
    psmove.Batt_CHARGING: "Charging",
    psmove.Batt_CHARGING_DONE: "Charged",
}
