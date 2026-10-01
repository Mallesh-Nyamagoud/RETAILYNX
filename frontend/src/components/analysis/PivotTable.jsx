import { useMemo, useState } from "react";
import clsx from "clsx";
import DataTable from "../common/DataTable";
import { UnitToggle } from "../common/ExportButton";
import { fmtPct, fmtQty, fmtVal, fmtCompactVal, growthTone } from "../../utils/format";
import { applySorting } from "../../utils/sorting";

const DIM_LABELS_FALLBACK = (col) => col.replace(/_/g, " ").toUpperCase();

function GrowthCell({ value }) {
  const tone = growthTone(value);
  const toneClass =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text-secondary";
  return <span className={clsx("font-medium", toneClass)}>{fmtPct(value)}</span>;
}

/**
 * result: { rows, columns: {dimensions, measures, units}, fy_context }
 * dimensionLabels: {column: label} for pretty headers
 * unitValLabel: display name of the ₹ unit (e.g. "Taxable Value (₹)")
 */
export default function PivotTable({ result, dimensionLabels = {}, unitValLabel = "Value (₹)" }) {
  const [unit, setUnit] = useState("val");
  const [sorting, setSorting] = useState([]);

  const dims = result?.columns?.dimensions || [];
  const measures = result?.columns?.measures || [];
  const fullDepth = dims.length;

  const rowsWithCumulative = useMemo(() => {
    const base = result?.rows || [];
    const unitKey = `cfytd_${unit}`;
    const cumKey = `cumulative_cfytd_${unit}`;
    const shareKey = `cumulative_pct_cfytd_${unit}`;
    // Filtered dataset total - the denominator for every contribution %. This
    // is the grand-total CFY value within the ACTIVE FILTERS (never a global,
    // unfiltered figure). Falls back to the sum of leaf rows if absent.
    let total = 0;
    for (const r of base) {
      if (r._is_total) {
        total = Number(r[unitKey]) || 0;
        break;
      }
    }
    if (total <= 0) total = base.reduce((s, r) => s + (Number(r[unitKey]) || 0), 0);

    const leafEligible = (r) =>
      !r._is_total && (fullDepth === 0 || (r._level ?? fullDepth) === fullDepth);

    // Cumulative is a Pareto/share curve over the FINEST (leaf) rows only:
    //   - default rank = CFY Value DESCENDING (highest -> lowest);
    //   - a user-requested sort (if any) is honoured instead.
    const ranking =
      sorting && sorting.length
        ? applySorting(base, sorting).filter(leafEligible)
        : base.filter(leafEligible).slice().sort((a, b) => (Number(b[unitKey]) || 0) - (Number(a[unitKey]) || 0));

    let running = 0;
    // Two parallel lookups keyed by the SAME row objects: the running cumulative
    // VALUE (₹ / units) and its [% share] of the filtered total, so the cell can
    // render both as `value [share%]` (Monthwise-style).
    const valueByIdx = new Map();
    const shareByIdx = new Map();
    for (const r of ranking) {
      running += Number(r[unitKey]) || 0;
      valueByIdx.set(r, running);
      shareByIdx.set(r, total > 0 ? (running / total) * 100 : 0);
    }

    // DISPLAY ORDER - this is what makes the column-header sort actually work.
    // The grid is fed `manualSorting`, so TanStack will NOT reorder rows for us;
    // the sorted order has to be applied HERE. It is a pure in-memory `.sort`
    // over the already-aggregated pivot rows (no refetch), so a header click
    // reorders the grid in microseconds. Grand-total / subtotal rows are kept
    // LAST so the summary never gets interleaved with the detail rows.
    const grand = [];
    const detail = [];
    for (const r of base) (r._is_total ? grand : detail).push(r);
    const ordered = sorting && sorting.length ? applySorting(detail, sorting) : detail;

    return [...ordered, ...grand].map((r) => {
      const isLeaf = fullDepth === 0
        ? r._is_total // single grand-total row when no dimensions selected
        : !r._is_total && (r._level ?? fullDepth) === fullDepth;
      return {
        ...r,
        [cumKey]: isLeaf ? valueByIdx.get(r) ?? null : null,
        [shareKey]: isLeaf ? shareByIdx.get(r) ?? null : null,
      };
    });
  }, [result?.rows, sorting, unit, fullDepth]);

  const columns = useMemo(() => {
    const dimCols = dims.map((d, idx) => ({
      accessorKey: d,
      header: dimensionLabels[d] || DIM_LABELS_FALLBACK(d),
      cell: ({ row, getValue }) => {
        const v = getValue();
        const level = row.original._level ?? fullDepth;
        const isTotal = row.original._is_total;
        const indent = idx === 0 ? level * 14 : 0;
        if (idx === 0) {
          return (
            <span
              style={{ paddingLeft: indent }}
              className={clsx(isTotal && "font-bold", level > 0 && level < fullDepth && "font-semibold")}
            >
              {v === null || v === undefined
                ? isTotal
                  ? "Grand Total"
                  : `All ${dimensionLabels[d] || d}`
                : v}
            </span>
          );
        }
        return (
          <span className={clsx(isTotal && "font-bold")}>
            {v === null || v === undefined ? "—" : v}
          </span>
        );
      },
    }));

    const measureCols = measures.map((m) => {
      const key = `${m.key}_${unit}`;
      // Percent measures are unit-independent - they always render with "%"
      // via GrowthCell regardless of the qty/val toggle.
      const isPct = m.key.includes("growth_pct");
      return {
        accessorKey: key,
        header: isPct ? m.label : `${m.label} (${unit === "qty" ? "Qty" : unitValLabel})`,
        cell: ({ getValue, row }) => {
          const v = getValue();
          const isTotal = row.original._is_total;
          const content = isPct ? (
            <GrowthCell value={v} />
          ) : unit === "qty" ? (
            fmtQty(v)
          ) : (
            fmtVal(v)
          );
          return <span className={clsx(isTotal && "font-bold")}>{content}</span>;
        },
      };
    });

    const cumulativeCol = {
      accessorKey: `cumulative_cfytd_${unit}`,
      header: `Cumulative ${unit === "qty" ? "Qty" : "Value"} [% Share]`,
      // Derived, order-relative column - it is recomputed FROM the current sort
      // order, so offering a sort toggle on it would be circular. Sorting every
      // other column reorders the grid and moves this column with it.
      enableSorting: false,
      cell: ({ getValue, row }) => {
        const v = getValue();
        if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
        // Running cumulative VALUE + its [% share] of the filtered total - the
        // same `value [share%]` convention the Monthwise grid uses.
        const p = row.original[`cumulative_pct_cfytd_${unit}`];
        return (
          <span className="text-teal font-medium whitespace-nowrap">
            {unit === "qty" ? fmtQty(v) : fmtVal(v)}
            {p !== null && p !== undefined && (
              <span className="text-text-muted font-normal"> [{fmtPct(p)}]</span>
            )}
          </span>
        );
      },
    };

    return [...dimCols, ...measureCols, cumulativeCol];
  }, [dims, measures, unit, dimensionLabels, fullDepth, unitValLabel]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end flex-wrap gap-2">
        <UnitToggle
          value={unit}
          onChange={setUnit}
          valLabel={unitValLabel}
          qtyLabel="Quantity"
        />
      </div>
      <DataTable
        columns={columns}
        data={rowsWithCumulative}
        manualSorting
        sorting={sorting}
        onSortingChange={setSorting}
        stickyFirstColumns={Math.min(dims.length, 2)}
        globalSearch={false}
        rowClassName={(row) =>
          row._is_total
            ? "bg-accent-soft/60 font-semibold"
            : row._level > 0 && row._level < fullDepth
            ? "bg-card-hover/40"
            : undefined
        }
        emptyTitle="No billing data for this selection"
        emptyDescription="Try removing a filter or choosing different dimensions."
      />
    </div>
  );
}
