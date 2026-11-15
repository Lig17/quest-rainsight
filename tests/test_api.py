"""API contract tests use a small deterministic fixture, never forecast data."""
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["RAINSIGHT_AUTO_REFRESH"] = "0"
from fastapi.testclient import TestClient
from rainsight import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        api.DATA = Path(self.tmp.name)
        now = datetime.now(timezone.utc)
        self.initialization = now.replace(hour=now.hour // 3 * 3, minute=0, second=0, microsecond=0)
        self.run_id = self.initialization.strftime("%Y%m%dT%H%MZ")
        end3 = (self.initialization + timedelta(hours=3)).isoformat()
        end6 = (self.initialization + timedelta(hours=6)).isoformat()
        fixture = {
            "run_id": self.run_id, "initialization": self.initialization.isoformat(),
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
                {"start_step": 0, "end_step": 3, "start_time": self.initialization.isoformat(),
                 "end_time": end3, "rounding_tolerance_mm": 0.02,
                 "rainfall_mm": [1.0, 2.0, 3.0, 4.0]},
                {"start_step": 3, "end_step": 6, "start_time": end3,
                 "end_time": end6, "rounding_tolerance_mm": 0.03,
                 "rainfall_mm": [12.0, 0.0, 1.0, 2.0]},
            ]}
        (api.DATA / "latest.json").write_text(json.dumps(fixture))
        (api.DATA / f"{self.run_id}.json").write_text(json.dumps(fixture))
        self.client = TestClient(api.app)

    def test_health_and_runs_shape(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["forecast_available"])
        self.assertIn("stale", response.json()["freshness"])
        self.assertFalse(response.json()["freshness"]["expired"])
        self.assertEqual(self.client.get("/api/runs").json()["runs"][0]["run_id"], self.run_id)

    def test_expired_snapshot_is_unavailable_as_a_current_forecast(self):
        frozen_now = self.initialization + timedelta(hours=50)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen_now if tz is None else frozen_now.astimezone(tz)

        with patch.object(api, "datetime", FrozenDateTime):
            health = self.client.get("/api/health").json()
            timeline = self.client.get("/api/timeline").json()
        self.assertFalse(health["forecast_available"])
        self.assertTrue(health["freshness"]["expired"])
        self.assertTrue(health["freshness"]["stale"])
        self.assertEqual(health["freshness"]["remaining_interval_count"], 0)
        self.assertIn("horizon has ended", health["detail"])
        self.assertTrue(all(row["phase"] == "elapsed" for row in timeline["intervals"]))

    def test_in_progress_interval_is_not_reported_as_a_future_forecast(self):
        frozen_now = self.initialization + timedelta(hours=4)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen_now if tz is None else frozen_now.astimezone(tz)

        with patch.object(api, "datetime", FrozenDateTime):
            health = self.client.get("/api/health").json()
            timeline = self.client.get("/api/timeline").json()
        self.assertFalse(health["forecast_available"])
        self.assertFalse(health["freshness"]["expired"])
        self.assertEqual(health["freshness"]["remaining_interval_count"], 1)
        self.assertEqual(health["freshness"]["upcoming_interval_count"], 0)
        self.assertIn("No complete future intervals", health["detail"])
        self.assertEqual([row["phase"] for row in timeline["intervals"]], ["elapsed", "in_progress"])

    def test_refresh_failure_preserves_the_validated_snapshot(self):
        cache = api.DATA / "latest.json"
        before = cache.read_bytes()

        class StopAfterAttempt(Exception):
            pass

        async def fail_download(*_args, **_kwargs):
            raise OSError("ECMWF endpoint unavailable")

        async def stop_sleep(_seconds):
            raise StopAfterAttempt()

        fake_asyncio = SimpleNamespace(to_thread=fail_download, sleep=stop_sleep)
        with self.assertLogs(api.logger, level="WARNING") as captured:
            with patch.object(api, "asyncio", fake_asyncio):
                with self.assertRaises(StopAfterAttempt):
                    asyncio.run(api.refresh_loop())
        self.assertIn("retaining prior cache", " ".join(captured.output))
        self.assertEqual(cache.read_bytes(), before)

    def test_latest_falls_back_to_newest_processed_run_snapshot(self):
        newer = json.loads((api.DATA / f"{self.run_id}.json").read_text())
        newer_initialization = self.initialization + timedelta(hours=3)
        newer_id = newer_initialization.strftime("%Y%m%dT%H%MZ")
        newer["run_id"] = newer_id
        newer["initialization"] = newer_initialization.isoformat()
        newer["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        for interval in newer["intervals"]:
            interval["start_time"] = (newer_initialization + timedelta(hours=interval["start_step"])).isoformat()
            interval["end_time"] = (newer_initialization + timedelta(hours=interval["end_step"])).isoformat()
        (api.DATA / f"{newer_id}.json").write_text(json.dumps(newer))
        (api.DATA / "latest.json").unlink()
        result = self.client.get("/api/location/test-city").json()
        self.assertEqual(result["run_id"], newer_id)
        self.assertEqual(result["intervals"][0]["rainfall_mm"], 1.0)

    def test_locations_timeline_and_threshold(self):
        self.assertEqual(self.client.get("/api/locations").json()["locations"][0]["id"], "test-city")
        result = self.client.get("/api/timeline?threshold_mm=10").json()
        self.assertEqual(result["units"], "mm")
        self.assertIn(result["intervals"][0]["phase"], ("in_progress", "upcoming"))
        self.assertEqual(result["intervals"][1]["phase"], "upcoming")
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
