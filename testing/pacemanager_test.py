import asyncio
import collections
import time
import unittest

import pacemanager

PACE1 = object()
PACE2 = object()
PACE3 = object()

class PaceManagerTest(unittest.TestCase):
    def assertPrettyClose(self, a, b, error=0.1):
        self.assertGreater(error, abs(a - b))

    def test_distribution(self):
        pm = pacemanager.PaceManager(lambda x: True, PACE1, 5)
        pm.add_or_update_pace(PACE1, 1.0, 1, 2)

        # Test to make sure we don't double up on PACE2
        pm.add_or_update_pace(PACE2, 1.0, 1, 2)
        pm.add_or_update_pace(PACE2, 1.0, 1, 2)
        pm.add_or_update_pace(PACE3, 2.0, 1, 2)

        results = collections.defaultdict(int)
        num_trials = 1000
        for i in range(num_trials):
            pace, duration = pm.choose_new_pace_(PACE1)
            results[pace] += 1
            self.assertLessEqual(1, duration)
            self.assertGreater(2, duration)

        self.assertEqual(3, len(results))
        self.assertPrettyClose(1/4, results[PACE1]/num_trials)
        self.assertPrettyClose(1/4, results[PACE2]/num_trials)
        self.assertPrettyClose(1/2, results[PACE3]/num_trials)

    def test_async(self):
        Entry = collections.namedtuple('Entry', ['pace', 'time'])
        results = []
        begin = time.time()
        def UpdatePace(pace):
            results.append(Entry(pace, time.time() - begin))
        uniform = lambda a, b: a

        DELTA = 0.1
        pm = pacemanager.PaceManager(UpdatePace, PACE1, DELTA, rng=uniform)
        pm.add_or_update_pace(PACE1, 1.0, DELTA, 1 + DELTA)
        pm.add_or_update_pace(PACE2, 1.0, DELTA, 1 + DELTA)
        loop = asyncio.get_event_loop()
        try:
            # This should get us 4 events.
            timeout = DELTA * 4.1
            loop.run_until_complete(asyncio.wait_for(pm.start(), timeout=timeout))
        except asyncio.TimeoutError:
            pass

        # We should have registered a new pace 4 times, about DELTA seconds apart.
        self.assertEqual(4, len(results))
        for i in range(4):
            self.assertPrettyClose(results[i].time, DELTA * (i+1))


if __name__ == '__main__':
    unittest.main()
