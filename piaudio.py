import pyaudio
import wave
import numpy
import psutil, os
import time
from multiprocessing import Process, Value, Lock



def audio_loop(file, ratio, end, fast_resample=True):

    proc = psutil.Process(os.getpid())
    proc.nice(-5)
    while True:
        chunk = 2048
        wf = wave.open(file, 'rb')
        data = wf.readframes(chunk)
        p = pyaudio.PyAudio()
        stream = p.open(
            format = p.get_format_from_width(wf.getsampwidth()), 
            channels = wf.getnchannels(),
            rate = wf.getframerate(),
            output = True,
            frames_per_buffer = chunk)
        while data != '':
            #need to try locking here for multiprocessing
            #array = numpy.fromstring(data, dtype=numpy.int16)
            stream.write(data)
            data = wf.readframes(chunk)
        
        stream.close()
        p.terminate()

        if end:
            break



# Start audio in seperate process to be non-blocking
class Audio:
    def __init__(self, file, fast_resample, end=False,):
        self.chunk = 2048
        self.file = file
        self.ratio = Value('d' , 1.0)
    	self.p = Process(target=audio_loop, args=(self.file,
                                                  self.ratio,
                                                  end,
                                                  fast_resample))

    def start_audio_loop(self):
        self.p.start()


    def change_ratio(self, ratio):
        self.ratio.value = ratio
          
