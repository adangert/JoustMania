import asyncio
import collections
import random
import typing

import common

PaceSettings_ = collections.namedtuple('PaceSettings_', ['weight', 'min_duration', 'max_duration'])


class PaceManager:
    """Manages transitions between game paces, and notifies users of changes via a callback.
       The game starts out in the initial pace, then switches pace according to parameters
       passed in. The actual pace is treated as an opaque object -- this class does not care
       what the pace represents, it is just in charge of timing transitions.
       Sample usage:

        pm = PaceManager(cb, pace1, 10)
        pm.add_or_update_pace(pace2, 1.0, 10, 20)
        pm.add_or_update_pace(pace3, 2.0, 5, 10)
        pm.start()
        ....
        pm.stop()

       Here, we start off with pace1 for 10 seconds. After that, we will switch to either pace2, or pace3,
       with pace3 being twice as likely. If pace2 is chosen, it will be kept for 10-20 seconds. pace3 will
       be kept for 5-10 seconds.
    """

    def __init__(self, callback, initial_pace, initial_pace_time: float, rng=random.uniform):
        self.initial_pace_ = initial_pace
        self.initial_pace_time_ = initial_pace_time
        self.available_paces_ = {}
        self.task_ = None
        self.rng_ = rng
        self.callback_ = callback

    def add_or_update_pace(self, pace, weight: float, min_duration: float, max_duration: float):
        self.available_paces_[pace] = PaceSettings_(weight, min_duration, max_duration)

    def start(self):
        self.task_ = asyncio.ensure_future(self.run_())
        return self.task_

    def stop(self):
        self.task_.cancel()

    def set_pace_(self, pace):
        self.callback_(pace)

    def choose_new_pace_(self, old_pace) -> typing.Tuple[object, float]:
        if len(self.available_paces_) == 0:
            raise RuntimeError("No paces registered.")
        candidates = self.available_paces_
        total_weight = sum([ params.weight for params in candidates.values() ])
        index = self.rng_(0, total_weight)
        cumulative_weight = 0
        for pace, params in candidates.items():
            cumulative_weight += params.weight
            if cumulative_weight >= index:
                return pace, self.rng_(params.min_duration, params.max_duration)
        raise ValueError("Couldn't find pace with index %s/%s!?" % (index, total_weight))

    @common.async_print_exceptions
    async def run_(self):
        await asyncio.sleep(self.initial_pace_time_)

        pace = self.initial_pace_
        while True:
            pace, duration_secs = self.choose_new_pace_(pace)
            self.set_pace_(pace)
            await asyncio.sleep(duration_secs)
