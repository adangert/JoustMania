"""
Simulate a full game using mock controllers.

Usage:
    python scripts/testing/simulate_game.py --mode FFA --controllers 4 --duration 30
"""

import asyncio
import argparse
import sys
import os
import random
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import grpc
from services.controller_manager import controller_manager_mock_pb2, controller_manager_mock_pb2_grpc
from services.game_coordinator import game_coordinator_pb2, game_coordinator_pb2_grpc


async def simulate_ffa_game(num_controllers: int, duration: int, host: str = 'localhost'):
    """Simulate an FFA game with random deaths."""

    # Connect to services
    mock_channel = grpc.aio.insecure_channel(f'{host}:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    game_channel = grpc.aio.insecure_channel(f'{host}:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    print(f"🎮 Starting FFA game simulation with {num_controllers} controllers")

    # Start game
    game_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="FFA")
    )

    if not game_response.success:
        print(f"❌ Failed to start game: {game_response.error}")
        await mock_channel.close()
        await game_channel.close()
        return

    print(f"✅ Game started: {game_response.game_id}")

    # Simulate game duration
    start_time = time.time()
    alive_controllers = list(range(num_controllers))

    try:
        while time.time() - start_time < duration and len(alive_controllers) > 1:
            # Random controller has movement
            if random.random() < 0.1:  # 10% chance per tick
                controller_idx = random.choice(alive_controllers)
                serial = f"mock_controller_{controller_idx}"

                # Small movement (warning)
                await mock_client.SimulateMovement(
                    controller_manager_mock_pb2.MovementRequest(
                        serial=serial,
                        accel_x=random.uniform(1.0, 1.8),
                        accel_y=random.uniform(0.5, 1.0),
                        accel_z=random.uniform(0.8, 1.2)
                    )
                )
                print(f"⚠️  Controller {controller_idx} moved (warning)")

            # Random death
            if random.random() < 0.05 and len(alive_controllers) > 1:  # 5% chance
                controller_idx = random.choice(alive_controllers)
                serial = f"mock_controller_{controller_idx}"

                response = await mock_client.SimulateDeath(
                    controller_manager_mock_pb2.DeathRequest(serial=serial)
                )

                if response.success:
                    alive_controllers.remove(controller_idx)
                    print(f"💀 Controller {controller_idx} died! (accel: {response.accel_magnitude:.2f})")
                    print(f"   {len(alive_controllers)} controllers remaining")

            await asyncio.sleep(0.1)

        # End game
        winner = alive_controllers[0] if alive_controllers else None
        print(f"🏁 Game ending. Winner: Controller {winner}" if winner is not None else "🏁 Game ending. No winner")

        await game_client.ForceEndGame(
            game_coordinator_pb2.ForceEndGameRequest()
        )

        print(f"✅ Game simulation complete")

    finally:
        await mock_channel.close()
        await game_channel.close()


async def simulate_teams_game(num_controllers: int, num_teams: int, duration: int, host: str = 'localhost'):
    """Simulate a Teams game with random deaths."""

    # Connect to services
    mock_channel = grpc.aio.insecure_channel(f'{host}:50062')
    mock_client = controller_manager_mock_pb2_grpc.MockControllerServiceStub(mock_channel)

    game_channel = grpc.aio.insecure_channel(f'{host}:50053')
    game_client = game_coordinator_pb2_grpc.GameCoordinatorServiceStub(game_channel)

    print(f"🎮 Starting Teams game simulation with {num_controllers} controllers, {num_teams} teams")

    # Start game
    game_response = await game_client.StartGame(
        game_coordinator_pb2.StartGameRequest(mode="Teams")
    )

    if not game_response.success:
        print(f"❌ Failed to start game: {game_response.error}")
        await mock_channel.close()
        await game_channel.close()
        return

    print(f"✅ Game started: {game_response.game_id}")

    # Simulate game duration
    start_time = time.time()
    alive_controllers = list(range(num_controllers))

    try:
        while time.time() - start_time < duration and len(alive_controllers) > 1:
            # Random controller has movement
            if random.random() < 0.1:  # 10% chance per tick
                controller_idx = random.choice(alive_controllers)
                serial = f"mock_controller_{controller_idx}"

                # Small movement (warning)
                await mock_client.SimulateMovement(
                    controller_manager_mock_pb2.MovementRequest(
                        serial=serial,
                        accel_x=random.uniform(1.0, 1.8),
                        accel_y=random.uniform(0.5, 1.0),
                        accel_z=random.uniform(0.8, 1.2)
                    )
                )
                print(f"⚠️  Controller {controller_idx} moved (warning)")

            # Random death
            if random.random() < 0.05 and len(alive_controllers) > 1:  # 5% chance
                controller_idx = random.choice(alive_controllers)
                serial = f"mock_controller_{controller_idx}"

                response = await mock_client.SimulateDeath(
                    controller_manager_mock_pb2.DeathRequest(serial=serial)
                )

                if response.success:
                    alive_controllers.remove(controller_idx)
                    team_num = controller_idx % num_teams
                    print(f"💀 Controller {controller_idx} (Team {team_num}) died! (accel: {response.accel_magnitude:.2f})")
                    print(f"   {len(alive_controllers)} controllers remaining")

            await asyncio.sleep(0.1)

        # End game
        print(f"🏁 Game ending")

        await game_client.ForceEndGame(
            game_coordinator_pb2.ForceEndGameRequest()
        )

        print(f"✅ Game simulation complete")

    finally:
        await mock_channel.close()
        await game_channel.close()


async def main():
    parser = argparse.ArgumentParser(description='Simulate a game with mock controllers')
    parser.add_argument('--mode', default='FFA', choices=['FFA', 'Teams', 'RandomTeams'],
                       help='Game mode')
    parser.add_argument('--controllers', type=int, default=4,
                       help='Number of controllers')
    parser.add_argument('--teams', type=int, default=2,
                       help='Number of teams (for Teams mode)')
    parser.add_argument('--duration', type=int, default=30,
                       help='Game duration in seconds')
    parser.add_argument('--host', default='localhost',
                       help='Server host (default: localhost)')

    args = parser.parse_args()

    if args.mode == 'FFA':
        await simulate_ffa_game(args.controllers, args.duration, args.host)
    elif args.mode in ['Teams', 'RandomTeams']:
        await simulate_teams_game(args.controllers, args.teams, args.duration, args.host)


if __name__ == '__main__':
    asyncio.run(main())
