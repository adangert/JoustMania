"""
Audio Tool - Interactive music tempo testing utility.

Uses the modern MusicPlayer implementation for testing tempo transitions.
"""

import asyncio
import sys

from services.audio.music_player import MusicPlayer


async def main():
    music = MusicPlayer("test")
    music.load("services/audio/assets/Joust/music/*.wav")
    music.start()

    print("Music started. Enter a tempo ratio (0.5-2.0) or 'q' to quit:")

    loop = asyncio.get_event_loop()

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        line = line.strip()

        if line.lower() == "q":
            break

        try:
            ratio = float(line)
            if 0.5 <= ratio <= 2.0:
                await music.transition_ratio(ratio, duration=1.0)
                print(f"Tempo set to {ratio:.2f}x")
            else:
                print("Ratio must be between 0.5 and 2.0")
        except ValueError:
            print(f"Invalid value: {line}")

    music.stop()
    music.cleanup()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
