/**
 * Unit tests for the Brand Share Shift maths (Category Performance chart).
 *
 * Run from c:\webapp\frontend:
 *     node --test tests/shareShift.test.mjs
 *
 * The payloads below are shaped exactly like the backend's
 * /tertiary/category-analysis response, so these tests pin the contract the
 * whole feature rests on:
 *
 *   cont%[brand, period] = brand_qty[period] / group_total_qty[period] * 100
 *   pp_change[brand]     = cont%_CFYTD - cont%_LFYTD
 *   Sum of pp_change per group is ~0
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_PERIOD_MASK,
  cellOf,
  computeShareShift,
  fmtPp,
  safeCont,
  str,
} from "../src/components/analysis/shareShift.js";

/** One measure cell, shaped like the backend's. */
function cell(saleLfy, saleLfytd, saleCfy) {
  return {
    sale_lfy: saleLfy,
    sale_lfytd: saleLfytd,
    sale_cfy: saleCfy,
    cont_pct_lfy: 0,
    cont_pct_lfytd: 0,
    cont_pct_cfy: 0,
  };
}

/* ---------------------------------------------------------------------------
 * Level-1 payload: 2 categories, 2 brands, 1 Overall row (single-level Row
 * Hierarchy, so rows2 carries level-1 rows only).
 *
 *   SHIRTS  total 100 / 100 / 100
 *     KILLER  60 / 60 / 40    ->  60% / 60% / 40%   pp -20
 *     LEVIS   40 / 40 / 60    ->  40% / 40% / 60%   pp +20
 *   DENIM   total 200 / 200 / 200
 *     KILLER  80 /  80 /  60  ->  40% / 40% / 30%   pp -10
 *     LEVIS  120 / 120 / 140  ->  60% / 60% / 70%   pp +10
 * ------------------------------------------------------------------------- */
function level1Payload() {
  return {
    categories: ["SHIRTS", "DENIM"],
    sub_categories: { SHIRTS: ["S1", "S2"], DENIM: ["D1"] },
    rows_level1: [
      {
        row_label: "Overall",
        is_overall: true,
        _level: 0,
        _data: { SHIRTS: cell(100, 100, 100), DENIM: cell(200, 200, 200) },
      },
      {
        row_label: "KILLER",
        is_overall: false,
        _level: 1,
        _data: { SHIRTS: cell(60, 60, 40), DENIM: cell(80, 80, 60) },
      },
      {
        row_label: "LEVIS",
        is_overall: false,
        _level: 1,
        _data: { SHIRTS: cell(40, 40, 60), DENIM: cell(120, 120, 140) },
      },
    ],
    rows_level2: [
      {
        row_label: "Overall",
        is_overall: true,
        _level: 0,
        _data: {
          SHIRTS: { S1: cell(50, 50, 50), S2: cell(50, 50, 50) },
          DENIM: { D1: cell(200, 200, 200) },
        },
      },
      {
        row_label: "KILLER",
        is_overall: false,
        _level: 1,
        _data: {
          SHIRTS: { S1: cell(40, 30, 20), S2: cell(20, 30, 20) },
          DENIM: { D1: cell(80, 80, 60) },
        },
      },
      {
        row_label: "LEVIS",
        is_overall: false,
        _level: 1,
        _data: {
          SHIRTS: { S1: cell(10, 20, 30), S2: cell(30, 20, 30) },
          DENIM: { D1: cell(120, 120, 140) },
        },
      },
    ],
  };
}

const approx = (a, b) => Math.abs(a - b) < 1e-9;
const shift = (mode, catName, result = level1Payload()) =>
  computeShareShift({ result, mode, catName });

test("categories mode returns one group per category, in payload order", () => {
  const { groups, cat } = shift("categories", "SHIRTS");
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.map((g) => g.key), ["SHIRTS", "DENIM"]);
  assert.deepEqual(groups.map((g) => g.label), ["SHIRTS", "DENIM"]);
  assert.equal(groups[0].subLabel, null);
  assert.equal(cat, "SHIRTS");
});

test("cont% is brand qty over the group total, per period", () => {
  const shirts = shift("categories", "SHIRTS").groups[0];
  assert.deepEqual(shirts.total, { lfy: 100, lfytd: 100, cfy: 100 });
  // Sorted by pp DESC: LEVIS (+20) first, KILLER (-20) last.
  assert.deepEqual(shirts.brands.map((b) => b.brand), ["LEVIS", "KILLER"]);
  const levis = shirts.brands[0];
  assert.equal(levis.contLfy, 40);
  assert.equal(levis.contLfytd, 40);
  assert.equal(levis.contCfy, 60);
  assert.equal(levis.pp, 20);
  assert.equal(levis.ppVsLfy, 20);
  const killer = shirts.brands[1];
  assert.equal(killer.contLfy, 60);
  assert.equal(killer.contLfytd, 60);
  assert.equal(killer.contCfy, 40);
  assert.equal(killer.pp, -20);
  assert.equal(shirts.unitEquiv, 1); // 100 units represented by 1 pp
});

test("DENIM group: same maths against a different group total", () => {
  const denim = shift("categories", "SHIRTS").groups[1];
  assert.deepEqual(denim.total, { lfy: 200, lfytd: 200, cfy: 200 });
  assert.deepEqual(denim.brands.map((b) => b.brand), ["LEVIS", "KILLER"]);
  assert.equal(denim.brands[0].contLfy, 60);
  assert.equal(denim.brands[0].contCfy, 70);
  assert.equal(denim.brands[0].pp, 10);
  assert.equal(denim.brands[1].contLfy, 40);
  assert.equal(denim.brands[1].contCfy, 30);
  assert.equal(denim.brands[1].pp, -10);
  assert.equal(denim.unitEquiv, 2); // 200 units / 100
});

test("pp changes sum to ~0 and each cont% column sums to 100 per group", () => {
  for (const g of shift("categories", "SHIRTS").groups) {
    assert.ok(approx(g.ppSum, 0), `${g.label} ppSum=${g.ppSum}`);
    for (const key of ["contLfy", "contLfytd", "contCfy"]) {
      const sum = g.brands.reduce((acc, b) => acc + b[key], 0);
      assert.ok(approx(sum, 100), `${g.label} ${key} sum=${sum}`);
    }
  }
});

test("the Overall row is the reference and never becomes a brand", () => {
  const { groups } = shift("categories", "SHIRTS");
  assert.ok(groups.every((g) => g.brands.every((b) => b.brand !== "Overall")));
});

test("rank change tracks the LFYTD -> CFYTD share order", () => {
  const shirts = shift("categories", "SHIRTS").groups[0];
  const levis = shirts.brands.find((b) => b.brand === "LEVIS");
  const killer = shirts.brands.find((b) => b.brand === "KILLER");
  assert.equal(killer.rankLfytd, 1); // 60% > 40%
  assert.equal(killer.rankCfy, 2); // 40% < 60%
  assert.equal(killer.rankDelta, -1);
  assert.equal(levis.rankLfytd, 2);
  assert.equal(levis.rankCfy, 1);
  assert.equal(levis.rankDelta, 1);
});

test("rows mode returns ONE group for the chosen category", () => {
  const { groups } = shift("rows", "DENIM");
  assert.equal(groups.length, 1);
  assert.equal(groups[0].key, "DENIM");
  assert.equal(groups[0].brands.length, 2);
});

test("subs mode returns one group per sub-category, keyed by parent category", () => {
  const { groups } = shift("subs", "SHIRTS");
  assert.deepEqual(groups.map((g) => g.label), ["S1", "S2"]);
  assert.deepEqual(groups.map((g) => g.subLabel), ["SHIRTS", "SHIRTS"]);
  assert.equal(groups[0].total.cfy, 50);
  // S1: KILLER 20/50=40% cfy vs 30/50=60% lfytd => -20 ; LEVIS +20
  assert.deepEqual(groups[0].brands.map((b) => b.brand), ["LEVIS", "KILLER"]);
  assert.equal(groups[0].brands[0].pp, 20);
  assert.equal(groups[0].brands[1].pp, -20);
  assert.ok(approx(groups[1].ppSum, 0));
});

test("an unknown catName falls back to the first category", () => {
  const r = shift("categories", "NOPE");
  assert.equal(r.cat, "SHIRTS");
  assert.equal(r.groups.length, 2);
});

test("missing / empty payloads yield no groups instead of throwing", () => {
  assert.deepEqual(shift("categories", "", null).groups, []);
  assert.deepEqual(shift("subs", "", {}).groups, []);
  assert.deepEqual(shift("rows", "", { categories: ["A"] }).groups, []);
});

test("brands with zero qty in every period are skipped", () => {
  const p = level1Payload();
  p.rows_level1.push({
    row_label: "GHOST",
    is_overall: false,
    _level: 1,
    _data: { SHIRTS: cell(0, 0, 0), DENIM: cell(0, 0, 0) },
  });
  const shirts = shift("categories", "SHIRTS", p).groups[0];
  assert.ok(shirts.brands.every((b) => b.brand !== "GHOST"));
  assert.equal(shirts.brands.length, 2);
});

test("a group that sold nothing produces no group at all", () => {
  const p = {
    categories: ["EMPTY"],
    sub_categories: {},
    rows_level1: [
      { row_label: "Overall", is_overall: true, _level: 0, _data: { EMPTY: cell(0, 0, 0) } },
      { row_label: "B1", is_overall: false, _level: 1, _data: { EMPTY: cell(0, 0, 0) } },
    ],
    rows_level2: [],
  };
  assert.deepEqual(shift("categories", "EMPTY", p).groups, []);
});

test("safeCont floors divide-by-zero at 0", () => {
  assert.equal(safeCont(5, 0), 0);
  assert.equal(safeCont(5, null), 0);
  assert.equal(safeCont(0, 10), 0);
  assert.equal(safeCont(null, 10), 0);
  assert.equal(safeCont(5, 10), 50);
});

test("fmtPp carries its own sign and unit", () => {
  assert.equal(fmtPp(2.34), "+2.3 pp");
  assert.equal(fmtPp(-2.34), "−2.3 pp");
  assert.equal(fmtPp(0), "±0.0 pp");
  assert.equal(fmtPp(null), "—");
  assert.equal(fmtPp(undefined), "—");
});

test("cellOf resolves level-1 and level-2 cells off the same payload", () => {
  const row = { _data: { SHIRTS: { sale_cfy: 1 }, DENIM: { S1: { sale_cfy: 2 } } } };
  assert.equal(cellOf(row, "SHIRTS").sale_cfy, 1);
  assert.equal(cellOf(row, "DENIM", "S1").sale_cfy, 2);
  assert.equal(cellOf(row, "DENIM", "S9"), null);
  assert.equal(cellOf(row, "NOPE"), null);
  assert.equal(cellOf(null, "SHIRTS"), null);
  assert.equal(cellOf(row, ""), null);
});

test("str mirrors the payload's string keying", () => {
  assert.equal(str(null), "");
  assert.equal(str(undefined), "");
  assert.equal(str(0), "0");
  assert.equal(str("DENIM"), "DENIM");
});

test("DEFAULT_PERIOD_MASK has every series on", () => {
  assert.deepEqual(DEFAULT_PERIOD_MASK, { lfy: true, lfytd: true, cfy: true });
});
