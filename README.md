# RainSight

Work in progress for the QUEST Lab precipitation forecast project. This is a real
data application under development, not a completed deployment.

## Current verified state

Terminal execution works. Nine offline scientific test methods pass. No real
forecast has yet been retrieved: the agent environment cannot resolve PyPI,
ECMWF, or its AWS mirror. GRIB decoding and cross-check code remain unexecuted.
There is no public deployment yet.

## Setup and ingestion

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
timeout 600 .venv/bin/python -m rainsight.ingest --hours 48 --source aws
python3 -m unittest discover -s tests -v
```

Direct dependency pins have not yet been installation-verified. The ingestion
command needs outbound HTTPS. It discovers a run at the final requested step,
pins the request to that initialization, selects only `tp` fields, and crops to
6–37°N, 67–98°E after decoding. Open Data field selection is not server-side
geographic subsetting. Raw GRIB and processed caches are ignored by Git.

It requires GRIB `tp`/228, surface, accumulated, hourly steps, zero startStep,
matching valid times and grids, and complete 3-hour cadence. Each interval is
the difference between successive accumulations, converted to millimetres.
The first accumulation spans initialization to +3h. Missing steps, resets,
nonfinite values, and substantive negative differences reject the run. Negative
differences up to 0.01 mm are clipped and counted; this explicit numerical
tolerance is provisional pending real-data inspection. A city cross-check records
the two decoded input values and the resulting displayed interval. Cache writes
occur only after validation; failed ingestion preserves the previous cache.

Nearest grid point extraction approximates a location, and amounts represent
water-equivalent precipitation, including snow. A deterministic model does not
provide calibrated uncertainty, probability, flood risk, or official warnings.

## Source and licence

- [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [Official retrieval client](https://github.com/ecmwf/ecmwf-opendata)
- Forecast attribution: ECMWF Open Data, CC BY 4.0.

## Session and Git integrity

All work occurs in the original session. No raw JSONL log is edited or generated
by this project. `docs/DEVELOPMENT.md` is a separate chronological engineering
record. The genuine original transcript has not yet been located.

The environment mounts `.git` read-only. Authentic commits currently use:

```bash
git --git-dir=.rainsight-git --work-tree=. status
git --git-dir=.rainsight-git --work-tree=. log --oneline
```

Keep `.rainsight-git` intact: it contains the real history. Once `.git` is writable,
the metadata can be migrated without rewriting commits.
