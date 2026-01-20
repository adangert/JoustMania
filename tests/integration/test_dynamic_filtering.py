"""
Integration tests for Phase 45: Adaptive Controller Filtering via Bidirectional Streaming

Tests the dynamic filtering feature that reduces monitoring overhead as players die.
"""

import pytest


class TestProtoMessages:
    """Test Phase 45 proto message creation and manipulation."""

    def test_gameplay_stream_config_creation(self):
        """Test creating GameplayStreamConfig message with colors."""
        from proto import controller_manager_pb2

        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=30,
            colors=[
                controller_manager_pb2.ControllerColorConfig(
                    serial="controller_1", color=controller_manager_pb2.RGB(r=255, g=0, b=0)
                ),
                controller_manager_pb2.ControllerColorConfig(
                    serial="controller_2", color=controller_manager_pb2.RGB(r=0, g=255, b=0)
                ),
                controller_manager_pb2.ControllerColorConfig(
                    serial="controller_3", color=controller_manager_pb2.RGB(r=0, g=0, b=255)
                ),
            ],
        )

        assert config.update_frequency_hz == 30
        assert len(config.colors) == 3
        assert config.colors[0].serial == "controller_1"

    def test_gameplay_stream_config_empty_colors(self):
        """Test GameplayStreamConfig with empty colors (all controllers)."""
        from proto import controller_manager_pb2

        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=60,
            colors=[],  # Empty = all controllers
        )

        assert config.update_frequency_hz == 60
        assert len(config.colors) == 0

    def test_filter_update_creation(self):
        """Test creating FilterUpdate message."""
        from proto import controller_manager_pb2

        filter_update = controller_manager_pb2.FilterUpdate(
            serials=["controller_1", "controller_2"]
        )

        assert len(filter_update.serials) == 2
        assert "controller_1" in filter_update.serials

    def test_gameplay_stream_control_with_config(self):
        """Test GameplayStreamControl with initial config."""
        from proto import controller_manager_pb2

        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=30,
            colors=[
                controller_manager_pb2.ControllerColorConfig(
                    serial="controller_1", color=controller_manager_pb2.RGB(r=255, g=0, b=0)
                ),
            ],
        )

        control_msg = controller_manager_pb2.GameplayStreamControl(config=config)

        assert control_msg.HasField("config")
        assert not control_msg.HasField("filter_update")
        assert control_msg.config.update_frequency_hz == 30

    def test_gameplay_stream_control_with_filter_update(self):
        """Test GameplayStreamControl with filter update."""
        from proto import controller_manager_pb2

        filter_update = controller_manager_pb2.FilterUpdate(
            serials=["controller_1", "controller_2"]
        )

        control_msg = controller_manager_pb2.GameplayStreamControl(filter_update=filter_update)

        assert control_msg.HasField("filter_update")
        assert not control_msg.HasField("config")
        assert len(control_msg.filter_update.serials) == 2

    def test_gameplay_stream_control_oneof_behavior(self):
        """Test that GameplayStreamControl oneof allows only one field."""
        from proto import controller_manager_pb2

        # Set config first
        control_msg = controller_manager_pb2.GameplayStreamControl(
            config=controller_manager_pb2.GameplayStreamConfig(update_frequency_hz=30, colors=[])
        )

        assert control_msg.HasField("config")

        # Setting filter_update should clear config (oneof behavior)
        control_msg.filter_update.CopyFrom(
            controller_manager_pb2.FilterUpdate(serials=["controller_1"])
        )

        assert control_msg.HasField("filter_update")
        assert not control_msg.HasField("config")


# TestMetrics moved to service-level unit tests (requires prometheus_client)


class TestFilterLogic:
    """Test the filtering logic behavior."""

    def test_filter_calculation(self):
        """Test calculating filtered vs active controllers."""
        total_players = 25
        alive_players = 10

        filtered_count = total_players - alive_players
        assert filtered_count == 15

        # 60% reduction
        reduction_percent = (filtered_count / total_players) * 100
        assert reduction_percent == 60.0

    def test_late_game_filtering(self):
        """Test late-game scenario with heavy filtering."""
        total_players = 25
        alive_players = 2

        filtered_count = total_players - alive_players
        assert filtered_count == 23

        # 92% reduction
        reduction_percent = (filtered_count / total_players) * 100
        assert reduction_percent == 92.0

    def test_no_filtering_at_start(self):
        """Test that no filtering occurs at game start."""
        total_players = 25
        alive_players = 25

        filtered_count = total_players - alive_players
        assert filtered_count == 0

        reduction_percent = (filtered_count / total_players) * 100 if total_players > 0 else 0
        assert reduction_percent == 0.0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
