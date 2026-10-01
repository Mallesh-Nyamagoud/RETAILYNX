import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import clsx from "clsx";
import { fmtPct, fmtQty } from "../../utils/format";
import { DEFAULT_PERIOD_MASK, cellOf, computeShareShift, fmtPp, str } from "./shareShift";

/* ---------------------------------------------------------------------------
 * Category Performance - CHART view (Module IV -> "Category Performance" tab).
 *
 * ONE grouped bar chart rendered from the SAME payload as the table (the parent
 * fetches `api.categoryAnalysis(filters, hierarchy)` once and hands it over), so
 * the chart is filter- and Row-Hierarchy-aware by construction - no second data
 * path, no table markup, and no table tooltip card is reused here.
 *
 *   X axis : the grouping that is active on the page.
 *            "Categories"     -> Row x Category
 *            "Sub-Categories" -> Row x Category x Sub-Category (level 2)
 *            "Rows"           -> Category x Row (i.e. the brand bars)
 *   Bars   : LFY | LFYTD | CFYTD - the three periods the table itself shows,
 *            in the app's period colour coding.
 *   Tooltip: PER-ITEM hover state ({ series, index } from that bar's own mouse
 *            handlers). Exactly one tooltip can exist in the DOM at a time, it
 *            sits next to the hovered bar, and it disappears on mouse-leave -
 *            nothing is rendered while nothing is hovered.
 * ------------------------------------------------------------------------- */

// Period colour coding used across the app: LFY is the slate "last year" grey,
// LFYTD the same grey one step lighter (last year so far), CFYTD the accent
// blue of the current year (the same LFY/CFY pair the Bill No. chart uses).
const LFY_COLOR = "#94a3b8";
const LFYTD_COLOR = "#cbd5e1";
const CFYTD_COLOR = "#5b7cfa";
const GRID_COLOR = "#94a3b8";
// Share-shift diverging colours: green = gained share, red = lost share.
const GAIN_COLOR = "#22c55e";
const LOSS_COLOR = "#ef4444";

const PERIODS = [
  { key: "lfy", label: "LFY", color: LFY_COLOR },
  { key: "lfytd", label: "LFYTD", color: LFYTD_COLOR },
  { key: "cfy", label: "CFYTD", color: CFYTD_COLOR },
];

const METRICS = [
  { key: "qty", label: "QTY", unit: "units" },
  { key: "cont", label: "CONT%", unit: "% of row" },
  { key: "shareShift", label: "Share Shift (pp)", unit: "pp = CFYTD cont% − LFYTD cont%" },
];

const AXIS_MODES = [
  { key: "categories", label: "Categories" },
  { key: "subs", label: "Sub-Categories" },
  { key: "rows", label: "Rows" },
];

const PILL = (active) =>
  clsx(
    "px-3 py-1.5 text-xs font-semibold rounded-md transition-colors border",
    active
      ? "bg-accent text-white border-transparent shadow-sm"
      : "bg-surface text-text-secondary border-border hover:text-text-primary"
  );

function fmtQtyAxis(value) {
  const v = Number(value) || 0;
  const abs = Math.abs(v);
  if (abs >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`;
  if (abs >= 1e5) return `${(v / 1e5).toFixed(1)}L`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(Math.round(v));
}

/** The same three periods the table renders, read off the same cell. */
function periodValue(cell, metric, period) {
  if (!cell) return 0;
  if (metric === "cont") return cell[`cont_pct_${period}`] ?? 0;
  return cell[`sale_${period}`] ?? 0;
}

/** A label/value line inside a tooltip. */
function Row({ label, value, tone = "neutral", strong = false }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-text-muted">{label}</span>
      <span
        className={clsx(
          "tabular-nums",
          strong ? "font-semibold text-text-primary" : "text-text-secondary",
          tone === "pos" && "font-bold text-positive",
          tone === "neg" && "font-bold text-negative"
        )}
      >
        {value}
      </span>
    </div>
  );
}

/** Rich hover card for ONE diverging bar: brand, group, every retained
 * period's qty + cont%, the pp change and its unit equivalent. */
function ShareShiftTooltip({ active, payload, group, periodMask }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const mask = periodMask || DEFAULT_PERIOD_MASK;
  const unitShift = d.pp * (group?.unitEquiv || 0);
  return (
    <div
      className="pointer-events-none rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-panel-lg"
      data-testid="cp-shift-tooltip"
    >
      <div className="font-bold text-text-primary">{d.brand}</div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
        {group?.subLabel ? `${group.subLabel} · ` : ""}
        {group?.label}
      </div>
      <div className="mt-1.5 space-y-0.5">
        {mask.lfy ? <Row label="LFY" value={`${fmtQty(d.qtyLfy)} · ${fmtPct(d.contLfy)}`} /> : null}
        {mask.lfytd ? <Row label="LFYTD" value={`${fmtQty(d.qtyLfytd)} · ${fmtPct(d.contLfytd)}`} /> : null}
        {mask.cfy ? <Row label="CFYTD" value={`${fmtQty(d.qtyCfy)} · ${fmtPct(d.contCfy)}`} strong /> : null}
      </div>
      <div className="mt-1.5 border-t border-border pt-1.5">
        <Row
          label="pp change"
          value={fmtPp(d.pp)}
          tone={d.pp > 0.001 ? "pos" : d.pp < -0.001 ? "neg" : "neutral"}
        />
        <Row
          label="unit equivalent"
          value={`${unitShift >= 0 ? "+" : "−"}${fmtQty(Math.abs(unitShift))} units`}
          tone={unitShift > 0.5 ? "pos" : unitShift < -0.5 ? "neg" : "neutral"}
        />
      </div>
    </div>
  );
}

/** ONE group's diverging chart: the Overall reference row (that group's 100%
 * total) plus one horizontal bar per brand, sorted by pp change. Negative pp
 * extends LEFT (red) and positive extends RIGHT (green) around a zero line, so
 * the biggest loser and the biggest gainer sit at opposite ends. */
function ShareShiftPanel({ group, highlightBrand, periodMask }) {
  const data = group.brands;
  const maxAbs = useMemo(() => {
    const m = Math.max(1, ...data.map((d) => Math.abs(d.pp)));
    return Math.ceil(m * 1.15 * 10) / 10;
  }, [data]);

  if (!data.length) {
    return (
      <div className="rounded-lg border border-border bg-card/40 p-3 text-xs text-text-muted">
        No brand sales in this group for the current filters.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card/40 p-3" data-testid={`cp-shift-${group.key}`}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-bold text-text-primary">
          {group.subLabel ? <span className="font-medium text-text-muted">{group.subLabel} · </span> : null}
          {group.label}
        </div>
        <div className="text-[10px] font-semibold tabular-nums text-text-muted">
          Σ pp {group.ppSum >= 0 ? "+" : "−"}
          {Math.abs(group.ppSum).toFixed(1)}
        </div>
      </div>

      {/* Whichever side lost share is answered by the other side right here:
          every brand's pp change in one group sums to ~0. */}
      <div className="mt-1.5 flex items-center justify-between gap-2 rounded border border-dashed border-border px-2 py-1 text-[10px] text-text-muted">
        <span className="font-bold uppercase tracking-wide">Overall · 100% of group</span>
        <span className="tabular-nums">
          LFY {fmtQty(group.total.lfy)} · LFYTD {fmtQty(group.total.lfytd)} · CFYTD {fmtQty(group.total.cfy)}
        </span>
      </div>

      <div className="mt-1 h-[168px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 6, right: 16, left: 4, bottom: 2 }}
            barCategoryGap="22%"
          >
            <CartesianGrid stroke={GRID_COLOR} strokeOpacity={0.15} horizontal={false} />
            <XAxis
              type="number"
              domain={[-maxAbs, maxAbs]}
              tick={{ fontSize: 9, fill: GRID_COLOR }}
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${Number(v).toFixed(0)}`}
              tickLine={false}
              axisLine={{ stroke: GRID_COLOR, strokeOpacity: 0.3 }}
            />
            <YAxis
              type="category"
              dataKey="brand"
              width={104}
              interval={0}
              tick={{ fontSize: 10, fill: GRID_COLOR }}
              tickLine={false}
              axisLine={false}
            />
            <ReferenceLine x={0} stroke={GRID_COLOR} strokeOpacity={0.75} />
            <Tooltip
              cursor={{ fill: GRID_COLOR, fillOpacity: 0.06 }}
              content={<ShareShiftTooltip group={group} periodMask={periodMask} />}
            />
            <Bar dataKey="pp" radius={[3, 3, 3, 3]} maxBarSize={20} isAnimationActive={false}>
              {data.map((d) => (
                <Cell
                  key={d.brand}
                  fill={d.pp >= 0 ? GAIN_COLOR : LOSS_COLOR}
                  fillOpacity={highlightBrand && d.brand !== highlightBrand ? 0.22 : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function CategoryBrandChart({
  result,
  rowDims = [],
  rowChainText = "Brand",
  activeFilterCount = 0,
  // Measure / axis / scope / periods are CONTROLLED when the page passes them
  // (the page's Table Format toggle uses the very same selections to render the
  // share-shift table); used standalone they fall back to local state.
  metric: metricProp,
  setMetric: setMetricProp,
  mode: modeProp,
  setMode: setModeProp,
  scopeLabel: scopeLabelProp,
  setScopeLabel: setScopeLabelProp,
  catLabel: catLabelProp,
  setCatLabel: setCatLabelProp,
  periodMask: periodMaskProp,
  setPeriodMask: setPeriodMaskProp,
}) {
  const [metricLocal, setMetricLocal] = useState("qty");
  const [modeLocal, setModeLocal] = useState("categories");
  const [scopeLabelLocal, setScopeLabelLocal] = useState("");
  const [catLabelLocal, setCatLabelLocal] = useState("");
  const [periodMaskLocal, setPeriodMaskLocal] = useState(DEFAULT_PERIOD_MASK);
  /** { series, index, x, y, width } - the ONE hovered bar, or null. */
  const [hover, setHover] = useState(null);
  const wrapRef = useRef(null);

  const metric = metricProp ?? metricLocal;
  const setMetric = setMetricProp ?? setMetricLocal;
  const mode = modeProp ?? modeLocal;
  const setMode = setModeProp ?? setModeLocal;
  const scopeLabel = scopeLabelProp ?? scopeLabelLocal;
  const setScopeLabel = setScopeLabelProp ?? setScopeLabelLocal;
  const catLabel = catLabelProp ?? catLabelLocal;
  const setCatLabel = setCatLabelProp ?? setCatLabelLocal;
  const periodMask = periodMaskProp ?? periodMaskLocal;
  const setPeriodMask = setPeriodMaskProp ?? setPeriodMaskLocal;

  const categories = result?.categories || [];
  const subCategories = result?.sub_categories || {};
  const rows1 = result?.rows_level1 || [];
  const rows2 = result?.rows_level2 || [];
  const rowHeaderLabel = rowDims[0]?.label || "Brand";

  // Selections fall back to the first available item, so a slicer/hierarchy
  // change can never leave the chart pointing at a row that no longer exists.
  const scopeName = rows1.some((r) => r.row_label === scopeLabel) ? scopeLabel : rows1[0]?.row_label || "";
  const scopeRow = rows1.find((r) => r.row_label === scopeName) || null;
  const scopeRow2 = rows2.find((r) => r.row_label === scopeName) || null;
  const catName = categories.some((c) => str(c) === catLabel) ? catLabel : str(categories[0] ?? "");
  const subs = subCategories[catName] || [];

  const isShift = metric === "shareShift";
  // Share Shift = ALL brands per group; the brand pills highlight one and dim
  // the rest (they never filter the view down to a single brand).
  const shift = useMemo(
    () => (isShift ? computeShareShift({ result, mode, catName }) : { groups: [], mode, cat: catName }),
    [isShift, result, mode, catName]
  );
  const highlightBrand = isShift && scopeName && scopeName !== "Overall" ? scopeName : "";
  const visiblePeriods = PERIODS.filter((p) => periodMask?.[p.key] !== false);


  const chartData = useMemo(() => {
    const items = [];
    if (mode === "rows") {
      for (const r of rows1) items.push({ label: r.row_label, cell: cellOf(r, catName) });
    } else if (mode === "subs") {
      for (const sub of subs) items.push({ label: str(sub), cell: cellOf(scopeRow2 || scopeRow, catName, sub) });
    } else {
      for (const cat of categories) items.push({ label: str(cat), cell: cellOf(scopeRow, cat) });
    }
    return items.map((item) => ({
      label: item.label,
      lfy: periodValue(item.cell, metric, "lfy"),
      lfytd: periodValue(item.cell, metric, "lfytd"),
      cfy: periodValue(item.cell, metric, "cfy"),
    }));
  }, [mode, catName, subs, categories, rows1, scopeRow, scopeRow2, metric]);

  // The one and only hover state: set by the bar that was entered, cleared by
  // that same bar's mouse-leave (and by any control change below).
  const periodKey = PERIODS.map((p) => (periodMask?.[p.key] === false ? "0" : "1")).join("");
  useEffect(() => {
    setHover(null);
  }, [metric, mode, scopeName, catName, periodKey]);

  const showTip = (series) => (data, index, event) => {
    const wrap = wrapRef.current;
    const el = event?.currentTarget;
    if (!wrap || !el) return;
    const wrapRect = wrap.getBoundingClientRect();
    const barRect = el.getBoundingClientRect();
    setHover({
      series,
      index,
      x: barRect.left + barRect.width / 2 - wrapRect.left,
      y: barRect.top - wrapRect.top,
      width: wrapRect.width,
    });
  };
  const hideTip = () => setHover(null);

  const formatValue = (value) => (metric === "cont" ? fmtPct(value) : fmtQty(value));
  const formatTick = (value) => (metric === "cont" ? fmtPct(value) : fmtQtyAxis(value));

  const angled = chartData.some((d) => String(d.label).length > 9) || chartData.length > 7;
  const hovered = hover ? chartData[hover.index] : null;
  const hoveredPeriod = hover ? PERIODS.find((p) => p.key === hover.series) : null;
  const tipLeft = hover ? Math.max(104, Math.min(hover.x, (hover.width || 208) - 104)) : 0;

  const modeHint =
    mode === "rows"
      ? `${catName || "Category"} x ${rowHeaderLabel}`
      : mode === "subs"
      ? `${rowChainText} x ${catName || "Category"} x Sub-Category`
      : `${rowChainText} x Category`;

  return (
    <div className="space-y-4" data-testid="cp-chart-root">
      {/* Controls - every one of them re-slices the SAME payload the table uses,
          so the chart can never disagree with the table. */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">X-Axis</span>
            {AXIS_MODES.map((m) => (
              <button
                key={m.key}
                type="button"
                title={
                  m.key === "rows"
                    ? `${catName || "Category"} x ${rowHeaderLabel}`
                    : m.key === "subs"
                    ? `${rowChainText} x Category x Sub-Category`
                    : `${rowChainText} x Category`
                }
                onClick={() => setMode(m.key)}
                className={PILL(mode === m.key)}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Measure</span>
            {METRICS.map((m) => (
              <button key={m.key} type="button" title={m.unit} onClick={() => setMetric(m.key)} className={PILL(metric === m.key)}>
                {m.label}
              </button>
            ))}
          </div>
          {/* Series checkboxes - they decide which periods the chart / tooltip
              carries. All three are ON by default, so the existing chart looks
              exactly as before until one is switched off. */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Series</span>
            {PERIODS.map((p) => {
              const on = periodMask?.[p.key] !== false;
              return (
                <button
                  key={p.key}
                  type="button"
                  data-testid={`cp-series-${p.key}`}
                  aria-pressed={on}
                  onClick={() => setPeriodMask((prev) => ({ ...(prev || DEFAULT_PERIOD_MASK), [p.key]: !on }))}
                  className={PILL(on)}
                >
                  <span className="mr-1.5 inline-block h-2 w-2 rounded-sm align-middle" style={{ background: p.color }} />
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
          <span className="font-bold tracking-widest uppercase">Rows</span>
          <span className="px-2 py-0.5 rounded-full border border-border bg-surface font-semibold text-text-secondary">{rowChainText}</span>
          <span>{activeFilterCount > 0 ? `· ${activeFilterCount} global filter${activeFilterCount > 1 ? "s" : ""} applied above` : "· no global filters applied"}</span>
        </div>
      </div>

      {/* Scope selectors.
          QTY / CONT%: the row pills PICK the single row the chart is cut by.
          Share Shift: every brand is on screen at once - the pills HIGHLIGHT
          one brand and dim the rest, so the shift stays comparable. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {mode !== "rows" && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
              {isShift ? `${rowHeaderLabel} · highlight` : rowHeaderLabel}
            </span>
            {rows1.map((r) => {
              const isOverallPill = r.row_label === "Overall";
              const active = isShift
                ? isOverallPill
                  ? !highlightBrand
                  : highlightBrand === r.row_label
                : scopeName === r.row_label;
              return (
                <button
                  key={r.row_label}
                  type="button"
                  data-testid={`cp-scope-${r.row_label}`}
                  onClick={() => {
                    if (!isShift) {
                      setScopeLabel(r.row_label);
                      return;
                    }
                    // Overall = show every brand; a brand pill toggles its
                    // highlight without ever hiding the others.
                    setScopeLabel(
                      isOverallPill || highlightBrand === r.row_label ? "Overall" : r.row_label
                    );
                  }}
                  className={PILL(active)}
                >
                  {r.row_label}
                </button>
              );
            })}
          </div>
        )}
        {mode !== "categories" && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Category</span>
            {categories.map((c) => (
              <button key={str(c)} type="button" onClick={() => setCatLabel(str(c))} className={PILL(catName === str(c))}>
                {str(c)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Legend + one-line readout of what is plotted. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-[11px] font-semibold">
          {isShift ? (
            <>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: LOSS_COLOR }} />
                Lost share
              </span>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: GAIN_COLOR }} />
                Gained share
              </span>
              <span className="font-medium text-text-muted">pp = CFYTD cont% − LFYTD cont%</span>
            </>
          ) : (
            visiblePeriods.map((p) => (
              <span key={p.key} className="inline-flex items-center gap-1.5 text-text-secondary">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: p.color }} />
                {p.label}
              </span>
            ))
          )}
        </div>
        <div className="text-[11px] text-text-muted">
          {isShift
            ? `${shift.groups.length} ${mode === "subs" ? "sub-category" : "category"} group${shift.groups.length === 1 ? "" : "s"} · `
            : `${chartData.length} x-axis item${chartData.length === 1 ? "" : "s"} · `}
          <span className="font-semibold text-text-secondary">{modeHint}</span>
        </div>
      </div>


      {isShift ? (
        <>
          {/* SMALL MULTIPLES - one diverging panel per group (one Category, or
              one Sub-Category when the x-axis asks for it). Every panel keeps
              ALL brands on screen; the highlight only dims the rest. */}
          <div
            className={clsx(
              "grid gap-4",
              shift.groups.length === 1 ? "grid-cols-1" : "md:grid-cols-2 xl:grid-cols-3"
            )}
            data-testid="cp-shift-chart"
          >
            {shift.groups.map((g) => (
              <ShareShiftPanel
                key={g.key}
                group={g}
                highlightBrand={highlightBrand}
                periodMask={periodMask}
              />
            ))}
          </div>

          {shift.groups.length === 0 && (
            <div className="p-6 text-center text-text-muted text-sm">No brand sales in the current selection.</div>
          )}
        </>
      ) : (
        <>
          {/* THE chart. The wrapper is `relative` so the ONE tooltip can be pinned
              to the bar that is actually hovered; the chart renders no other
              tooltip component at all. */}
          <div ref={wrapRef} className="relative" data-testid="cp-chart">
            {hovered && hoveredPeriod && (
              <div
                data-testid="cp-chart-tooltip"
                className="absolute z-20 pointer-events-none -translate-x-1/2 -translate-y-full"
                style={{ left: tipLeft, top: Math.max(4, hover.y - 6) }}
              >
                <div className="bg-surface border border-border shadow-panel-lg rounded-lg px-3 py-2 text-xs whitespace-nowrap">
                  <div className="font-bold text-text-primary">{hovered.label}</div>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-1.5 font-semibold text-text-secondary">
                      <span className="inline-block w-2 h-2 rounded-sm" style={{ background: hoveredPeriod.color }} />
                      {hoveredPeriod.label}
                    </span>
                    <span className="font-bold tabular-nums text-text-primary">{formatValue(hovered[hoveredPeriod.key])}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="h-[420px] w-full" onMouseLeave={hideTip} data-testid="cp-chart-canvas">
              {visiblePeriods.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-text-muted">
                  Select at least one series to plot.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 14, right: 20, left: 8, bottom: 4 }} barCategoryGap="22%">
                    <CartesianGrid stroke={GRID_COLOR} strokeOpacity={0.18} vertical={false} />
                    <XAxis
                      dataKey="label"
                      interval={0}
                      tick={{ fontSize: 11, fill: GRID_COLOR }}
                      angle={angled ? -25 : 0}
                      textAnchor={angled ? "end" : "middle"}
                      height={angled ? 74 : 30}
                      tickLine={false}
                      axisLine={{ stroke: GRID_COLOR, strokeOpacity: 0.35 }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: GRID_COLOR }}
                      tickFormatter={formatTick}
                      width={64}
                      tickLine={false}
                      axisLine={false}
                    />
                    {visiblePeriods.map((p) => (
                      <Bar
                        key={p.key}
                        dataKey={p.key}
                        name={p.label}
                        fill={p.color}
                        radius={[3, 3, 0, 0]}
                        maxBarSize={38}
                        isAnimationActive={false}
                        onMouseEnter={showTip(p.key)}
                        onMouseLeave={hideTip}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {chartData.length === 0 && (
            <div className="p-6 text-center text-text-muted text-sm">No cells in the current selection.</div>
          )}
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * TABLE FALLBACK - the SAME share-shift numbers as the diverging chart, one
 * block per group:
 *
 *     Category -> Overall (reference row)
 *       Brand | LFY Cont% | LFYTD Cont% | CFYTD Cont% | pp Chg | Rank Chg
 *
 * The Overall row comes first (that group's own 100% total), then every brand
 * in pp-change order. Negative pp is red, positive is green, and each group
 * header prints the pp sum so the reader can confirm it lands on ~0.
 * ------------------------------------------------------------------------- */
export function ShareShiftTable({ result, mode, catName, scopeLabel, periodMask, rowHeaderLabel = "Brand" }) {
  const categories = result?.categories || [];
  const cat = categories.some((c) => str(c) === catName) ? catName : str(categories[0] ?? "");
  const shift = useMemo(() => computeShareShift({ result, mode, catName: cat }), [result, mode, cat]);
  const mask = periodMask || DEFAULT_PERIOD_MASK;
  const highlightBrand = scopeLabel && scopeLabel !== "Overall" ? scopeLabel : "";
  const colCount = 5 + (mask.lfy ? 1 : 0) + (mask.lfytd ? 1 : 0) + (mask.cfy ? 1 : 0);

  if (!shift.groups.length) {
    return <div className="p-6 text-center text-text-muted text-sm">No brand sales in the current selection.</div>;
  }

  const th = "px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-text-secondary border-b border-border whitespace-nowrap";
  const td = "px-3 py-2 border-b border-border/60";

  return (
    <div className="space-y-4" data-testid="cp-shift-table">
      <div className="overflow-auto rounded-xl border border-border" style={{ maxHeight: "70vh" }}>
        <table className="w-full text-sm" style={{ borderCollapse: "separate", borderSpacing: 0 }}>
          <thead className="sticky top-0 z-[4] bg-card-hover">
            <tr>
              <th className={`${th} text-left`}>Category</th>
              <th className={`${th} text-left`}>{rowHeaderLabel}</th>
              {mask.lfy ? <th className={`${th} text-right`}>LFY Cont%</th> : null}
              {mask.lfytd ? <th className={`${th} text-right`}>LFYTD Cont%</th> : null}
              {mask.cfy ? <th className={`${th} text-right`}>CFYTD Cont%</th> : null}
              <th className={`${th} text-right`}>pp Chg (LFYTD→CFYTD)</th>
              <th className={`${th} text-right`}>Rank Chg</th>
              <th className={`${th} text-right`}>Unit Δ (CFYTD)</th>
            </tr>
          </thead>
          <tbody>
            {shift.groups.map((g) => (
              <Fragment key={g.key}>
                {/* Group header - the pp sum is printed so the reader can see
                    the shift nets to ~0 inside the group. */}
                <tr className="bg-surface">
                  <td colSpan={colCount} className="border-b border-border px-3 py-1.5">
                    <span className="text-xs font-bold text-accent">
                      {g.subLabel ? `${g.subLabel} · ` : ""}
                      {g.label}
                    </span>
                    <span className="ml-2 text-[10px] font-medium text-text-muted">
                      Overall {fmtQty(g.total.cfy)} units (100%) · Σ pp {g.ppSum >= 0 ? "+" : "−"}
                      {Math.abs(g.ppSum).toFixed(1)} (≈0 proves the shift)
                    </span>
                  </td>
                </tr>
                {/* Overall reference row - 100% by construction, never part of
                    the delta. */}
                <tr className="bg-card-hover/40">
                  <td className={clsx(td, "text-text-muted")}>—</td>
                  <td className={clsx(td, "whitespace-nowrap font-semibold text-accent")}>Overall (100%)</td>
                  {mask.lfy ? <td className={clsx(td, "text-right tabular-nums text-text-secondary")}>100.0%</td> : null}
                  {mask.lfytd ? <td className={clsx(td, "text-right tabular-nums text-text-secondary")}>100.0%</td> : null}
                  {mask.cfy ? <td className={clsx(td, "text-right tabular-nums text-text-secondary")}>100.0%</td> : null}
                  <td className={clsx(td, "text-right tabular-nums text-text-muted")}>±0.0 pp</td>
                  <td className={clsx(td, "text-right text-text-muted")}>—</td>
                  <td className={clsx(td, "text-right tabular-nums text-text-muted")}>{fmtQty(g.total.cfy)}</td>
                </tr>
                {/* Brand rows, biggest gainer first. */}
                {g.brands.map((b) => {
                  const isHl = highlightBrand && b.brand === highlightBrand;
                  const unitDelta = b.pp * g.unitEquiv;
                  return (
                    <tr
                      key={b.brand}
                      className={clsx("transition-colors", isHl ? "bg-accent-soft" : "hover:bg-card-hover/40")}
                    >
                      <td className={clsx(td, "text-[10px] text-text-muted")}>{g.label}</td>
                      <td className={clsx(td, "whitespace-nowrap font-medium", isHl ? "text-accent" : "text-text-primary")}>
                        {b.brand}
                      </td>
                      {mask.lfy ? <td className={clsx(td, "text-right tabular-nums text-text-secondary")}>{fmtPct(b.contLfy)}</td> : null}
                      {mask.lfytd ? <td className={clsx(td, "text-right tabular-nums text-text-secondary")}>{fmtPct(b.contLfytd)}</td> : null}
                      {mask.cfy ? <td className={clsx(td, "text-right tabular-nums font-semibold text-text-primary")}>{fmtPct(b.contCfy)}</td> : null}
                      <td
                        className={clsx(
                          td,
                          "text-right tabular-nums font-bold",
                          b.pp > 0.001 ? "text-positive" : b.pp < -0.001 ? "text-negative" : "text-text-secondary"
                        )}
                      >
                        {fmtPp(b.pp)}
                      </td>
                      <td
                        className={clsx(
                          td,
                          "text-right tabular-nums font-semibold",
                          b.rankDelta > 0 ? "text-positive" : b.rankDelta < 0 ? "text-negative" : "text-text-muted"
                        )}
                      >
                        {b.rankDelta === 0 ? "—" : `${b.rankDelta > 0 ? "▲" : "▼"} ${Math.abs(b.rankDelta)}`}
                      </td>
                      <td
                        className={clsx(
                          td,
                          "text-right tabular-nums",
                          unitDelta > 0.5 ? "text-positive" : unitDelta < -0.5 ? "text-negative" : "text-text-muted"
                        )}
                      >
                        {unitDelta >= 0 ? "+" : "−"}
                        {fmtQty(Math.abs(unitDelta))}
                      </td>
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

