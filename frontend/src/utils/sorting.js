/** Sorts rows by a TanStack-style `sorting` state ([{id, desc}]), always
 * pushing null/undefined to the bottom regardless of direction. Kept
 * outside the table component so callers can recompute a cumulative
 * column against the freshly-sorted order (see utils/format#withCumulative),
 * matching the requirement that cumulative totals "recalculate whenever the
 * sorting/order changes." */
export function applySorting(rows, sorting) {
  if (!sorting || sorting.length === 0) return rows;
  const { id, desc } = sorting[0];
  const copy = [...rows];
  copy.sort((a, b) => {
    const av = a[id];
    const bv = b[id];
    const aNull = av === null || av === undefined;
    const bNull = bv === null || bv === undefined;
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    if (typeof av === "string" || typeof bv === "string") {
      const cmp = String(av).localeCompare(String(bv));
      return desc ? -cmp : cmp;
    }
    const cmp = av - bv;
    return desc ? -cmp : cmp;
  });
  return copy;
}
