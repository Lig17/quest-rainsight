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
    if run_id is None:
        path = DATA / "latest.json"
        if not path.exists():
            snapshots = sorted(p for p in DATA.glob("*.json") if p.name != "latest.json")
            path = snapshots[-1] if snapshots else path
    else:
        path = DATA / f"{run_id}.json"
    if run_id is not None and ("/" in run_id or "\\" in run_id or run_id in (".", "..")):
        raise HTTPException(400, "Invalid run identifier")
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        raise HTTPException(503, "No successful ECMWF forecast cache is available")
    except (OSError, json.JSONDecodeError):
        raise HTTPException(503, "Forecast cache is unavailable or malformed")
    if not isinstance(payload.get("intervals"), list) or not payload["intervals"]:
        raise HTTPException(503, "Forecast cache has no validated intervals")
    return payload


def freshness(payload: dict) -> dict:
    now = datetime.now(timezone.utc)
    retrieved = datetime.fromisoformat(payload["retrieved_at"])
    initialized = datetime.fromisoformat(payload["initialization"])
    retrieved_age = max(0.0, (now - retrieved).total_seconds() / 3600)
    run_age = max(0.0, (now - initialized).total_seconds() / 3600)
    return {"retrieved_at": payload["retrieved_at"], "run_age_hours": round(run_age, 1),
            "cache_age_hours": round(retrieved_age, 2),
            "stale": run_age > 18 or retrieved_age > 24}


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
        return {"service": "ok", "forecast_available": True, "run_id": p["run_id"],
                "freshness": freshness(p)}
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
    for interval in p["intervals"]:
        values = interval["rainfall_mm"]
        intervals.append({k: interval[k] for k in ("start_step", "end_step", "start_time", "end_time")}
                         | {"max_grid_mm": max(values),
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
    for i, amount in zip(p["intervals"], amounts):
        total += amount
        rows.append({"start_step": i["start_step"], "end_step": i["end_step"],
                     "start_time": i["start_time"], "end_time": i["end_time"],
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
            "end_time": interval["end_time"], "units": "mm", "features": features,
            "freshness": freshness(p)}


@app.get("/api/provenance")
def provenance(run_id: Optional[str] = None):
    p = load_forecast(run_id)
    return {k: p[k] for k in ("run_id", "initialization", "model", "resolution_degrees",
                               "retrieved_at", "bounds", "source", "request", "grib_sha256",
                               "grib_metadata", "cross_check", "attribution", "limitations",
                               "negative_tolerance_mm", "clipped_negative_differences")
            if k in p} | {"freshness": freshness(p)}


