#!/usr/bin/env python3
"""
Phase 46 Validation Script: Stream-Based Controller Feedback

This script validates that the stream-based feedback feature is working correctly.

Usage:
    python3 tools/validate_stream_feedback.py

What it checks:
1. Proto messages are generated correctly
2. Metrics are defined and accessible
3. Server internal methods exist
4. Client stream handling is implemented
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_proto_messages():
    """Validate Phase 46 proto messages exist and work."""
    print("=" * 60)
    print("1. Checking Proto Messages")
    print("=" * 60)

    try:
        from proto import controller_manager_pb2

        # Test ColorCommand
        color_cmd = controller_manager_pb2.ColorCommand(
            serial="test_1",
            color=controller_manager_pb2.RGB(r=255, g=0, b=0)
        )
        print(f"✓ ColorCommand created: serial={color_cmd.serial}, color=RGB({color_cmd.color.r},{color_cmd.color.g},{color_cmd.color.b})")

        # Test EffectCommand
        effect_cmd = controller_manager_pb2.EffectCommand(
            serial="test_1",
            effect=controller_manager_pb2.EFFECT_FLASH,
            color=controller_manager_pb2.RGB(r=0, g=255, b=0),
            duration_ms=1000
        )
        print(f"✓ EffectCommand created: serial={effect_cmd.serial}, effect={effect_cmd.effect}, duration={effect_cmd.duration_ms}ms")

        # Test VibrationCommand
        vib_cmd = controller_manager_pb2.VibrationCommand(
            serial="test_1",
            intensity=200,
            duration_ms=500
        )
        print(f"✓ VibrationCommand created: serial={vib_cmd.serial}, intensity={vib_cmd.intensity}, duration={vib_cmd.duration_ms}ms")

        # Test GameplayStreamControl with ColorCommand
        control_color = controller_manager_pb2.GameplayStreamControl(color_command=color_cmd)
        print(f"✓ GameplayStreamControl with color_command: HasField={control_color.HasField('color_command')}")

        # Test GameplayStreamControl with EffectCommand
        control_effect = controller_manager_pb2.GameplayStreamControl(effect_command=effect_cmd)
        print(f"✓ GameplayStreamControl with effect_command: HasField={control_effect.HasField('effect_command')}")

        # Test GameplayStreamControl with VibrationCommand
        control_vib = controller_manager_pb2.GameplayStreamControl(vibration_command=vib_cmd)
        print(f"✓ GameplayStreamControl with vibration_command: HasField={control_vib.HasField('vibration_command')}")

        # Test oneof behavior
        control_msg = controller_manager_pb2.GameplayStreamControl(
            config=controller_manager_pb2.GameplayStreamConfig(
                update_frequency_hz=30,
                serials=[]
            )
        )
        assert control_msg.HasField('config')

        # Setting color_command should clear config (oneof)
        control_msg.color_command.CopyFrom(color_cmd)
        assert control_msg.HasField('color_command')
        assert not control_msg.HasField('config')
        print("✓ oneof behavior works correctly (only one field active)")

        print("\n✅ All proto messages validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Proto message validation failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_metrics():
    """Validate Phase 46 metrics are defined."""
    print("=" * 60)
    print("2. Checking Prometheus Metrics")
    print("=" * 60)

    try:
        from services.controller_manager import metrics
        from prometheus_client import Counter

        # Phase 46 metric
        assert hasattr(metrics, 'stream_commands_total')
        assert isinstance(metrics.stream_commands_total, Counter)
        print("✓ Controller Manager: stream_commands_total (Counter)")

        # Test metric can be updated
        metrics.stream_commands_total.labels(command_type='color').inc()
        metrics.stream_commands_total.labels(command_type='effect').inc()
        metrics.stream_commands_total.labels(command_type='vibration').inc()
        print("✓ stream_commands_total metric can be updated without errors")

        print("\n✅ All metrics validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Metrics validation failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_server_implementation():
    """Check that server internal methods exist."""
    print("=" * 60)
    print("3. Checking Server Internal Methods")
    print("=" * 60)

    try:
        from services.controller_manager.server import ControllerManagerServicer
        import inspect

        # Check _set_controller_color_internal exists and is async
        assert hasattr(ControllerManagerServicer, '_set_controller_color_internal')
        method = getattr(ControllerManagerServicer, '_set_controller_color_internal')
        assert inspect.iscoroutinefunction(method)
        print("✓ _set_controller_color_internal method exists and is async")

        # Check _play_effect_internal exists and is async
        assert hasattr(ControllerManagerServicer, '_play_effect_internal')
        method = getattr(ControllerManagerServicer, '_play_effect_internal')
        assert inspect.iscoroutinefunction(method)
        print("✓ _play_effect_internal method exists and is async")

        # Check _set_vibration_internal exists and is async
        assert hasattr(ControllerManagerServicer, '_set_vibration_internal')
        method = getattr(ControllerManagerServicer, '_set_vibration_internal')
        assert inspect.iscoroutinefunction(method)
        print("✓ _set_vibration_internal method exists and is async")

        print("\n✅ Server internal methods validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Server internal methods validation failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_client_implementation():
    """Check that client uses stream-based feedback commands."""
    print("=" * 60)
    print("4. Checking Client Implementation")
    print("=" * 60)

    try:
        # Check base game mode
        with open('services/game_coordinator/games/base.py', 'r') as f:
            base_content = f.read()

        assert 'self.gameplay_stream' in base_content
        print("✓ base.py uses self.gameplay_stream")

        assert 'color_command' in base_content
        print("✓ base.py creates ColorCommand messages")

        assert 'vibration_command' in base_content
        print("✓ base.py creates VibrationCommand messages")

        assert 'if self.gameplay_stream:' in base_content
        print("✓ base.py checks for active stream before sending commands")

        # Check nonstop joust
        with open('services/game_coordinator/games/nonstop_joust.py', 'r') as f:
            nonstop_content = f.read()

        assert 'self.gameplay_stream' in nonstop_content
        print("✓ nonstop_joust.py uses self.gameplay_stream")

        print("\n✅ Client implementation validated successfully\n")
        return True

    except Exception as e:
        print(f"\n❌ Client implementation validation failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all validation checks."""
    print("\n" + "=" * 60)
    print("PHASE 46 VALIDATION: Stream-Based Controller Feedback")
    print("=" * 60 + "\n")

    results = {
        "Proto Messages": check_proto_messages(),
        "Prometheus Metrics": check_metrics(),
        "Server Internal Methods": check_server_implementation(),
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
        print("Phase 46 implementation is ready for testing.\n")
        return 0
    else:
        print("\n❌ SOME VALIDATIONS FAILED\n")
        print("Please review the errors above and fix the issues.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
