import psmove
import colorsys
import time
from math import sqrt

def hsv2rgb(h, s, v):
    return tuple(int(color * 255) for color in colorsys.hsv_to_rgb(h, s, v))

moves = [psmove.PSMove(x) for x in range(psmove.count_connected())]

rgbwheel = [
'FF0000',
'FF8000',
'FFFF00',
'80FF00',
'00FF00',
'00FF80',
'00FFFF',
'0080FF',
'0000FF',
'8000FF',
'FF00FF',
'FF0080']

rbywheel = [
'FE2712',
'FC600A',
'FB9902',
'FCCC1A',
'FEFE33',
'B2D732',
'66B032',
'347C98',
'0247FE',
'4424D6',
'8601AF',
'C21460']

rbywheel2 = [
'FF0000',
'FF2000',
'FF4000',
'FFA000',
'FFFF00',
'80FF00',
'00FF00',
'008080',
'0000FF',
'4000FF',
'8000FF',
'800080']

joustwheel = [
'FF7070', #pink
'FF00C0', #magenta
'FF4000', #orange
'FFFF00', #yellow
'00FF00', #green
'00FFFF', #turquoise
'0000FF', #blue
'6000FF', #purple
'ffffff', #white
'FF0000', #red
'FF3278', #splatoon pink
'1edc00'] #splatoon green

newcolors = [
'FFFF00', #yellow
'6000FF', #purple
'FF4000', #orange
'FF6060', #pink
'00FFFF', #turquoise
'FF0000', #red
'ffff14', #YELLOW =     
'7e1e9c', #PURPLE =     
'f97306', #ORANGE =     
'ff81c0', #PINK =       
'06c2ac', #TURQUOISE =  
'653700'] #BROWN =      

def colorhex(hex):
    r = int(hex[0:2],16)
    g = int(hex[2:4],16)
    b = int(hex[4:6],16)
    return (r,g,b)


s=0
while True:
    for i,move in enumerate(moves):
        color = colorhex(joustwheel[(s+i)%12])
        move.set_leds(*color)
        move.update_leds()
        move.poll()
        ax,ay,az = tuple(move.get_accelerometer_frame(psmove.Frame_SecondHalf))
        print('%+1.1f %+1.1f %+1.1f %+1.1f' % (ax,ay,az,sqrt(sum([ax**2, ay**2, az**2]))))
    #time.sleep(.1)
    #s += 1