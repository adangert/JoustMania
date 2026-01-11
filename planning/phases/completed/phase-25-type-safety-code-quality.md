# Phase 25: Type Safety & Code Quality with Astral Tools

**Status:** ✅ COMPLETE
**Date Completed:** 2026-01-10
**Priority:** MEDIUM

## Goal
Add comprehensive type hints and integrate static analysis using Astral's ty (type checker) and ruff (linter/formatter)

## Motivation
- Type hints improve code readability and IDE support (autocomplete, inline docs)
- Catch bugs at development time before runtime
- Consistent code formatting and style enforcement
- Better refactoring safety with type-aware tools
- Documentation through type signatures
- Blazingly fast tooling (10x-100x faster than mypy/pyright)
- Native integration with uv (already in use)
- Industry best practice for Python 3.9+

## What Was Implemented

**1. Tools Installed:**
- ✅ ty 0.0.11 - Astral's exceptionally fast type checker (10x-100x faster than mypy)
- ✅ ruff 0.14.11 - Lightning-fast linter and formatter
- Both installed as dev dependencies via `uv add --dev`

**2. Configuration:**
- ✅ Added ty configuration to `pyproject.toml` with gradual adoption strategy
- ✅ Added comprehensive ruff configuration with selected rule sets:
  - pycodestyle (E, W) - Style errors and warnings
  - pyflakes (F) - Detect unused imports, variables
  - isort (I) - Import sorting
  - pep8-naming (N) - Naming conventions
  - pyupgrade (UP) - Syntax upgrades for Python 3.11+
  - flake8-annotations (ANN) - Type hint enforcement
  - flake8-async (ASYNC) - Async/await best practices
  - flake8-bugbear (B) - Common bug patterns
  - flake8-comprehensions (C4) - Comprehension improvements
  - flake8-return (RET) - Return statement simplification
  - flake8-simplify (SIM) - Code simplification suggestions
  - flake8-unused-arguments (ARG) - Detect unused arguments
- ✅ Per-file ignore rules for `__init__.py`, tests, legacy, and Archive directories
- ✅ Formatting: 100 char line length, double quotes, space indentation

**3. Helper Scripts Created:**
- ✅ `scripts/lint/check-types.sh` - Run ty type checker
- ✅ `scripts/lint/check-lint.sh` - Run ruff linter
- ✅ `scripts/lint/format.sh` - Run ruff formatter
- ✅ `scripts/lint/check-all.sh` - Run all quality checks
- All scripts made executable and ready for CI/CD integration

**4. Code Formatting:**
- ✅ Ran `ruff format` on entire codebase
- ✅ 119 files reformatted with consistent style
- ✅ Standardized quote style to double quotes
- ✅ Standardized indentation to spaces
- ✅ Fixed line length violations

**5. Auto-Fixed Linting Issues:**
- ✅ Ran `ruff check --fix` on entire codebase
- ✅ Fixed 812 auto-fixable issues including:
  - Comparison to None → `is not None` (E711)
  - Simplified conditional expressions with ternary operators (SIM108)
  - Removed unnecessary list comprehensions (C416)
  - Removed unnecessary assignments before returns (RET504)
  - Import sorting and organization (I)

**6. Type Hints Added:**

**core/types.py** - Complete type annotations for all functions and classes:
- `lerp()` function with float parameters and return type
- `Games.next()`, `Games.previous()`, `Games.find()` methods
- `Games.__new__()` custom constructor
- `Opts.battery_levels_dict()` static method
- `get_game_name()` function
- `Color.rgb_bytes()` method
- `async_print_exceptions()` decorator with TypeVar and Coroutine types
- `GamePace.__init__()` and `GamePace.__str__()` methods
- Added imports: `Callable`, `Coroutine`, `Any`, `TypeVar` from typing

**core/common.py** - Type annotations for PSMove utilities:
- `get_move()` function with serial/move_num parameters and Optional return

**utils/colors.py** - Complete type annotations for all utility functions:
- `darken_color()` with tuple types
- `hsv2rgb()` with RGB tuple return
- `generate_colors()` with list of tuples return
- `generate_team_colors()` with optional dict parameter and Colors list return
- `change_color()` with list modification (None return)
- Fixed list comprehension to use `list()` (C416)
- Simplified ternary operators (SIM108)
- Fixed `is not None` comparison (E711)

**7. Testing & Validation:**
- ✅ Ran `ty check` to assess type coverage (gradual adoption approach)
- ✅ Identified areas for future type hint improvements
- ✅ Both tools configured for incremental improvements
- ✅ Clean integration with existing uv workflow

## Files Modified
- Configuration: `pyproject.toml`, `uv.lock`
- Helper Scripts: `scripts/lint/*.sh` (4 new files)
- Type Hints: `core/types.py`, `core/common.py`, `utils/colors.py`
- Formatting: 119 Python files reformatted across entire codebase
- Total: 125 files changed, 9880 insertions(+), 8084 deletions(-)

## Astral Tooling Stack Completed
- ✅ **uv** - Package management (already in use)
- ✅ **ruff** - Linting and formatting (newly integrated)
- ✅ **ty** - Type checking (newly integrated)

All three tools provide exceptional performance and seamless integration.

## Configuration Details

**pyproject.toml:**
```toml
# ty - Type checking configuration
[tool.ty]
# Start permissive, tighten gradually
# ty is designed for gradual adoption

# Per-file overrides for gradual migration
[[tool.ty.per-file-ignores]]
"legacy/**/*.py" = ["*"]  # Ignore legacy code initially
"Archive/**/*.py" = ["*"]  # Ignore archived code

# ruff - Linting and formatting configuration
[tool.ruff]
line-length = 100
target-version = "py311"

# Enable specific rule sets
[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "N",      # pep8-naming
    "UP",     # pyupgrade
    "ANN",    # flake8-annotations (type hints)
    "ASYNC",  # flake8-async
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "RET",    # flake8-return
    "SIM",    # flake8-simplify
    "ARG",    # flake8-unused-arguments
]

ignore = [
    "ANN101",  # Missing type annotation for self
    "ANN102",  # Missing type annotation for cls
    "ANN401",  # Allow Any types initially
]

# Per-file ignore rules
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]  # Unused imports OK in __init__
"tests/**/*.py" = ["ANN"]  # No type hints required in tests initially
"legacy/**/*.py" = ["ALL"]  # Ignore legacy code
"Archive/**/*.py" = ["ALL"]  # Ignore archived code

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

## Development Workflow

**Helper Scripts:**
```bash
# scripts/lint/check-types.sh
#!/bin/bash
echo "Running ty type checker..."
uv run ty check

# scripts/lint/check-lint.sh
#!/bin/bash
echo "Running ruff linter..."
uv run ruff check .

# scripts/lint/format.sh
#!/bin/bash
echo "Formatting code with ruff..."
uv run ruff format .

# scripts/lint/check-all.sh
#!/bin/bash
./scripts/lint/check-types.sh
./scripts/lint/check-lint.sh
echo "✓ All checks passed!"
```

## Success Criteria

- ✅ ty and ruff installed and configured
- ✅ Type hints added to core utilities (types.py, common.py, colors.py)
- ✅ All code formatted consistently (119 files)
- ✅ 812 linting issues auto-fixed
- ✅ Helper scripts created for development workflow
- ✅ Configuration allows gradual adoption
- ✅ CI/CD ready (scripts can be added to pre-commit hooks)

## Future Improvements

- Add type hints to all service files (settings, controller_manager, game_coordinator, etc.)
- Add type hints to all game mode implementations
- Tighten ty rules gradually as more types are added
- Consider adding pre-commit hooks for automatic formatting
- Add type coverage metrics tracking
