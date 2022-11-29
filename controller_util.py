import asyncio
import psmove
import player
import piparty
import math
#import filterpy
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np
from itertools import count
import random
import multiprocessing
import matplotlib.animation as animation
from multiprocessing import Process
import numpy as np
import time
# from filterpy.kalman import ExtendedKalmanFilter
#https://thepoorengineer.com/en/ekf-impl/
#https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python/blob/master/11-Extended-Kalman-Filters.ipynb
#link 3
#https://kusemanohar.info/2020/04/08/sensor-fusion-extended-kalman-filter-ekf/

#Check this one out:
#https://github.com/mrsp/imu_ekf/blob/7fb544b99bfb2638e008517105e18a369bef5f18/src/imu_estimator.cpp
#https://github.com/soarbear/imu_ekf/blob/master/imu_extended_kalman_filter.py

#another good link:
#https://nitinjsanket.github.io/tutorials/attitudeest/kf
#http://philsal.co.uk/projects/imu-attitude-estimation

#complimentory filter
#http://www.pieter-jan.com/node/11

#maybe we should try a complimentory filter as from above first!

#we are trying to find the best process model of an IMU that contains linear acceleration
#because that is the value we care most about and the one we want to track

# Continually prints sensor readings from the first controller found.

#notes 9/30/21
#well if we have the orientation!! then we can just get the linear acceleration by subtraction of it.

#so maybe we should just try the standard tutorials and then just do some regular estimation of linear accelration after we have
#orientation and acceleration

def FormatVec(v, places=5):
    fmt = '{:%d.2f}' % places
    return ', '.join([ fmt.format(e) for e in v ])
def VecLen(v):
    return math.sqrt(sum([ e*e for e in v ]))
def Normalize(v):
    m = VecLen(v)
    return tuple([ e / m for e in v ])

async def Loop(plr,q):
    print("Acceleration   Jerk    Gyro")
    dt = 0.05
    # rk = ExtendedKalmanFilter(dim_x=12,dim_z=6)
    #initial starting values
    #we care about linear acceleration.
    #orientation, acceleration, velocity?
    #gyroscope, accelerometer
    
    #From Link3 we are going to use orientation, linear acceleration, gyroscope bias, and accelerometer bias
    #for the Joustmania game we don't care so much about position
    
    #there is 4 states each with 3 variables,.
    # rk.x = array([0,0,0,0,0,0,0,0,0,0,0,0])
    
    #state transition matrix
    #again Link3
    #This needs to be linearized likely with a program that can find the Jacobian
    #x_dot = 
    #[G(X_2)^(-1)(W_m-x_4-n_g),
    #[g + R(x_2)(a_m-x_5-n_a)
    #n_bg
    #n_ba]
    
    #currently incorect, needs to be updated with maths
    #we need dead reconing for the orientation first:
    
    #current orientation 
    #look at github code next
    
    #So the question is, how does orientation affect linear velocity??
    
    
    #we need to estimate the direction of the controller first
    
    #so for the new direction: complementary filter to get the angle the controller is at
    
    #we need to then subtract the angle from the acceleration data to get the linear acceleration
    
    #we are using many more frames, so this actually should be more performant too
    
    
    # rk.F = eye(3) + array([[0, 1, 0],
                       # [0, 0, 0],
                       # [0, 0, 0]]) * dt

    # range_std = 5. # meters
    # rk.R = np.diag([range_std**2])
    # rk.Q[0:2, 0:2] = Q_discrete_white_noise(2, dt=dt, var=0.1)
    # rk.Q[2,2] = 0.1
    # rk.P *= 50

    # xs, track = [], []
    # for i in range(int(20/dt)):
        # z = radar.get_range()
        # track.append((radar.pos, radar.vel, radar.alt))
        
        # rk.update(array([z]), HJacobian_at, hx)
        # xs.append(rk.x)
        # rk.predict()

    # xs = asarray(xs)
    # track = asarray(track)
    # time = np.arange(0, len(xs)*dt, dt)
    # ekf_internal.plot_radar(xs, track, time)
    
    
    #we should first get the gyro and accelerometer data and plot it
    #so we can see how noisy it is 

    # plt.pause(0.0001)
    
    # size=100
    # line1 = []
    # x_vec = np.linspace(0,1,size+1)[0:-1]
    # y1_data = np.random.randn(len(x_vec))
    # print(x_vec)
    # print(y1_data)
    # if line1==[]:
        
        # # this is the call to matplotlib that allows dynamic plotting
        # plt.ion()
        # fig = plt.figure(figsize=(13,6))
        # # ax = fig.add_subplot(111)
        # # create a variable for the line so we can later update it
             
        # #update plot label/title
        # plt.ylabel('Y Label')
        # plt.title('Title: {}'.format("acceleration"))
        # x = np.arange(0, 2*np.pi, 0.01)
        # ax = plt.axes(xlim=(0, 100), ylim=(-1, 1))
        # Color = [ 1 ,0.498039, 0.313725];
        # # line, = ax.plot([], [], '*',color = Color)
        # # line1, = ax.plot(x_vec,y1_data,'-o',alpha=0.8) 
        # x = np.arange(0, 2*np.pi, 0.01)
        # line, = ax.plot(x, np.sin(x))
    
    # # y1_data = []
    # def update_function(i):
        # print("UPDATING")
        # # line.set_data(y1_data)
        # # return line
        # # x = np.linspace(0, i+1, i+1)
        # # ts = 5*np.cos(x * 0.02 * np.pi) * np.sin(np.cos(x)  * 0.02 * np.pi)
        # # line.set_data(x, ts)
        # line.set_ydata(np.sin(x + i/10.0)) 
        # return line,
        
    # def init():
        # print("INITIALIZING")
        # line.set_ydata(np.ma.array(x, mask=True))
        # # line.set_data([], [])
        # print("ok now")
        # return line,
    # ani = FuncAnimation(fig, update_function,  init_func=init, repeat=False, interval=200,  blit=True)
    # # plt.pause(0.0001)
    # # plt.show()
    # plt.pause(0.001)
    while True:
        
        for event in plr.get_events():
            if event.type != player.EventType.SENSOR:
                continue
            
            print('acc:|%s| = %+.02f    jerk:|%s| = %+7.02f      gyro:|%s| = %+2.02f\n'  % (
                FormatVec(event.acceleration),
                event.acceleration_magnitude,
                FormatVec(event.jerk, 7),
                event.jerk_magnitude,
                FormatVec(event.gyroscope),
                VecLen(event.gyroscope)), end='')
            q.put(float(event.acceleration_magnitude))
            # y1_data  = np.delete(y1_data, [0])
            # y1_data = np.append(y1_data,[float(event.acceleration_magnitude)])
            # # y1_data.pop(0)
            # # y1_data.append(event.acceleration_magnitude)
            # line1.set_ydata(y1_data)
            # # adjust limits if new data goes beyond bounds
            # if np.min(y1_data)<=line1.axes.get_ylim()[0] or np.max(y1_data)>=line1.axes.get_ylim()[1]:
                # plt.ylim([np.min(y1_data)-np.std(y1_data),np.max(y1_data)+np.std(y1_data)])
            # # this pauses the data so the figure/axis can catch up - the amount of pause can be altered above
            # #plt.show()
            # plt.pause(0.0001)
            

        #this should be the minimum amount to capture packets
        await asyncio.sleep(1/30)



def runGraph(q):
    # Parameters
    # print('show')
    x_len = 200         # Number of points to display
    y_range = [-10, 10]  # Range of possible Y values to display

    # Create figure for plotting
    fig, axs = plt.subplots(2)
    # fig = plt.figure()
    # ax = fig.add_subplot(1, 1, 1)
    xs = list(range(0, 200))
    ys = [0] * x_len
    axs[0].set_ylim(y_range)

    # Create a blank line. We will update the line in animate
    line, = axs[0].plot(xs, ys)

    # Add labels
    axs[0].set_title('Acceleration Magnitude')
    # plt.xlabel('Samples')
    # plt.ylabel('Temperature (deg C)')

    # This function is called periodically from FuncAnimation
    def animate(i, ys):
        while not q.empty():
            temp_c = q.get()
            # print(q.get())
            # temp_c = np.random.random(1)*40

            # Add y to list
            ys.append(temp_c)

            # Limit y list to set number of items
            ys = ys[-x_len:]

        # Update line with new Y values
            line.set_ydata(ys)

        return line,


    # Set up plot to call animate() function periodically

    ani = animation.FuncAnimation(fig,
        animate,
        fargs=(ys,),
        interval=20,
        blit=True)
    plt.show()



def MainProgram():
     while 1:
         print('Main program')
         time.sleep(0.5)


def Main():
    print("starting main")
    q = multiprocessing.Queue()
    p = Process(target=runGraph, args=(q,))
    p.start()
    # MainProgram()
    # piparty.Menu.enable_bt_scanning()
    
    move = psmove.PSMove()
    # move.enable_orientation(True)
    p1 = player.Player(move)
    asyncio.get_event_loop().run_until_complete(Loop(p1,q))
    p.join()

if __name__ == '__main__':
    #print("hello this is the main program")
    Main()
