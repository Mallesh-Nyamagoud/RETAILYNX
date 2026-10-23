import assert from "node:assert/strict";
import test from "node:test";
import { canLoadSohSummary, getSohSourceError, hasSohSourceRefreshFailure } from "../src/utils/sohQueryState.js";

test("cached SOH dates survive a failed background refresh", () => {
  const error = new Error("Request failed with status code 500");
  const dates = { data: { dates: ["2026-07-01", "2026-08-01"] }, error, isError: true };
  assert.equal(canLoadSohSummary(dates, "2026-07-01", "2026-08-01"), true);
  assert.equal(getSohSourceError(dates), null);
  assert.equal(hasSohSourceRefreshFailure(dates), true);
});

test("first-load source errors remain visible and do not start summary requests", () => {
  const error = new Error("SOH dates could not load");
  const dates = { data: undefined, error, isError: true };
  assert.equal(canLoadSohSummary(dates, "", ""), false);
  assert.equal(getSohSourceError(dates), error);
  assert.equal(hasSohSourceRefreshFailure(dates), false);
});
