"""Dependency-free scientific core. All amounts are water-equivalent precipitation."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import cos, isfinite, radians


@dataclass(frozen=True)
class Field:
    initialization: datetime
    valid_time: datetime
    start_step: int
    end_step: int
    units: str
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    values: tuple[float, ...]
    short_name: str = "tp"
    step_type: str = "accum"


def validate(field: Field) -> None:
    if field.initialization.utcoffset() != timedelta(0):
        raise ValueError("Initialization must have an explicit UTC timezone")
    if field.valid_time.utcoffset() != timedelta(0):
        raise ValueError("Valid time must have an explicit UTC timezone")
    if type(field.start_step) is not int or type(field.end_step) is not int:
        raise ValueError("Forecast steps must be integer hours")
    if field.start_step != 0 or field.end_step <= 0:
        raise ValueError("Only positive steps accumulated from initialization are supported")
    if field.valid_time != field.initialization + timedelta(hours=field.end_step):
        raise ValueError("Valid time does not match initialization plus end step")
    if field.short_name != "tp" or field.step_type != "accum":
        raise ValueError("Expected accumulated total precipitation")
    if field.units not in ("m", "mm", "kg m**-2"):
        raise ValueError(f"Unsupported precipitation units: {field.units}")
    if not field.values or not (len(field.values) == len(field.latitudes) == len(field.longitudes)):
        raise ValueError("Empty or inconsistent coordinate/value arrays")
    if not all(isfinite(x) for arr in (field.values, field.latitudes, field.longitudes) for x in arr):
        raise ValueError("Missing/nonfinite data")
    if any(not -90 <= x <= 90 for x in field.latitudes):
        raise ValueError("Invalid latitude")
    if any(not -180 <= x <= 360 for x in field.longitudes):
        raise ValueError("Invalid longitude")
    if len(set(zip(field.latitudes, field.longitudes))) != len(field.values):
        raise ValueError("Duplicate grid coordinates")


def interval_rainfall(fields: list[Field], cadence_hours: int = 3,
                      negative_tolerance_mm: float = 0.01) -> dict:
    """Convert cumulative fields; refuse gaps, reset accumulations, or mixed grids/runs.

    The zero baseline is mathematical: a startStep=0 accumulation starts at the
    initialization instant. It is not a fabricated forecast field.
    """
    if not fields or cadence_hours <= 0 or negative_tolerance_mm < 0:
        raise ValueError("Need fields, a positive cadence, and nonnegative tolerance")
    ordered = sorted(fields, key=lambda f: f.end_step)
    for field in ordered:
        validate(field)
    first = ordered[0]
    previous = [0.0] * len(first.values)
    previous_step = 0
    intervals = []
    clipped = 0
    for field in ordered:
        if (field.initialization != first.initialization or
            field.latitudes != first.latitudes or field.longitudes != first.longitudes):
            raise ValueError("Mixed initialization or inconsistent grid")
        if field.end_step - previous_step != cadence_hours:
            raise ValueError("Missing, duplicate, or unexpected forecast step")
        factor = 1000.0 if field.units == "m" else 1.0
        cumulative = [x * factor for x in field.values]
        if min(cumulative) < -negative_tolerance_mm:
            raise ValueError("Substantial negative accumulated precipitation")
        cumulative = [max(0.0, x) for x in cumulative]
        differences = [now - before for now, before in zip(cumulative, previous)]
        if min(differences) < -negative_tolerance_mm:
            raise ValueError("Substantial negative interval: possible reset or inconsistent fields")
        clipped += sum(x < 0 for x in differences)
        intervals.append({
            "start_step": previous_step, "end_step": field.end_step,
            "start_time": (field.initialization + timedelta(hours=previous_step)).isoformat(),
            "end_time": field.valid_time.isoformat(),
            "rainfall_mm": [max(0.0, x) for x in differences],
        })
        previous = cumulative
        previous_step = field.end_step
    return {"initialization": first.initialization.isoformat(), "units": "mm",
            "latitudes": list(first.latitudes), "longitudes": list(first.longitudes),
            "intervals": intervals, "clipped_negative_differences": clipped,
            "negative_tolerance_mm": negative_tolerance_mm}


def nearest_index(latitudes, longitudes, latitude: float, longitude: float) -> int:
    if not isfinite(latitude) or not isfinite(longitude) or not -90 <= latitude <= 90:
        raise ValueError("Invalid requested coordinate")
    if not -180 <= longitude <= 180 or not latitudes or len(latitudes) != len(longitudes):
        raise ValueError("Invalid longitude or grid")
    def distance(i):
        delta_lon = (longitudes[i] - longitude + 180) % 360 - 180
        return (latitudes[i] - latitude) ** 2 + (delta_lon * cos(radians(latitude))) ** 2
    return min(range(len(latitudes)), key=distance)
