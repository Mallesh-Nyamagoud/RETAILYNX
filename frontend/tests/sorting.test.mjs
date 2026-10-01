/**
 * Unit tests for the shared sorting helper.
 *
 * Run from c:\webapp\frontend:
 *     node --test tests/sorting.test.mjs
 *
 * `applySorting` is the contract every grid that uses `manualSorting` relies on
 * (PivotTable, MonthwiseTable, MonthwiseRowsTable). Because those grids disable
 * TanStack's built-in `getSortedRowModel`, the parent MUST reorder the `data`
 * array itself - a header click that toggles the sort state but never touches
 * the rows is exactly the "sort not working" bug this pins against.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { applySorting } from "../src/utils/sorting.js";

test("no sorting state returns the rows untouched", () => {
  const rows = [{ v: 2 }, { v: 1 }, { v: 3 }];
  assert.equal(applySorting(rows, []), rows);
  assert.equal(applySorting(rows, undefined), rows);
});

test("numeric column sorts ascending then descending", () => {
  const rows = [{ v: 3 }, { v: 1 }, { v: 2 }];
  assert.deepEqual(
    applySorting(rows, [{ id: "v", desc: false }]).map((r) => r.v),
    [1, 2, 3]
  );
  assert.deepEqual(
    applySorting(rows, [{ id: "v", desc: true }]).map((r) => r.v),
    [3, 2, 1]
  );
});

test("string column sorts with localeCompare in both directions", () => {
  const rows = [{ n: "Beta" }, { n: "alpha" }, { n: "Gamma" }];
  assert.deepEqual(
    applySorting(rows, [{ id: "n", desc: false }]).map((r) => r.n),
    ["alpha", "Beta", "Gamma"]
  );
  assert.deepEqual(
    applySorting(rows, [{ id: "n", desc: true }]).map((r) => r.n),
    ["Gamma", "Beta", "alpha"]
  );
});

test("null / undefined always sink to the bottom, both directions", () => {
  const rows = [{ v: 2 }, { v: null }, { v: 1 }, { v: undefined }];
  assert.deepEqual(
    applySorting(rows, [{ id: "v", desc: false }]).map((r) => r.v),
    [1, 2, null, undefined]
  );
  assert.deepEqual(
    applySorting(rows, [{ id: "v", desc: true }]).map((r) => r.v),
    [2, 1, null, undefined]
  );
});

test("the source array is never mutated", () => {
  const rows = [{ v: 3 }, { v: 1 }, { v: 2 }];
  const snapshot = rows.map((r) => r.v);
  applySorting(rows, [{ id: "v", desc: false }]);
  assert.deepEqual(rows.map((r) => r.v), snapshot);
});
