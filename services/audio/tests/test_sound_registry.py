"""
Unit tests for audio service sound registry and path resolution.

These tests verify that:
1. All Sound enum values can be resolved to existing files
2. The registry correctly categorizes vox vs sound effects
3. Path resolution uses correct voice directories for vox sounds
4. All asset directories are scanned (Joust, Menu, Zombie, Fight_Club, Commander)
"""

from pathlib import Path

import pytest

from lib.types import Sound

# Get the assets directory relative to this test file
ASSETS_DIR = Path(__file__).parent.parent / "assets"


class TestSoundRegistry:
    """Test the sound registry building and lookup."""

    @pytest.fixture
    def registry(self):
        """Build a sound registry like the audio service does."""
        sound_registry: dict[str, tuple[str, str]] = {}

        for base_dir in ["Joust", "Menu", "Zombie", "Fight_Club", "Commander"]:
            assets_path = ASSETS_DIR / base_dir

            # Scan vox directory (use aaron as reference)
            vox_dir = assets_path / "vox" / "aaron"
            if vox_dir.exists():
                for wav_file in vox_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in sound_registry:
                        sound_registry[sound_name] = ("vox", base_dir)
                    if sound_name.lower() not in sound_registry:
                        sound_registry[sound_name.lower()] = ("vox", base_dir)

            # Scan sounds directory
            sounds_dir = assets_path / "sounds"
            if sounds_dir.exists():
                for wav_file in sounds_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in sound_registry:
                        sound_registry[sound_name] = ("sound", base_dir)
                    if sound_name.lower() not in sound_registry:
                        sound_registry[sound_name.lower()] = ("sound", base_dir)

        return sound_registry

    def test_registry_scans_all_directories(self, registry):
        """Verify all asset directories are scanned."""
        base_dirs_found = set()
        for _sound_name, (_, base_dir) in registry.items():
            base_dirs_found.add(base_dir)

        # At minimum, Joust and Menu should have sounds
        assert "Joust" in base_dirs_found, "Joust directory not scanned"
        assert "Menu" in base_dirs_found, "Menu directory not scanned"

    def test_registry_has_sounds(self, registry):
        """Verify registry contains sounds."""
        assert len(registry) > 0, "Registry is empty"
        # Should have at least 100 sounds
        assert len(registry) > 100, f"Registry has only {len(registry)} sounds"

    def test_all_sound_enum_values_resolve(self, registry):
        """Verify every Sound enum value can be found in the registry."""
        missing = []
        for sound in Sound:
            value = sound.value
            if value not in registry and value.lower() not in registry:
                missing.append(f"{sound.name}: {value}")

        assert not missing, "Missing sounds in registry:\n" + "\n".join(missing)

    def test_explosion_sounds_registered(self, registry):
        """Verify explosion sounds are in the registry."""
        assert "Explosion34" in registry, "Explosion34 not in registry"
        assert "Explosion22" in registry, "Explosion22 not in registry"

        # Check they're registered as sound effects, not vox
        sound_type, base_dir = registry["Explosion34"]
        assert sound_type == "sound", f"Explosion34 should be 'sound', got '{sound_type}'"
        assert base_dir == "Joust", f"Explosion34 should be in 'Joust', got '{base_dir}'"

    def test_congratulations_is_vox(self, registry):
        """Verify congratulations is registered as vox sound."""
        assert "congratulations" in registry, "congratulations not in registry"

        sound_type, base_dir = registry["congratulations"]
        assert sound_type == "vox", f"congratulations should be 'vox', got '{sound_type}'"
        assert base_dir == "Joust", f"congratulations should be in 'Joust', got '{base_dir}'"

    def test_beep_loud_exists(self, registry):
        """Verify beep_loud is in registry (SFX_BEEP points to this)."""
        assert "beep_loud" in registry, "beep_loud not in registry"

        sound_type, base_dir = registry["beep_loud"]
        assert sound_type == "sound", f"beep_loud should be 'sound', got '{sound_type}'"

    def test_zombie_sounds_registered(self, registry):
        """Verify zombie game sounds are registered."""
        zombie_sounds = ["zombie_victory", "zombie_death", "human_victory"]
        for sound_name in zombie_sounds:
            assert sound_name in registry, f"{sound_name} not in registry"
            sound_type, base_dir = registry[sound_name]
            assert base_dir == "Zombie", f"{sound_name} should be in 'Zombie', got '{base_dir}'"


class TestPathResolution:
    """Test sound path resolution logic."""

    @pytest.fixture
    def registry(self):
        """Build a minimal registry for path resolution tests."""
        return {
            "congratulations": ("vox", "Joust"),
            "Explosion34": ("sound", "Joust"),
            "zombie_victory": ("vox", "Zombie"),
            "beep_loud": ("sound", "Joust"),
            "menu Joust FFA": ("vox", "Menu"),
        }

    def resolve_sound_path(self, sound_input: str, registry: dict, menu_voice: str = "ivy") -> str:
        """Simulate the audio service's _resolve_sound_path method."""
        lookup_name = sound_input
        if lookup_name.endswith(".wav"):
            lookup_name = lookup_name[:-4]

        if "/" not in lookup_name and "\\" not in lookup_name:
            registry_entry = registry.get(lookup_name) or registry.get(lookup_name.lower())
            if registry_entry:
                sound_type, base_dir = registry_entry
                if sound_type == "vox":
                    return f"{base_dir}/vox/{menu_voice}/{lookup_name}.wav"
                return f"{base_dir}/sounds/{lookup_name}.wav"
            return f"Joust/vox/{menu_voice}/{lookup_name}.wav"

        if "/vox/" in sound_input:
            parts = sound_input.split("/vox/")
            if len(parts) == 2:
                remainder = parts[1]
                if not remainder.startswith("aaron/") and not remainder.startswith("ivy/"):
                    return f"{parts[0]}/vox/{menu_voice}/{remainder}"

        return sound_input

    def test_vox_sound_uses_voice_directory(self, registry):
        """Verify vox sounds include voice folder in path."""
        path = self.resolve_sound_path("congratulations", registry, menu_voice="ivy")
        assert path == "Joust/vox/ivy/congratulations.wav"

        path = self.resolve_sound_path("congratulations", registry, menu_voice="aaron")
        assert path == "Joust/vox/aaron/congratulations.wav"

    def test_sfx_sound_uses_sounds_directory(self, registry):
        """Verify sound effects use sounds folder, not vox."""
        path = self.resolve_sound_path("Explosion34", registry)
        assert path == "Joust/sounds/Explosion34.wav"
        assert "/vox/" not in path

    def test_zombie_vox_uses_zombie_directory(self, registry):
        """Verify zombie vox sounds use Zombie base directory."""
        path = self.resolve_sound_path("zombie_victory", registry, menu_voice="ivy")
        assert path == "Zombie/vox/ivy/zombie_victory.wav"

    def test_menu_vox_uses_menu_directory(self, registry):
        """Verify menu vox sounds use Menu base directory."""
        path = self.resolve_sound_path("menu Joust FFA", registry, menu_voice="ivy")
        assert path == "Menu/vox/ivy/menu Joust FFA.wav"


class TestSoundEnumValues:
    """Test that Sound enum values match actual file names."""

    @pytest.fixture
    def registry(self):
        """Build full registry."""
        sound_registry: dict[str, tuple[str, str]] = {}

        for base_dir in ["Joust", "Menu", "Zombie", "Fight_Club", "Commander"]:
            assets_path = ASSETS_DIR / base_dir

            vox_dir = assets_path / "vox" / "aaron"
            if vox_dir.exists():
                for wav_file in vox_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in sound_registry:
                        sound_registry[sound_name] = ("vox", base_dir)
                    if sound_name.lower() not in sound_registry:
                        sound_registry[sound_name.lower()] = ("vox", base_dir)

            sounds_dir = assets_path / "sounds"
            if sounds_dir.exists():
                for wav_file in sounds_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in sound_registry:
                        sound_registry[sound_name] = ("sound", base_dir)
                    if sound_name.lower() not in sound_registry:
                        sound_registry[sound_name.lower()] = ("sound", base_dir)

        return sound_registry

    def test_sfx_beep_points_to_existing_file(self, registry):
        """SFX_BEEP should point to beep_loud (beep.wav doesn't exist)."""
        assert Sound.SFX_BEEP.value == "beep_loud", "SFX_BEEP should be 'beep_loud'"
        assert "beep_loud" in registry

    def test_vox_congratulations_exists(self, registry):
        """VOX_CONGRATULATIONS should resolve."""
        assert Sound.VOX_CONGRATULATIONS.value in registry

    def test_explosion_sounds_exist(self, registry):
        """Explosion sounds should resolve."""
        assert Sound.SFX_EXPLOSION.value in registry
        assert Sound.SFX_EXPLOSION_22.value in registry

    def test_team_win_sounds_exist(self, registry):
        """Team win sounds should all resolve."""
        team_sounds = [
            Sound.VOX_BLUE_TEAM_WIN,
            Sound.VOX_RED_TEAM_WIN,
            Sound.VOX_GREEN_TEAM_WIN,
            Sound.VOX_YELLOW_TEAM_WIN,
        ]
        for sound in team_sounds:
            assert sound.value in registry, f"{sound.name} ({sound.value}) not in registry"

    def test_zombie_sounds_exist(self, registry):
        """Zombie game sounds should resolve."""
        zombie_sounds = [
            Sound.VOX_ZOMBIE_VICTORY,
            Sound.VOX_ZOMBIE_DEATH,
            Sound.VOX_HUMAN_VICTORY,
            Sound.VOX_ZOMBIE_ONE_MINUTE,
            Sound.VOX_ZOMBIE_THIRTY_SECONDS,
            Sound.VOX_ZOMBIE_TEN_SECONDS,
        ]
        for sound in zombie_sounds:
            assert sound.value in registry, f"{sound.name} ({sound.value}) not in registry"

    def test_werewolf_vox_sounds_exist(self, registry):
        """Werewolf VOX sounds should resolve."""
        werewolf_sounds = [
            Sound.VOX_WEREWOLF_INTRO,
            Sound.VOX_WEREWOLF_REVEAL,
            Sound.VOX_WEREWOLF_WIN,
            Sound.VOX_HUMAN_WIN,
        ]
        for sound in werewolf_sounds:
            assert sound.value in registry, f"{sound.name} ({sound.value}) not in registry"


class TestActualFileExistence:
    """Test that resolved paths point to actual files."""

    def resolve_full_path(self, sound_value: str) -> Path | None:
        """Resolve a sound value to its full file path."""
        registry: dict[str, tuple[str, str]] = {}

        for base_dir in ["Joust", "Menu", "Zombie", "Fight_Club", "Commander"]:
            assets_path = ASSETS_DIR / base_dir

            vox_dir = assets_path / "vox" / "aaron"
            if vox_dir.exists():
                for wav_file in vox_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in registry:
                        registry[sound_name] = ("vox", base_dir)

            sounds_dir = assets_path / "sounds"
            if sounds_dir.exists():
                for wav_file in sounds_dir.glob("*.wav"):
                    sound_name = wav_file.stem
                    if sound_name not in registry:
                        registry[sound_name] = ("sound", base_dir)

        entry = registry.get(sound_value) or registry.get(sound_value.lower())
        if not entry:
            return None

        sound_type, base_dir = entry
        if sound_type == "vox":
            return ASSETS_DIR / base_dir / "vox" / "ivy" / f"{sound_value}.wav"
        return ASSETS_DIR / base_dir / "sounds" / f"{sound_value}.wav"

    def test_all_sound_enum_files_exist(self):
        """Every Sound enum value should resolve to an existing file."""
        missing_files = []
        for sound in Sound:
            path = self.resolve_full_path(sound.value)
            if path is None:
                missing_files.append(f"{sound.name}: {sound.value} - not in registry")
            elif not path.exists():
                missing_files.append(f"{sound.name}: {sound.value} - file not found at {path}")

        assert not missing_files, "Missing sound files:\n" + "\n".join(missing_files)

    def test_explosion34_file_exists(self):
        """Explosion34.wav should exist."""
        path = ASSETS_DIR / "Joust" / "sounds" / "Explosion34.wav"
        assert path.exists(), f"Explosion34.wav not found at {path}"

    def test_beep_loud_file_exists(self):
        """beep_loud.wav should exist."""
        path = ASSETS_DIR / "Joust" / "sounds" / "beep_loud.wav"
        assert path.exists(), f"beep_loud.wav not found at {path}"

    def test_congratulations_file_exists_for_both_voices(self):
        """congratulations.wav should exist for both aaron and ivy."""
        for voice in ["aaron", "ivy"]:
            path = ASSETS_DIR / "Joust" / "vox" / voice / "congratulations.wav"
            assert path.exists(), f"congratulations.wav not found for voice '{voice}' at {path}"
