import multiprocessing
import unittest
from report_timing import ReportTiming


def publish_in_child(timing):
    timing.record(0, 1.0)
    timing.record(0, 1.020)


class ReportTimingTest(unittest.TestCase):
    def test_equal_average_rates_can_have_different_gaps(self):
        regular, bursty = ReportTiming(1), ReportTiming(1)
        for i in range(101):
            regular.record(0, i * .01)
            bursty.record(0, (i // 2) * .02)
        self.assertEqual(regular.snapshot(0, 1)['p95_ms'], 10)
        self.assertEqual(bursty.snapshot(0, 1)['p95_ms'], 20)

    def test_rolling_window_and_current_stall(self):
        timing = ReportTiming(1)
        for t in [0, .2, 20, 20.01]:
            timing.record(0, t)
        data = timing.snapshot(0, 20.01)
        self.assertEqual(data['sample_count'], 2)
        self.assertEqual(data['max_ms'], 19800)
        self.assertEqual(data['gaps_over_100ms'], 1)
        stalled = timing.snapshot(0, 31)
        self.assertIsNone(stalled['p95_ms'])
        self.assertEqual(stalled['last_report_age_ms'], 10990)

    def test_ring_wrap_and_reconnect_do_not_mix_sessions(self):
        timing = ReportTiming(1, capacity=4)
        for t in [0, 1, 2, 3, 4, 5]:
            timing.record(0, t)
        data = timing.snapshot(0, 5)
        self.assertEqual(data['sample_count'], 3)
        self.assertEqual(data['max_ms'], 1000)
        self.assertTrue(data['sample_limited'])
        timing.reset(0)
        self.assertIsNone(timing.snapshot(0, 10)['last_report_age_ms'])
        timing.record(0, 20)
        self.assertIsNone(timing.snapshot(0, 20)['p95_ms'])
        timing.record(0, 20.01)
        self.assertEqual(timing.snapshot(0, 20.01)['p95_ms'], 10)

    def test_reader_in_another_process_sees_timing(self):
        timing = ReportTiming(1)
        process = multiprocessing.Process(target=publish_in_child, args=(timing,))
        process.start()
        process.join(timeout=5)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(timing.snapshot(0, 1.02)['p95_ms'], 20)


if __name__ == '__main__':
    unittest.main()
