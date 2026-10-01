/**
 * ContributionDonutChart - the Dashboard's share-of-total visual.
 *
 * Same Power BI behaviours as the comparison bars:
 *   · dynamic Indian compact numbers in the slice labels, the centre read-out
 *     and the hover card ("1.00Cr" / "1.00L"),
 *   · a centre total that switches to the SELECTED slice's value + share,
 *   · click a slice to cross-filter the page - this visual keeps every slice on
 *     screen and dims the others (cross-highlight), the rest re-query.
 */
import { useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import clsx from "clsx";
import { Filter, X } from "lucide-react";
import Card from "../common/Card";
import { fmtIndianCompact, fmtPct, fmtVal } from "../../utils/format";
import { useChartPalette } from "./chartTheme";

/** Power BI style donut hover card: compact value, exact value, contribution. */
function DonutTooltip({ active, payload, palette, measureLabel, selectedValue, interactive }) {
  if (!active || !payload || !payload.length) return null;
  const slice = payload[0]?.payload;
  if (!slice) return null;
  const isSelected = selectedValue !== null && selectedValue !== undefined && selectedValue === slice.name;
  return (
    <div
      className="pointer-events-none w-[218px] rounded-lg border px-3 py-2.5 text-xs shadow-panel-lg backdrop-blur-sm"
      style={{ background: palette.tooltipBg, borderColor: palette.tooltipBorder }}
      data-testid="dash-donut-tooltip"
    >
      <div className="flex items-start gap-2">
        <span className="mt-1 h-2 w-2 shrink-0 rounded-sm" style={{ background: slice.fill }} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold text-text-primary" title={slice.name}>
            {slice.name}
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {measureLabel}
          </div>
        </div>
        <span
          className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-text-secondary"
          title="Rank by CFYTD"
        >
          #{slice.rank}
        </span>
      </div>
      <div className="mt-2 space-y-1">
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">CFYTD</span>
          <span className="font-bold tabular-nums text-text-primary" title={fmtVal(slice.value)}>
            {fmtIndianCompact(slice.value)}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">Exact</span>
          <span className="tabular-nums font-semibold text-text-secondary">{fmtVal(slice.value)}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-text-muted">Contribution</span>
          <span className="font-bold tabular-nums text-accent">{fmtPct((slice.percent || 0) * 100)}</span>
        </div>
      </div>
      {interactive && (
        <div className="mt-2 border-t border-border pt-1.5 text-[10px] font-medium text-text-muted">
          {isSelected ? "Click again to clear this cross-filter" : "Click to cross-filter every visual"}
        </div>
      )}
    </div>
  );
}

export default function ContributionDonutChart({
  title,
  data = [],
  measureLabel = "Taxable Value (₹)",
  selectedValue = null,
  onSelect,
  receivingFilter = null,
  onClearFilters,
  dataTestId,
  height = 250,
  /** Slices thinner than this keep their tooltip but drop the outside label. */
  labelThreshold = 0.03,
}) {
  const palette = useChartPalette();
  /** Hovered category - shared by the slices and the legend rows, so hovering
   *  either one highlights the other (Power BI cross-highlight). */
  const [hoveredName, setHoveredName] = useState(null);

  const slices = useMemo(
    () =>
      data.map((slice, index) => ({
        ...slice,
        rank: index + 1,
        fill: palette.donut[index % palette.donut.length],
      })),
    [data, palette]
  );
  const total = useMemo(
    () => slices.reduce((sum, slice) => sum + (Number(slice.value) || 0), 0),
    [slices]
  );

  const interactive = typeof onSelect === "function";
  const filtered = Boolean(selectedValue || receivingFilter);
  const selectedSlice = selectedValue ? slices.find((slice) => slice.name === selectedValue) : null;

  /** Outside label: compact value + contribution %, skipped when too thin. */
  const renderSliceLabel = ({ cx, cy, midAngle, outerRadius, percent, value, name }) => {
    if (!percent || percent < labelThreshold) return null;
    const radius = outerRadius + 14;
    const RADIAN = Math.PI / 180;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);
    // Selection (cross-filter) wins over hover - same rule as the slices.
    const focus = selectedValue || hoveredName;
    const dimmed = Boolean(focus) && focus !== name;
    return (
      <text
        key={`label-${name}`}
        x={x}
        y={y}
        textAnchor={x > cx ? "start" : "end"}
        dominantBaseline="central"
        fontSize={10}
        fontWeight={600}
        fill={dimmed ? palette.axis : palette.label}
        opacity={dimmed ? 0.45 : 1}
      >
        {`${fmtIndianCompact(value)} · ${(percent * 100).toFixed(1)}%`}
      </text>
    );
  };

  const handleSliceClick = (entry) => {
    if (!interactive) return;
    const name = entry?.name ?? entry?.payload?.name;
    if (name === undefined || name === null || name === "") return;
    onSelect(name);
  };

  return (
    <Card data-testid={dataTestId}>
      <h3 className="text-center text-sm font-semibold uppercase tracking-wide text-text-primary">{title}</h3>

      {filtered && (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          <Filter size={12} className="shrink-0 text-accent" />
          {selectedValue && (
            <button
              type="button"
              onClick={() => onSelect(selectedValue)}
              title="Clear this selection"
              className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent-soft px-2 py-0.5 text-[10px] font-bold text-accent transition-colors hover:border-accent"
            >
              {selectedValue}
              <X size={10} />
            </button>
          )}
          {receivingFilter && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
              {receivingFilter.label} ={" "}
              <span className="font-bold text-text-primary">{receivingFilter.value}</span>
            </span>
          )}
          {onClearFilters && (
            <button
              type="button"
              onClick={onClearFilters}
              className="text-[10px] font-semibold text-text-muted underline-offset-2 transition-colors hover:text-text-primary hover:underline"
            >
              Clear
            </button>
          )}
        </div>
      )}

      <div className="relative mt-2" style={{ height }}>
        {slices.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-surface/40 px-4 text-center text-xs font-medium text-text-muted">
            No contribution to show for the current filters.
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius="52%"
                  outerRadius="74%"
                  paddingAngle={2}
                  label={renderSliceLabel}
                  labelLine={{ stroke: palette.grid, strokeWidth: 1 }}
                  onClick={handleSliceClick}
                  onMouseEnter={(_, index) => setHoveredName(slices[index]?.name ?? null)}
                  onMouseLeave={() => setHoveredName(null)}
                  style={{ cursor: interactive ? "pointer" : "default" }}
                  isAnimationActive={false}
                >
                  {slices.map((slice) => {
                    // Selection (cross-filter) wins over hover, exactly like the
                    // comparison bars: every category stays on screen and the
                    // ones that are not in focus are dimmed.
                    const focus = selectedValue || hoveredName;
                    const dimmed = Boolean(focus) && slice.name !== focus;
                    const emphasised = slice.name === focus;
                    return (
                      <Cell
                        key={slice.name}
                        fill={slice.fill}
                        fillOpacity={dimmed ? 0.22 : 1}
                        stroke={emphasised ? palette.series.CFYTD : "transparent"}
                        strokeWidth={emphasised ? 2 : 0}
                      />
                    );
                  })}
                </Pie>
                <Tooltip
                  content={
                    <DonutTooltip
                      palette={palette}
                      measureLabel={measureLabel}
                      selectedValue={selectedValue}
                      interactive={interactive}
                    />
                  }
                />
              </PieChart>
            </ResponsiveContainer>

            {/* Centre read-out: the visual total, or the selected slice's own
                value + contribution once a cross-filter is on. */}
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
              <span className="text-[9px] font-bold uppercase tracking-widest text-text-muted">
                {selectedSlice ? "Selected" : "Total"}
              </span>
              <span className="font-display text-lg font-bold leading-tight tabular-nums text-text-primary">
                {fmtIndianCompact(selectedSlice ? selectedSlice.value : total)}
              </span>
              <span
                className={
                  selectedSlice
                    ? "text-[10px] font-bold text-accent"
                    : "text-[10px] font-semibold text-text-muted"
                }
              >
                {selectedSlice
                  ? fmtPct((selectedSlice.percent || 0) * 100)
                  : `${slices.length} ${slices.length === 1 ? "slice" : "slices"}`}
              </span>
            </div>
          </>
        )}
      </div>

      {/* FLAGSHIP LEGEND - every category NAMED, with its CFYTD value and its
          share of the total, plus a proportional tint bar behind each row so the
          ranking reads at a glance. Rows behave exactly like the slices:
          hovering highlights both, clicking cross-filters the whole page. */}
      {slices.length > 0 && (
        <div
          className="mt-4 border-t border-border pt-3"
          data-testid={dataTestId ? `${dataTestId}-legend` : "dash-donut-legend"}
        >
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
              Legend
            </span>
            <span className="text-[10px] font-semibold text-text-muted">
              {slices.length} {slices.length === 1 ? "category" : "categories"} · {measureLabel}
            </span>
          </div>

          <ul
            role="list"
            onMouseLeave={() => setHoveredName(null)}
            className="max-h-48 space-y-0.5 overflow-y-auto pr-1"
          >
            {slices.map((slice) => {
              const isSelected = slice.name === selectedValue;
              const focus = selectedValue || hoveredName;
              const dimmed = Boolean(focus) && slice.name !== focus;
              const share = (slice.percent || 0) * 100;
              return (
                <li key={slice.name}>
                  <button
                    type="button"
                    onClick={interactive ? () => onSelect(slice.name) : undefined}
                    onMouseEnter={() => setHoveredName(slice.name)}
                    tabIndex={interactive ? 0 : -1}
                    aria-pressed={isSelected}
                    aria-disabled={!interactive}
                    title={`${slice.name} — ${fmtVal(slice.value)} (${fmtPct(share)} of ${measureLabel})`}
                    className={clsx(
                      "relative flex w-full items-center gap-2 overflow-hidden rounded-lg border px-2 py-1.5 text-left transition-colors",
                      isSelected
                        ? "border-accent bg-accent-soft"
                        : "border-transparent hover:border-border-strong hover:bg-card-hover",
                      dimmed && "opacity-60",
                      interactive ? "cursor-pointer" : "cursor-default"
                    )}
                  >
                    {/* Proportional tint bar: this category's weight in the ring. */}
                    <span
                      aria-hidden="true"
                      className="absolute inset-y-0 left-0 rounded-r-sm"
                      style={{
                        width: `${Math.max(share, 1)}%`,
                        background: slice.fill,
                        opacity: dimmed ? 0.1 : 0.16,
                      }}
                    />
                    <span
                      className="relative h-2.5 w-2.5 shrink-0 rounded-sm ring-1 ring-inset ring-black/10"
                      style={{ background: slice.fill }}
                    />
                    <span
                      className="relative min-w-0 flex-1 truncate text-xs font-semibold text-text-primary"
                      title={slice.name}
                    >
                      {slice.name}
                    </span>
                    <span className="relative shrink-0 text-xs font-bold tabular-nums text-text-primary">
                      {fmtIndianCompact(slice.value)}
                    </span>
                    <span
                      className={clsx(
                        "relative w-[52px] shrink-0 rounded-md px-1.5 py-0.5 text-center text-[10px] font-bold tabular-nums",
                        isSelected ? "bg-accent text-white" : "bg-surface text-text-secondary"
                      )}
                    >
                      {fmtPct(share)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

