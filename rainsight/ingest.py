"""Retrieve a pinned real run, inspect GRIB, validate, and atomically cache India.

Run: python -m rainsight.ingest --hours 48 --source aws
No synthetic forecast fallback exists. Optional dependencies load only on use.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile

from rainsight.processing import Field, interval_rainfall, nearest_index

BOUNDS = {"south": 6.0, "north": 37.0, "west": 67.0, "east": 98.0}
CITIES = {
    "bengaluru": ("Bengaluru", 12.9716, 77.5946),
    "chennai": ("Chennai", 13.0827, 80.2707),
    "mumbai": ("Mumbai", 19.0760, 72.8777),
    "delhi": ("Delhi", 28.6139, 77.2090),
    "kolkata": ("Kolkata", 22.5726, 88.3639),
    "hyderabad": ("Hyderabad", 17.3850, 78.4867),
    "kochi": ("Kochi", 9.9312, 76.2673),
    "guwahati": ("Guwahati", 26.1445, 91.7362),
}


def decode(path: Path):
    import eccodes as ec
    import numpy as np
    fields, metadata = [], []
    keys = ["shortName", "paramId", "units", "stepType", "startStep", "endStep",
            "stepUnits", "dataDate", "dataTime", "validityDate", "validityTime",
            "typeOfLevel", "gridType", "Ni", "Nj", "numberOfMissing",
            "edition", "centre", "generatingProcessIdentifier"]
    with path.open("rb") as source:
        while (handle := ec.codes_grib_new_from_file(source)) is not None:
            try:
                meta = {key: ec.codes_get(handle, key) for key in keys}
                if meta["stepUnits"] not in (1, "h") or meta["typeOfLevel"] != "surface":
                    raise ValueError("Unsupported step units or vertical level")
                if meta["numberOfMissing"] != 0 or meta["paramId"] != 228:
                    raise ValueError("Missing data or unexpected parameter")
                lats = ec.codes_get_array(handle, "latitudes")
                lons = ec.codes_get_array(handle, "longitudes")
                values = ec.codes_get_values(handle)
                mask = ((lats >= BOUNDS['south']) & (lats <= BOUNDS['north']) &
                        (lons >= BOUNDS['west']) & (lons <= BOUNDS['east']))
                if not np.any(mask):
                    raise ValueError("GRIB does not cover India bounding box")
                def timestamp(date, time):
                    return datetime.strptime(f"{date}{int(time):04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                fields.append(Field(
                    timestamp(meta['dataDate'], meta['dataTime']),
                    timestamp(meta['validityDate'], meta['validityTime']),
                    int(meta['startStep']), int(meta['endStep']), meta['units'],
                    tuple(lats[mask].tolist()), tuple(lons[mask].tolist()),
                    tuple(values[mask].tolist()), meta['shortName'], meta['stepType']))
                metadata.append(meta)
            finally:
                ec.codes_release(handle)
    return fields, metadata


def atomic_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(payload, output, allow_nan=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=48, choices=range(6, 73, 3))
    parser.add_argument("--source", choices=["aws", "ecmwf", "google"], default="aws")
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    # Bound socket operations; invoke with an outer process timeout for a total limit.
    socket.setdefaulttimeout(60)
    from ecmwf.opendata import Client
    client = Client(source=args.source, model="ifs", resol="0p25")
    # Discover availability at the last requested step, then pin EVERY field to
    # that run. A disappearing/incomplete run fails without replacing old cache.
    run = client.latest(type="fc", param="tp", step=args.hours)
    args.output.mkdir(parents=True, exist_ok=True)
    run_id = run.strftime("%Y%m%dT%H%MZ")
    raw_path = args.output / f"ifs-{run_id}.grib2"
    request = dict(date=run.strftime("%Y%m%d"), time=run.hour, type="fc", param="tp",
                   step=list(range(3, args.hours + 1, 3)))
    client.retrieve(**request, target=str(raw_path))
    fields, metadata = decode(raw_path)
    processed = interval_rainfall(fields)
    if len(fields) != args.hours // 3 or processed['initialization'] != run.replace(tzinfo=timezone.utc).isoformat():
        raise ValueError("Retrieved run or field count differs from request")
    locations = []
    for key, (name, lat, lon) in CITIES.items():
        index = nearest_index(processed['latitudes'], processed['longitudes'], lat, lon)
        locations.append(dict(id=key, name=name, latitude=lat, longitude=lon,
                              grid_latitude=processed['latitudes'][index],
                              grid_longitude=processed['longitudes'][index], grid_index=index))
    # Independent decoded-GRIB cross-check for a displayed city, without using
    # interval_rainfall's output as the expected value.
    sorted_fields = sorted(fields, key=lambda f: f.end_step)
    city = locations[0]
    index = city['grid_index']
    before, after = sorted_fields[:2]
    expected = max(0.0, after.values[index] * (1000 if after.units == 'm' else 1)
                   - before.values[index] * (1000 if before.units == 'm' else 1))
    actual = processed['intervals'][1]['rainfall_mm'][index]
    if abs(actual - expected) > 1e-9:
        raise ValueError("Decoded GRIB cross-check failed")
    check = dict(location=city['id'], grid_index=index, start_step=before.end_step,
                 end_step=after.end_step, decoded_before=before.values[index],
                 decoded_after=after.values[index], source_units=after.units,
                 expected_interval_mm=expected, displayed_interval_mm=actual)
    with raw_path.open('rb') as raw:
        grib_sha256 = hashlib.file_digest(raw, 'sha256').hexdigest()
    processed.update(run_id=run_id, model="IFS deterministic", resolution_degrees=0.25,
                     retrieved_at=datetime.now(timezone.utc).isoformat(), bounds=BOUNDS,
                     locations=locations, grib_metadata=metadata, request=request,
                     source=args.source, grib_sha256=grib_sha256,
                     cross_check=check,
                     attribution="ECMWF Open Data, CC BY 4.0",
                     limitations="Deterministic precipitation forecast; no calibrated probabilities. Nearest grid point, not a station observation. Includes snow water equivalent.")
    atomic_json(args.output / f"{run_id}.json", processed)
    atomic_json(args.output / "latest.json", processed)
    print(json.dumps({"run_id": run_id, "fields": len(fields), "grib_metadata": metadata,
                      "cross_check": check}, indent=2))


if __name__ == "__main__":
    main()
