#!/home/pi/JoustMania/venv/bin/python3.6
import asyncio
import sys

import piaudio


def Main():
    music = piaudio.Music('audio/Joust/music/classical.wav')
    music.start_audio_loop()

    loop = asyncio.get_event_loop()
    print("Enter a FP number:")
    async def ProcessInput():
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            try:
                ratio = float(line)
            except ValueError:
                print("invalid value: %s" % line)
            await music.transition_ratio(ratio)
            print("OK.")
            
    loop.run_until_complete(ProcessInput())
    music.stop_audio()


if __name__ == '__main__':
    Main()
