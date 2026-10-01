import { useMemo, useState } from "react";
import clsx from "clsx";
import DataTable from "../common/DataTable";
import { fmtPct, fmtQty, fmtVal, growthTone } from "../../utils/format";
import { applySorting } from "../../utils/sorting";

const DIM_LABELS_FALLBACK = (col) => col.replace(/_/g, " ").toUpperCase();

function GrowthCell({ value }) {
  if (value === null || value === undefined) return <span className="text-text-muted">—</span>;
  const tone = growthTone(value);
  const toneClass =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text-secondary";
  return <span className={clsx("font-medium", toneClass)}>{fmtPct(value)}</span>;
}

/**
 * Month-as-ROWS monthwise table (Tertiary Sales Analysis).
 *
 * result: { rows, dimensions, measure_keys, ratio_keys, growth_keys, fy_context }
 * Each row is one dimension combination + one month (April..March). Every KPI
 * is rendered with BOTH fiscal years side by side (CFY | LFY) so the full
 * picture is visible at once, plus per-measure growth % and a cumulative
 * column shown as `Value [contribution %]` (ms_cum_val / ms_cum_pct are
 * recomputed client-side as a running total over the CURRENT row order, so
 * the column always matches the sort on screen — the final data row reaches
 * ~100%).
 */
export default function MonthwiseRowsTable({ result, dimensionLabels = {} }) {
  const [sorting, setSorting] = useState([{ id: "month_order", desc: false }]);

  const dims = result?.dimensions || [];
  const measureShape = result?.measure_keys || [];

  const rows = useMemo(() => {
    const sorted = applySorting(result?.rows || [], sorting);
    // Grand Bill Value of the filtered dataset - denominator for the running %.
    const grand = sorted.reduce((s, r) => s + (Number(r.bill_val) || 0), 0);
    // Running cumulative over the CURRENT (sorted) row order. The backend
    // sends the fiscal-month accumulation, but once the user re-sorts the
    // grid that becomes stale - so the running total / running % are
    // recomputed here against the visible sequence instead (final data row
    // reaches ~100%).
    let running = 0;
    return sorted.map((row) => {
      const v = row.bill_val;
      if (v === null || v === undefined) {
        return { ...row, ms_cum_val: null, ms_cum_pct: null };
      }
      running += v;
      return {
        ...row,
        ms_cum_val: running,
        ms_cum_pct: grand > 0 ? (running / grand) * 100 : null,
      };
    });
  }, [result?.rows, sorting]);

  // Every KPI present in the payload (they all have a `_ly` LFY twin).
  const MEASURE_SPECS = [
    { key: "qty", label: "Qty", unit: "qty" },
    { key: "mrp_value", label: "MRP Value", unit: "val" },
    { key: "discount", label: "Discount", unit: "val" },
    { key: "bill_val", label: "Bill Value", unit: "val" },
  ];
  const fmtFor = (unit) => (unit === "qty" ? fmtQty : fmtVal);

  const columns = useMemo(() => {
    const dimCols = dims.map((d) => ({
      accessorKey: d,
      header: dimensionLabels[d] || DIM_LABELS_FALLBACK(d),
      size: 140,
      cell: ({ getValue }) => getValue() ?? "—",
    }));

    const monthCol = {
      accessorKey: "month",
      header: "Month",
      size: 110,
      cell: ({ getValue }) => <span className="font-medium">{getValue()}</span>,
    };

    // Every available KPI as a grouped header: CFY | LFY side by side.
    // LFY is populated for all 12 months (Apr..Mar); only CFY is blank for
    // future months (shown as n/a).
    const measureCols = MEASURE_SPECS.filter((m) => measureShape.includes(m.key)).map(
      ({ key, label, unit }) => ({
        header: label,
        size: 260,
        columns: [
          {
            accessorKey: key,
            header: "CFY",
            size: 130,
            cell: ({ getValue }) => {
              const v = getValue();
              return v === null || v === undefined ? (
                <span className="text-text-muted italic">n/a</span>
              ) : (
                <span className="font-medium">{fmtFor(unit)(v)}</span>
              );
            },
          },
          {
            accessorKey: `${key}_ly`,
            header: "LFY",
            size: 130,
            cell: ({ getValue }) => (
              <span className="text-text-secondary">{fmtFor(unit)(getValue())}</span>
            ),
          },
        ],
      })
    );

    const ratioCols = (result?.ratio_keys || []).map((key) => ({
      accessorKey: key,
      header: "Bill Discount %",
      size: 110,
      cell: ({ getValue }) => {
        const v = getValue();
        return v === null || v === undefined ? (
          <span className="text-text-muted">—</span>
        ) : (
          <span className="font-medium">{fmtPct(v)}</span>
        );
      },
    }));

    // Growth KPIs - always rendered as % with +/- tone.
    const growthCols = (result?.growth_keys || []).map((g) => ({
      accessorKey: `${g}_growth_pct`,
      header: g === "bill_val" ? "Bill Value Growth %" : "Qty Growth %",
      size: 128,
      cell: ({ getValue }) => <GrowthCell value={getValue()} />,
    }));

    // Cumulative Value [contribution %] - running total / running % over the
    // current sorted rows (see the rows useMemo above); recalculated whenever
    // the user re-sorts so it always matches what's on screen.
    const cumCol = {
      accessorKey: "ms_cum_val",
      header: "Cumulative Value",
      size: 240,
      cell: ({ getValue, row }) => {
        const v = getValue();
        const p = row.original.ms_cum_pct;
        if (v === null || v === undefined || p === null || p === undefined) {
          return <span className="text-text-muted">—</span>;
        }
        return (
          <span className="text-teal font-medium whitespace-nowrap">
            {fmtVal(v)}
            <span className="text-text-muted font-normal"> [{fmtPct(p)}]</span>
          </span>
        );
      },
    };

    const contribCol = {
      accessorKey: "ms_contrib_pct",
      header: "Contribution %",
      size: 140,
      cell: ({ getValue }) => {
        const v = getValue();
        if (v === null || v === undefined) {
          return <span className="text-text-muted">—</span>;
        }
        return <span className="font-medium">{fmtPct(v)}</span>;
      },
    };

    return [...dimCols, monthCol, ...measureCols, ...ratioCols, ...growthCols, cumCol, contribCol];
  }, [dims, measureShape, dimensionLabels, result?.ratio_keys, result?.growth_keys]);

  return (
    <div className="space-y-3">
      <DataTable
        columns={columns}
        data={rows}
        manualSorting
        sorting={sorting}
        onSortingChange={setSorting}
        stickyFirstColumns={Math.min(dims.length, 2)}
        globalSearch={false}
        emptyTitle="No monthwise data for this selection"
        emptyDescription="Try removing a filter or choosing different dimensions."
      />
    </div>
  );
}