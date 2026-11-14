# RainSight

RainSight is a small FastAPI application for exploring real ECMWF deterministic
precipitation forecasts over India. It shows the model run and data freshness,
three-hour interval amounts, a map, city comparisons, and processing provenance.

## Verified data

The local cache contains 16 real IFS fields for run 2026-11-12 18 UTC, forecast
steps 3–48 hours, retrieved from ECMWF Open Data. ecCodes confirmed total
precipitation (paramId 228), surface level, accumulated from startStep 0,
matching valid times, units metres, no missing values, and a regular 1440×721
lat-lon grid. The India crop contains 15,625 points.

An independent nonzero city cross-check uses Chennai: step 3 decoded
0.00018310546875 m, or 0.18310546875 mm, matching the processed first interval
exactly. The first field covers 0–3 h; later cumulative fields are differenced to
obtain consecutive three-hour amounts.

Direct dependency versions are pinned in `requirements.txt`; the complete
resolved environment from the successful install is captured in `requirements.lock`.
Ingestion discovers a run at the final requested step, pins every field to that initialization, selects
only `tp`, and crops to 6–37°N, 67–98°E after decoding. Open Data selection does
not perform server-side geographic cropping. The verified processed initial
snapshot is committed so a clean checkout can build and run; raw GRIB and future
run caches remain ignored by Git.

The converter requires GRIB `tp`/228, surface level, accumulated fields from
startStep zero, matching valid times and grids, and complete three-hour cadence.
Each interval is the difference between successive cumulative fields, converted
from metres to millimetres. It rejects gaps, malformed/nonfinite values, and
substantial negative differences. Real CCSDS-packed cumulative fields can decode
to small negative differences. The allowed bound is derived per interval from
the two fields' half-quantum error (`2**binaryScaleFactor *
10**(-decimalScaleFactor)`) converted to mm. Differences beyond that bound reject
the run, and clipped values are counted. Cache updates happen atomically only
after validation and an independent city-value cross-check.

The deterministic forecast provides no calibrated probabilities, uncertainty
intervals, flood risk, or official warnings. City values use the nearest 0.25°
grid point, not a station observation. Total precipitation is water equivalent
and includes frozen precipitation.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/uvicorn rainsight.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Set `RAINSIGHT_AUTO_REFRESH=0` to disable scheduled
downloads or `RAINSIGHT_DATA_DIR=/path/to/cache` to select another cache. While
the process is running, the application attempts an ECMWF refresh every six
hours; a failed refresh preserves the last validated cache and reports its age
and staleness. Map tiles come from OpenStreetMap.

## Public deployment

The application is deployed at [quest-rainsight-2glz.onrender.com](https://quest-rainsight-2glz.onrender.com) from the public `Lig17/quest-rainsight` GitHub repository. It uses the Docker Free Web Service configured in `render.yaml`. The service bundles the verified reference snapshot and attempts ECMWF refresh at startup and every six hours while awake.

Render Free has ephemeral local storage and sleeps after idle periods. A successful refresh can be lost on restart or spin-down; the bundled 2026-11-12 18 UTC snapshot is then the fallback. Its 48-hour horizon ended at 2026-11-14 18 UTC. RainSight reports model initialization separately from retrieval age and labels each interval elapsed, in progress, or upcoming. The health API reports a future forecast available only when at least one complete interval starts in the future; an in-progress interval's full-period total is not treated as a future interval. When a restart finds no complete future interval, the browser waits up to 20 minutes for the startup refresh and displays the wait. Expiry, when all interval end times have passed, is reported separately. The refresh loop retains the prior cache if ECMWF retrieval or validation fails. Since storage is ephemeral, freshness after restart still depends on a successful live refresh. A sleeping Free service may take about a minute to answer its first request.

## API

- `GET /api/health`
- `GET /api/runs`
- `GET /api/locations`
- `GET /api/timeline?threshold_mm=10`
- `GET /api/location/{location_id}?threshold_mm=10`
- `GET /api/spatial?end_step=3`
- `GET /api/provenance`

The responsive interface has an interval map, configurable threshold, location
analysis, comparison chart, and source-field provenance. API responses include
the run and freshness where relevant. Deterministic values are rainfall amounts,
never probabilities or calibrated uncertainty estimates.

## Source and licence

- [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [Official retrieval client](https://github.com/ecmwf/ecmwf-opendata)
- The forecast data and products are based on data and products of the European
  Centre for Medium-Range Weather Forecasts (ECMWF). Copyright © 2026 European
  Centre for Medium-Range Weather Forecasts (ECMWF).
- RainSight modifies the data by selecting the India coverage and converting
  cumulative total precipitation fields into three-hour interval amounts.
- ECMWF Open Data is published under the
  [Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
  and [ECMWF Terms of Use](https://apps.ecmwf.int/datasets/licences/general/).
  ECMWF does not accept liability for errors or
  omissions, availability, or loss or damage arising from use of its data.
- The RainSight source code has no separate software licence in this repository;
  the ECMWF data licence does not grant rights to the application code.

## Deployment and session record

The chronological live checks, source commits, test results, and deployment
status are recorded in [DEVELOPMENT.md](docs/DEVELOPMENT.md). Read the API's
model initialization and data freshness; page retrieval time is not a forecast
run time.

All development was done in the original session. The original JSONL transcript remains in Codex-managed session storage outside this repository. It was checked read-only; it was not copied into or directly modified by this project.

The environment mounts `.git` read-only. Authentic commit history is in
`.rainsight-git`; use:

```bash
git --git-dir=.rainsight-git --work-tree=. status
git --git-dir=.rainsight-git --work-tree=. log --oneline
```
