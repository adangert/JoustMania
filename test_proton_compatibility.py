import os
import unittest
from unittest import mock

import proton_psmove
import runtime_platform


class ProtonPathTest(unittest.TestCase):
    def test_converts_proton_game_drive_path(self):
        environment = {
            "STEAM_COMPAT_INSTALL_PATH": (
                "/home/deck/.local/share/Steam/steamapps/common/JoustMania"
            ),
            "STEAM_COMPAT_LIBRARY_PATHS": (
                "/mnt/external/SteamLibrary:"
                "/home/deck/.local/share/Steam"
            ),
        }

        with mock.patch.dict(os.environ, environment, clear=True):
            result = proton_psmove._unix_path(
                r"S:\steamapps\common\JoustMania\proton\psmoveapi\psmove"
            )

        self.assertEqual(
            result,
            (
                "/home/deck/.local/share/Steam/steamapps/common/"
                "JoustMania/proton/psmoveapi/psmove"
            ),
        )

    def test_uses_longest_matching_library_path(self):
        environment = {
            "STEAM_COMPAT_INSTALL_PATH": (
                "/mnt/games/SteamLibrary/steamapps/common/JoustMania"
            ),
            "STEAM_COMPAT_LIBRARY_PATHS": (
                "/mnt/games:/mnt/games/SteamLibrary"
            ),
        }

        with mock.patch.dict(os.environ, environment, clear=True):
            result = proton_psmove._unix_path(
                r"S:\steamapps\common\JoustMania\piparty.exe"
            )

        self.assertEqual(
            result,
            (
                "/mnt/games/SteamLibrary/steamapps/common/"
                "JoustMania/piparty.exe"
            ),
        )

    def test_reports_missing_game_drive_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "Cannot resolve Proton S: drive",
            ):
                proton_psmove._unix_path(r"S:\steamapps\common\JoustMania")


class ProtonWebPortTest(unittest.TestCase):
    def test_uses_8081_by_default_under_proton(self):
        with mock.patch.object(runtime_platform, "is_proton", return_value=True):
            self.assertEqual(runtime_platform.default_web_port(), 8081)

    def test_native_default_remains_port_80(self):
        with mock.patch.object(runtime_platform, "is_proton", return_value=False):
            self.assertEqual(runtime_platform.default_web_port(), 80)


if __name__ == "__main__":
    unittest.main()
