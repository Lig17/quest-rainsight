# Chronological development notes

These notes are an engineering record, not a replacement for the original raw
session JSONL. The transcript must remain untouched.

## 2026-11-13 — environment and scientific core

- Earlier terminal attempts in this session failed in Bubblewrap before execution.
- Execution subsequently passed: project `/home/lighittha/quest-rainsight`,
  Python 3.12.3, Git 2.43.0. Workspace contained only empty protected directories.
- `.git` is a read-only mount; ordinary `git init` failed. Initialized real Git
  metadata in `.rainsight-git` inside the writable project instead. Commands use
  `git --git-dir=.rainsight-git --work-tree=.` until the mount is repaired.
- Official ECMWF client documentation consulted. Selected deterministic IFS
  0.25-degree tp fields, a limited step range, and local India cropping.
- Installing ingestion dependencies failed because PyPI DNS was unavailable.
  Direct DNS checks also failed for ECMWF and its AWS mirror. No real acquisition
  or GRIB metadata verification has occurred at this stage.
- Implemented an offline scientific core which only accepts startStep=0 hourly
  accumulations. It validates timestamps, coordinates, units, run/grid consistency,
  and cadence before differencing. This is an explicit supported contract to be
  checked against actual GRIB metadata, not a claim about an acquired field.
- Deterministic forecasts provide no calibrated probabilities, flood warnings,
  or uncertainty estimates. Precipitation includes snow water equivalent.
- Executed `python3 -m unittest discover -s tests -v`: all nine test methods
  passed, including malformed-input subcases. Compilation also passed.
- Added ingestion using official client retrieval, metadata inspection, raw-file
  SHA-256, India cropping, city extraction, independent decoded-value cross-check,
  and atomic validated cache publication. Its execution stopped on the missing
  `ecmwf` import because installation was blocked; it has not decoded real data.
- Pinned the current published ECMWF client 0.3.35 and ecCodes Python 2.50.1
  after checking PyPI release information. Full dependency installation and
  compatibility remain unverified. No deployment or API tests are claimed.
