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
while the process is running, the application attempts an ECMWF refresh every
six hours; a failed refresh preserves the last validated cache and reports its
age and staleness. Map tiles come from OpenStreetMap.

## Deploy on Render

The repository includes a Render Blueprint at `render.yaml`. In Render, create
a Blueprint from `Lig17/quest-rainsight` on the `main` branch and apply the
Docker Web Service configuration. It selects the Free plan in Singapore,
checks `/api/health`, bundles the verified processed forecast snapshot, and
enables best-effort ECMWF refresh at startup and every six hours while the
service is running.

The bundled forecast remains available if a refresh fails. The app reports the
retrieval age and model initialization time, and labels old data as stale. A
successful refresh writes to the container's local filesystem; Render Free
services have ephemeral storage, so that refreshed cache can disappear after a
restart, redeploy, or idle spin-down. The committed snapshot is the fallback on
the next start. Free services also sleep after 15 minutes without traffic, so
the six-hour refresh is not a guaranteed schedule while the service is asleep.
The first request after sleep can take about a minute to wake the service.

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

The Docker image includes the processed real forecast cache and refreshes it at
runtime. The temporary review URL uses an account-free Cloudflare Quick Tunnel
and the current host process, so it has no uptime guarantee. The Render
Blueprint is prepared, but its public service has not yet been deployed. See
[DEVELOPMENT.md](docs/DEVELOPMENT.md) for the chronological record and actual
test outcomes.

All development was done in the original session. The original JSONL transcript
is in Codex-managed session storage outside this repository. It was checked
read-only for this application's title and transcript-preservation instruction;
it was not copied into or directly modified by this project.

The environment mounts `.git` read-only. Authentic commit history is in
`.rainsight-git`, including the initial milestone commit; use:

```bash
git --git-dir=.rainsight-git --work-tree=. status
git --git-dir=.rainsight-git --work-tree=. log --oneline
```
