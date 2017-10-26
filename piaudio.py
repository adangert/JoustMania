import asyncio
import wave
import functools
import io
import numpy
import psutil, os
import time
import scipy.signal as signal
from multiprocessing import Value
from threading import Thread
import pygame
import alsaaudio
import threading
from pydub import AudioSegment

import common

def audio_loop(wav_data, ratio, stop_proc):
    # TODO: As a future improvment, we could precompute resampled versions of the track
    # at the "steady" playback rates, and only do dynamic resampling when transitioning
    # between them.

    PERIOD=1024 * 4
    # Two channels, two bytes per sample.
    PERIOD_BYTES = PERIOD * 2 * 2

    time.sleep(0.5)
    proc = psutil.Process(os.getpid())
    proc.nice(-5)
    time.sleep(0.02)

    device = alsaaudio.PCM()
    wf = wave.open(io.BytesIO(wav_data), 'rb')
    device.setchannels(wf.getnchannels())

    device.setformat(alsaaudio.PCM_FORMAT_S16_LE)
    device.setperiodsize(PERIOD)
        
    if len(wf.readframes(1)) == 0:
        raise ValueError("Empty WAV file played.")
    wf.rewind()
    device.setrate(wf.getframerate())

    # Loops samples of up to read_size bytes from the wav file.
    def ReadSamples(wf, read_size):
        while True:
            sample = wf.readframes(read_size)
            if len(sample) > 0:
                yield sample
            else:
                wf.rewind()

    # Writes incoming samples in chunks of write_size to device.
    # Quits when stop_proc is set to a non-zero value.
    def WriteSamples(device, write_size, samples):
        buf = bytearray()
        for sample in samples:
            buf.extend(sample)
            while len(buf) >= write_size:
                device.write(buf[:write_size])
                del buf[:write_size]
            if stop_proc.value:
                return

    # Resamples audio data at the rate given by 'ratio' above.
    def Resample(samples):
        for data in samples:
            array = numpy.fromstring(data, dtype=numpy.int16)
            # Split data into seperate channels and resample. Divide by two
            # since there are two channels. We round to the nearest multiple of
            # 32 as the resampling is more efficient the closer the sizes are to
            # being powers of two.
            num_output_frames = int(array.size / (ratio.value * 2)) & (~0x1f)
            reshapel = signal.resample(array[0::2], num_output_frames)
            reshaper = signal.resample(array[1::2], num_output_frames)

            final = numpy.ones((num_output_frames,2))
            final[:, 0] = reshapel
            final[:, 1] = reshaper

            out_data = final.flatten().astype(numpy.int16).tostring()
            yield out_data

    WriteSamples(device, PERIOD_BYTES, Resample(ReadSamples(wf, PERIOD)))

    wf.close()
    device.close()

@functools.lru_cache(maxsize=128)
class Audio:
    def __init__(self, fname):
        segment = AudioSegment.from_file(fname)
        buf = io.BytesIO()
        segment.export(buf, 'wav')
        buf.seek(0)
        self.sample_ = pygame.mixer.Sound(file=buf)
        self.fname_ = fname
  
    #this will not work for files other than wav at the moment
    def start_effect(self):
        self.sample_.play()

    def stop_effect(self):
        self.sample_.stop()

    def start_effect_music(self):
        self.sample_.play(-1)

    def stop_effect_music(self):
        self.sample_.stop()
            
    def get_length_secs(self):
        return self.sample_.get_length()

    def start_effect_and_wait(self):
        self.start_effect()
        time.sleep(self.get_length_secs())

@functools.lru_cache(maxsize=16)
class Music:
    def __init__(self, fname):
        self.load_thread_ = threading.Thread(target=lambda: self.load_sample_(fname))
        self.load_thread_.start()
        self.transition_future_ = asyncio.Future()

    def wait_for_sample_(self):
        if self.load_thread_:
            self.load_thread_.join()
            self.load_thread_ = None

    def load_sample_(self, fname):
        try:
          segment = AudioSegment.from_file(fname)
        except:
          print("error can not convert "+fname+" to wav")
          print("trying to play classical.wav instead")
          segment = AudioSegment.from_wav("audio/Joust/music/classical.wav")

        self.fname_ = fname
        wav_data = io.BytesIO()
        segment.export(wav_data, 'wav')
        self.wav_data_ = wav_data.getbuffer()

    def start_audio_loop(self):
        self.wait_for_sample_()
        print ('audio file is ' + str(self.fname_))
        # Start audio in seperate process to be non-blocking
        self.stop_proc = Value('i', 0)
        self.ratio = Value('d' , 1.0)

        self.t = Thread(target=audio_loop, args=(self.wav_data_, self.ratio, self.stop_proc))
        self.t.start()

    def stop_audio(self):
        self.stop_proc.value = 1
        time.sleep(0.1)
        self.t.join()
        self.transition_future_.cancel()

    def change_ratio(self, ratio):
        self.ratio.value = ratio

    def transition_ratio(self, new_ratio, transition_duration=1.0):
        """Smoothly transitions between the current sampling ratio and the given one.
           Returns a task that completes once the transition is finished."""
        async def do_transition():
            num_steps = 20
            old_ratio = self.ratio.value
            for i in range(num_steps):
                t = (i+1) / 20
                ratio = common.lerp(old_ratio, new_ratio, t)
                ratio = old_ratio * (1-t) + new_ratio * t
                self.change_ratio(ratio)
                await asyncio.sleep(transition_duration / num_steps)

        self.transition_future_.cancel()
        self.transition_future_ = asyncio.ensure_future(do_transition())
        return self.transition_future_

class DummyMusic:
    def start_audio_loop(self): pass
    def stop_audio(self): pass
    def change_ratio(self): pass
    def transition_ratio(self, new_ratio, transition_duration=None):
        async def do_nothing(): pass
        return asyncio.ensure_future(do_nothing())

def InitAudio():
    pygame.mixer.init(47000, -16, 2 , 4096)
