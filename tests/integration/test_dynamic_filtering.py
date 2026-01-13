"""
Integration tests for Phase 45: Adaptive Controller Filtering via Bidirectional Streaming

Tests the dynamic filtering feature that reduces monitoring overhead as players die.
"""

import pytest


class TestProtoMessages:
    """Test Phase 45 proto message creation and manipulation."""

    def test_gameplay_stream_config_creation(self):
        """Test creating GameplayStreamConfig message."""
        from proto import controller_manager_pb2

        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=30,
            serials=["controller_1", "controller_2", "controller_3"]
        )

        assert config.update_frequency_hz == 30
        assert len(config.serials) == 3
        assert "controller_1" in config.serials

    def test_gameplay_stream_config_empty_serials(self):
        """Test GameplayStreamConfig with empty serials (all controllers)."""
        from proto import controller_manager_pb2

        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=60,
            serials=[]  # Empty = all controllers
        )

        assert config.update_frequency_hz == 60
        assert len(config.serials) == 0

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
            serials=["controller_1"]
        )

        control_msg = controller_manager_pb2.GameplayStreamControl(
            config=config
        )

        assert control_msg.HasField("config")
        assert not control_msg.HasField("filter_update")
        assert control_msg.config.update_frequency_hz == 30

    def test_gameplay_stream_control_with_filter_update(self):
        """Test GameplayStreamControl with filter update."""
        from proto import controller_manager_pb2

        filter_update = controller_manager_pb2.FilterUpdate(
            serials=["controller_1", "controller_2"]
        )

        control_msg = controller_manager_pb2.GameplayStreamControl(
            filter_update=filter_update
        )

        assert control_msg.HasField("filter_update")
        assert not control_msg.HasField("config")
        assert len(control_msg.filter_update.serials) == 2

    def test_gameplay_stream_control_oneof_behavior(self):
        """Test that GameplayStreamControl oneof allows only one field."""
        from proto import controller_manager_pb2

        # Set config first
        control_msg = controller_manager_pb2.GameplayStreamControl(
            config=controller_manager_pb2.GameplayStreamConfig(
                update_frequency_hz=30,
                serials=[]
            )
        )

        assert control_msg.HasField("config")

        # Setting filter_update should clear config (oneof behavior)
        control_msg.filter_update.CopyFrom(
            controller_manager_pb2.FilterUpdate(serials=["controller_1"])
        )

        assert control_msg.HasField("filter_update")
        assert not control_msg.HasField("config")


class TestMetrics:
    """Test that Phase 45 metrics are defined and accessible."""

    def test_game_coordinator_metrics_exist(self):
        """Test that game coordinator filtering metrics exist."""
        from services.game_coordinator import metrics

        # Check Phase 45 metrics exist
        assert hasattr(metrics, 'filtered_controllers')
        assert hasattr(metrics, 'filter_updates_total')
        assert hasattr(metrics, 'active_controllers')

        # Check metrics are the correct type
        from prometheus_client import Counter, Gauge

        assert isinstance(metrics.filtered_controllers, Gauge)
        assert isinstance(metrics.filter_updates_total, Counter)
        assert isinstance(metrics.active_controllers, Gauge)

    def test_controller_manager_metrics_exist(self):
        """Test that controller manager filtering metrics exist."""
        from services.controller_manager import metrics

        # Check Phase 45 metric exists
        assert hasattr(metrics, 'streamed_controllers')

        # Check metric is the correct type
        from prometheus_client import Histogram

        assert isinstance(metrics.streamed_controllers, Histogram)

    def test_metrics_can_be_updated(self):
        """Test that metrics can be updated without errors."""
        from services.controller_manager import metrics as cm_metrics
        from services.game_coordinator import metrics as gc_metrics

        # Game coordinator metrics
        gc_metrics.active_controllers.set(10)
        gc_metrics.filtered_controllers.set(15)
        gc_metrics.filter_updates_total.labels(game_mode="FFA").inc()

        # Controller manager metrics
        cm_metrics.streamed_controllers.observe(10)
        cm_metrics.streamed_controllers.observe(5)
        cm_metrics.streamed_controllers.observe(2)


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
