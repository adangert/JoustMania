import wave
import functools
import io
import numpy
import psutil, os
import time
import scipy.signal as signal
from multiprocessing import Process, Value
import pygame
import alsaaudio
import threading
from pydub import AudioSegment


def audio_loop(wav_data, ratio, chunk_size, stop_proc):
    time.sleep(0.5)
    proc = psutil.Process(os.getpid())
    proc.nice(-5)
    time.sleep(0.02)
    
    while True:
        device = alsaaudio.PCM()
        wf = wave.open(io.BytesIO(wav_data), 'rb')
        device.setchannels(wf.getnchannels())

        device.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        device.setperiodsize(320)
        
        data = wf.readframes(1024)
        device.setrate(wf.getframerate())

        time.sleep(0.03)
        data = wf.readframes(chunk_size.value)
        time.sleep(0.03)


        
        while data != '' and stop_proc.value == 0:
            #need to try locking here for multiprocessing
            array = numpy.fromstring(data, dtype=numpy.int16)
            result = numpy.reshape(array, (array.size//2, 2))
            if (array.size == 0):
                break
            #split data into seperate channels and resample
            final = numpy.ones((1024,2))
            reshapel = signal.resample(result[:, 0], 1024)

            final[:, 0] = reshapel
            reshaper = signal.resample(result[:, 1], 1024)
            final[:, 1] = reshaper
            out_data = final.flatten().astype(numpy.int16).tostring()
            #data = signal.resample(array, chunk_size.value*ratio.value)
            device.write(out_data)
            round_data = (int)(chunk_size.value*ratio.value)
            if round_data % 2 != 0:
                round_data += 1
            data = wf.readframes(round_data)

        wf.close()
        device.close()

        
        if stop_proc.value == 1:
            break
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
        self.chunk_size = Value('i', int(2048/2))

        self.p = Process(target=audio_loop, args=(self.wav_data_, self.ratio, self.chunk_size, self.stop_proc))
        self.p.start()
    def stop_audio(self):
        self.stop_proc.value = 1
        time.sleep(0.1)
        self.p.terminate()
    def change_ratio(self, ratio):
        self.ratio.value = ratio
    def change_chunk_size(self, increase):
        if increase:
            self.chunk_size.value = int(2048/4)
        else:
            self.chunk_size.value = int(2048/2)

class DummyMusic:
    def start_audio_loop(self): pass
    def stop_audio(self): pass
    def change_ratio(self): pass
    def change_chunk_size(self): pass

def InitAudio():
  pygame.mixer.init(47000, -16, 2 , 4096)
