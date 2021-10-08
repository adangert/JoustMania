#!/home/pi/JoustMania/venv/bin/python3.6

import asyncio
import psmove
import player
import piparty
import math
import filterpy
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

async def Loop(plr):
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
        for event in plr.get_events():
            if event.type != player.EventType.SENSOR:
                continue
            print('\r|%s| = %+.02f    |%s| = %+7.02f      |%s| = %+2.02f'  % (
                FormatVec(event.acceleration),
                event.acceleration_magnitude,
                FormatVec(event.jerk, 7),
                event.jerk_magnitude,
                FormatVec(event.gyroscope),
                VecLen(event.gyroscope)), end='')

        #this should be the minimum amount to capture packets
        await asyncio.sleep(1/30)


def Main():
    # piparty.Menu.enable_bt_scanning()
    move = psmove.PSMove(0)
    # move.enable_orientation(True)
    p1 = player.Player(move)
    asyncio.get_event_loop().run_until_complete(Loop(p1))

if __name__ == '__main__':
    Main()
