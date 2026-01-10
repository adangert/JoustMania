#!/usr/bin/env python3
"""
Test script for ControllerManager process integration.

This script tests:
1. Starting the ControllerManager process
2. Sending IPC commands
3. Receiving responses
4. Graceful shutdown

Run this to verify the ControllerManager integration works
before testing with real Move controllers.
"""

import time
import logging
from multiprocessing import Queue, Value, Manager
import controller_manager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_controller_manager():
    """Test ControllerManager process lifecycle and IPC."""

    logger.info("=== Starting ControllerManager Integration Test ===")

    # Create shared values (same as Menu does)
    manager = Manager()
    ns = manager.Namespace()
    ns.settings = {'sensitivity': 2}

    menu_flag = Value('i', 1)  # Menu mode
    restart_flag = Value('i', 0)
    dead_count = Value('i', 0)
    music_speed = Value('d', 0.0)
    show_battery = Value('i', 0)
    show_team_colors = Value('i', 0)
    red_on_kill = Value('i', 0)
    revive = Value('b', False)
    controller_game_mode = Value('i', 1)

    # Create IPC queues
    command_queue = Queue()
    response_queue = Queue()

    # Start ControllerManager process
    logger.info("Starting ControllerManager process...")
    controller_manager_proc = controller_manager.ControllerManagerProcess(
        command_queue=command_queue,
        response_queue=response_queue,
        menu_flag=menu_flag,
        restart_flag=restart_flag,
        dead_count=dead_count,
        music_speed=music_speed,
        show_battery=show_battery,
        show_team_colors=show_team_colors,
        red_on_kill=red_on_kill,
        revive=revive,
        controller_game_mode=controller_game_mode,
        ns=ns,
        use_state_based_tracking=True
    )
    controller_manager_proc.start()
    logger.info(f"✓ ControllerManager process started (PID: {controller_manager_proc.pid})")

    # Give it a moment to initialize
    time.sleep(0.5)

    # Test 1: Get controller count
    logger.info("\n--- Test 1: Get controller count ---")
    response = controller_manager.send_command(
        command_queue, response_queue, 'get_controller_count', timeout=2.0
    )
    if response['status'] == 'success':
        count = response['data']['count']
        logger.info(f"✓ Controller count: {count}")
    else:
        logger.error(f"✗ Failed to get controller count: {response.get('error')}")

    # Test 2: Get ready controllers
    logger.info("\n--- Test 2: Get ready controllers ---")
    response = controller_manager.send_command(
        command_queue, response_queue, 'get_ready_controllers',
        params={'force_all': False}, timeout=2.0
    )
    if response['status'] == 'success':
        controllers = response['data']['controllers']
        logger.info(f"✓ Ready controllers: {controllers}")
    else:
        logger.error(f"✗ Failed to get ready controllers: {response.get('error')}")

    # Test 3: Get game controllers
    logger.info("\n--- Test 3: Get game controllers ---")
    response = controller_manager.send_command(
        command_queue, response_queue, 'get_game_controllers', timeout=2.0
    )
    if response['status'] == 'success':
        controllers = response['data']['controllers']
        logger.info(f"✓ Game controllers: {controllers}")
    else:
        logger.error(f"✗ Failed to get game controllers: {response.get('error')}")

    # Test 4: Reset state
    logger.info("\n--- Test 4: Reset controller state ---")
    response = controller_manager.send_command(
        command_queue, response_queue, 'reset_state', timeout=2.0
    )
    if response['status'] == 'success':
        reset_count = response['data']['reset_count']
        logger.info(f"✓ Reset {reset_count} controllers")
    else:
        logger.error(f"✗ Failed to reset state: {response.get('error')}")

    # Test 5: Shutdown
    logger.info("\n--- Test 5: Graceful shutdown ---")
    response = controller_manager.send_command(
        command_queue, response_queue, 'shutdown', timeout=2.0
    )
    if response['status'] == 'success':
        logger.info("✓ Shutdown command acknowledged")
    else:
        logger.error(f"✗ Shutdown failed: {response.get('error')}")

    # Wait for process to finish
    logger.info("Waiting for ControllerManager process to terminate...")
    controller_manager_proc.join(timeout=3.0)

    if not controller_manager_proc.is_alive():
        logger.info("✓ ControllerManager process terminated gracefully")
    else:
        logger.warning("✗ ControllerManager process didn't terminate, forcing...")
        controller_manager_proc.terminate()
        controller_manager_proc.join()
        logger.info("✓ ControllerManager process terminated forcefully")

    logger.info("\n=== ControllerManager Integration Test Complete ===")
    logger.info("All basic IPC operations working correctly!")


if __name__ == '__main__':
    try:
        test_controller_manager()
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"\nTest failed with error: {e}", exc_info=True)
