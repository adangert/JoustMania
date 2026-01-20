"""
Music Player with Real-Time Tempo Control

Phase 70: Dynamic Music System
Phase 80: Migrated from scipy to resampy for distroless compatibility

Uses resampy for real-time tempo changes without pitch shifting.
Runs audio playback in a separate process to avoid blocking the gRPC server.
"""

import asyncio
import contextlib
import glob
import io
import logging
import os
import random
import time
import wave
from multiprocessing import Manager, Process, Value
from sys import platform

import numpy as np
import resampy
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Platform-specific audio backend
if platform == "linux" or platform == "linux2":
    try:
        import alsaaudio

        HAS_ALSA = True
    except ImportError:
        HAS_ALSA = False
        logger.warning("alsaaudio not available, music playback disabled")
else:
    HAS_ALSA = False
    logger.info("Non-Linux platform, using pygame for music")


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b by t (0.0 to 1.0)."""
    return a * (1 - t) + b * t


def _linux_audio_loop(fname: dict, ratio: Value, volume: Value, stop_proc: Value):
    """
    Linux audio playback loop using ALSA with real-time resampling.

    Runs in a separate process for non-blocking playback.

    Args:
        fname: Manager dict with 'song' key containing glob pattern
        ratio: Shared Value for playback speed (1.0 = normal)
        volume: Shared Value for volume (0.0 to 1.0)
        stop_proc: Shared Value to control playback (0=play, 1=stop)
    """
    period = 1024 * 4
    period_bytes = period * 2 * 2  # Two channels, two bytes per sample

    time.sleep(0.1)  # Brief startup delay

    # Try to set higher process priority for smoother audio
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        proc.nice(-5)
    except Exception:
        pass

    song_loaded = False
    wav_data = None

    while True:
        try:
            if stop_proc.value == 1:
                # Stopped - wait for start signal
                song_loaded = False
                time.sleep(0.05)
                continue

            if fname["song"] == "":
                time.sleep(0.05)
                continue

            # Load song if not loaded
            if not song_loaded:
                try:
                    pattern = fname["song"]
                    files = glob.glob(pattern)
                    if not files:
                        logger.error(f"No files match pattern: {pattern}")
                        time.sleep(0.5)
                        continue

                    random_song = random.choice(files)
                    logger.info(f"Loading music: {random_song}")

                    segment = AudioSegment.from_file(random_song)
                    # Ensure stereo, 44100Hz, 16-bit
                    segment = segment.set_channels(2).set_frame_rate(44100).set_sample_width(2)

                    wav_data = io.BytesIO()
                    segment.export(wav_data, format="wav")
                    wav_data = wav_data.getvalue()
                    song_loaded = True
                    logger.info(f"Music loaded: {random_song} ({len(wav_data)} bytes)")
                    continue

                except Exception as e:
                    logger.error(f"Error loading music: {e}")
                    time.sleep(0.5)
                    continue

            # Play the loaded song
            if stop_proc.value == 0 and song_loaded:
                try:
                    wf = wave.open(io.BytesIO(wav_data), "rb")  # noqa: SIM115
                    if len(wf.readframes(1)) == 0:
                        logger.error("Empty WAV data")
                        song_loaded = False
                        continue
                    wf.rewind()

                    device = alsaaudio.PCM(
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        format=alsaaudio.PCM_FORMAT_S16_LE,
                        periodsize=period,
                        device="default",
                    )

                    def read_samples(wf, read_size):
                        """Generator to read audio samples."""
                        while True:
                            sample = wf.readframes(read_size)
                            if len(sample) > 0:
                                yield sample
                            else:
                                return

                    def resample_audio(samples, ratio_val, vol_val):
                        """Resample audio data for tempo change with volume using resampy."""
                        for data in samples:
                            try:
                                array = np.frombuffer(data, dtype=np.int16)

                                # Calculate output frames based on ratio
                                # ratio > 1 means faster playback = fewer output samples
                                ratio = ratio_val.value
                                if ratio <= 0.5 or ratio > 2.0:
                                    ratio = 1.0  # Safety clamp

                                num_input_frames = len(array) // 2  # Stereo
                                num_output_frames = int(num_input_frames / ratio) & (~0x1F)
                                if num_output_frames < 32:
                                    yield data
                                    continue

                                # Split stereo channels and convert to float for resampy
                                left_in = array[0::2].astype(np.float64)
                                right_in = array[1::2].astype(np.float64)

                                # Resample using resampy (audio-quality resampling)
                                # Use 'kaiser_fast' for real-time performance
                                sr_in = 44100
                                sr_out = int(44100 / ratio)
                                left = resampy.resample(left_in, sr_in, sr_out, filter="kaiser_fast")
                                right = resampy.resample(right_in, sr_in, sr_out, filter="kaiser_fast")

                                # Apply volume and convert back to int16
                                vol = vol_val.value
                                left = (left * vol).astype(np.int16)
                                right = (right * vol).astype(np.int16)

                                # Interleave channels
                                final = np.empty(len(left) * 2, dtype=np.int16)
                                final[0::2] = left
                                final[1::2] = right

                                yield final.tobytes()
                            except Exception as e:
                                logger.warning(f"Resample error: {e}")
                                yield data

                    def write_samples(device, write_size, samples):
                        """Write audio samples to device."""
                        buf = bytearray()
                        for sample in samples:
                            buf.extend(sample)
                            while len(buf) >= write_size:
                                try:
                                    device.write(bytes(buf[:write_size]))
                                except alsaaudio.ALSAAudioError as e:
                                    logger.warning(f"ALSA write error: {e}")
                                    break
                                del buf[:write_size]
                            if stop_proc.value:
                                return

                    # Play with resampling
                    write_samples(device, period_bytes, resample_audio(read_samples(wf, period), ratio, volume))

                    wf.close()
                    device.close()

                    # Song finished, will loop if not stopped
                    if stop_proc.value == 0:
                        logger.debug("Music track finished, looping")

                except Exception as e:
                    logger.error(f"Playback error: {e}")
                    time.sleep(0.5)
                    song_loaded = False

        except Exception as e:
            logger.error(f"Audio loop error: {e}")
            time.sleep(0.5)


class MusicPlayer:
    """
    Music player with real-time tempo control.

    Uses a separate process for audio playback with resampy resampling.
    """

    def __init__(self, name: str = "music"):
        """
        Initialize music player.

        Args:
            name: Player instance name for logging
        """
        self.name = name
        self._use_alsa = HAS_ALSA and (platform == "linux" or platform == "linux2")

        # Shared state for inter-process communication
        self._stop_proc = Value("i", 1)  # 1 = stopped, 0 = playing
        self._ratio = Value("d", 1.0)  # Playback speed
        self._volume = Value("d", 0.7)  # Volume level

        self._manager = Manager()
        self._fname = self._manager.dict()
        self._fname["song"] = ""

        self._process = None
        self._track_id = None
        self._transitioning = False
        self._transition_task = None

        if self._use_alsa:
            # Start audio process
            self._process = Process(
                target=_linux_audio_loop, args=(self._fname, self._ratio, self._volume, self._stop_proc), daemon=True
            )
            self._process.start()
            logger.info(f"MusicPlayer '{name}' initialized with ALSA backend")
        else:
            logger.info(f"MusicPlayer '{name}' initialized (no tempo control - using pygame fallback)")

    def load(self, file_pattern: str):
        """
        Load music file pattern.

        Args:
            file_pattern: Glob pattern for music files
        """
        self._fname["song"] = file_pattern
        logger.debug(f"Music pattern loaded: {file_pattern}")

    def start(self) -> str:
        """
        Start music playback.

        Returns:
            Track ID for this playback session
        """
        import uuid

        self._track_id = str(uuid.uuid4())
        self._stop_proc.value = 0
        logger.info(f"Music started: {self._track_id}")
        return self._track_id

    def stop(self):
        """Stop music playback."""
        self._stop_proc.value = 1
        self._fname["song"] = ""

        # Cancel any ongoing transition
        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()
        self._transitioning = False

        logger.info(f"Music stopped: {self._track_id}")
        self._track_id = None

    def set_ratio(self, ratio: float):
        """
        Set playback speed immediately.

        Args:
            ratio: Playback speed (1.0 = normal, 1.3 = 30% faster)
        """
        self._ratio.value = max(0.5, min(2.0, ratio))
        logger.debug(f"Music ratio set: {ratio}")

    def set_volume(self, volume: float):
        """
        Set playback volume.

        Args:
            volume: Volume level (0.0 to 1.0)
        """
        self._volume.value = max(0.0, min(1.0, volume))
        logger.debug(f"Music volume set: {volume}")

    async def transition_ratio(self, new_ratio: float, duration: float = 1.0):
        """
        Smoothly transition to a new playback speed.

        Args:
            new_ratio: Target playback speed
            duration: Transition duration in seconds
        """
        # Cancel any existing transition
        if self._transition_task and not self._transition_task.done():
            self._transition_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._transition_task

        async def do_transition():
            num_steps = 20
            old_ratio = self._ratio.value
            step_duration = duration / num_steps

            for i in range(num_steps):
                if self._stop_proc.value == 1:  # Stopped
                    return
                t = (i + 1) / num_steps
                ratio = lerp(old_ratio, new_ratio, t)
                self._ratio.value = ratio
                await asyncio.sleep(step_duration)

            self._ratio.value = new_ratio
            logger.info(f"Music tempo transition complete: {old_ratio:.2f} -> {new_ratio:.2f}")

        self._transition_task = asyncio.create_task(do_transition())
        return self._transition_task

    @property
    def ratio(self) -> float:
        """Current playback ratio."""
        return self._ratio.value

    @property
    def volume(self) -> float:
        """Current volume level."""
        return self._volume.value

    @property
    def is_playing(self) -> bool:
        """Whether music is currently playing."""
        return self._stop_proc.value == 0

    @property
    def track_id(self) -> str | None:
        """Current track ID."""
        return self._track_id

    def cleanup(self):
        """Clean up resources."""
        self.stop()
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        logger.info(f"MusicPlayer '{self.name}' cleaned up")


class DummyMusicPlayer:
    """Dummy music player for mock mode or when audio is unavailable."""

    def __init__(self, name: str = "dummy"):
        self.name = name
        self._ratio = 1.0
        self._volume = 0.7
        self._playing = False
        self._track_id = None

    def load(self, file_pattern: str):
        pass

    def start(self) -> str:
        import uuid

        self._track_id = str(uuid.uuid4())
        self._playing = True
        return self._track_id

    def stop(self):
        self._playing = False
        self._track_id = None

    def set_ratio(self, ratio: float):
        self._ratio = ratio

    def set_volume(self, volume: float):
        self._volume = volume

    async def transition_ratio(self, new_ratio: float, _duration: float = 1.0):
        self._ratio = new_ratio

    @property
    def ratio(self) -> float:
        return self._ratio

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def track_id(self) -> str | None:
        return self._track_id

    def cleanup(self):
        pass
