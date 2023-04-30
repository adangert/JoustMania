#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: t; c-basic-offset: 4; tab-width: 4 -*-

# Simple test script that plays (some) wav files

from __future__ import print_function

import sys
import wave
import getopt
import alsaaudio

def play(device, f):	

	format = alsaaudio.PCM_FORMAT_S16_LE

	# 8bit is unsigned in wav files
	# if f.getsampwidth() == 1:
		# format = alsaaudio.PCM_FORMAT_U8
	# # Otherwise we assume signed data, little endian
	# elif f.getsampwidth() == 2:
		# format = alsaaudio.PCM_FORMAT_S16_LE
	# elif f.getsampwidth() == 3:
		# format = alsaaudio.PCM_FORMAT_S24_3LE
	# elif f.getsampwidth() == 4:
		# format = alsaaudio.PCM_FORMAT_S32_LE
	# else:
		# raise ValueError('Unsupported format')

	# periodsize = f.getframerate() // 8
	periodsize = 1024 * 2

	print('%d channels, %d sampling rate, format %d, periodsize %d\n' % (f.getnchannels(),
																		 f.getframerate(),
																		 format,
																		 periodsize))

	device = alsaaudio.PCM(channels=2, rate=f.getframerate(), format=format, periodsize=periodsize, device=device)
	
	data = ReadSamples(f,periodsize)
	while data:
		# Read data from stdin
		WriteSamples(device,periodsize,data)
		# device.write(data)
		data = ReadSamples(f,periodsize)
		# data = f.readframes(periodsize)
		                # Loops samples of up to read_size bytes from the wav file.
		                
# Writes incoming samples in chunks of write_size to device.
# Quits when stop_proc is set to a non-zero value.
def WriteSamples(device, write_size, samples):
	buf = bytearray()
	for sample in samples:
		buf.extend(sample)
		while len(buf) >= write_size:
			try:
				device.write(buf[:write_size])
			except alsaaudio.ALSAAudioError as e:
				print("Error writing to ALSA device: {}".format(e))
				break
			del buf[:write_size]            
		                
def ReadSamples(wf, read_size):
	while True:
		sample = wf.readframes(read_size)
		if len(sample) > 0:
			yield sample
		else:
			return


def usage():
	print('usage: playwav.py [-d <device>] <file>', file=sys.stderr)
	sys.exit(2)

if __name__ == '__main__':

	device = 'default'

	opts, args = getopt.getopt(sys.argv[1:], 'd:')
	for o, a in opts:
		if o == '-d':
			device = a

	if not args:
		usage()
		
	with wave.open(args[0], 'rb') as f:
		play(device, f)
