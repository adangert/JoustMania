import unittest

import numpy

from piaudio import resample_stereo_s16


class StereoResamplingTest(unittest.TestCase):
    def setUp(self):
        frame_count = 1024
        phase = numpy.linspace(0, 8 * numpy.pi, frame_count, endpoint=False)
        left = (numpy.sin(phase) * 12000).astype(numpy.int16)
        right = (numpy.cos(phase) * 12000).astype(numpy.int16)
        self.pcm = numpy.column_stack((left, right)).tobytes()

    def test_normal_ratio_preserves_frame_count(self):
        output = resample_stereo_s16(self.pcm, 1.0)

        self.assertEqual(len(output), len(self.pcm))

    def test_faster_ratio_produces_fewer_frames(self):
        output = resample_stereo_s16(self.pcm, 1.3)

        self.assertLess(len(output), len(self.pcm))
        self.assertEqual(len(output), 3072)

    def test_rejects_non_positive_ratio(self):
        with self.assertRaises(ValueError):
            resample_stereo_s16(self.pcm, 0)


if __name__ == "__main__":
    unittest.main()
