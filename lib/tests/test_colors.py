"""Tests for lib/colors.py"""

import sys
from pathlib import Path

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.colors import (
    Colors,
    change_color,
    darken_color,
    generate_colors,
    generate_team_colors,
    hsv2rgb,
)


class TestDarkenColor:
    """Tests for darken_color function."""

    def test_darken_by_zero_returns_original(self):
        """Factor 0 should return original color."""
        color = (255, 128, 64)
        result = darken_color(color, 0)
        assert result == (255, 128, 64)

    def test_darken_by_one_returns_black(self):
        """Factor 1 should return black."""
        color = (255, 128, 64)
        result = darken_color(color, 1)
        assert result == (0, 0, 0)

    def test_darken_by_half(self):
        """Factor 0.5 should halve the values."""
        color = (200, 100, 50)
        result = darken_color(color, 0.5)
        assert result == (100, 50, 25)

    def test_factor_clamped_above_one(self):
        """Factor > 1 should be clamped to 1."""
        color = (255, 255, 255)
        result = darken_color(color, 2.0)
        assert result == (0, 0, 0)

    def test_factor_clamped_below_zero(self):
        """Factor < 0 should be clamped to 0."""
        color = (255, 128, 64)
        result = darken_color(color, -0.5)
        assert result == (255, 128, 64)


class TestHsv2Rgb:
    """Tests for hsv2rgb function."""

    def test_red(self):
        """Hue 0 with full saturation and value should be red."""
        result = hsv2rgb(0, 1, 1)
        assert result == (255, 0, 0)

    def test_green(self):
        """Hue 1/3 should be green."""
        result = hsv2rgb(1 / 3, 1, 1)
        assert result == (0, 255, 0)

    def test_blue(self):
        """Hue 2/3 should be blue."""
        result = hsv2rgb(2 / 3, 1, 1)
        assert result == (0, 0, 255)

    def test_white(self):
        """Zero saturation with full value should be white."""
        result = hsv2rgb(0, 0, 1)
        assert result == (255, 255, 255)

    def test_black(self):
        """Zero value should be black."""
        result = hsv2rgb(0, 1, 0)
        assert result == (0, 0, 0)


class TestGenerateColors:
    """Tests for generate_colors function."""

    def test_generates_correct_count(self):
        """Should generate the requested number of colors."""
        for count in [2, 4, 6, 8]:
            colors = generate_colors(count)
            assert len(colors) == count

    def test_colors_are_distinct(self):
        """Generated colors should be distinct."""
        colors = generate_colors(6)
        # Convert to set of tuples to check uniqueness
        unique_colors = set(colors)
        assert len(unique_colors) == 6

    def test_avoids_red(self):
        """Generated colors should avoid red hues."""
        colors = generate_colors(8)
        for r, g, b in colors:
            # Red would be high R with low G and B
            # Our hue range 0.1-0.9 avoids pure red
            is_pure_red = r > 200 and g < 50 and b < 50
            assert not is_pure_red, f"Color ({r}, {g}, {b}) is too close to red"

    def test_single_color(self):
        """Should handle single color request."""
        colors = generate_colors(1)
        assert len(colors) == 1
        assert len(colors[0]) == 3  # RGB tuple


class TestGenerateTeamColors:
    """Tests for generate_team_colors function."""

    def test_two_teams_returns_two_colors(self):
        """Two teams should return two distinct colors."""
        colors = generate_team_colors(2)
        assert len(colors) == 2
        assert colors[0] != colors[1]

    def test_three_teams_returns_three_colors(self):
        """Three teams should return three colors."""
        colors = generate_team_colors(3)
        assert len(colors) == 3

    def test_four_teams_returns_four_colors(self):
        """Four teams should return four colors."""
        colors = generate_team_colors(4)
        assert len(colors) == 4

    def test_returns_colors_enum_members(self):
        """Should return Colors enum members."""
        colors = generate_team_colors(2)
        for color in colors:
            assert isinstance(color, Colors)

    def test_more_than_four_teams(self):
        """More than 4 teams should return ordered color list."""
        colors = generate_team_colors(6)
        assert len(colors) == 6
        for color in colors:
            assert isinstance(color, Colors)

    def test_color_lock_two_teams(self):
        """Color lock should return specified colors for 2 teams."""
        choices = {2: ["Blue", "Yellow"]}
        colors = generate_team_colors(2, color_lock=True, color_lock_choices=choices)
        assert colors == [Colors.Blue, Colors.Yellow]

    def test_color_lock_ignored_without_choices(self):
        """Color lock without choices should fall back to random."""
        colors = generate_team_colors(2, color_lock=True, color_lock_choices=None)
        assert len(colors) == 2


class TestChangeColor:
    """Tests for change_color function."""

    def test_changes_color_in_place(self):
        """Should modify the list in place."""
        color = [0, 0, 0]
        change_color(color, 255, 128, 64)
        assert color == [255, 128, 64]

    def test_overwrites_existing_values(self):
        """Should overwrite existing values."""
        color = [100, 100, 100]
        change_color(color, 0, 255, 0)
        assert color == [0, 255, 0]


class TestColorsEnum:
    """Tests for Colors enum."""

    def test_team_colors_are_first_eight(self):
        """First 8 colors should be team colors (no red)."""
        team_colors = list(Colors)[:8]
        for color in team_colors:
            assert color != Colors.Red

    def test_color_values_are_rgb_tuples(self):
        """All color values should be RGB tuples."""
        for color in Colors:
            assert isinstance(color.value, tuple)
            assert len(color.value) == 3
            r, g, b = color.value
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255

    def test_specific_colors(self):
        """Test specific color values."""
        assert Colors.Red.value == (255, 0, 0)
        assert Colors.Green.value == (0, 255, 0)
        assert Colors.Blue.value == (0, 0, 255)
        assert Colors.White.value == (255, 255, 255)
        assert Colors.Black.value == (0, 0, 0)
