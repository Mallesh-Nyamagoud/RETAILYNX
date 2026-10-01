import Card from "./Card";
import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { fmtCompactVal, fmtPct, fmtQty, growthTone } from "../../utils/format";

const ACCENT_GRADIENTS = {
  accent: "from-accent to-accent-hover",
  teal: "from-teal to-teal-dark",
  positive: "from-positive to-positive-dark",
  negative: "from-negative to-negative-dark",
  warn: "from-warn to-warn-dark",
};

function GrowthPill({ value }) {
  const tone = growthTone(value);
  if (tone === "neutral" && (value === null || value === undefined)) return null;
  const Icon = tone === "positive" ? ArrowUpRight : tone === "negative" ? ArrowDownRight : Minus;
  const toneClass =
    tone === "positive"
      ? "text-positive bg-positive-soft"
      : tone === "negative"
      ? "text-negative bg-negative-soft"
      : "text-text-secondary bg-border/50";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-0.5 text-xs font-bold px-2 py-1 rounded-full tabular-nums",
        toneClass
      )}
    >
      <Icon size={12} />
      {fmtPct(Math.abs(value))}
    </span>
  );
}

export default function KpiCard({
  label,
  qty,
  val,
  /** pct: main figure is a percentage (e.g. Growth %) - always rendered with the "%" symbol */
  pct,
  /** qtyPct: companion percentage for the Quantity unit, shown as a muted sub-line */
  qtyPct,
  growthPct,
  /** unitTag: small unit badge shown top-right (e.g. "₹ Taxable Value") */
  unitTag,
  accent = "accent",
  hint,
  compactVal = true,
  /** metaVal: optional compact currency sub-line under the main figure
   * (e.g. MRP Value on a quantity card). Renders as "MRP Val: ₹3.2Cr". */
  metaVal,
  metaLabel = "MRP Val",
  isApmCard = false,
  apmData,
}) {
  if (isApmCard && apmData) {
    // APM is now shown for ALL THREE periods in ONE card - LFY (average per
    // month across the full last fiscal year), LFYTD (the same year-to-date
    // window, last fiscal year) and CFYTD (the current year-to-date window).
    // Every period keeps the established card shape: value on top, "X units"
    // beneath it.
    const periods = [
      { key: "lfy", label: "LFY APM", tone: "muted" },
      { key: "lfytd", label: "LFYTD APM", tone: "muted" },
      { key: "cfytd", label: "CFYTD APM", tone: "current" },
    ];
    return (
      <Card
        padded={false}
        className="flex flex-col col-span-2 md:col-span-4 xl:col-span-2 shadow-sm border border-border/50 relative overflow-hidden group hover:border-border transition-colors bg-surface"
      >
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-accent via-accent to-teal opacity-80" />
        <div className="px-3 pt-3 pb-2 flex justify-between items-center">
          <h3 className="text-[11px] font-bold text-text-muted uppercase tracking-widest">{label}</h3>
          <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wide">avg / month</span>
        </div>
        <div className="px-3 pb-3 flex flex-row gap-3 divide-x divide-border">
          {periods.map((p, idx) => {
            const period = apmData[p.key] || {};
            return (
              <div key={p.key} className={clsx("flex-1 min-w-0", idx > 0 && "pl-3")}>
                <div className={clsx("text-[10px] font-bold uppercase tracking-wider mb-1", p.tone === "current" ? "text-teal" : "text-text-secondary")}>
                  {p.label}
                </div>
                <div className="flex items-baseline gap-1.5 truncate">
                  <span className="text-lg font-black tracking-tight text-text-primary truncate">
                    {fmtCompactVal(period.val)}
                  </span>
                  {unitTag && <span className="text-[10px] font-semibold text-text-muted whitespace-nowrap">/ {unitTag}</span>}
                </div>
                <div className="text-xs font-medium text-text-secondary mt-0.5 truncate">
                  <span className="font-bold text-text-primary">{period.qty == null ? "—" : fmtQty(period.qty)}</span> units
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    );
  }
  const isPctMain = pct !== undefined;
  const mainText = isPctMain
    ? fmtPct(pct)
    : val !== undefined
    ? compactVal
      ? fmtCompactVal(val)
      : val
    : fmtQty(qty);
  // Percentage headlines carry their own +/- tone colour instead of the pill
  const pctTone = isPctMain ? growthTone(pct) : null;
  const mainClass = isPctMain
    ? pctTone === "positive"
      ? "text-positive"
      : pctTone === "negative"
      ? "text-negative"
      : "text-text-secondary"
    : "text-text-primary";
  const sub = isPctMain
    ? qtyPct !== undefined
      ? `${fmtPct(qtyPct)} units`
      : null
    : val !== undefined && qty !== undefined
    ? `${fmtQty(qty)} units`
    : null;

  return (
    <Card padded={false}>
      <div
        className={clsx(
          "absolute left-0 top-0 h-full w-2 bg-gradient-to-b rounded-l-xl",
          ACCENT_GRADIENTS[accent]
        )}
      />
      <div className="pl-6 pr-4 py-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-bold tracking-wider text-text-secondary uppercase">
            {label}
          </p>
          {growthPct !== undefined ? (
            <GrowthPill value={growthPct} />
          ) : unitTag ? (
            <span className="text-[10px] font-semibold tracking-wide text-text-muted uppercase whitespace-nowrap">
              {unitTag}
            </span>
          ) : null}
        </div>
        <div className="mt-2 flex items-end justify-between gap-3">
          <div>
            <p
              className={clsx(
                "font-display text-3xl font-bold tabular-nums leading-tight",
                mainClass
              )}
            >
              {mainText}
            </p>
            {sub && <p className="text-base text-text-muted mt-1 tabular-nums">{sub}</p>}
            {metaVal !== undefined && metaVal !== null && (
              <p className="text-base text-text-secondary mt-1 tabular-nums font-medium">
                <span className="text-text-muted font-semibold">{metaLabel}: </span>
                {fmtCompactVal(metaVal)}
              </p>
            )}
          </div>
        </div>
        {hint && <p className="text-sm text-text-muted mt-2">{hint}</p>}
      </div>
    </Card>
  );
}
