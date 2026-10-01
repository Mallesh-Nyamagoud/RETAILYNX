/**
 * Unit tests for the Dashboard's dynamic number formatting.
 *
 * Run from c:\webapp\frontend:
 *     node --test tests/format.test.mjs
 *
 * These pin the contract every Dashboard chart label / axis tick / tooltip
 * relies on: monetary values are rendered on the INDIAN scale (Cr / L / K) with
 * the precision following the magnitude, so a label reads "1.00Cr" for 1 crore,
 * "1.00L" for 1 lakh, "1.00K" for a thousand, and never grows wider than the
 * bar it sits on.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { fmtIndianCompact } from "../src/utils/format.js";

test("crore scale: scaled value under 10 keeps two decimals", () => {
  assert.equal(fmtIndianCompact(1e7), "1.00Cr");
  assert.equal(fmtIndianCompact(12345678), "1.23Cr");
  assert.equal(fmtIndianCompact(9.99e7), "9.99Cr");
});

test("lakh scale: two decimals under 10, one decimal under 100", () => {
  assert.equal(fmtIndianCompact(1e5), "1.00L");
  assert.equal(fmtIndianCompact(123456), "1.23L");
  assert.equal(fmtIndianCompact(1e6), "10.0L");
  assert.equal(fmtIndianCompact(9.5e6), "95.0L");
});

test("above 100 units the suffix form drops to whole numbers", () => {
  assert.equal(fmtIndianCompact(1e9), "100Cr");
  assert.equal(fmtIndianCompact(2.5e9), "250Cr");
  assert.equal(fmtIndianCompact(5e7), "5.00Cr");
});

test("thousand scale uses the same dynamic precision", () => {
  assert.equal(fmtIndianCompact(1000), "1.00K");
  assert.equal(fmtIndianCompact(12345), "12.3K");
  assert.equal(fmtIndianCompact(99999), "100.0K");
});

test("the crore/lakh boundary switches to the next suffix", () => {
  assert.equal(fmtIndianCompact(999999), "10.00L");
  assert.equal(fmtIndianCompact(9999999), "100.0L");
  assert.equal(fmtIndianCompact(1e7), "1.00Cr");
});

test("values below a thousand keep plain en-IN grouping", () => {
  assert.equal(fmtIndianCompact(0), "0");
  assert.equal(fmtIndianCompact(999), "999");
});

test("negatives keep their sign on the same scale", () => {
  assert.equal(fmtIndianCompact(-2345678), "-23.5L");
  assert.equal(fmtIndianCompact(-1e7), "-1.00Cr");
});

test("missing values render the blank placeholder", () => {
  assert.equal(fmtIndianCompact(null), "\u2014");
  assert.equal(fmtIndianCompact(undefined), "\u2014");
  assert.equal(fmtIndianCompact(NaN), "\u2014");
  assert.equal(fmtIndianCompact("not a number"), "\u2014");
});

test("chart labels can ask for an empty string instead of the placeholder", () => {
  assert.equal(fmtIndianCompact(null, { blank: "" }), "");
  assert.equal(fmtIndianCompact(0, { blank: "" }), "0");
});
