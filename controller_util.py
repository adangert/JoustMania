#!/home/pi/JoustMania/venv/bin/python3.6

import asyncio
import psmove
import player
import piparty
import math
import filterpy
from filterpy.kalman import ExtendedKalmanFilter
#https://thepoorengineer.com/en/ekf-impl/
#https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python/blob/master/11-Extended-Kalman-Filters.ipynb
#link 3
#https://kusemanohar.info/2020/04/08/sensor-fusion-extended-kalman-filter-ekf/

# Continually prints sensor readings from the first controller found.

def FormatVec(v, places=5):
    fmt = '{:%d.2f}' % places
    return ', '.join([ fmt.format(e) for e in v ])
def VecLen(v):
    return math.sqrt(sum([ e*e for e in v ]))
def Normalize(v):n
    m = VecLen(v)
    return tuple([ e / m for e in v ])

async def Loop(plr):
    print("Acceleration   Jerk    Gyro")
    dt = 0.05
    rk = ExtendedKalmanFilter(dim_x=12,dim_z=6)
    #initial starting values
    #we care about linear acceleration.
    #orientation, acceleration, velocity?
    #gyroscope, accelerometer
    
    #From Link3 we are going to use orientation, linear velocity, gyroscope bias, and accelerometer bias
    #for the Joustmania game we don't care so much about position
    
    #there is 4 states each with 3 variables,.
    rk.x = array([0,0,0,0,0,0,0,0,0,0,0,0])
    
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
    
    rk.F = eye(3) + array([[0, 1, 0],
                       [0, 0, 0],
                       [0, 0, 0]]) * dt

    range_std = 5. # meters
    rk.R = np.diag([range_std**2])
    rk.Q[0:2, 0:2] = Q_discrete_white_noise(2, dt=dt, var=0.1)
    rk.Q[2,2] = 0.1
    rk.P *= 50

    xs, track = [], []
    for i in range(int(20/dt)):
        z = radar.get_range()
        track.append((radar.pos, radar.vel, radar.alt))
        
        rk.update(array([z]), HJacobian_at, hx)
        xs.append(rk.x)
        rk.predict()

    xs = asarray(xs)
    track = asarray(track)
    time = np.arange(0, len(xs)*dt, dt)
    ekf_internal.plot_radar(xs, track, time)
    
    
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
    piparty.Menu.enable_bt_scanning()
    move = psmove.PSMove(0)
    move.enable_orientation(True)
    p1 = player.Player(move)
    asyncio.get_event_loop().run_until_complete(Loop(p1))

if __name__ == '__main__':
    Main()
