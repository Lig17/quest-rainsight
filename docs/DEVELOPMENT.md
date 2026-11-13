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
- Connectivity recovered. DNS resolved PyPI, data.ecmwf.int and ECMWF's AWS
  endpoint; HTTPS returned 200 for PyPI and the ECMWF portal. Installed all pinned
  requirements into `.venv` successfully.
- Retrieved real IFS `tp` GRIB from AWS, run 2026-11-12 18 UTC, steps 3 and 6,
  644,574 bytes. ecCodes decoded parameter 228, surface, accum, startStep 0,
  valid times 21 UTC and 00 UTC; both had zero missing values on a 1440x721
  regular lat-lon grid. India crop contains 15,625 points.
- First real processing attempt correctly failed because 192 India-grid cells
  showed negative differences, minimum -0.0305176 mm. Investigation found CCSDS
  packing, 12 bits, binary scales -15 and -14 (quanta 0.0305176 and 0.0610352
  mm). Their combined half-quantum bound is 0.0457764 mm, enough to explain the
  observed artifact. Processing now uses the field metadata-derived bound per
  interval and still rejects differences beyond it. A real ingestion rerun and
  independent city cross-check are pending.

## 2026-11-13 follow-up — connectivity, real GRIB validation, and app

- Corrected the earlier pending note: DNS and HTTPS recovered. `pypi.org`,
  `data.ecmwf.int`, and `ecmwf-forecasts.s3.eu-central-1.amazonaws.com` resolved;
  HTTPS to PyPI and ECMWF returned 200. Installed `requirements.txt` into `.venv`.
- A repeated request to the AWS mirror received HTTP 503 and began retrying after
  120 seconds. Stopped that retry and successfully retrieved the same run from
  the primary ECMWF endpoint instead.
- Retrieved 48 h of real IFS precipitation: run 2026-11-12 18 UTC, 16 fields for
  steps 3–48 h, raw GRIB size 6,331,912 bytes. GRIB metadata confirms `tp`,
  parameter 228, units m, surface, `stepType=accum`, `startStep=0`, three-hour
  step cadence, matching validity times, `typeOfStatisticalProcessing=1`, and
  zero missing values on a regular 1440×721 grid. The India crop has 15,625 cells.
- Independently decoded Chennai's step-3 value of 0.00018310546875 m; multiplied
  by 1000 this is 0.18310546875 mm, exactly the published first-interval value.
- CCSDS packing metadata explains small negative differences: at steps 3 and 6
  the decoded quanta are 0.030517578125 mm and 0.06103515625 mm. The observed
  minimum difference, -0.030517578125 mm, is within the combined half-quantum
  bound, 0.0457763671875 mm. Processing now records each bound and clips/counts
  only differences within it; larger decreases still fail validation.
- Added FastAPI endpoints and static UI: run freshness, supported locations,
  interval timeline and threshold, location values and totals, GeoJSON map cells,
  and full GRIB provenance. API refresh runs in the background every six hours;
  failed refreshes preserve the validated cache.
- First API suite run had one spatial downsampling test failure because the
  fixture points were one degree apart, not adjacent 0.25-degree cells. Fixed
  the fixture and bucket aggregation. Final `python -m unittest discover -s
  tests -v`: 15 tests passed. `node --check web/app.js` and Python compileall
  also passed.
- Live Uvicorn smoke checks returned HTTP 200 for `/`, `/api/health`, `/api/runs`,
  `/api/locations`, `/api/timeline`, `/api/location/chennai`, `/api/spatial`,
  and `/api/provenance`. The actual cache returned Chennai 0.183 mm and 3,969
  spatial cells.
- Docker build completed. Container smoke check reported real run
  `20261112T1800Z`, rendered the page, and returned Chennai 0.183 mm. Image build
  and container tests used the exact processed real forecast cache.
- Found and verified the original session transcript read-only at
  `/home/lighittha/.codex/sessions/2026/11/13/rollout-2026-11-13T08-58-37-01a1d2f3-376e-7081-a293-afcb412143c3.jsonl`. It contains the unique application title
  and preservation instruction. Its SHA-256 is
  `ec39318d5ec57cb2db78a3063a784d7e6442c22324ee7803a86e81220268ba0d`; the file
  was not edited, copied, or regenerated.
- Deployment CLI checks found no authenticated cloud hosting or registry account.
  Docker Engine 28.3.3 and `cloudflared` are available. Durable public deployment
  still needs an account/authorization step. No public URL has been verified.

## 2026-11-13 follow-up — clean image and public verification

- Added the verified processed run JSON as a small initial application snapshot and
  a fallback when `latest.json` does not yet exist. Raw GRIB remains ignored. This
  makes Docker build from a fresh source checkout viable while the background
  refresh attempts a newer run.
- Added a unit case for snapshot fallback. Final suite now reports 16 passing
  tests; JS syntax and Python compile checks pass.
- Rebuilt `rainsight:0.3.1` with the fully pinned `requirements.lock`. Confirmed
  the image contains the single committed run snapshot and no `latest.json`.
  Container health and Chennai's 0.183 mm field pass using this fallback.
- Exposed the running application through an account-free Cloudflare Quick
  Tunnel. From the public HTTPS URL, GET requests to `/`, health, runs, locations,
  timeline, Chennai, spatial GeoJSON, and provenance all returned HTTP 200. Public
  checks confirmed the real run, 0.183 mm Chennai value, and 3,969 map cells.
  The tunnel is currently tied to this host process and has no uptime guarantee.
- Cloud hosting and registry logins are absent in this environment. Render is a
  viable Docker host, but its own documentation describes Free services as a
  preview tier; they sleep after 15 minutes idle, lose local filesystem changes
  on sleep/restart, and receive 750 instance hours per workspace/month. Durable
  hosting still requires the user's provider login and plan choice.

## 2026-11-13 follow-up — interval clock labels

- Final interface review found a presentation defect: interval values were
  formatted in Asia/Kolkata but labeled UTC. Corrected all interval/map/timeline
  labels to IST with local calendar dates, while the initialization remains UTC.
  Chennai is now the initial selected city so the independently cross-checked
  nonzero forecast is visible immediately.
- Rebuilt `rainsight:0.3.2`; fresh-container checks confirmed the Chennai value,
  Chennai default, IST labels, and date labels. Replaced the public tunnel's
  container and rechecked its HTTPS URL: all 10 page, API, and asset GET routes
  returned 200; the page is still serving run `20261112T1800Z` and health reports
  `stale=false` at verification time.
