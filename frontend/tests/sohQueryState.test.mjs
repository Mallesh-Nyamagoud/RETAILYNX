import assert from "node:assert/strict";
import test from "node:test";
import { canLoadSohSummary, getSohSourceError, hasSohSourceRefreshFailure } from "../src/utils/sohQueryState.js";

test("cached SOH dates and filters survive a failed background refresh", () => {
  const error = new Error("Request failed with status code 500");
  const dates = { data: { dates: ["2026-07-01", "2026-08-01"] }, error, isError: true };
  const filters = { data: { filters: {} }, error: null, isError: false };
  assert.equal(canLoadSohSummary(dates, filters, "2026-07-01", "2026-08-01"), true);
  assert.equal(getSohSourceError(dates, filters), null);
  assert.equal(hasSohSourceRefreshFailure(dates, filters), true);
});

test("first-load source errors remain visible and do not start summary requests", () => {
  const error = new Error("SOH dates could not load");
  const dates = { data: undefined, error, isError: true };
  const filters = { data: { filters: {} }, error: null, isError: false };
  assert.equal(canLoadSohSummary(dates, filters, "", ""), false);
  assert.equal(getSohSourceError(dates, filters), error);
  assert.equal(hasSohSourceRefreshFailure(dates, filters), false);
});
