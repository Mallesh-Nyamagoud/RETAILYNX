/* One-off validation: runs the SHIPPED computeShareShift() against a REAL
 * /tertiary/category-analysis payload dumped from the backend.
 *
 *   cd backend; .venv\Scripts\python.exe tmp\dump_category_payload.py
 *   cd frontend; node tests/validateRealPayload.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { computeShareShift } from "../src/components/analysis/shareShift.js";

const payload = JSON.parse(
  readFileSync(new URL("../../backend/tmp/category_payload.json", import.meta.url), "utf8")
);

console.log("payload categories  :", payload.categories.length, payload.categories.join(", "));
console.log("rows_level1 brands  :", payload.rows_level1.map((r) => r.row_label).join(", "));

const { groups } = computeShareShift({
  result: payload,
  mode: "categories",
  catName: payload.categories[0],
});

console.log("groups produced     :", groups.length);
assert.equal(groups.length, payload.categories.length, "one group per category");

let grandPp = 0;
for (const g of groups) {
  assert.ok(g.brands.length >= 1, `${g.label} must have brands`);
  assert.ok(
    g.brands.every((b) => b.brand !== "Overall"),
    `${g.label} must not contain the Overall reference row as a brand`
  );
  const ppSum = g.brands.reduce((a, b) => a + b.pp, 0);
  assert.ok(Math.abs(ppSum) < 1e-6, `${g.label} ppSum=${ppSum} must be ~0`);
  for (const key of ["contLfy", "contLfytd", "contCfy"]) {
    const s = g.brands.reduce((a, b) => a + b[key], 0);
    assert.ok(Math.abs(s - 100) < 1e-6, `${g.label} ${key} sum=${s} must be 100`);
  }
  for (let i = 1; i < g.brands.length; i++) {
    assert.ok(g.brands[i - 1].pp >= g.brands[i].pp, `${g.label} must be pp-DESC sorted`);
  }
  grandPp += ppSum;
  console.log(
    `  ${g.label.padEnd(13)} cfy=${String(g.total.cfy).padStart(8)}  unitEquiv=${g.unitEquiv.toFixed(2)}  ` +
      `ppSum=${ppSum.toExponential(2)}  brands=${g.brands.length}`
  );
}
console.log("grand sum of pp     :", grandPp.toExponential(3));

const sample = groups.find((g) => g.label === "DENIM") || groups[0];
console.log(`\nOBSERVED SHIFT - ${sample.label} (sorted biggest gainer first):`);
for (const b of sample.brands) {
  console.log(
    `  ${b.brand.padEnd(13)} LFY ${b.contLfy.toFixed(1).padStart(5)}%  LFYTD ${b.contLfytd
      .toFixed(1)
      .padStart(5)}%  CFYTD ${b.contCfy.toFixed(1).padStart(5)}%  ` +
      `pp ${(b.pp >= 0 ? "+" : "") + b.pp.toFixed(2)}  rank ${b.rankLfytd}->${b.rankCfy}`
  );
}

console.log("\nALL REAL-PAYLOAD CHECKS PASSED");
