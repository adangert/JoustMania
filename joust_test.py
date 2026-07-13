"""Print event rates and motion data for one connected PS Move controller."""

# Historical results from the old SWIG poll test:
# Old PSMove controller: about 88 messages per second, with two sensor frames
# per message and about 64 to 65 messages retained in the poll buffer.
# Newer ZCM2 Move controller: about 790 messages per second, identical first
# and second sensor frames, and about 90 to 160 messages retained in the buffer.

import time

import controller_manager


manager = controller_manager.get_manager()
controllers = manager.connected_controllers()
if not controllers:
    raise SystemExit("No PS Move controller is connected")

move_controller = controllers[0]
previous = time.monotonic()
intervals = []

while len(intervals) < 1000:
    state = move_controller.read_update()
    if state is None:
        time.sleep(0.001)
        continue

    now = time.monotonic()
    intervals.append(now - previous)
    previous = now
    rate = len(intervals) / sum(intervals)
    print("{:.1f} Hz acceleration={} gyroscope={}".format(
        rate,
        state.acceleration,
        state.gyroscope,
    ))

controller_manager.stop_manager()
