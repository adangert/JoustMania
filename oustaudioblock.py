import pyaudio
import wave
import numpy
import scikits.samplerate
from multiprocessing import Process, Value


def audio_loop(file, ratio):
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
            array = numpy.fromstring(data, dtype=numpy.int16)
            data = scikits.samplerate.resample(array, ratio.value, "sinc_fastest").astype(numpy.int16).tostring()

            stream.write(data)
            data = wf.readframes(chunk)

        stream.close()
        p.terminate()


# Start audio in seperate process to be non-blocking
class Oustaudioblock:
    def __init__(self):
        self.chunk = 2048

    def load_audio(self, file):
        self.file = file

    def start_audio(self):
	self.ratio = Value('d' , 1.0)
    	self.p = Process(target=audio_loop, args=(self.file, self.ratio))
        self.p.start()

    def stop_audio(self):
        self.p.terminate()

    def change_ratio(self, ratio):
        self.ratio.value = ratio
          