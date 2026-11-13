"""API contract tests use a small deterministic fixture, never forecast data."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

os.environ["RAINSIGHT_AUTO_REFRESH"] = "0"
from fastapi.testclient import TestClient
from rainsight import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        api.DATA = Path(self.tmp.name)
        fixture = {
            "run_id": "20261112T1800Z", "initialization": "2026-11-12T18:00:00+00:00",
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "model": "IFS deterministic",
            "resolution_degrees": 0.25, "bounds": {"south": 6, "north": 37, "west": 67, "east": 98},
            "source": "ecmwf", "request": {"param": "tp"}, "grib_sha256": "a" * 64,
            "attribution": "ECMWF Open Data, CC BY 4.0", "limitations": "Deterministic forecast.",
            "negative_tolerance_mm": 0.01, "clipped_negative_differences": 0,
            "grib_metadata": [{"paramId": 228}], "cross_check": {"location": "test"},
            "latitudes": [13.0, 13.0, 13.25, 13.25], "longitudes": [77.5, 77.75, 77.5, 77.75],
            "locations": [{"id": "test-city", "name": "Test City", "latitude": 13.1,
                           "longitude": 77.6, "grid_latitude": 13.0, "grid_longitude": 77.5,
                           "grid_index": 0}],
            "intervals": [
                {"start_step": 0, "end_step": 3, "start_time": "2026-11-12T18:00:00+00:00",
                 "end_time": "2026-11-12T21:00:00+00:00", "rounding_tolerance_mm": 0.02,
                 "rainfall_mm": [1.0, 2.0, 3.0, 4.0]},
                {"start_step": 3, "end_step": 6, "start_time": "2026-11-12T21:00:00+00:00",
                 "end_time": "2026-11-13T00:00:00+00:00", "rounding_tolerance_mm": 0.03,
                 "rainfall_mm": [12.0, 0.0, 1.0, 2.0]},
            ]}
        (api.DATA / "latest.json").write_text(json.dumps(fixture))
        (api.DATA / "20261112T1800Z.json").write_text(json.dumps(fixture))
        self.client = TestClient(api.app)

    def test_health_and_runs_shape(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["forecast_available"])
        self.assertIn("stale", response.json()["freshness"])
        self.assertEqual(self.client.get("/api/runs").json()["runs"][0]["run_id"], "20261112T1800Z")

    def test_locations_timeline_and_threshold(self):
        self.assertEqual(self.client.get("/api/locations").json()["locations"][0]["id"], "test-city")
        result = self.client.get("/api/timeline?threshold_mm=10").json()
        self.assertEqual(result["units"], "mm")
        self.assertFalse(result["intervals"][0]["threshold_crossed_somewhere"])
        self.assertTrue(result["intervals"][1]["threshold_crossed_somewhere"])

    def test_location_accumulation_and_threshold_shape(self):
        result = self.client.get("/api/location/test-city?threshold_mm=10").json()
        self.assertEqual(result["location"]["name"], "Test City")
        self.assertEqual(result["interval_total_mm"], 13)
        self.assertTrue(result["intervals"][1]["threshold_crossed"])
        self.assertEqual(result["intervals"][1]["cumulative_mm"], 13)

    def test_spatial_geojson_shape(self):
        result = self.client.get("/api/spatial?end_step=3").json()
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(result["features"][0]["geometry"]["type"], "Point")
        self.assertEqual(result["features"][0]["properties"]["sample_count"], 4)
        self.assertEqual(result["features"][0]["properties"]["rainfall_mm"], 2.5)

    def test_provenance_and_rejections(self):
        provenance = self.client.get("/api/provenance").json()
        self.assertEqual(provenance["grib_metadata"][0]["paramId"], 228)
        self.assertEqual(len(provenance["grib_sha256"]), 64)
        self.assertEqual(self.client.get("/api/location/unknown").status_code, 404)
        self.assertEqual(self.client.get("/api/spatial?end_step=7").status_code, 404)
        self.assertEqual(self.client.get("/api/timeline?threshold_mm=900").status_code, 422)


if __name__ == "__main__":
    unittest.main()
