# Chronological development notes

These notes are an engineering record, not a replacement for the original raw
session JSONL. The transcript must remain untouched.

## 2026-11-13 — environment and scientific core

- Earlier terminal attempts in this session failed in Bubblewrap before execution.
- Execution subsequently passed in the original project workspace, Python
  3.12.3, Git 2.43.0. Workspace contained only empty protected directories.
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
- Found and checked the original session transcript read-only in Codex-managed
  session storage. Checks confirmed the application title and preservation
  instruction are present. The file was not directly edited, copied, or
  regenerated.
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

## 2026-11-13 follow-up — publication and Render preparation

- GitHub's read-only repository API returned HTTP 200 for
  `Lig17/quest-rainsight`: public, default branch `main`, with no contents. The
  existing `.rainsight-git` history still contains the five original commits in
  their original order.
- Scanned every tracked blob in all five commits for private-key markers,
  GitHub tokens, AWS access-key patterns, and credential assignments; no pattern
  matches were found. The historical commits do contain personal author
  metadata and an earlier documentation reference to the local transcript path.
  The local path was removed from the current README and development notes; the
  original commits were not rewritten, so those historical metadata remain.
- Read the official ECMWF Open Data terms. Updated the visible credit with the
  full institution name, copyright, CC BY 4.0 and Terms of Use links, the India
  crop/interval-conversion modification note, and the ECMWF liability disclaimer.
  The repository has no separate software licence; the ECMWF data licence does
  not cover the application code.
- Added `render.yaml` for a Docker Free Web Service in Singapore with
  `/api/health`, bundled-snapshot startup, and best-effort ECMWF refresh enabled.
  Render's current Free-service documentation says services sleep after 15
  minutes idle and local filesystem changes disappear on sleep or restart; the
  bundled forecast remains the startup fallback and the freshness API reports
  its model run age.
- After these changes, `python -m unittest discover -s tests -v` reported 16
  passing tests; `node --check web/app.js`, Python compilation, and local
  `render.yaml` parsing/configuration checks passed.
- No GitHub authentication, push, or Render deployment has occurred yet.
- Rebuilt Docker image `rainsight:0.3.4`. With auto-refresh disabled, a fresh
  container served the committed run from `/app/data` with neither
  `latest.json` nor raw GRIB present, confirming the image snapshot is sufficient
  after an ephemeral-storage reset.
- Started a separate auto-refresh-enabled container with a 512 MiB memory limit
  and 0.1 CPU quota. Health served the bundled snapshot before refresh completed;
  startup ingestion then wrote a valid latest cache. The successful refresh
  still selected run `20261112T1800Z`, reported retrieval age 0.04 h and run age
  11.8 h, and stayed below the memory limit (observed peak 191.3 MiB). A new
  container still starts from the bundled snapshot. Free-tier idle sleeping
  means the six-hour in-process loop is best-effort while the service is awake.
- Final container HTTP checks returned 200 for the page, health, timeline,
  location, spatial map, and provenance. The page identified ECMWF terms and
  licence; Chennai's first interval was 0.183 mm, the timeline had 16 intervals,
  and the map returned 3,969 aggregated cells.
- A headless Chromium mobile emulation at 390 CSS pixels reported no horizontal
  overflow. All four navigation links, 16 timeline slots, eight supported
  locations, the Leaflet map layer, and a rendered two-city comparison chart
  were present. The chart used Bengaluru and Mumbai in the browser check.
- GitHub CLI 2.104.0 was placed under `/tmp` after verifying its SHA-256 against
  the official release checksum file. Browser/device authentication has not
  been started, so no authentication code or token was captured in this log.


## 2026-11-14 — live freshness and elapsed-interval audit

- Read-only live checks at 2026-11-14 16:10 UTC returned the same run ID from
  health, provenance, timeline, Chennai, and spatial endpoints:
  `20261114T0600Z`. The API reported retrieval at 16:10 UTC, run age 10.2 h,
  cache age 0.03 h, `stale=false`, 16 intervals, and horizon end
  2026-11-16 06 UTC. ECMWF's official client `latest(type=fc,param=tp,step=48)`
  lookup on both the ECMWF portal and AWS returned `20261114T0600Z` at
  15:38 UTC. The 12 UTC run was not yet available at that check; retrieval age
  was not mistaken for initialization age.
- The published app initialized the timeline at step 3 (06–09 UTC) after that
  interval had ended. The bundled commit snapshot is initialized 2026-11-12
  18 UTC and its 48 h horizon ends 2026-11-14 18 UTC. Before this correction,
  `/api/health` still set `forecast_available=true` after all snapshot intervals
  ended, though the age-based `stale` flag would be true.
- Live GRIB provenance for the 06 UTC run identified 16 CCSDS-packed fields,
  parameter 228 (`tp`), units metres, `stepType=accum`, and `startStep=0`.
  Per-field half-quantum error bounds ranged from 0.0152588 to 0.1220703 mm;
  adjacent-field interval tolerance peaked at 0.244140625 mm. The decoded
  Chennai step-3 value 0.000152587890625 m converted to 0.152587890625 mm and
  matched the displayed value exactly. The run reported 1,740 clipped negative
  grid-cell differences, each constrained by its adjacent packing bounds; the
  larger-decrease regression rejects differences beyond that bound.
- The focused correction adds elapsed/in-progress/upcoming phase labels,
  prevents selection of elapsed intervals, selects the first still-valid
  interval by default, exposes an explicit expired horizon in freshness/health,
  waits up to five minutes for a post-restart refresh, and pins browser API calls
  to the run selected by health. Regression coverage includes expired snapshots,
  interval phase, and failed-refresh cache preservation.


## 2026-11-14 — restart fallback and future-window correction

- A second read-only public audit at 16:46 UTC returned HTTP 200 for the
  homepage, health, provenance, timeline, Chennai, and spatial endpoints. The
  Render instance had restarted onto the bundled `20261112T1800Z` snapshot,
  retrieved at 2026-11-13 04:11 UTC. It reported run age 46.9 h, cache age
  36.74 h, and `stale=true`. The horizon ended at 18 UTC; at the check only the
  15–18 UTC interval remained, and it was already in progress. A fresh read of
  ECMWF's supported Python client `latest(type=fc,param=tp,step=48)` returned
  `20261114T0600Z` from both the ECMWF portal and AWS mirror. Therefore Render
  was serving the old fallback, not the latest available run. This was a
  genuine freshness weakness after ephemeral-storage restart.
- At 16:46 UTC the prior API still reported `forecast_available=true` for that
  run. Its last amount covered a three-hour interval that had already begun;
  using that full-period total as a future interval could mislead a user. The
  new health contract requires at least one interval start time in the future.
  It reports in-progress and fully expired states separately, and exposes the
  remaining and upcoming interval counts.
- The browser now waits up to 20 minutes for startup refresh when no complete
  future interval is present, shows the waiting state, selects the first
  upcoming interval by default, and pins requests to the run ID chosen by
  health so a refresh cannot mix model runs during one page load. It continues
  to allow explicit inspection of a still-in-progress interval when a future
  forecast is available.
- Regression check: `.venv/bin/python -m unittest discover -s tests -v` ran 19
  tests, all passed. `node --check web/app.js` and `git diff --check` passed.
  Docker build `rainsight:audit2` succeeded (image SHA-256
  `e0a963b367125c430bb20299c1905ce82aed85f37bff22245843471abdbda11c`). A
  temporary container on port 18766 returned HTTP 200 for `/` and health. With
  the bundled snapshot at the then-current time, health correctly returned
  `forecast_available=false`, `expired=false`, one remaining interval, zero
  upcoming intervals, and the in-progress phase. The first local container
  attempt could not bind port 8765; the smoke check was rerun successfully on
  18765 and then 18766. Temporary containers were stopped after checking.
- The raw GRIB evidence remains consistent with the processing policy:
  16 fields, `tp`/228, metres, `stepType=accum`, `startStep=0`, and
  `typeOfStatisticalProcessing=1`. CCSDS packing-derived per-field half-quantum
  bounds are summed for adjacent cumulative fields; the test suite covers a
  bounded negative increment and rejects a large negative decrease. The
  displayed city field is independently cross-checked against decoded GRIB.
- This correction is local and has not yet been pushed or deployed at the time
  of this entry. The preceding public source remains commit `5379514`; final
  publication and Render checks must be appended after they are observed.
