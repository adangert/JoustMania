# Phase: Remove Battery Indication by Dimming

**Status**: Complete

## Summary

Removed battery-based LED dimming and low battery warning from the menu service. These features were confusing for users and didn't provide clear benefit.

## Changes Made

### 1. Simplified LED Dimming (`services/menu/server.py`)
- **Before**: Connected (not ready) controllers had variable brightness based on battery level (15-50%)
- **After**: Connected controllers use fixed 30% brightness, ready controllers use 100%

### 2. Removed `_get_battery_dim_factor()` Method
- Deleted the battery-to-brightness mapping function

### 3. Removed Low Battery Warning
- Deleted `_check_low_battery_warning()` method that flashed red on low battery controllers
- Removed the call to this method before game start

## Rationale

- Battery-based dimming was too subtle to notice and confusing when noticed
- Low battery warning flash was unclear - users didn't understand why controller flashed red
- The admin Triangle button still shows battery levels for those who want to check
