/* ---------------------------------------------------------------------------
 * BRAND SHARE SHIFT - the pure data layer behind the "Share Shift (pp)"
 * measure of the Category Performance chart section.
 *
 * Deliberately framework-free (no React, no recharts) so the maths can be unit
 * tested directly, and it is a PURE function of the SAME payload the table
 * renders - the chart, its tooltip and the table fallback can therefore never
 * disagree with the KPI tables above them.
 *
 * For every group - one Category, or one Sub-Category inside the selected
 * Category:
 *
 *     cont%[brand, period] = brand_qty[period] / group_total_qty[period] * 100
 *     pp_change[brand]     = cont%_CFYTD - cont%_LFYTD
 *
 * The group total is read off the payload's OWN "Overall" row, which the
 * backend re-aggregates over the whole filtered context, so the denominator
 * always matches the numbers the table shows.
 *
 * `cont%_LFY` is carried as a REFERENCE value only; it never feeds the delta.
 * Brands are sorted by pp_change DESC, so the biggest gainer sits first and the
 * biggest loser last - the two opposite ends of the diverging chart. Because
 * every cont% column sums to 100 in each period, the brand pp changes sum to
 * ~0 per group, which is exactly what proves the share only MOVED.
 * ------------------------------------------------------------------------- */

export const DEFAULT_PERIOD_MASK = { lfy: true, lfytd: true, cfy: true };

/** Stringify a dimension value the same way the payload keys it. */
export function str(v) {
  return String(v ?? "");
}

/** Level-1 cells live at `_data[category]`, level-2 cells at
 * `_data[category][sub-category]` - both straight from the table payload. */
export function cellOf(row, cat, sub) {
  if (!row || !cat) return null;
  const byCat = row._data?.[str(cat)];
  if (!byCat) return null;
  return sub ? byCat[str(sub)] ?? null : byCat;
}

/** brand_qty / group_total_qty * 100 - floored at 0 when the group is empty. */
export function safeCont(numerator, denominator) {
  const d = Number(denominator) || 0;
  if (d <= 0) return 0;
  return ((Number(numerator) || 0) / d) * 100;
}

/** "+2.4 pp" / "−1.1 pp" - the sign is baked into the text so every caller can
 * colour the value without re-deriving the sign. */
export function fmtPp(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const v = Number(value);
  const sign = v > 0.001 ? "+" : v < -0.001 ? "−" : "±";
  return `${sign}${Math.abs(v).toFixed(1)} pp`;
}

export function computeShareShift({ result, mode, catName }) {
  const categories = result?.categories || [];
  const subCategories = result?.sub_categories || {};
  const rows1 = result?.rows_level1 || [];
  const rows2 = result?.rows_level2 || [];

  const overall1 = rows1.find((r) => r.is_overall) || null;
  const overall2 = rows2.find((r) => r.is_overall) || null;
  const bodies1 = rows1.filter((r) => !r.is_overall);
  // Level-2 rows carry the sub-category grain. With a single-level Row
  // Hierarchy there are no level-2 children, and the level-1 rows ARE the leaf
  // grain, so they are used as-is.
  const leaves2 = rows2.filter((r) => !r.is_overall && (r._level ?? 1) >= 2);
  const bodies2 = leaves2.length ? leaves2 : rows2.filter((r) => !r.is_overall);

  const buildGroup = (key, label, subLabel, overallCell, bodies, cellGetter) => {
    const total = {
      lfy: overallCell?.sale_lfy ?? 0,
      lfytd: overallCell?.sale_lfytd ?? 0,
      cfy: overallCell?.sale_cfy ?? 0,
    };
    const brands = [];
    for (const row of bodies) {
      const cell = cellGetter(row);
      const qtyLfy = cell?.sale_lfy ?? 0;
      const qtyLfytd = cell?.sale_lfytd ?? 0;
      const qtyCfy = cell?.sale_cfy ?? 0;
      if (qtyLfy === 0 && qtyLfytd === 0 && qtyCfy === 0) continue;
      const contLfy = safeCont(qtyLfy, total.lfy);
      const contLfytd = safeCont(qtyLfytd, total.lfytd);
      const contCfy = safeCont(qtyCfy, total.cfy);
      brands.push({
        brand: row.row_label,
        qtyLfy,
        qtyLfytd,
        qtyCfy,
        contLfy,
        contLfytd,
        contCfy,
        pp: contCfy - contLfytd,
        ppVsLfy: contCfy - contLfy,
      });
    }
    brands.sort((a, b) => b.pp - a.pp);
    // Rank change across the two LIKE-FOR-LIKE windows (LFYTD -> CFYTD): rank 1
    // is the biggest share, and a positive delta means the brand climbed.
    const lfytdRank = new Map(
      [...brands].sort((a, b) => b.contLfytd - a.contLfytd).map((b, i) => [b.brand, i + 1])
    );
    const cfyRank = new Map(
      [...brands].sort((a, b) => b.contCfy - a.contCfy).map((b, i) => [b.brand, i + 1])
    );
    brands.forEach((b, i) => {
      b.rank = i + 1;
      b.rankLfytd = lfytdRank.get(b.brand) ?? 0;
      b.rankCfy = cfyRank.get(b.brand) ?? 0;
      b.rankDelta = b.rankLfytd - b.rankCfy;
    });
    return {
      key,
      label,
      subLabel,
      total,
      brands,
      unitEquiv: total.cfy / 100, // units represented by ONE percentage point
      ppSum: brands.reduce((acc, b) => acc + b.pp, 0),
    };
  };

  const groups = [];
  const cat = categories.some((c) => str(c) === catName) ? catName : str(categories[0] ?? "");

  if (mode === "subs") {
    for (const sub of subCategories[cat] || []) {
      const g = buildGroup(
        `${cat}::${str(sub)}`,
        str(sub),
        cat,
        cellOf(overall2 || overall1, cat, sub),
        bodies2.length ? bodies2 : bodies1,
        (row) => cellOf(row, cat, sub)
      );
      if (g.brands.length) groups.push(g);
    }
  } else if (mode === "rows") {
    const g = buildGroup(str(cat), str(cat), null, cellOf(overall1, cat), bodies1, (row) => cellOf(row, cat));
    if (g.brands.length) groups.push(g);
  } else {
    for (const category of categories) {
      const g = buildGroup(
        str(category),
        str(category),
        null,
        cellOf(overall1, category),
        bodies1,
        (row) => cellOf(row, category)
      );
      if (g.brands.length) groups.push(g);
    }
  }
  return { groups, mode, cat };
}