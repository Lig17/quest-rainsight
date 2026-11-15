"use strict";

const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const vm = require("node:vm");

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {promise, resolve};
}

function responseFor(latitude) {
  const start = "2026-11-15T21:00:00+00:00";
  const end = "2026-11-16T00:00:00+00:00";
  return {
    run_id: "20261115T0000Z", initialization: "2026-11-15T00:00:00+00:00",
    retrieved_at: "2026-11-15T08:55:47+00:00", model: "IFS deterministic", source_units: "m", units: "mm",
    threshold_mm: 10, interval_total_mm: latitude,
    selection: {clicked_latitude: latitude, clicked_longitude: 80, grid_latitude: latitude,
      grid_longitude: 80, grid_index: 0, method: "nearest actual ECMWF grid point"},
    freshness: {expired: false, stale: false, cache_age_hours: 1, run_age_hours: 10},
    intervals: [{start_step: 21, end_step: 24, start_time: start, end_time: end,
      phase: "upcoming", rainfall_mm: latitude, cumulative_mm: latitude,
      threshold_crossed: false, rounding_tolerance_mm: 0.01}],
  };
}

const mobileStyles = readFileSync("web/styles.css", "utf8");
assert.match(mobileStyles, /\.method-section\{grid-template-columns:minmax\(0,1fr\);min-width:0;/,
  "the mobile method grid must be allowed to shrink inside the viewport");
assert.match(mobileStyles, /\.method-title,\.method-grid article\{min-width:0\}/,
  "mobile grid children must not restore intrinsic-width overflow");

async function main() {
  const elements = new Map();
  const document = {querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      textContent: "", innerHTML: "", className: "", value: "", hidden: false,
      dataset: {}, querySelectorAll: () => [],
    });
    return elements.get(selector);
  }};
  const requests = [];
  const context = vm.createContext({document, window: {}, fetch: (url) => {
    const request = deferred();
    requests.push({url, ...request});
    return request.promise;
  }});
  const app = readFileSync("web/app.js", "utf8").replace(/\ninit\(\);\s*$/, "\nglobalThis.testApp = {state, loadCity};\n");
  vm.runInContext(app, context, {filename: "web/app.js"});
  const {state, loadCity} = context.testApp;
  state.runId = "20261115T0000Z";
  state.cityId = "chennai";
  state.threshold = 10;
  state.selectedStep = 24;
  state.timeline = {initialization: "2026-11-15T00:00:00+00:00", intervals: [
    {start_step: 21, end_step: 24, start_time: "2026-11-15T21:00:00+00:00",
      end_time: "2026-11-16T00:00:00+00:00", phase: "upcoming", max_grid_mm: 0,
      threshold_crossed_somewhere: false},
  ]};

  state.selectedPoint = {latitude: 10, longitude: 80};
  const olderRequest = loadCity();
  state.selectedPoint = {latitude: 20, longitude: 80};
  const newerRequest = loadCity();
  assert.equal(requests.length, 2);
  assert.ok(requests.every(({url}) => url.includes("run_id=20261115T0000Z")));

  requests[1].resolve({ok: true, json: async () => responseFor(20)});
  await newerRequest;
  requests[0].resolve({ok: true, json: async () => responseFor(10)});
  await olderRequest;

  assert.equal(state.pointForecast.selection.clicked_latitude, 20,
    "a late response for the earlier map click must not replace the newest selection");
  assert.equal(state.selectedPoint.latitude, 20);
}

main().then(() => process.stdout.write("Point request ordering and mobile CSS regression checks passed\n"))
  .catch((error) => { console.error(error); process.exitCode = 1; });
