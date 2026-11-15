"""Small read-only API over atomically published real ECMWF forecast caches."""
from collections import defaultdict
from datetime import datetime, timezone
import asyncio
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("RAINSIGHT_DATA_DIR", ROOT / "data"))
WEB = ROOT / "web"
logger = logging.getLogger("rainsight.refresh")


async def refresh_loop():
    """Refresh in the background; a failed fetch leaves the validated cache intact."""
    while True:
        try:
            result = await asyncio.to_thread(subprocess.run,
                [sys.executable, "-m", "rainsight.ingest", "--hours", "48",
                 "--source", os.environ.get("RAINSIGHT_ECMWF_SOURCE", "ecmwf"),
                 "--output", str(DATA)], cwd=ROOT, capture_output=True, text=True,
                timeout=900, check=True)
            logger.info("Forecast refresh succeeded: %s", result.stdout[-4000:])
        except Exception as exc:
            logger.warning("Forecast refresh failed; retaining prior cache: %s", exc)
        await asyncio.sleep(6 * 60 * 60)


@asynccontextmanager
async def lifespan(_app):
    task = None
    if os.environ.get("RAINSIGHT_AUTO_REFRESH", "1").lower() not in ("0", "false", "no"):
        task = asyncio.create_task(refresh_loop())
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="RainSight API", version="0.2.0", lifespan=lifespan,
              description="ECMWF deterministic total precipitation forecasts for supported Indian locations.")
app.mount("/static", StaticFiles(directory=WEB), name="static")


def load_forecast(run_id: Optional[str] = None) -> dict:
    if run_id is not None and ("/" in run_id or "\\" in run_id or run_id in (".", "..")):
        raise HTTPException(400, "Invalid run identifier")

    if run_id is None:
        latest_path = DATA / "latest.json"
        latest = _read_valid_cache(latest_path)
        newest_snapshot = None
        snapshot_paths = sorted((p for p in DATA.glob("*.json")
                                 if p.name != "latest.json"), reverse=True)
        for snapshot_path in snapshot_paths:
            newest_snapshot = _read_valid_cache(snapshot_path)
            if newest_snapshot is not None:
                break
        # A surviving runtime cache can be older than a newly bundled run.
        # Compare model run IDs, not retrieval times, and keep a usable snapshot
        # when latest.json is malformed or incomplete.
        candidates = [p for p in (latest, newest_snapshot) if p is not None]
        if candidates:
            return max(candidates, key=lambda payload: payload["run_id"])
        if latest_path.exists() or snapshot_paths:
            raise HTTPException(503, "Forecast cache is unavailable or malformed")
        raise HTTPException(503, "No successful ECMWF forecast cache is available")

    path = DATA / f"{run_id}.json"
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        raise HTTPException(503, "No successful ECMWF forecast cache is available")
    except (OSError, json.JSONDecodeError):
        raise HTTPException(503, "Forecast cache is unavailable or malformed")
    if not isinstance(payload, dict) or not isinstance(payload.get("intervals"), list) or not payload["intervals"]:
        raise HTTPException(503, "Forecast cache has no validated intervals")
    return payload


def _read_valid_cache(path: Path) -> Optional[dict]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if (not isinstance(payload, dict) or not isinstance(payload.get("run_id"), str) or
        not isinstance(payload.get("intervals"), list) or not payload["intervals"]):
        return None
    return payload


def interval_phase(interval: dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(interval["start_time"])
    end = datetime.fromisoformat(interval["end_time"])
    if end <= now:
        return "elapsed"
    if start < now:
        return "in_progress"
    return "upcoming"


def freshness(payload: dict) -> dict:
    now = datetime.now(timezone.utc)
    retrieved = datetime.fromisoformat(payload["retrieved_at"])
    initialized = datetime.fromisoformat(payload["initialization"])
    interval_bounds = [(datetime.fromisoformat(i["start_time"]),
                        datetime.fromisoformat(i["end_time"]))
                       for i in payload["intervals"]]
    retrieved_age = max(0.0, (now - retrieved).total_seconds() / 3600)
    run_age = max(0.0, (now - initialized).total_seconds() / 3600)
    remaining = sum(end > now for _, end in interval_bounds)
    upcoming = sum(start >= now for start, _ in interval_bounds)
    horizon_end = max(end for _, end in interval_bounds)
    expired = remaining == 0
    return {"retrieved_at": payload["retrieved_at"], "run_age_hours": round(run_age, 1),
            "cache_age_hours": round(retrieved_age, 2), "forecast_horizon_end": horizon_end.isoformat(),
            "remaining_interval_count": remaining, "upcoming_interval_count": upcoming,
            "future_forecast_available": upcoming > 0, "expired": expired,
            "stale": expired or run_age > 18 or retrieved_age > 24}


def threshold_value(value: float) -> float:
    if not 0 <= value <= 500:
        raise HTTPException(422, "Threshold must be between 0 and 500 mm")
    return value


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    try:
        p = load_forecast()
        current = freshness(p)
        available = current["future_forecast_available"]
        result = {"service": "ok", "forecast_available": available,
                  "run_id": p["run_id"], "freshness": current}
        if not available:
            result["detail"] = ("Forecast horizon has ended; waiting for a current ECMWF run"
                                 if current["expired"] else
                                 "No complete future intervals remain; waiting for a refreshed ECMWF run")
        return result
    except HTTPException as exc:
        return {"service": "ok", "forecast_available": False, "detail": exc.detail}


@app.get("/api/runs")
def runs():
    found = []
    for path in sorted(DATA.glob("*.json"), reverse=True):
        if path.name == "latest.json":
            continue
        try:
            p = json.loads(path.read_text())
            found.append({"run_id": p["run_id"], "initialization": p["initialization"],
                          "model": p["model"], "interval_count": len(p["intervals"]),
                          "freshness": freshness(p)})
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return {"runs": found}


@app.get("/api/locations")
def locations(run_id: Optional[str] = None):
    p = load_forecast(run_id)
    return {"run_id": p["run_id"], "locations": p["locations"], "freshness": freshness(p)}


@app.get("/api/timeline")
def timeline(run_id: Optional[str] = None, threshold_mm: float = Query(10, ge=0, le=500)):
    p = load_forecast(run_id)
    threshold = threshold_value(threshold_mm)
    intervals = []
    now = datetime.now(timezone.utc)
    for interval in p["intervals"]:
        values = interval["rainfall_mm"]
        intervals.append({k: interval[k] for k in ("start_step", "end_step", "start_time", "end_time")}
                         | {"phase": interval_phase(interval, now),
                            "max_grid_mm": max(values),
                            "mean_grid_mm": round(sum(values) / len(values), 3),
                            "threshold_crossed_somewhere": max(values) >= threshold,
                            "rounding_tolerance_mm": interval.get("rounding_tolerance_mm", 0)})
    return {"run_id": p["run_id"], "initialization": p["initialization"],
            "units": "mm", "threshold_mm": threshold, "intervals": intervals,
            "freshness": freshness(p)}


@app.get("/api/location/{location_id}")
def location_forecast(location_id: str, run_id: Optional[str] = None,
                      threshold_mm: float = Query(10, ge=0, le=500)):
    p = load_forecast(run_id)
    threshold = threshold_value(threshold_mm)
    loc = next((x for x in p["locations"] if x["id"] == location_id), None)
    if loc is None:
        raise HTTPException(404, "Unsupported location")
    index = loc["grid_index"]
    amounts = [i["rainfall_mm"][index] for i in p["intervals"]]
    rows = []
    total = 0.0
    now = datetime.now(timezone.utc)
    for i, amount in zip(p["intervals"], amounts):
        total += amount
        rows.append({"start_step": i["start_step"], "end_step": i["end_step"],
                     "start_time": i["start_time"], "end_time": i["end_time"],
                     "phase": interval_phase(i, now),
                     "rainfall_mm": round(amount, 3), "cumulative_mm": round(total, 3),
                     "threshold_crossed": amount >= threshold,
                     "rounding_tolerance_mm": i.get("rounding_tolerance_mm", 0)})
    return {"run_id": p["run_id"], "location": loc, "units": "mm",
            "threshold_mm": threshold, "interval_total_mm": round(total, 3),
            "intervals": rows, "freshness": freshness(p)}


@app.get("/api/spatial")
def spatial(end_step: int = Query(..., ge=3), run_id: Optional[str] = None):
    p = load_forecast(run_id)
    interval = next((i for i in p["intervals"] if i["end_step"] == end_step), None)
    if interval is None:
        raise HTTPException(404, "Forecast interval is unavailable")
    # Aggregate native 0.25-degree cells into ~0.5-degree display cells.
    bins = defaultdict(lambda: [0.0, 0, 0.0, 0.0])
    for lat, lon, value in zip(p["latitudes"], p["longitudes"], interval["rainfall_mm"]):
        key = (int((lat - 6.0) / 0.5), int((lon - 67.0) / 0.5))
        bins[key][0] += value
        bins[key][1] += 1
        bins[key][2] += lat
        bins[key][3] += lon
    features = []
    for (_lat_bin, _lon_bin), (total, count, lat_total, lon_total) in bins.items():
        lat, lon = lat_total / count, lon_total / count
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                         "properties": {"rainfall_mm": round(total / count, 3), "sample_count": count}})
    return {"type": "FeatureCollection", "run_id": p["run_id"], "end_step": end_step,
            "start_step": interval["start_step"], "start_time": interval["start_time"],
            "end_time": interval["end_time"], "phase": interval_phase(interval),
            "units": "mm", "features": features, "freshness": freshness(p)}


@app.get("/api/provenance")
def provenance(run_id: Optional[str] = None):
    p = load_forecast(run_id)
    return {k: p[k] for k in ("run_id", "initialization", "model", "resolution_degrees",
                               "retrieved_at", "bounds", "source", "request", "grib_sha256",
                               "grib_metadata", "cross_check", "attribution", "limitations",
                               "negative_tolerance_mm", "clipped_negative_differences")
            if k in p} | {"freshness": freshness(p)}


