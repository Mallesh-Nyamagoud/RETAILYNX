/**
 * ComparisonBarChart - the Dashboard's Power BI style period-comparison visual.
 *
 * One grouped bar chart per analysis dimension (Brand / Group / ...) showing the
 * three periods the rest of the app reports - LFY FULL, LFYTD and CFYTD - with
 * everything a Power BI visual gives you:
 *
 *   · Data labels + value axis in DYNAMIC Indian compact numbers ("1.00Cr",
 *     "1.00L", "1.00K"), so a label never widens the plot area.
 *   · A rich hover tooltip card: category, per-period compact + exact value,
 *     CFYTD share of the visible total and CFYTD-vs-LFYTD growth.
 *   · Cross-filtering: clicking a bar selects that category for the WHOLE page.
 *     This visual keeps every category on screen and dims the rest (Power BI's
 *     cross-highlight), while the other visuals re-query filtered.
 *   · Per-period series toggles, theme-aware colours and a header summary
 *     (total CFYTD + growth) exactly like a report-page visual header.
 */
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, Filter, Minus, X } from "lucide-react";
import Card from "../common/Card";
import { fmtIndianCompact, fmtPct, fmtVal, growthTone } from "../../utils/format";
import { PERIOD_SERIES, useChartPalette } from "./chartTheme";

const CHIP =
  "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-semibold text-text-secondary";

const pillClass = (active) =>
  clsx(
    "px-3 py-1.5 text-xs font-semibold rounded-md transition-colors border",
    active
      ? "bg-accent text-white border-transparent shadow-sm"
      : "bg-surface text-text-secondary border-border hover:text-text-primary"
  );

/** CFYTD vs LFYTD growth in %, or null when there is no prior-period base.
 *  The base is divided as an ABSOLUTE value so the sign always reads as
 *  "better / worse" - a negative prior period flips the sign of a signed
 *  denominator and would report a recovery as a decline. */
function pctGrowth(previous, current) {
  const base = Number(previous) || 0;
  if (!base) return null;
  return (((Number(current) || 0) - base) / Math.abs(base)) * 100;
}

function GrowthPill({ value }) {
  const tone = growthTone(value);
  if (value === null || value === undefined) {
    return <span className={clsx(CHIP, "text-text-muted")}>no base</span>;
  }
  const Icon = tone === "positive" ? ArrowUpRight : tone === "negative" ? ArrowDownRight : Minus;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-0.5 rounded-full px-2.5 py-1 text-[11px] font-bold tabular-nums",
        tone === "positive"
          ? "bg-positive-soft text-positive"
          : tone === "negative"
          ? "bg-negative-soft text-negative"
          : "bg-border/50 text-text-secondary"
      )}
      title="CFYTD vs LFYTD"
    >
      <Icon size={12} />
      {fmtPct(Math.abs(value))}
    </span>
  );
}

/** One period line inside the hover card: swatch · label · compact · exact. */
function SeriesRow({ color, label, value }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: color }} />
      <span className="w-12 shrink-0 font-semibold text-text-secondary">{label}</span>
      <span className="flex-1 text-right font-bold tabular-nums text-text-primary" title={fmtVal(value)}>
        {fmtIndianCompact(value)}
      </span>
    </div>
  );
}

/** Power BI style hover card for one bar group. Reads the whole data row off the
 * payload (so hidden periods are skipped) and adds the derived read-outs a
 * report tooltip carries: CFYTD share, growth and the exact rupee figure. */
function ComparisonTooltip({ active, payload, palette, measureLabel, visibleKeys, interactive, selectedValue }) {
  if (!active || !payload || !payload.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const growth = pctGrowth(row.LFYTD, row.CFYTD);
  const isSelected = selectedValue !== null && selectedValue !== undefined && selectedValue === row.name;
  return (
    <div
      className="pointer-events-none w-[248px] rounded-lg border px-3 py-2.5 text-xs shadow-panel-lg backdrop-blur-sm"
      style={{ background: palette.tooltipBg, borderColor: palette.tooltipBorder }}
      data-testid="dash-comparison-tooltip"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-bold text-text-primary" title={row.name}>
            {row.name}
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {measureLabel}
          </div>
        </div>
        {row.share !== null && row.share !== undefined && (
          <span
            className="shrink-0 rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-accent"
            title="Share of the visible CFYTD total"
          >
            {fmtPct(row.share * 100)}
          </span>
        )}
      </div>

      <div className="mt-2 space-y-1">
        {PERIOD_SERIES.filter((s) => visibleKeys.includes(s.key)).map((s) => (
          <SeriesRow key={s.key} color={palette.series[s.key]} label={s.label} value={row[s.key]} />
        ))}
      </div>

      <div className="mt-2 space-y-1 border-t border-border pt-1.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">CFYTD vs LFYTD</span>
          <GrowthPill value={growth} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">Exact CFYTD</span>
          <span className="font-semibold tabular-nums text-text-secondary">{fmtVal(row.CFYTD)}</span>
        </div>
      </div>

      {interactive && (
        <div className="mt-2 border-t border-border pt-1.5 text-[10px] font-medium text-text-muted">
          {isSelected ? "Click the bar again to clear this cross-filter" : "Click the bar to cross-filter every visual"}
        </div>
      )}
    </div>
  );
}

export default function ComparisonBarChart({
  title,
  eyebrow,
  measureLabel = "Taxable Value (₹)",
  data = [],
  /** This visual's own cross-filter selection (keeps all bars, dims the rest). */
  selectedValue = null,
  /** (name) => void - toggles the page-wide cross-filter for this dimension. */
  onSelect,
  /** { label, value } coming from ANOTHER visual - this one is filtered by it. */
  receivingFilter = null,
  onClearFilters,
  dataTestId,
  height = 350,
}) {
  const palette = useChartPalette();
  const [hidden, setHidden] = useState({});

  const visibleSeries = PERIOD_SERIES.filter((s) => !hidden[s.key]);
  const visibleKeys = visibleSeries.map((s) => s.key);

  const totals = useMemo(() => {
    const acc = { LFY: 0, LFYTD: 0, CFYTD: 0 };
    for (const row of data) {
      for (const key of ["LFY", "LFYTD", "CFYTD"]) acc[key] += Number(row[key]) || 0;
    }
    return acc;
  }, [data]);

  const chartData = useMemo(
    () =>
      data.map((row) => ({
        ...row,
        share: totals.CFYTD > 0 ? (Number(row.CFYTD) || 0) / totals.CFYTD : null,
      })),
    [data, totals]
  );

  const growth = pctGrowth(totals.LFYTD, totals.CFYTD);
  const angledTicks = useMemo(() => data.some((row) => String(row.name ?? "").length > 12), [data]);
  // A report hides data labels once the bars get too dense to read.
  const showLabels = data.length > 0 && data.length <= 15;
  const showBrush = data.length > 12;
  const interactive = typeof onSelect === "function";
  const filtered = Boolean(selectedValue || receivingFilter);

  /** Recharts hands the chart-level click the hovered category in activeLabel.
   * The event is checked so dragging the Brush (only present when there are
   * many categories) never fires a cross-filter. */
  const handleChartClick = (state, event) => {
    if (!interactive) return;
    if (event?.target?.closest?.(".recharts-brush")) return;
    const name =
      state?.activeLabel !== undefined && state?.activeLabel !== null
        ? state.activeLabel
        : state?.activePayload?.[0]?.payload?.name;
    if (name === undefined || name === null || name === "") return;
    onSelect(name);
  };

  /** Never let the user switch every period off - the last one stays on. */
  const toggleSeries = (key, isOn) =>
    setHidden((prev) => {
      const next = { ...prev, [key]: isOn };
      return PERIOD_SERIES.some((s) => !next[s.key]) ? next : prev;
    });

  return (
    <Card data-testid={dataTestId}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
          )}
          <h3 className="mt-1 text-sm font-semibold uppercase tracking-wide text-text-primary">{title}</h3>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className={CHIP}>
              <span className="text-text-muted">Total CFYTD</span>
              <span className="tabular-nums font-bold text-text-primary">
                {fmtIndianCompact(totals.CFYTD)}
              </span>
            </span>
            <GrowthPill value={growth} />
            {data.length > 0 && (
              <span className={clsx(CHIP, "tabular-nums")} title="Categories on screen">
                {data.length} {data.length === 1 ? "category" : "categories"}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Series</span>
            {PERIOD_SERIES.map((s) => {
              const on = !hidden[s.key];
              return (
                <button
                  key={s.key}
                  type="button"
                  aria-pressed={on}
                  title={`${s.hint} — toggle this series`}
                  data-testid={dataTestId ? `${dataTestId}-series-${s.key}` : undefined}
                  onClick={() => toggleSeries(s.key, on)}
                  className={pillClass(on)}
                >
                  <span
                    className="mr-1.5 inline-block h-2 w-2 rounded-sm align-middle"
                    style={{ background: palette.series[s.key] }}
                  />
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {filtered && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <Filter size={13} className="shrink-0 text-accent" />
          {selectedValue && (
            <button
              type="button"
              onClick={() => onSelect(selectedValue)}
              title="Clear this selection"
              className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent-soft px-2.5 py-1 text-[11px] font-bold text-accent transition-colors hover:border-accent"
            >
              Selected · {selectedValue}
              <X size={11} />
            </button>
          )}
          {receivingFilter && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-semibold text-text-secondary">
              Filtered by {receivingFilter.label} =
              <span className="font-bold text-text-primary">{receivingFilter.value}</span>
            </span>
          )}
          {onClearFilters && (
            <button
              type="button"
              onClick={onClearFilters}
              className="ml-auto text-[11px] font-semibold text-text-muted underline-offset-2 transition-colors hover:text-text-primary hover:underline"
            >
              Clear all filters
            </button>
          )}
        </div>
      )}

      <div className="mt-4" style={{ height }}>
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-surface/40 px-4 text-center text-xs font-medium text-text-muted">
            No categories to compare for the current filters.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 18, right: 12, left: 4, bottom: angledTicks ? 30 : 6 }}
              barCategoryGap="20%"
              style={{ cursor: interactive ? "pointer" : "default" }}
              onClick={handleChartClick}
            >
              <CartesianGrid vertical={false} stroke={palette.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                interval={0}
                angle={angledTicks ? -20 : 0}
                textAnchor={angledTicks ? "end" : "middle"}
                height={angledTicks ? 72 : 30}
                tick={{ fill: palette.axis, fontSize: 11, fontWeight: 500 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={58}
                tick={{ fill: palette.axis, fontSize: 11 }}
                tickFormatter={(value) => fmtIndianCompact(value, { blank: "0" })}
              />
              <Tooltip
                cursor={{ fill: palette.cursor }}
                content={
                  <ComparisonTooltip
                    palette={palette}
                    measureLabel={measureLabel}
                    visibleKeys={visibleKeys}
                    interactive={interactive}
                    selectedValue={selectedValue}
                  />
                }
              />
              {showBrush && (
                <Brush
                  dataKey="name"
                  height={22}
                  stroke={palette.grid}
                  fill="transparent"
                  travellerWidth={9}
                  tickFormatter={() => ""}
                />
              )}
              {visibleSeries.map((s) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  name={s.label}
                  fill={palette.series[s.key]}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={34}
                >
                  {chartData.map((row, index) => {
                    // Power BI cross-highlight: the selected category keeps full
                    // colour, every other bar of THIS visual dims out.
                    const dimmed = selectedValue ? row.name !== selectedValue : false;
                    return (
                      <Cell
                        key={`${s.key}-${index}`}
                        fill={palette.series[s.key]}
                        fillOpacity={dimmed ? 0.2 : 1}
                      />
                    );
                  })}
                  {showLabels && (
                    <LabelList
                      dataKey={s.key}
                      position="top"
                      offset={6}
                      formatter={(value) => fmtIndianCompact(value, { blank: "" })}
                      fill={palette.label}
                      fontSize={10}
                      fontWeight={600}
                    />
                  )}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
