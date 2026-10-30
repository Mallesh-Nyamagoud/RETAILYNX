import { Fragment, useMemo, useState, useRef, useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { LayoutGrid, BarChart3, RefreshCw } from "lucide-react";
import Card from "../common/Card";
import SectionCard from "../common/SectionCard";
import { fmtPct, fmtQty, fmtVal } from "../../utils/format";

import CategoryBrandChart, { ShareShiftTable } from "./CategoryBrandChart";
import { DEFAULT_PERIOD_MASK } from "./shareShift";

function str(v) { return String(v ?? ""); }

function toneClass(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "text-text-muted";
  if (value > 0.001) return "text-positive";
  if (value < -0.001) return "text-negative";
  return "text-text-secondary";
}

/** In-cell column layout: KPI | LFY | LFYTD | CFYTD | Change ------------------ */
const CELL_GRID = "grid grid-cols-[54px_repeat(3,minmax(0,1fr))_58px] gap-x-2 items-baseline";

/** "▲12.3%" / "▼4.1 pp" - the sign carries the tone, the text carries the unit. */
function changeText(value, suffix) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  const sign = value > 0.001 ? "▲" : value < -0.001 ? "▼" : "•";
  return `${sign}${Math.abs(value).toFixed(1)}${suffix}`;
}

/** One KPI cell = the SAME KPI over ALL THREE periods (LFY · LFYTD · CFYTD) plus
 * the like-for-like Change: CFYTD against LFYTD, never against a full LFY year.
 * ASP / AVG.MRP show a third period too - the LFYTD value comes straight from
 * the payload (`asp_lfytd` / `avg_mrp_lfytd`), no extra plumbing. */
function KpiCell({ data, isOverall = false, hideContAcross = false }) {
  const stickyBg = isOverall ? "bg-card-hover/95" : "bg-transparent";

  if (!data) {
    return (
      <div className={clsx("flex items-center justify-center py-2 px-3 min-w-[300px] min-h-[94px]", stickyBg)}>
        <span className="text-text-muted text-xs font-medium">—</span>
      </div>
    );
  }

  const qtyCfy = data.sale_cfy ?? 0;
  const qtyLfy = data.sale_lfy ?? 0;
  const qtyLfytd = data.sale_lfytd ?? 0;
  const contCfy = data.cont_pct_cfy;
  const contLfy = data.cont_pct_lfy;
  const contLfytd = data.cont_pct_lfytd;
  const contAcrossCfy = data.cont_across_pct_cfy;
  const contAcrossLfy = data.cont_across_pct_lfy;
  const contAcrossLfytd = data.cont_across_pct_lfytd;
  const aspCfy = data.asp_cfy;
  const aspLfy = data.asp_lfy;
  const aspLfytd = data.asp_lfytd;
  const mrpCfy = data.avg_mrp_cfy;
  const mrpLfy = data.avg_mrp_lfy;
  const mrpLfytd = data.avg_mrp_lfytd;

  // A row that sold nothing in either prior period has nothing to compare with,
  // so only CFYTD is meaningful there.
  const hasPrior = qtyLfy > 0 || qtyLfytd > 0;
  const priorQty = (v) => (hasPrior ? fmtQty(v) : null);
  const money = (v, qty) => (qty > 0 ? fmtVal(v) : null);
  const priorMoney = (v, qty) => (hasPrior ? money(v, qty) : null);
  // Growth divides by |base| so a NEGATIVE prior period can never flip the sign
  // (loss -> profit must read as positive growth). 0 base => no % (null).
  const growth = (cfy, lfytd) => (lfytd ? ((cfy - lfytd) / Math.abs(lfytd)) * 100 : null);

  // Every metric carries the same three periods; the Change column is always
  // CFYTD vs LFYTD (percentage points for CONT.%, % for the rest).
  const rows = [
    {
      label: "QTY",
      lfy: priorQty(qtyLfy),
      lfytd: priorQty(qtyLfytd),
      cfy: fmtQty(qtyCfy),
      change: hasPrior ? data.qty_growth_lfytd_pct ?? growth(qtyCfy, qtyLfytd) : null,
      suffix: "%",
      strong: true,
    },
    {
      label: hideContAcross ? "CONT" : "CONT (WITHIN)",
      lfy: hasPrior ? fmtPct(contLfy) : null,
      lfytd: hasPrior ? fmtPct(contLfytd) : null,
      cfy: fmtPct(contCfy),
      change: hasPrior ? data.change_in_cont ?? (contCfy ?? 0) - (contLfytd ?? 0) : null,
      suffix: " pp",
      strong: true,
    },
  ];

  if (!hideContAcross) {
    rows.push({
      label: "CONT (ACROSS)",
      lfy: hasPrior ? fmtPct(contAcrossLfy) : null,
      lfytd: hasPrior ? fmtPct(contAcrossLfytd) : null,
      cfy: fmtPct(contAcrossCfy),
      change: hasPrior ? data.change_in_cont_across ?? (contAcrossCfy ?? 0) - (contAcrossLfytd ?? 0) : null,
      suffix: " pp",
      strong: true,
    });
  }

  rows.push(
    {
      label: "ASP",
      lfy: priorMoney(aspLfy, qtyLfy),
      lfytd: priorMoney(aspLfytd, qtyLfytd),
      cfy: money(aspCfy, qtyCfy),
      change: hasPrior ? data.asp_growth_lfytd_pct ?? growth(aspCfy, aspLfytd) : null,
      suffix: "%",
    },
    {
      label: "AVG.MRP",
      lfy: priorMoney(mrpLfy, qtyLfy),
      lfytd: priorMoney(mrpLfytd, qtyLfytd),
      cfy: money(mrpCfy, qtyCfy),
      change: hasPrior ? data.avg_mrp_growth_lfytd_pct ?? growth(mrpCfy, mrpLfytd) : null,
      suffix: "%",
    }
  );

  return (
    <div className={clsx("py-2 px-3 min-w-[300px]", stickyBg)}>
      <div className={CELL_GRID}>
        <span className="text-[9px] font-semibold text-text-muted uppercase tracking-widest">KPI</span>
        <span className="text-[9px] font-semibold text-text-muted uppercase tracking-widest text-right">LFY</span>
        <span className="text-[9px] font-semibold text-text-muted uppercase tracking-widest text-right">LFYTD</span>
        <span className="text-[9px] font-semibold text-text-muted uppercase tracking-widest text-right">CFYTD</span>
        <span className="text-[9px] font-semibold text-text-muted uppercase tracking-widest text-right">Change</span>


        {rows.map((row) => (
          <Fragment key={row.label}>
            <span className={clsx("pt-1 text-[10px] font-semibold uppercase tracking-wider", row.strong ? "text-text-secondary" : "text-text-muted")}>{row.label}</span>
            <span className="pt-1 text-right text-[10px] tabular-nums leading-tight text-text-secondary">{row.lfy ?? "—"}</span>
            <span className="pt-1 text-right text-[10px] tabular-nums leading-tight text-text-secondary">{row.lfytd ?? "—"}</span>
            <span className={clsx("pt-1 text-right tabular-nums leading-tight text-text-primary", row.strong ? "text-[11px] font-bold" : "text-[10px] font-semibold")}>{row.cfy ?? "—"}</span>
            <span className={clsx("pt-1 text-right text-[10px] font-semibold tabular-nums leading-tight", toneClass(row.change))}>
              {changeText(row.change, row.suffix) ?? "—"}
            </span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}



function StickyTable({ columns, data, rowHeaderLabel = "Brand", maxHeightClass = "max-h-[600px]" }) {
  const headerRef = useRef(null);
  const firstRowRef = useRef(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [firstRowHeight, setFirstRowHeight] = useState(0);
  useEffect(() => {
    if (!headerRef.current) return undefined;
    const el = headerRef.current;
    const update = () => setHeaderHeight(el.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [columns]);

  // The pinned "Overall" row is measured so pinned PARENT rows can stack
  // underneath it without overlapping.
  useEffect(() => {
    if (!firstRowRef.current) return undefined;
    const el = firstRowRef.current;
    const update = () => setFirstRowHeight(el.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [columns, data]);

  // Parent-row freeze only applies to a nested table (the Level 2 drill-down);
  // the flat Level 1 table has no children to scroll under it.
  const hasChildren = useMemo(() => (data || []).some((r) => (r?._level ?? 0) > 1), [data]);

  return (
    <div className={clsx("overflow-auto relative", maxHeightClass)}>
      <table className="w-full text-sm" style={{ borderCollapse: "separate", borderSpacing: 0, tableLayout: "auto" }}>
        <thead ref={headerRef} className="sticky top-0 z-[4] bg-card-hover">
          <tr>
            <th rowSpan={2} className="px-3 py-2 text-left text-[11px] font-semibold tracking-wide text-text-secondary uppercase border-b border-r border-border sticky left-0 bg-card-hover z-[5]" style={{ minWidth: 160 }}>{rowHeaderLabel}</th>
            {columns.map((col) => (
              <th key={col.key} colSpan={col.colSpan} className="px-3 py-2 text-center text-[11px] font-semibold tracking-wide text-text-secondary uppercase border-b border-r border-border last:border-r-0" style={{ minWidth: col.minWidth }}>{col.header}</th>
            ))}
          </tr>
          <tr>
            {columns.flatMap((col) => col.subHeaders.map((sub, si) => (
              <th key={`${col.key}-${si}`} className="px-2 py-1.5 text-center text-[10px] font-medium text-text-muted border-b border-r border-border last:border-r-0" style={{ minWidth: 90 }}>{sub}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIdx) => {
            const isFirst = rowIdx === 0;
            const level = row._level || 1;
            const isChild = !row.is_overall && level > 1;
            // FROZEN PARENT ROW: the overall row plus, in the nested Level 2
            // table, every level-1 parent row stay pinned beneath the header
            // while their children scroll under them (a later parent pushes the
            // previous one away, exactly like Excel's frozen group headers).
            const pinned = isFirst || (hasChildren && level === 1);
            const pinTop = isFirst ? headerHeight : headerHeight + firstRowHeight;
            return (
              <tr key={rowIdx} ref={isFirst ? firstRowRef : undefined} className={clsx("border-b border-border/70 last:border-0 transition-colors", pinned ? "bg-card-hover" : "hover:bg-card-hover/50")} style={pinned ? { position: "sticky", top: pinTop, zIndex: 3 } : undefined}>
                <td className={clsx("px-3 py-2.5 whitespace-nowrap border-r border-border sticky left-0 z-[1]", pinned ? "bg-card-hover" : "bg-card")}>
                  <span className={clsx("flex items-center gap-1.5 text-sm", isChild && "pl-5", row.is_overall ? "text-accent font-medium" : isChild ? "text-text-secondary" : "text-text-primary font-semibold")}>
                    {isChild && <span className="text-text-muted select-none">↳</span>}
                    {row.row_label}
                  </span>
                </td>
                {row.cells.map((cell, ci) => (
                  <td key={ci} className={clsx("px-3 py-2 border-r border-border/50 last:border-r-0 align-top", pinned && "bg-card-hover")}>{cell}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


export default function CategoryPerformance({ api, filters: globalFilters, hierarchy = [], eyebrow }) {
  const [view, setView] = useState("table");
  // The chart section's own selections are owned HERE so the Table Format
  // toggle can render the share-shift TABLE from the exact same measure /
  // x-axis / scope / series the chart is showing.
  const [chartMetric, setChartMetric] = useState("qty");
  const [chartMode, setChartMode] = useState("categories");
  const [chartScope, setChartScope] = useState("");
  const [chartCat, setChartCat] = useState("");
  const [chartPeriodMask, setChartPeriodMask] = useState(DEFAULT_PERIOD_MASK);

  // This section renders NO filters/slicers of its own: it is driven purely by
  // the page-level ROW HIERARCHY and the page-level global slicers.  Both are
  // part of the query key, and react-query keeps the previous payload on screen
  // while a new combination is in flight, so changing a slicer or a row
  // dimension never flashes a skeleton.
  const filterKey = useMemo(() => JSON.stringify(globalFilters || {}), [globalFilters]);
  const hierarchyKey = useMemo(() => (hierarchy || []).join("|"), [hierarchy]);
  const categoryQ = useQuery({
    queryKey: [eyebrow, "category-performance", filterKey, hierarchyKey],
    queryFn: () => api.categoryAnalysis(globalFilters, hierarchy),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const result = categoryQ.data;
  const categories = result?.categories || [];
  const subCategories = result?.sub_categories || [];
  const rowDims = result?.row_dims || [];

  const { l1Columns, l1Rows, l2Columns, l2Rows } = useMemo(() => {
    if (!result) return { l1Columns: [], l1Rows: [], l2Columns: [], l2Rows: [] };
    const l1Cols = categories.map((cat) => ({ key: str(cat), header: str(cat), colSpan: 1, subHeaders: ["LFY · LFYTD · CFYTD + Change"], minWidth: 300 }));
    const l1Data = result.rows_level1.map((row) => ({
      row_label: row.row_label, is_overall: row.is_overall, _level: row._level,
      cells: categories.map((cat) => <KpiCell data={row._data?.[str(cat)]} isOverall={row.is_overall} />),
    }));
    const l2Cols = [];
    for (const cat of categories) {
      const subs = subCategories[str(cat)] || [];
      if (subs.length === 0) {
        l2Cols.push({ key: str(cat), header: str(cat), colSpan: 1, subHeaders: ["(none)"], minWidth: 300 });
      } else {
        for (const sub of subs) {
          l2Cols.push({ key: `${str(cat)}-${str(sub)}`, header: str(cat), colSpan: 1, subHeaders: [str(sub)], minWidth: 300 });
        }
      }
    }
    const l2Data = result.rows_level2.map((row) => {
      const cells = [];
      for (const cat of categories) {
        const subs = subCategories[str(cat)] || [];
        if (subs.length === 0) {
          cells.push(<KpiCell data={null} isOverall={row.is_overall} hideContAcross={true} />);
        } else {
          for (const sub of subs) {
            cells.push(<KpiCell data={row._data?.[str(cat)]?.[str(sub)]} isOverall={row.is_overall} hideContAcross={true} />);
          }
        }
      }
      return { row_label: row.row_label, is_overall: row.is_overall, _level: row._level, cells };
    });
    return { l1Columns: l1Cols, l1Rows: l1Data, l2Columns: l2Cols, l2Rows: l2Data };
  }, [result, categories, subCategories]);

  // Row H1/H2 headings track the page-level Row Hierarchy, so the tables always
  // say which dimension(s) they are rowed by.  ("Brand" is the historical
  // default the backend itself falls back to when the hierarchy is empty.)
  const rowChainText = rowDims.length ? rowDims.map((d) => str(d.label)).join(" > ") : "Brand";
  const rowHeaderLabel = rowDims[0]?.label || "Brand";
  const level1Title = `Level 1 - Category Performance - ${rowChainText} x Category`;
  const level2Title = `Level 2 - Sub-Category Performance - ${rowChainText} x Category x Sub-Category`;
  const activeFilterCount = useMemo(
    () => Object.values(globalFilters || {}).reduce((acc, v) => acc + (v?.length || 0), 0),
    [globalFilters]
  );

  return (
    <div className="space-y-5">
                  <div className="flex items-center justify-end flex-wrap gap-3">
        <div className="inline-flex items-center rounded-lg border border-border-strong p-0.5 bg-surface">
          {[
            { key: "table", label: "Table Format", icon: LayoutGrid },
            { key: "chart", label: "Chart", icon: BarChart3 },
          ].map((opt) => (
            <button key={opt.key} type="button" onClick={() => setView(opt.key)} className={clsx("flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors", view === opt.key ? "bg-accent text-white shadow-sm" : "text-text-secondary hover:text-text-primary")}>
              <opt.icon size={13} />{opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Deliberately NO filters/slicers here - the ROW HIERARCHY and the global
          slicer card above are the only inputs (both are in the query key). */}
      {result && categories.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
          <span className="font-bold tracking-widest uppercase">Rows</span>
          <span className="px-2 py-0.5 rounded-full border border-border bg-surface font-semibold text-text-secondary">{rowChainText}</span>
          <span>{activeFilterCount > 0 ? `· ${activeFilterCount} global filter${activeFilterCount > 1 ? "s" : ""} applied above` : "· no global filters applied"}</span>
          {categoryQ.isFetching && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent font-semibold animate-pulse">
              <RefreshCw size={10} /> updating to your selection…
            </span>
          )}
        </div>
      )}


      {categoryQ.isLoading ? (
        <Card><div className="animate-pulse space-y-3 p-4"><div className="h-4 bg-border rounded w-1/3" /><div className="h-32 bg-border/50 rounded" /></div></Card>
      ) : categoryQ.isError ? (
        <Card><div className="p-6 text-center"><p className="text-negative font-medium">{categoryQ.error.message}</p><button onClick={() => categoryQ.refetch()} className="mt-2 text-xs text-accent hover:underline">Retry</button></div></Card>
      ) : !result || categories.length === 0 ? (
        <Card><div className="p-6 text-center text-text-muted">No category dimension found in the dataset.</div></Card>
      ) : view === "chart" ? (
        /* Chart view = ONE chart built from the SAME payload as the table (same
           global slicers, same Row Hierarchy). The measure pills choose QTY /
           CONT% / Share Shift (pp); Share Shift swaps the grouped bars for the
           brand diverge panels and repurposes the brand pills as a highlight. */
        <Card padded={false} className="overflow-hidden">
          <div className="p-4 bg-surface">
            <CategoryBrandChart
              result={result}
              rowDims={rowDims}
              rowChainText={rowChainText}
              activeFilterCount={activeFilterCount}
              metric={chartMetric}
              setMetric={setChartMetric}
              mode={chartMode}
              setMode={setChartMode}
              scopeLabel={chartScope}
              setScopeLabel={setChartScope}
              catLabel={chartCat}
              setCatLabel={setChartCat}
              periodMask={chartPeriodMask}
              setPeriodMask={setChartPeriodMask}
            />
          </div>
        </Card>
      ) : chartMetric === "shareShift" ? (
        /* TABLE FORMAT while the Share Shift (pp) measure is active: the SAME
           numbers the diverging panels plot, as one table per group with the
           Overall reference row first and the brands sorted by pp change. */
        <Card padded={false} className="overflow-hidden">
          <div className="p-4 bg-surface">
            <ShareShiftTable
              result={result}
              mode={chartMode}
              catName={chartCat}
              scopeLabel={chartScope}
              periodMask={chartPeriodMask}
              rowHeaderLabel={rowDims[0]?.label || "Brand"}
            />
          </div>
        </Card>
      ) : (
        <div className="space-y-5">
          <SectionCard
            dot="bg-accent"
            title={level1Title}
          >
            {({ maximized }) => (
              <StickyTable
                columns={l1Columns}
                data={l1Rows}
                rowHeaderLabel={rowHeaderLabel}
                maxHeightClass={maximized ? "max-h-[calc(100vh-180px)]" : "max-h-[600px]"}
              />
            )}
          </SectionCard>
          <SectionCard
            dot="bg-teal"
            title={level2Title}
          >
            {({ maximized }) => (
              <StickyTable
                columns={l2Columns}
                data={l2Rows}
                rowHeaderLabel={rowChainText}
                maxHeightClass={maximized ? "max-h-[calc(100vh-180px)]" : "max-h-[650px]"}
              />
            )}
          </SectionCard>
        </div>
      )}
    </div>
  );
}
