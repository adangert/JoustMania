import wave
import numpy
import psutil, os
import time
import scipy.signal as signal
from multiprocessing import Process, Value, Lock, Manager
import pygame
import alsaaudio
from pydub import AudioSegment


def audio_loop(file,  ratio, end, chunk_size, stop_proc):
    time.sleep(0.5)
    proc = psutil.Process(os.getpid())
    proc.nice(-5)
    time.sleep(0.02)
    print ('audio file is ' + str(file))
    
    while True:

        device = alsaaudio.PCM()
        wf = wave.open(file, 'rb')
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

        
        if end or stop_proc.value == 1:
            break
    wf.close()
    device.close()


#convert between any supported file type and wav
def convert_audio(file, return_dict):
    filename, file_extension = os.path.splitext(file)
    try:
        song = AudioSegment.from_file(file,file_extension[1:])
        song.export(filename+".wav", format="wav")
        return_dict["filename"] = filename+".wav"
    except Exception:
        print("error can not convert "+file+" to wav")
        print("trying to play classical.wav instead")
        return_dict["filename"] = "audio/Joust/music/classical.wav"

# Start audio in seperate process to be non-blocking
class Audio:
    def __init__(self, file, end=False, musicexists=True):
        self.musicexists = musicexists
        if self.musicexists:
            self.counter = 1
            self.stop_proc = Value('i', 0)
            self.chunk = 2048
            self.manager = Manager()
            self.return_dict = self.manager.dict()
            self.input_file = file
            self.delete_file = False
            self.can_play = False
            
            filename, file_extension = os.path.splitext(self.input_file)
            if (file_extension.lower() != '.wav'):
                print('now converting '+self.input_file+' to wav')
                self.delete_file = True
                self.convert_p = Process(target=convert_audio, args=(self.input_file, self.return_dict))
                self.convert_p.start()
            else:
                self.can_play = True
                self.file = self.input_file
            self.ratio = Value('d' , 1.0)
            self.chunk_size = Value('i', int(2048/2))
            self.end = end
            #pygame.mixer.init(44100, -16, 2 , 2048)
            pygame.mixer.init(47000, -16, 2 , 4096)
  
    def start_audio_loop(self):
        if self.musicexists:
            if(not self.can_play):
                self.convert_p.join()
                self.can_play = True
                self.file = self.return_dict["filename"]
            self.p = Process(target=audio_loop, args=(self.file, self.ratio, self.end, self.chunk_size, self.stop_proc))
            self.p.start()
        
    def stop_audio(self):
        if self.musicexists:
            self.stop_proc.value = 1
            time.sleep(0.1)
            self.p.terminate()
            self.p.join()
            if self.delete_file and self.file != "audio/Joust/music/classical.wav":
                os.remove(self.file)

    def change_ratio(self, ratio):
        if self.musicexists:
            self.ratio.value = ratio

    def change_chunk_size(self, increase):
        if self.musicexists:
            if increase:
                self.chunk_size.value = int(2048/4)
            else:
                self.chunk_size.value = int(2048/2)

    #this will not work for files other than wav at the moment
    def start_effect(self):
        if self.musicexists:
            self.effect = pygame.mixer.Sound(self.file)
            self.effect.play()

    def stop_effect(self):
        if self.musicexists:
            self.effect.stop()

    def start_effect_music(self):
        if self.musicexists:
            if(not self.can_play):
                self.convert_p.join()
                self.can_play = True
                self.file = self.return_dict["filename"]
            pygame.mixer.music.load(self.file)
            pygame.mixer.music.play()

    def stop_effect_music(self):
        if self.musicexists:
            pygame.mixer.music.fadeout(1)
            if self.delete_file and self.file != "audio/Joust/music/classical.wav":
                os.remove(self.file)
            
        
          
