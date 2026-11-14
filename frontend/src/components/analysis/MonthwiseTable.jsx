import { useMemo, useState } from "react";
import clsx from "clsx";
import { Columns3, Rows3 } from "lucide-react";
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
 * Monthwise Sales table - ONE backend payload, TWO layouts.
 *
 *   · "rows" (DEFAULT - months VERTICAL): every fiscal month (April → March) is
 *     a table ROW, so the eye reads Apr → Mar downwards instead of scanning 36
 *     month sub-columns sideways. Columns: selected dimensions · Month · LFY ·
 *     CFY · Growth % · Contribution % · running Cumulative (CFY).
 *   · "cols" (months HORIZONTAL): the original arrangement - one row per
 *     dimension combination with a grouped LFY | CFY | Growth % header per month.
 *
 * Both layouts are projections of the SAME payload and the SAME active measure,
 * so switching orientation is instant and the figures can never disagree.
 *
 * result: { rows, months: [{key,label}], dimensions, fy_context }
 * measureOptions: [{key, label, isPct, unit}]
 * defaultMeasure: measure key preselected on mount (falls back to first option)
 */
export default function MonthwiseTable({
  result,
  measureOptions,
  dimensionLabels = {},
  defaultMeasure,
}) {
  const [measure, setMeasure] = useState(
    () =>
      (defaultMeasure && measureOptions.some((m) => m.key === defaultMeasure)
        ? defaultMeasure
        : measureOptions[0]?.key) || undefined
  );
  /** "rows" = months vertical (flagship default), "cols" = months horizontal. */
  const [layout, setLayout] = useState("rows");
  // One sorting state per layout, so flipping the orientation never carries a
  // month-column id into the month-row grid (or vice versa).
  const [colsSorting, setColsSorting] = useState([]);
  // The LONG grid opens UNSORTED, which preserves the payload's natural order:
  // one block of fiscal months (Apr → Mar) per dimension combination - so every
  // dimension's year reads top-down before the next dimension starts. Sorting a
  // column header (including Month, which sorts on `month_order`) replaces it.
  const [rowsSorting, setRowsSorting] = useState([]);

  const dims = result?.dimensions || [];
  const months = result?.months || [];
  const activeMeasure = measureOptions.find((m) => m.key === measure) || measureOptions[0];
  const currentFyLabel = result?.fy_context?.current_fy_label || "Current FY";
  const fyMatch = currentFyLabel.match(/^FY(\d{4})-(\d{2})$/);
  const previousFyLabel = fyMatch ? `FY${Number(fyMatch[1]) - 1}-${String(Number(fyMatch[1]) - 1 + 1).slice(-2)}` : "Prior FY";

  const cumulativeKey = `__cumulative_${measure}`;
  const pctKey = `__cumulativePct_${measure}`;
  const rowTotalKey = `__rowTotal_${measure}`;
  const contribKey = `__contrib_${measure}`;
  const fmtMeasure = activeMeasure?.isPct ? fmtPct : activeMeasure?.unit === "qty" ? fmtQty : fmtVal;

  /** WIDE layout rows: one row per dimension combination (months as columns). */
  const wideRows = useMemo(() => {
    const sorted = applySorting(result?.rows || [], colsSorting);
    // Per-row CFY total of the active measure (summed across the months).
    const withTotals = sorted.map((row) => {
      let total = 0;
      let any = false;
      for (const m of months) {
        const v = row[`${m.key}__cfy_${measure}`];
        if (v !== null && v !== undefined) {
          total += v;
          any = true;
        }
      }
      return { ...row, [rowTotalKey]: any ? total : null };
    });
    // Grand total across all rows of this filtered dataset - the denominator
    // for both the contribution and the cumulative contribution %.
    const grand = withTotals.reduce((s, r) => s + (Number(r[rowTotalKey]) || 0), 0);
    // Running cumulative over the CURRENT (sorted) row order, so the column
    // always reflects the visible sequence: after any re-sort the running
    // total is recomputed here and the final row reaches the full filtered
    // total (~100%).
    let running = 0;
    return withTotals.map((row) => {
      if (row[rowTotalKey] == null) {
        return { ...row, [cumulativeKey]: null, [pctKey]: null, [contribKey]: null };
      }
      running += row[rowTotalKey];
      return {
        ...row,
        [cumulativeKey]: running,
        [pctKey]: grand > 0 ? (running / grand) * 100 : null,
        // The row's own share of the filtered total (the backend's
        // `ms_contrib_pct` is not populated for this payload, so it is derived
        // here from the same CFY months that feed the cumulative column).
        [contribKey]: grand > 0 ? (row[rowTotalKey] / grand) * 100 : null,
      };
    });
  }, [result?.rows, colsSorting, measure, months, cumulativeKey, pctKey, rowTotalKey, contribKey]);

  /** LONG layout rows: one row per dimension combination × fiscal month
   *  (April → March) - the months-vertical projection of the SAME payload. */
  const longRows = useMemo(() => {
    const out = [];
    for (const row of result?.rows || []) {
      for (const [index, m] of months.entries()) {
        const record = { month_order: index + 1, month: m.label };
        for (const d of dims) record[d] = row[d];
        record.ms_lfy = row[`${m.key}__lfy_${measure}`] ?? null;
        record.ms_cfy = row[`${m.key}__cfy_${measure}`] ?? null;
        record.ms_growth = row[`${m.key}__growth_pct_${measure}`] ?? null;
        out.push(record);
      }
    }
    return out;
  }, [result?.rows, result?.dimensions, months, measure]);

  /** LONG layout derived columns: each month row's Contribution % to the
   *  filtered total of the active measure, plus the running Cumulative (CFY)
   *  total and its [% of filtered total] over the CURRENT sorted order. */
  const monthRows = useMemo(() => {
    // Unsorted = the natural per-dimension Apr → Mar blocks; any header sort
    // (Month included, via `month_order`) re-orders this before it is measured.
    const sorted = applySorting(longRows, rowsSorting);
    const grand = sorted.reduce((s, r) => s + (Number(r.ms_cfy) || 0), 0);
    let running = 0;
    return sorted.map((row) => {
      if (row.ms_cfy === null || row.ms_cfy === undefined) {
        // A future month: no CFY data exists yet, so it can contribute nothing.
        return { ...row, ms_contrib_pct: null, [cumulativeKey]: null, [pctKey]: null };
      }
      const value = Number(row.ms_cfy) || 0;
      running += value;
      return {
        ...row,
        ms_contrib_pct: grand > 0 ? (value / grand) * 100 : null,
        [cumulativeKey]: running,
        [pctKey]: grand > 0 ? (running / grand) * 100 : null,
      };
    });
  }, [longRows, rowsSorting, cumulativeKey, pctKey]);

  /** Column model - WIDE layout: months are COLUMNS (grouped LFY|CFY|Growth%). */
  const wideColumns = useMemo(() => {
    const dimCols = dims.map((d) => ({
      accessorKey: d,
      header: dimensionLabels[d] || DIM_LABELS_FALLBACK(d),
      size: 150,
      cell: ({ getValue }) => getValue() ?? "—",
    }));

    const monthCols = months.map((m) => ({
      header: m.label,
      size: 360,
      columns: [
        {
          accessorKey: `${m.key}__lfy_${measure}`,
          header: previousFyLabel,
          size: 130,
          cell: ({ getValue }) => (
            <span className="text-text-secondary">{fmtMeasure(getValue())}</span>
          ),
        },
        {
          accessorKey: `${m.key}__cfy_${measure}`,
          header: currentFyLabel,
          size: 130,
          cell: ({ getValue }) => {
            const v = getValue();
            return v === null || v === undefined ? (
              <span className="text-text-muted italic">n/a</span>
            ) : (
              <span className="font-medium">{fmtMeasure(v)}</span>
            );
          },
        },
        {
          accessorKey: `${m.key}__growth_pct_${measure}`,
          header: "Growth %",
          size: 96,
          cell: ({ getValue }) => <GrowthCell value={getValue()} />,
        },
      ],
    }));

const contribCol = {
      accessorKey: contribKey,
      header: "Contribution %",
      size: 150,
      cell: ({ getValue }) => {
        const v = getValue();
        if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
        return <span className="font-medium">{fmtPct(v)}</span>;
      },
    };
    const cumulativeCol = {
      accessorKey: cumulativeKey,
      header: `Cumulative (${currentFyLabel})`,
      size: 220,
      cell: ({ getValue, row }) => {
        const v = getValue();
        if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
        const p = row.original[pctKey];
        return (
          <span className="text-teal font-medium whitespace-nowrap">
            {fmtMeasure(v)}
            {p != null && <span className="text-text-muted font-normal"> [{fmtPct(p)}]</span>}
          </span>
        );
      },
    };

    return [...dimCols, ...monthCols, contribCol, cumulativeCol];
  }, [dims, months, measure, dimensionLabels, cumulativeKey, pctKey, contribKey, fmtMeasure, previousFyLabel, currentFyLabel]);

  /** Column model - LONG layout: months are ROWS (Apr → Mar reading top-down).
   *  Each month row carries the active measure's LFY / CFY / Growth %, the row's
   *  Contribution % to the filtered total and the running Cumulative (CFY). */
  const monthColumns = useMemo(() => {
    const dimCols = dims.map((d) => ({
      accessorKey: d,
      header: dimensionLabels[d] || DIM_LABELS_FALLBACK(d),
      size: 150,
      cell: ({ getValue }) => getValue() ?? "—",
    }));

    // Sorted on `month_order` (Apr=1 … Mar=12) while DISPLAYING the month name,
    // so clicking the header always walks the fiscal year, never the alphabet.
    const monthCol = {
      id: "month_order",
      accessorFn: (row) => row.month_order,
      header: "Month",
      size: 120,
      cell: ({ row }) => (
        <span className="font-semibold text-text-primary">{row.original.month}</span>
      ),
    };

    const valueCols = [
      {
        accessorKey: "ms_lfy",
        header: previousFyLabel,
        size: 130,
        cell: ({ getValue }) => (
          <span className="text-text-secondary">{fmtMeasure(getValue())}</span>
        ),
      },
      {
        accessorKey: "ms_cfy",
        header: currentFyLabel,
        size: 130,
        cell: ({ getValue }) => {
          const v = getValue();
          return v === null || v === undefined ? (
            <span className="text-text-muted italic">n/a</span>
          ) : (
            <span className="font-medium">{fmtMeasure(v)}</span>
          );
        },
      },
      {
        accessorKey: "ms_growth",
        header: "Growth %",
        size: 110,
        cell: ({ getValue }) => <GrowthCell value={getValue()} />,
      },
      {
        accessorKey: "ms_contrib_pct",
        header: "Contribution %",
        size: 140,
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          return <span className="font-medium">{fmtPct(v)}</span>;
        },
      },
      {
        accessorKey: cumulativeKey,
        header: `Cumulative (${currentFyLabel})`,
        size: 220,
        cell: ({ getValue, row }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          const p = row.original[pctKey];
          return (
            <span className="text-teal font-medium whitespace-nowrap">
              {fmtMeasure(v)}
              {p != null && <span className="text-text-muted font-normal"> [{fmtPct(p)}]</span>}
            </span>
          );
        },
      },
    ];

    return [...dimCols, monthCol, ...valueCols];
  }, [dims, measure, dimensionLabels, cumulativeKey, pctKey, fmtMeasure, previousFyLabel, currentFyLabel]);

  const isVertical = layout === "rows";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Months orientation - vertical (default) or horizontal. */}
          <div className="flex items-center gap-1 rounded-lg border border-border-strong p-0.5 bg-surface">
            {[
              { key: "rows", label: "Months vertical", Icon: Rows3 },
              { key: "cols", label: "Months horizontal", Icon: Columns3 },
            ].map(({ key, label, Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => setLayout(key)}
                aria-pressed={layout === key}
                title={label}
                data-testid={`monthwise-layout-${key}`}
                className={clsx(
                  "flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md transition-colors",
                  layout === key
                    ? "bg-accent text-white"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                <Icon size={13} />
                {label}
              </button>
            ))}
          </div>

          {/* Measure selector - one measure at a time keeps the grid legible. */}
          <div className="flex items-center gap-1 rounded-lg border border-border-strong p-0.5 bg-surface flex-wrap">
            {measureOptions.map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => setMeasure(m.key)}
                className={clsx(
                  "px-3 py-1 text-xs font-semibold rounded-md transition-colors",
                  measure === m.key
                    ? "bg-accent text-white"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isVertical ? (
        <div data-testid="monthwise-vertical">
          <DataTable
            columns={monthColumns}
            data={monthRows}
            manualSorting
            sorting={rowsSorting}
            onSortingChange={setRowsSorting}
            stickyFirstColumns={Math.min(dims.length, 2)}
            globalSearch={false}
            emptyTitle="No monthwise data for this selection"
            emptyDescription="Try removing a filter or choosing different dimensions."
          />
        </div>
      ) : (
        <div data-testid="monthwise-horizontal">
          <DataTable
            columns={wideColumns}
            data={wideRows}
            manualSorting
            sorting={colsSorting}
            onSortingChange={setColsSorting}
            stickyFirstColumns={Math.min(dims.length, 2)}
            globalSearch={false}
            emptyTitle="No monthwise data for this selection"
            emptyDescription="Try removing a filter or choosing different dimensions."
          />
        </div>
      )}
    </div>
  );
}
