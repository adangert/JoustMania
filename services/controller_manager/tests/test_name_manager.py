"""
Unit tests for NameManager.

Tests human-readable controller name generation and persistence.
"""

import os
import tempfile

from services.controller_manager.name_manager import (
    ADJECTIVES,
    NOUNS,
    NameManager,
)


class TestNameGeneration:
    """Tests for deterministic name generation."""

    def test_name_format(self):
        """Generated names follow 'Adjective Noun' format."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            name = manager.get_name("TEST_SERIAL_001")

            # Name should be "Adjective Noun"
            parts = name.split(" ")
            assert len(parts) == 2
            assert parts[0] in ADJECTIVES
            assert parts[1] in NOUNS
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_deterministic_generation(self):
        """Same serial always generates same name."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager1 = NameManager(names_file)
            name1 = manager1._generate_name("SERIAL_ABC123")

            manager2 = NameManager(names_file)
            name2 = manager2._generate_name("SERIAL_ABC123")

            assert name1 == name2
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_different_serials_different_names(self):
        """Different serials produce different names (with high probability)."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)

            # Generate names for 10 different serials
            names = [manager._generate_name(f"SERIAL_{i}") for i in range(10)]

            # Should have at least 5 unique names (with 256 possibilities)
            unique_names = set(names)
            assert len(unique_names) >= 5
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_get_name_returns_generated_name(self):
        """get_name returns deterministically generated name for new serials."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)

            # Generate using internal method
            expected = manager._generate_name("NEW_SERIAL")

            # get_name should return the same
            actual = manager.get_name("NEW_SERIAL")
            assert actual == expected
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)


class TestNamePersistence:
    """Tests for name persistence to file."""

    def test_name_saved_on_first_get(self):
        """First get_name saves the name to file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            name = manager.get_name("SERIAL_TO_SAVE")

            # Read file directly
            with open(names_file) as f:
                content = f.read()

            assert "SERIAL_TO_SAVE=" in content
            assert name in content
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_names_persist_across_instances(self):
        """Names persist when creating new NameManager instance."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            # Create first manager and get a name
            manager1 = NameManager(names_file)
            name1 = manager1.get_name("PERSISTENT_SERIAL")

            # Create new manager loading from same file
            manager2 = NameManager(names_file)
            name2 = manager2.get_name("PERSISTENT_SERIAL")

            assert name1 == name2
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_custom_name_persists(self):
        """Custom names set via set_name persist."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager1 = NameManager(names_file)
            manager1.set_name("CUSTOM_SERIAL", "My Custom Name")

            # New instance should load custom name
            manager2 = NameManager(names_file)
            assert manager2.get_name("CUSTOM_SERIAL") == "My Custom Name"
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_file_format(self):
        """File uses expected serial=name format with header."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            manager.set_name("SERIAL1", "Name One")
            manager.set_name("SERIAL2", "Name Two")

            with open(names_file) as f:
                lines = f.readlines()

            # First line is header comment
            assert lines[0].startswith("#")

            # Remaining lines are serial=name format
            data_lines = [line.strip() for line in lines[1:] if line.strip()]
            assert "SERIAL1=Name One" in data_lines
            assert "SERIAL2=Name Two" in data_lines
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_load_handles_missing_file(self):
        """NameManager handles missing file gracefully."""
        nonexistent = "/tmp/nonexistent_controller_names_test.txt"
        if os.path.exists(nonexistent):
            os.unlink(nonexistent)

        try:
            manager = NameManager(nonexistent)
            # Should work without error
            name = manager.get_name("TEST_SERIAL")
            assert name is not None
        finally:
            if os.path.exists(nonexistent):
                os.unlink(nonexistent)

    def test_load_ignores_comments_and_empty_lines(self):
        """Loading ignores comments and empty lines."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("# This is a comment\n")
            f.write("\n")
            f.write("SERIAL1=Valid Name\n")
            f.write("  # Another comment\n")
            f.write("SERIAL2=Another Name\n")
            names_file = f.name

        try:
            manager = NameManager(names_file)

            assert manager.get_name("SERIAL1") == "Valid Name"
            assert manager.get_name("SERIAL2") == "Another Name"
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)


class TestSetName:
    """Tests for custom name assignment."""

    def test_set_name_overrides_generated(self):
        """set_name overrides auto-generated name."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)

            # Get auto-generated name first
            auto_name = manager.get_name("OVERRIDE_SERIAL")

            # Override it
            manager.set_name("OVERRIDE_SERIAL", "Custom Override")
            assert manager.get_name("OVERRIDE_SERIAL") == "Custom Override"
            assert manager.get_name("OVERRIDE_SERIAL") != auto_name
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_set_name_returns_true(self):
        """set_name returns True on success."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            result = manager.set_name("TEST_SERIAL", "Test Name")
            assert result is True
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_set_name_for_new_serial(self):
        """set_name works for serials that haven't been seen before."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            manager.set_name("BRAND_NEW_SERIAL", "Brand New Name")

            assert manager.get_name("BRAND_NEW_SERIAL") == "Brand New Name"
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)


class TestGetAllNames:
    """Tests for get_all_names method."""

    def test_get_all_names_returns_copy(self):
        """get_all_names returns a copy of internal state."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            manager.set_name("SERIAL1", "Name1")

            all_names = manager.get_all_names()

            # Modifying returned dict shouldn't affect internal state
            all_names["SERIAL1"] = "Modified"
            assert manager.get_name("SERIAL1") == "Name1"
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_get_all_names_includes_all(self):
        """get_all_names includes all registered names."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            manager.set_name("SERIAL1", "Name1")
            manager.set_name("SERIAL2", "Name2")
            manager.get_name("SERIAL3")  # Auto-generated

            all_names = manager.get_all_names()

            assert "SERIAL1" in all_names
            assert "SERIAL2" in all_names
            assert "SERIAL3" in all_names
            assert len(all_names) == 3
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_get_name(self):
        """get_name is thread-safe for concurrent calls."""
        import threading

        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            results = {}
            errors = []

            def get_name_thread(serial):
                try:
                    results[serial] = manager.get_name(serial)
                except Exception as e:
                    errors.append(e)

            # Start multiple threads getting names concurrently
            threads = []
            for i in range(20):
                t = threading.Thread(target=get_name_thread, args=(f"SERIAL_{i}",))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            assert len(errors) == 0
            assert len(results) == 20
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)

    def test_concurrent_set_and_get(self):
        """Concurrent set_name and get_name operations are thread-safe."""
        import threading

        with tempfile.NamedTemporaryFile(delete=False) as f:
            names_file = f.name

        try:
            manager = NameManager(names_file)
            errors = []

            def set_name_thread(serial, name):
                try:
                    manager.set_name(serial, name)
                except Exception as e:
                    errors.append(e)

            def get_name_thread(serial):
                try:
                    manager.get_name(serial)
                except Exception as e:
                    errors.append(e)

            threads = []
            for i in range(10):
                t1 = threading.Thread(target=set_name_thread, args=(f"SERIAL_{i}", f"Name {i}"))
                t2 = threading.Thread(target=get_name_thread, args=(f"SERIAL_{i}",))
                threads.extend([t1, t2])
                t1.start()
                t2.start()

            for t in threads:
                t.join()

            assert len(errors) == 0
        finally:
            if os.path.exists(names_file):
                os.unlink(names_file)
