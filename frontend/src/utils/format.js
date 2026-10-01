const intFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const decFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 1,
  minimumFractionDigits: 1,
});
const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function fmtQty(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return intFormatter.format(value);
}

export function fmtVal(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return currencyFormatter.format(value);
}

export function fmtCompactVal(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(1)}K`;
  return currencyFormatter.format(value);
}

export function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${decFormatter.format(value)}%`;
}

export function fmtNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return decFormatter.format(value);
}

export function fmtDate(value) {
  if (!value) return "—";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return String(value);
  }
}

/** Adds a running-total (cumulative) column over the CURRENT row order -
 * recomputed every time the caller re-sorts, per the requirements doc:
 * "cumulative value must automatically recalculate ... whenever the
 * sorting/order changes." */
export function withCumulative(rows, key, { skipSubtotals = true } = {}) {
  let running = 0;
  return rows.map((row) => {
    if (skipSubtotals && row._is_total) {
      return { ...row, [`cumulative_${key}`]: null };
    }
    const v = Number(row[key]) || 0;
    running += v;
    return { ...row, [`cumulative_${key}`]: running };
  });
}

export function growthTone(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "neutral";
  if (value > 0.001) return "positive";
  if (value < -0.001) return "negative";
  return "neutral";
}

/** Dynamic Indian-scale compact number WITHOUT the rupee symbol - the single
 * label/axis formatter used by every dashboard chart (bar data labels, value
 * axis ticks, donut labels and tooltips):
 *
 *     1_00_00_000 -> "1.00Cr"    1_00_000 -> "1.00L"    1_000 -> "1.00K"
 *
 * Precision is dynamic so a label never lies about its magnitude and never
 * blows up the layout: two decimals while the scaled figure is under 10
 * ("1.00L"), one decimal under 100 ("12.4L") and none at or above 100
 * ("150L"). Values below 1_000 keep their plain en-IN grouping.
 */
export function fmtIndianCompact(value, { blank = "—" } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return blank;
  const num = Number(value);
  if (!Number.isFinite(num)) return blank;
  const abs = Math.abs(num);
  const scales = [
    { limit: 1e7, suffix: "Cr" },
    { limit: 1e5, suffix: "L" },
    { limit: 1e3, suffix: "K" },
  ];
  for (const { limit, suffix } of scales) {
    if (abs >= limit) {
      const scaled = num / limit;
      const magnitude = Math.abs(scaled);
      const decimals = magnitude >= 100 ? 0 : magnitude >= 10 ? 1 : 2;
      return `${scaled.toFixed(decimals)}${suffix}`;
    }
  }
  return intFormatter.format(num);
}
