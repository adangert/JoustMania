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


    while True:
        #we could try just changing this to the change in jerk over time (smoothed out?)
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
            disp_tup = ( float(event.acceleration_magnitude), event.acceleration[0], event.acceleration[1], event.acceleration[2],
                VecLen(event.gyroscope), event.gyroscope[0], event.gyroscope[1], event.gyroscope[2],
                event.jerk_magnitude, event.jerk[0],event.jerk[1],event.jerk[2])
            q.put(disp_tup)
            # q.put(float(event.acceleration_magnitude))
            
            
            
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
    x_len = 100         # Number of points to display
    y_range = [-0.05, 0.05]  # Range of possible Y values to display

    # Create figure for plotting
    n_rows = 4
    n_cols = 4
    num_plots = n_rows * n_cols
    fig, axs = plt.subplots(n_rows,n_cols)
    # fig = plt.figure()
    # ax = fig.add_subplot(1, 1, 1)
    xs = list(range(0, x_len))
    mag_ys = [0] * x_len
    
    # acc_x_xs = list(range(0, x_len))
    acc_x_ys = [0] * x_len
    
    plots_ys = [[0]* x_len for x in range(num_plots)]
    
    plots = []
    for x in range(n_rows):
        for y in range(n_cols):
            axs[y,x].set_ylim(y_range)
            plots.append(axs[y,x].plot(xs, plots_ys[y+(x*n_rows)])[0])



    # plots.append(axs[0,0].plot(xs, plots_ys[0])[0])
    # plots.append(axs[1,0].plot(xs, plots_ys[1])[0])
    # plots.append(axs[2,0].plot(xs, plots_ys[2])[0])
    # plots.append(axs[3,0].plot(xs, plots_ys[3])[0])

    # Add labels
    # axs[0,0].set_title('Acceleration Magnitude')
    # axs[0,1].set_title('Acceleration x')
    # axs[0,2].set_title('Acceleration y')
    # axs[0,3].set_title('Acceleration z')
    # plt.xlabel('Samples')
    # plt.ylabel('Temperature (deg C)')

    # This function is called periodically from FuncAnimation
    def animate(i):
        nonlocal mag_ys, acc_x_ys, plots, plots_ys
        while not q.empty():
            q_val = q.get()
            
            for j, plt in enumerate(plots):
                if(j < len(q_val)):
                    q_val_info = q_val[j]
                    plots_ys[j].append(q_val_info)
                    plots_ys[j] = plots_ys[j][-x_len:]
                    plots[j].set_ydata(plots_ys[j])
                
            
            # q_mag = q_val[0]
            # q_acc_x = q_val[1]

            # # Add y to list
            # mag_ys.append(q_mag)
            # acc_x_ys.append(q_acc_x)

            # # Limit y list to set number of items
            # mag_ys = mag_ys[-x_len:]
            # acc_x_ys = acc_x_ys[-x_len:]

            # # Update line with new Y values
            # mag.set_ydata(mag_ys)
            # acc_x.set_ydata(acc_x_ys)

        return plots


    # Set up plot to call animate() function periodically

    ani = animation.FuncAnimation(fig,
        animate,
        interval=20,
        blit=True)
    plt.show()


def Main():
    print("starting main")
    q = multiprocessing.Queue()
    p = Process(target=runGraph, args=(q,))
    p.start()
    # piparty.Menu.enable_bt_scanning()
    
    move = psmove.PSMove(0)
    # move.enable_orientation(True)
    p1 = player.Player(move)
    asyncio.get_event_loop().run_until_complete(Loop(p1,q))
    p.join()

if __name__ == '__main__':
    #print("hello this is the main program")
    Main()
