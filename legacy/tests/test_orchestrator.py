"""
Test script for JoustMania gRPC Orchestrator

Tests the orchestrator with Settings gRPC service.

Usage:
1. Start Settings service: python services/settings/server.py
2. Run this test: python test_orchestrator.py
"""

import logging
import time

from piparty_grpc import JoustManiaOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_orchestrator():
    """Test orchestrator with Settings service."""
    logger.info("=" * 60)
    logger.info("Testing JoustMania gRPC Orchestrator")
    logger.info("=" * 60)

    # Create orchestrator
    orchestrator = JoustManiaOrchestrator(services_host="localhost")

    try:
        # Start orchestrator
        logger.info("\n1. Starting orchestrator...")
        orchestrator.start()
        logger.info("✅ Orchestrator started")

        # Check initial settings
        logger.info("\n2. Checking initial settings...")
        sensitivity = orchestrator.get_setting("sensitivity")
        current_game = orchestrator.get_setting("current_game")
        logger.info(f"✅ sensitivity = {sensitivity}")
        logger.info(f"✅ current_game = {current_game}")

        # Update a setting
        logger.info("\n3. Updating setting...")
        orchestrator.update_setting("sensitivity", 4, source="test")
        time.sleep(0.5)  # Wait for change event
        new_sensitivity = orchestrator.get_setting("sensitivity")
        logger.info(f"✅ Updated sensitivity = {new_sensitivity}")

        # Update another setting
        logger.info("\n4. Updating another setting...")
        orchestrator.update_setting("current_game", "Werewolf", source="test")
        time.sleep(0.5)
        new_game = orchestrator.get_setting("current_game")
        logger.info(f"✅ Updated current_game = {new_game}")

        # Wait a bit to see subscription events
        logger.info("\n5. Waiting for subscription events...")
        time.sleep(2.0)

        # Display all settings
        logger.info("\n6. All settings:")
        for key, value in sorted(orchestrator.ns.settings.items()):
            logger.info(f"  {key}: {value}")

        logger.info("\n" + "=" * 60)
        logger.info("✅ All tests passed!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}", exc_info=True)
        return 1

    finally:
        # Stop orchestrator
        logger.info("\n7. Stopping orchestrator...")
        orchestrator.stop()
        logger.info("✅ Orchestrator stopped")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(test_orchestrator())
