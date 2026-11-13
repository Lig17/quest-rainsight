"""Synthetic arrays exist exclusively in tests; no network or third-party packages."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from rainsight.processing import Field, interval_rainfall, nearest_index

INIT = datetime(2026, 11, 13, tzinfo=timezone.utc)


def field(step=3, values=(0.001, 0.002), **changes):
    base = Field(INIT, INIT + timedelta(hours=step), 0, step, "m",
                 (13.0, 14.0), (77.5, 78.0), values)
    return replace(base, **changes)


class ProcessingTests(unittest.TestCase):
    def test_conversion_and_interval_times(self):
        result = interval_rainfall([field(6, (0.004, 0.003)), field()])
        self.assertEqual(result['intervals'][0]['rainfall_mm'], [1, 2])
        self.assertEqual(result['intervals'][1]['rainfall_mm'], [3, 1])
        self.assertEqual(result['intervals'][1]['start_time'], (INIT + timedelta(hours=3)).isoformat())

    def test_mm_and_mass_units(self):
        for unit in ['mm', 'kg m**-2']:
            self.assertEqual(interval_rainfall([field(values=(1, 2), units=unit)])['intervals'][0]['rainfall_mm'], [1, 2])

    def test_bad_metadata_rejected(self):
        cases = [dict(valid_time=INIT), dict(initialization=INIT.replace(tzinfo=None)),
                 dict(valid_time=INIT.replace(tzinfo=None)), dict(start_step=3),
                 dict(units='m/s'), dict(short_name='cp'), dict(step_type='instant'),
                 dict(end_step=3.0), dict(latitudes=(91, 14)), dict(longitudes=(400, 78)),
                 dict(values=(float('nan'), 0)), dict(values=(float('inf'), 0)),
                 dict(values=()), dict(values=(1,)), dict(values=(-0.1, 0))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                interval_rainfall([field(**case)])

    def test_missing_and_duplicate_steps(self):
        for fields in [[], [field(6)], [field(), field()], [field(), field(9)]]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                interval_rainfall(fields)

    def test_mixed_run_and_grid(self):
        for second in [field(6, initialization=INIT + timedelta(days=1), valid_time=INIT + timedelta(days=1, hours=6)),
                       field(6, longitudes=(77.75, 78.0))]:
            with self.assertRaises(ValueError):
                interval_rainfall([field(), second])

    def test_negative_difference_policy(self):
        with self.assertRaises(ValueError):
            interval_rainfall([field(), field(6, (0, 0.003))])
        result = interval_rainfall([field(), field(6, (0.000999, 0.003))])
        self.assertEqual(result['clipped_negative_differences'], 1)
        self.assertEqual(result['intervals'][1]['rainfall_mm'][0], 0)

    def test_grib_quantization_rounding_bound(self):
        first = field(3, (0.00262451171875, 0.002532958984375), quantization_error_mm=0.0152587890625)
        second = field(6, (0.002593994140625, 0.002685546875), quantization_error_mm=0.030517578125)
        result = interval_rainfall([first, second])
        self.assertEqual(result['intervals'][1]['rainfall_mm'][0], 0)
        self.assertAlmostEqual(result['intervals'][1]['rounding_tolerance_mm'], 0.0457763671875)

    def test_known_city_arrays(self):
        lats, lons = [12, 13, 14], [77, 77.5, 78]
        index = nearest_index(lats, lons, 12.9716, 77.5946)
        self.assertEqual(index, 1)
        self.assertEqual([2, 7, 9][index], 7)

    def test_longitude_wrap(self):
        self.assertEqual(nearest_index([0, 0], [359.75, 1], 0, -0.2), 0)

    def test_bad_city_coordinates(self):
        for lat, lon in [(91, 0), (0, 181), (float('nan'), 0)]:
            with self.assertRaises(ValueError):
                nearest_index([0], [0], lat, lon)


if __name__ == '__main__':
    unittest.main()
