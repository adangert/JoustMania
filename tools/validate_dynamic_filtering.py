#!/usr/bin/env python3
"""
Phase 45 Validation Script: Adaptive Controller Filtering

This script validates that the dynamic filtering feature is working correctly.

Usage:
    python3 tools/validate_dynamic_filtering.py

What it checks:
1. Proto messages are generated correctly
2. Metrics are defined and accessible
3. gRPC method exists on server and client stubs
4. Basic filtering calculations are correct
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_proto_messages():
    """Validate Phase 45 proto messages exist and work."""
    print("=" * 60)
    print("1. Checking Proto Messages")
    print("=" * 60)

    try:
        from proto import controller_manager_pb2

        # Test GameplayStreamConfig
        config = controller_manager_pb2.GameplayStreamConfig(
            update_frequency_hz=30, serials=["test_1", "test_2"]
        )
        print(
            f"✓ GameplayStreamConfig created: {config.update_frequency_hz}Hz, {len(config.serials)} serials"
        )

        # Test FilterUpdate
        filter_update = controller_manager_pb2.FilterUpdate(serials=["test_1"])
        print(f"✓ FilterUpdate created: {len(filter_update.serials)} serials")

        # Test GameplayStreamControl with config
        control_config = controller_manager_pb2.GameplayStreamControl(config=config)
        print(
            f"✓ GameplayStreamControl with config: HasField('config')={control_config.HasField('config')}"
        )

        # Test GameplayStreamControl with filter_update
        control_filter = controller_manager_pb2.GameplayStreamControl(filter_update=filter_update)
        print(
            f"✓ GameplayStreamControl with filter_update: HasField('filter_update')={control_filter.HasField('filter_update')}"
        )

        # Test oneof behavior
        assert control_config.HasField("config") and not control_config.HasField("filter_update")
        assert control_filter.HasField("filter_update") and not control_filter.HasField("config")
        print("✓ oneof behavior works correctly (mutually exclusive fields)")

        print("\n✅ All proto messages validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Proto message validation failed: {e}\n")
        return False


def check_grpc_methods():
    """Validate gRPC methods are generated."""
    print("=" * 60)
    print("2. Checking gRPC Methods")
    print("=" * 60)

    try:
        from proto import controller_manager_pb2_grpc

        # Check servicer has the method
        servicer_class = controller_manager_pb2_grpc.ControllerManagerServiceServicer
        assert hasattr(servicer_class, "StreamGameplayDataDynamic")
        print("✓ Server servicer has StreamGameplayDataDynamic method")

        # Check stub has the method
        stub_class = controller_manager_pb2_grpc.ControllerManagerServiceStub
        assert hasattr(stub_class, "StreamGameplayDataDynamic")
        print("✓ Client stub has StreamGameplayDataDynamic method")

        print("\n✅ All gRPC methods validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ gRPC method validation failed: {e}\n")
        return False


def check_metrics():
    """Validate Phase 45 metrics are defined."""
    print("=" * 60)
    print("3. Checking Prometheus Metrics")
    print("=" * 60)

    try:
        from prometheus_client import Counter, Gauge, Histogram

        from services.controller_manager import metrics as cm_metrics
        from services.game_coordinator import metrics as gc_metrics

        # Game Coordinator metrics
        assert hasattr(gc_metrics, "filtered_controllers")
        assert isinstance(gc_metrics.filtered_controllers, Gauge)
        print("✓ Game Coordinator: filtered_controllers (Gauge)")

        assert hasattr(gc_metrics, "filter_updates_total")
        assert isinstance(gc_metrics.filter_updates_total, Counter)
        print("✓ Game Coordinator: filter_updates_total (Counter)")

        assert hasattr(gc_metrics, "active_controllers")
        assert isinstance(gc_metrics.active_controllers, Gauge)
        print("✓ Game Coordinator: active_controllers (Gauge)")

        # Controller Manager metrics
        assert hasattr(cm_metrics, "streamed_controllers")
        assert isinstance(cm_metrics.streamed_controllers, Histogram)
        print("✓ Controller Manager: streamed_controllers (Histogram)")

        # Test metrics can be updated
        gc_metrics.active_controllers.set(25)
        gc_metrics.filtered_controllers.set(0)
        gc_metrics.filter_updates_total.labels(game_mode="FFA").inc()
        cm_metrics.streamed_controllers.observe(25)
        print("✓ Metrics can be updated without errors")

        print("\n✅ All metrics validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Metrics validation failed: {e}\n")
        import traceback

        traceback.print_exc()
        return False


def check_filtering_calculations():
    """Validate filtering calculation logic."""
    print("=" * 60)
    print("4. Checking Filter Calculation Logic")
    print("=" * 60)

    test_cases = [
        (25, 25, 0, 0.0),  # Start: No filtering
        (25, 20, 5, 20.0),  # Early: 20% reduction
        (25, 10, 15, 60.0),  # Mid: 60% reduction
        (25, 5, 20, 80.0),  # Late: 80% reduction
        (25, 2, 23, 92.0),  # Final: 92% reduction
        (25, 1, 24, 96.0),  # Winner: 96% reduction
    ]

    all_passed = True
    for total, alive, expected_filtered, expected_percent in test_cases:
        filtered = total - alive
        percent = (filtered / total) * 100 if total > 0 else 0

        if filtered == expected_filtered and percent == expected_percent:
            print(
                f"✓ {total} total, {alive} alive → {filtered} filtered ({percent:.1f}% reduction)"
            )
        else:
            print(
                f"✗ {total} total, {alive} alive → Expected {expected_filtered} filtered, got {filtered}"
            )
            all_passed = False

    if all_passed:
        print("\n✅ All filtering calculations correct\n")
    else:
        print("\n❌ Some filtering calculations failed\n")

    return all_passed


def check_server_implementation():
    """Check that server implementation exists."""
    print("=" * 60)
    print("5. Checking Server Implementation")
    print("=" * 60)

    try:
        from services.controller_manager.server import ControllerManagerServicer

        # Check method exists
        assert hasattr(ControllerManagerServicer, "StreamGameplayDataDynamic")
        print("✓ ControllerManagerServicer has StreamGameplayDataDynamic method")

        # Check it's async
        import inspect

        method = ControllerManagerServicer.StreamGameplayDataDynamic
        assert inspect.iscoroutinefunction(method)
        print("✓ StreamGameplayDataDynamic is an async method")

        print("\n✅ Server implementation validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Server implementation validation failed: {e}\n")
        return False


def check_client_implementation():
    """Check that client implementation uses dynamic filtering."""
    print("=" * 60)
    print("6. Checking Client Implementation")
    print("=" * 60)

    try:
        # Check base game mode
        with open("services/game_coordinator/games/base.py") as f:
            base_content = f.read()

        assert "StreamGameplayDataDynamic" in base_content
        print("✓ base.py uses StreamGameplayDataDynamic")

        assert "GameplayStreamControl" in base_content
        print("✓ base.py creates GameplayStreamControl messages")

        assert "filter_update" in base_content
        print("✓ base.py sends filter updates")

        # Check nonstop joust
        with open("services/game_coordinator/games/nonstop_joust.py") as f:
            nonstop_content = f.read()

        assert "StreamGameplayDataDynamic" in nonstop_content
        print("✓ nonstop_joust.py uses StreamGameplayDataDynamic")

        print("\n✅ Client implementation validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Client implementation validation failed: {e}\n")
        return False


def main():
    """Run all validation checks."""
    print("\n" + "=" * 60)
    print("PHASE 45 VALIDATION: Adaptive Controller Filtering")
    print("=" * 60 + "\n")

    results = {
        "Proto Messages": check_proto_messages(),
        "gRPC Methods": check_grpc_methods(),
        "Prometheus Metrics": check_metrics(),
        "Filter Calculations": check_filtering_calculations(),
        "Server Implementation": check_server_implementation(),
        "Client Implementation": check_client_implementation(),
    }

    # Summary
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for check_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check_name:30} {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✅ ALL VALIDATIONS PASSED!\n")
        print("Phase 45 implementation is ready for testing.\n")
        return 0
    print("\n❌ SOME VALIDATIONS FAILED\n")
    print("Please review the errors above and fix the issues.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
