import ctypes
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import proton_psmove
import runtime_platform


class ProtonPathTest(unittest.TestCase):
    def setUp(self):
        self.wine = mock.Mock()
        self.kernel32 = mock.Mock()
        self.kernel32.GetProcessHeap.return_value = 123
        self.cdll = mock.patch.object(ctypes, "CDLL", return_value=self.wine)
        self.windll = mock.patch.object(
            ctypes, "WinDLL", return_value=self.kernel32, create=True
        )
        self.cdll.start()
        self.windll.start()
        self.addCleanup(self.cdll.stop)
        self.addCleanup(self.windll.stop)

    def set_unix_path(self, path):
        self.buffer = ctypes.create_string_buffer(path.encode("utf-8"))
        self.pointer = ctypes.addressof(self.buffer)
        self.wine.wine_get_unix_file_name.return_value = self.pointer

    def test_library_entry_ending_in_steamapps_does_not_duplicate_directory(self):
        environment = {
            "STEAM_COMPAT_INSTALL_PATH": (
                "/home/deck/.local/share/Steam/steamapps/common/JoustMania"
            ),
            "STEAM_COMPAT_LIBRARY_PATHS": (
                "/home/deck/.local/share/Steam/steamapps"
            ),
        }
        expected = (
            "/home/deck/.local/share/Steam/steamapps/common/"
            "JoustMania/proton/psmoveapi/psmove"
        )
        self.set_unix_path(expected)
        helper = r"S:\steamapps\common\JoustMania\proton\psmoveapi\psmove"

        with mock.patch.dict(os.environ, environment, clear=True):
            result = proton_psmove._unix_path(helper)

        self.assertEqual(result, expected)
        self.wine.wine_get_unix_file_name.assert_called_once_with(helper)

    def test_uses_actual_mapping_instead_of_longest_library_match(self):
        environment = {
            "STEAM_COMPAT_INSTALL_PATH": (
                "/mnt/games/SteamLibrary/steamapps/common/JoustMania"
            ),
            "STEAM_COMPAT_LIBRARY_PATHS": (
                "/mnt/games:/mnt/games/SteamLibrary"
            ),
        }
        expected = "/mnt/actual-library/steamapps/common/JoustMania/piparty.exe"
        self.set_unix_path(expected)

        with mock.patch.dict(os.environ, environment, clear=True):
            result = proton_psmove._unix_path(
                r"S:\steamapps\common\JoustMania\piparty.exe"
            )

        self.assertEqual(result, expected)

    def test_sd_card_game_drive_keeps_steamapps_root_when_proton_does(self):
        expected = "/run/media/deck/SD Card/steamapps/common/JoustMania/piparty.exe"
        self.set_unix_path(expected)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                proton_psmove._unix_path(r"S:\common\JoustMania\piparty.exe"),
                expected,
            )

    def test_resolves_game_library_symlinks_without_steam_environment(self):
        expected = "/home/deck/.steam/steam/steamapps/common/JoustMania/piparty.exe"
        self.set_unix_path(expected)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                proton_psmove._unix_path(r"s:\steamapps\common\JoustMania\piparty.exe"),
                expected,
            )

    def test_resolves_other_drive_letters_and_unicode_paths(self):
        cases = (
            (r"Z:\home\deck\JoustMania\psmove", "/home/deck/JoustMania/psmove"),
            (r"C:\users\steamuser\AppData\Roaming\.psmoveapi", "/real/prefix/appdata/.psmoveapi"),
            (r"D:\Games\JoustMania\psmove", "/mnt/games/JoustMania/psmove"),
            (r"S:\Games\JöustMania\psmove", "/mnt/SD Card/Games/JöustMania/psmove"),
        )
        for wine_path, unix_path in cases:
            with self.subTest(wine_path=wine_path):
                self.set_unix_path(unix_path)
                self.assertEqual(proton_psmove._unix_path(wine_path), unix_path)

    def test_forward_slashes_are_normalized_for_wine(self):
        self.set_unix_path("/mnt/games/psmove")
        self.assertEqual(proton_psmove._unix_path("S:/games/psmove"), "/mnt/games/psmove")
        self.wine.wine_get_unix_file_name.assert_called_once_with(r"S:\games\psmove")

    def test_absolute_linux_paths_do_not_load_wine(self):
        path = "/mnt/SD Card/JoustMania/psmove"
        self.assertEqual(proton_psmove._unix_path(path), path)
        ctypes.CDLL.assert_not_called()
        ctypes.WinDLL.assert_not_called()

    def test_rejects_relative_paths_before_calling_wine(self):
        for path in ("psmove", r"S:psmove", ""):
            with self.subTest(path=path):
                with self.assertRaisesRegex(RuntimeError, "Cannot convert Wine path"):
                    proton_psmove._unix_path(path)
        self.wine.wine_get_unix_file_name.assert_not_called()

    def test_reports_missing_wine_path_api(self):
        del self.wine.wine_get_unix_file_name
        with self.assertRaisesRegex(RuntimeError, "This Proton version cannot resolve"):
            proton_psmove._unix_path(r"S:\games\psmove")

    def test_reports_unavailable_wine_library(self):
        ctypes.CDLL.side_effect = OSError("Wine is unavailable")
        with self.assertRaisesRegex(RuntimeError, "This Proton version cannot resolve"):
            proton_psmove._unix_path(r"S:\games\psmove")

    def test_reports_failed_conversion_without_guessing_a_path(self):
        self.wine.wine_get_unix_file_name.return_value = None
        with self.assertRaisesRegex(RuntimeError, "Cannot resolve Wine path"):
            proton_psmove._unix_path(r"S:\games\psmove")
        self.kernel32.HeapFree.assert_not_called()

    def test_copies_and_frees_wine_buffer_with_pointer_sized_types(self):
        self.set_unix_path("/mnt/games/psmove")
        proton_psmove._unix_path(r"S:\games\psmove")
        self.assertEqual(self.wine.wine_get_unix_file_name.argtypes, [ctypes.c_wchar_p])
        self.assertIs(self.wine.wine_get_unix_file_name.restype, ctypes.c_void_p)
        self.assertIs(self.kernel32.GetProcessHeap.restype, ctypes.c_void_p)
        self.assertEqual(
            self.kernel32.HeapFree.argtypes,
            [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p],
        )
        self.kernel32.HeapFree.assert_called_once_with(123, 0, self.pointer)

    def test_frees_wine_buffer_even_if_decoding_fails(self):
        self.buffer = ctypes.create_string_buffer(b"\xff")
        pointer = ctypes.addressof(self.buffer)
        self.wine.wine_get_unix_file_name.return_value = pointer
        with self.assertRaises(UnicodeDecodeError):
            proton_psmove._unix_path(r"S:\games\psmove")
        self.kernel32.HeapFree.assert_called_once_with(123, 0, pointer)


class ProtonHelperPathTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.helper = Path(directory.name) / "psmove"
        self.library = Path(directory.name) / "libpsmoveapi.so"
        self.helper.touch()
        self.library.touch()
        self.bundle = mock.patch.object(
            proton_psmove, "_bundle_paths", return_value=(self.helper, self.library)
        )
        self.bundle.start()
        self.addCleanup(self.bundle.stop)
        self.resolved = "/home/deck/.local/share/Steam/steamapps/common/JoustMania/proton/psmoveapi/psmove"

    @mock.patch.object(proton_psmove, "_started_by_pid", None)
    @mock.patch.object(proton_psmove.runtime_platform, "is_proton", return_value=True)
    @mock.patch.object(proton_psmove, "_show_password_setup_if_needed")
    @mock.patch.object(proton_psmove, "_write_host_config")
    @mock.patch.object(proton_psmove.time, "sleep")
    @mock.patch.object(proton_psmove, "_run_host", return_value=0)
    def test_start_uses_resolved_path_for_chmod_and_daemon(self, run, *_):
        with mock.patch.object(proton_psmove, "_unix_path", return_value=self.resolved) as resolve:
            proton_psmove.start()
        resolve.assert_called_once_with(self.helper)
        run.assert_any_call(["/usr/bin/chmod", "u+x", self.resolved])
        self.assertEqual(run.call_args.args[0][-2:], [self.resolved, "daemon"])

    @mock.patch.object(proton_psmove, "stop")
    @mock.patch.object(proton_psmove, "_run_host", return_value=1)
    def test_pair_uses_resolved_path(self, run, _):
        with mock.patch.object(proton_psmove, "_unix_path", return_value=self.resolved) as resolve:
            self.assertTrue(proton_psmove.pair("AA:BB:CC:DD:EE:FF"))
        resolve.assert_called_once_with(self.helper)
        run.assert_called_once_with(
            ["/usr/bin/pkexec", self.resolved, "pair", "aa:bb:cc:dd:ee:ff"],
            success_statuses=(1,),
        )


class ProtonWebPortTest(unittest.TestCase):
    def test_uses_8090_by_default_under_proton(self):
        with mock.patch.object(runtime_platform, "is_proton", return_value=True):
            self.assertEqual(runtime_platform.default_web_port(), 8090)

    def test_native_default_remains_port_80(self):
        with mock.patch.object(runtime_platform, "is_proton", return_value=False):
            self.assertEqual(runtime_platform.default_web_port(), 80)


if __name__ == "__main__":
    unittest.main()
