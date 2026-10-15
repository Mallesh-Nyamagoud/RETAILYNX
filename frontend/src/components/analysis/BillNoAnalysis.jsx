import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Layers,
  Minus,
  RefreshCw,
  Table2,
  Trophy,
} from "lucide-react";
import clsx from "clsx";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Card from "../common/Card";
import SectionCard from "../common/SectionCard";
import DataTable from "../common/DataTable";
import { LoadingState, ErrorState } from "../common/LoadingState";
import { billKpiApi } from "../../api/client";
import {
  fmtCompactVal,
  fmtDate,
  fmtNumber,
  fmtPct,
  fmtQty,
  fmtVal,
  growthTone,
} from "../../utils/format";

/* ---------------------------------------------------------------------------
 * Bill No. Based Analysis (Tertiary Sales)
 *
 * Every figure comes from the backend's BILL-LEVEL dataset (INTERNAL_BILL_ID
 * = ADONIS_CODE-FY{yy}-{MM}-BILL_NO per store).  A bill is counted once and
 * never split by brand; buckets are classified on the AGGREGATED bill qty /
 * value; invalid "NA"/blank bill numbers are excluded server-side.
 *
 * Layout (all sections react to the same global filter bar):
 *   1. KPI cards       - Total Bills / UPT / ABV / ASP / SPD / Active Days,
 *                        each with CFY + LFY + Growth % in one card.
 *   2. Row hierarchy   - drag-and-drop dimensional column picker (1..3
 *                        levels); every cell shows ALL KPIs as one stack of
 *                        CFY / LFY / Growth.
 *   3. Distributions   - chart-first (auto-falls back to table); buckets are
 *                        the COLUMN HEADERS; each cell answers "HOW MANY bills
 *                        landed in this bucket" - CFY / Cont% / LFY / Cont% /
 *                        pp Δ - bill-count based, NO UPT / ABV / ASP.
 *   4. Top Bills       - podium ranks (gold/silver/bronze), ranked by bill
 *                        value (descending), ALWAYS in rank order 1..n, LFY vs
 *                        CFY side by side (or toggled).
 * ------------------------------------------------------------------------- */

const MAX_LEVELS = 3;
const KPI_ORDER = ["total_bills", "upt", "abv", "asp"];
const KPI_LABELS = { total_bills: "Bills", upt: "UPT", abv: "ABV", asp: "ASP" };
const ACCENT_BAR = {
  accent: "bg-accent",
  teal: "bg-teal",
  positive: "bg-positive",
  warn: "bg-warn",
};
const CARD_ACCENTS = ["accent", "teal", "positive", "warn"];

// Podium styling for the Top-3 bills (gold / silver / bronze look).
const RANK_BADGE = {
  1: "bg-warn-soft text-warn",
  2: "bg-border/60 text-text-secondary",
  3: "bg-teal-soft text-teal",
};

const kpiFmt = (kpi) =>
  kpi?.fmt === "val" ? fmtCompactVal : kpi?.fmt === "qty" ? fmtQty : fmtNumber;

function fmtKpi(v, kpi) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return kpiFmt(kpi)(v);
}

/** Subtle value-change animation (KPI cards / cells). */
function AnimatedNumber({ value, format, className = "" }) {
  const prev = useRef(value);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 500);
      return () => clearTimeout(t);
    }
  }, [value]);
  return (
    <span
      className={clsx(
        "inline-block transition-all duration-300 ease-out",
        flash ? "scale-110 text-accent" : "scale-100",
        className
      )}
    >
      {format(value)}
    </span>
  );
}

/** Colour-coded growth pill (green = positive, red = negative, neutral = flat). */
function GrowthPill({ value }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-text-muted text-xs">—</span>;
  }
  const tone = growthTone(value);
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
        "inline-flex items-center gap-0.5 text-[11px] font-semibold px-1.5 py-0.5 rounded-md tabular-nums",
        toneClass
      )}
    >
      <Icon size={11} />
      {fmtPct(Math.abs(value))}
    </span>
  );
}

/** Colour-coded percentage-point (pp) delta pill - green = share gained,
 * red = share lost, neutral = flat. The unit is part of the text ("+2.3 pp" /
 * "-2.3 pp" / "±0.0 pp") so the number always reads as POINTS of Cont%, never
 * as a % change - this replaces the old Cont%-growth pill in the distribution
 * bucket cells. */
function PpPill({ value }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-text-muted text-xs">—</span>;
  }
  const tone = growthTone(value);
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
        "inline-flex items-center gap-0.5 text-[11px] font-semibold px-1.5 py-0.5 rounded-md tabular-nums",
        toneClass
      )}
    >
      <Icon size={11} />
      {(value > 0 ? "+" : value < 0 ? "−" : "±") + Math.abs(value).toFixed(1) + " pp"}
    </span>
  );
}

/** A single KPI rendered as ONE cell that holds CFY (bold) + LFY + Growth pill.
 * Used in KPI cards and every hierarchy row - this is the "LFY / CFY / Growth
 * in the same cell" contract (distribution bucket cells use BucketCell below).
 * NOTE: contribution % is deliberately NOT shown for Bills / UPT / ABV / ASP -
 * it is not a valid measure for them (user-confirmed). */
function KpiCell({ kpi }) {
  return (
    <div className="leading-tight">
      <div className="flex items-center gap-1.5">
        <span className="font-display text-[15px] font-semibold tabular-nums text-text-primary">
          {fmtKpi(kpi?.cfy, kpi)}
        </span>
        <GrowthPill value={kpi?.growth_pct} />
      </div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">LFY</span>
        <span className="text-xs tabular-nums text-text-secondary">{fmtKpi(kpi?.lfy, kpi)}</span>
      </div>
    </div>
  );
}

/** Four flagship KPI cards - every card shows CFY (big), LFY and the growth
 * pill together, animating whenever the filter context changes. */
function KpiCard({ kpi, accent }) {
  const fmt = kpiFmt(kpi);
  return (
    <div className="relative overflow-hidden rounded-xl2 border border-border bg-card shadow-panel group hover:border-border-strong transition-colors">
      <div className={clsx("absolute left-0 top-0 h-full w-[3px]", ACCENT_BAR[accent])} />
      <div className="pl-5 pr-4 py-4">
        <p className="text-[11px] font-semibold tracking-wide text-text-secondary uppercase">{kpi.label}</p>
        <div className="mt-1.5 flex items-center gap-2">
          <p className="font-display text-2xl font-semibold tabular-nums leading-tight text-text-primary">
            <AnimatedNumber value={kpi.cfy} format={fmt} />
          </p>
          <GrowthPill value={kpi.growth_pct} />
        </div>
        <div className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-card-hover/60 px-2 py-1">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">LFY</span>
          <span className="text-xs tabular-nums text-text-secondary">
            <AnimatedNumber value={kpi.lfy} format={fmt} />
          </span>
        </div>
      </div>
    </div>
  );
}

function DimSelect({ label, value, onChange, options, includeAll = false }) {
  return (
    <label className="flex flex-col gap-1 min-w-[190px]">
      <span className="text-[11px] font-semibold tracking-wide text-text-secondary uppercase">{label}</span>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="h-9 rounded-lg border border-border bg-card px-2.5 text-sm text-text-primary focus:border-accent focus:outline-none"
      >
        {includeAll && <option value="all">All</option>}
        {options.map((o) => (
          <option key={o.column} value={o.column}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ---------------------------------------------------------------------------
 * Row hierarchy: dynamic N-level, driven by the dimensional column picker.
 * KPI cells are server-computed TRUE re-aggregations at each row's own grain
 * (a Brand total is NEVER an average of its Store child rows).
 * ------------------------------------------------------------------------- */
function HierarchyTable({ hierarchy, labels, globalKpis, maxHeightClass = "max-h-[65vh]" }) {
  const dims = hierarchy?.dims || [];
  const rows = hierarchy?.rows || [];
  const chain = dims.length ? dims.map((d) => labels[d] || d).join(" → ") : "All";

  const tableData = useMemo(() => {
    if (!dims.length) return [{ _level: 0, _label: "All", kpis: globalKpis }];
    // The backend already includes the "(All)" grand-total row (rows[0],
    // _level 0) genuinely re-aggregated over the whole context - don't add
    // a second one on top.
    return rows.some((r) => r._level === 0)
      ? rows
      : [{ _level: 0, _label: "All", kpis: globalKpis }, ...rows];
  }, [dims.length, rows, globalKpis]);

  const columns = useMemo(() => {
    const cols = [
      {
        id: "dim",
        header: chain,
        accessorFn: (r) => r._label,
        enableSorting: false,
        minSize: 240,
        size: 320,
        cell: ({ row }) => {
          const r = row.original;
          const lvl = r._level;
          return (
            <div className={clsx("flex items-center gap-2", lvl > 1 && "pl-5 border-l-2 border-border")}>
              <span
                className={clsx(
                  lvl === 0
                    ? "font-semibold text-text-primary"
                    : lvl === 1
                    ? "font-medium text-text-primary"
                    : "text-text-secondary"
                )}
              >
                {r._label}
              </span>
              {lvl === 1 && dims.length > 1 && (
                <span className="rounded bg-accent-soft text-accent text-[9px] font-semibold uppercase tracking-wide px-1 py-px whitespace-nowrap">
                  {labels[dims[0]] || dims[0]} total
                </span>
              )}
            </div>
          );
        },
      },
    ];
    KPI_ORDER.forEach((key) => {
      cols.push({
        id: `kpi_${key}`,
        header: KPI_LABELS[key],
        enableSorting: false,
        accessorFn: (r) => r.kpis?.find((k) => k.key === key)?.cfy,
        size: 210,
        cell: ({ row }) => {
          const kpi = row.original.kpis?.find((k) => k.key === key);
          return kpi ? <KpiCell kpi={kpi} /> : <span className="text-xs text-text-muted">—</span>;
        },
      });
    });
    return cols;
  }, [chain, dims, labels]);

  return (
    <DataTable
      columns={columns}
      data={tableData}
      globalSearch={false}
      columnVisibilityToggle={false}
      dense
      maxHeightClass={maxHeightClass}
      /* Freeze panes: row-dimension column + the "(All)" row + the PARENT row
         of the drill-down group you are scrolling through. */
      stickyFirstColumns={1}
      stickyFirstDataRow
      stickyParentRows
      rowClassName={(data) =>
        data?._level === 0
          ? "bg-accent-soft/40 font-semibold"
          : data?._level === 1
          ? "bg-border/25 border-t-2 border-border"
          : ""
      }
    />
  );
}

/* ---------------------------------------------------------------------------
 * Distribution pivots: buckets are the COLUMN HEADERS.
 * Each bucket cell answers "HOW MANY bills landed in this bucket" (e.g. how
 * many 1-qty bills, how many 0-3K bills) - the simple user-confirmed layout:
 *
 *     CFY:    <bill count>
 *     CONT%:  <share of the row's CFY bill total>
 *     LFY:    <bill count>
 *     CONT%:  <share of the row's LFY bill total>
 *     PP Δ:   <pill = CFY Cont% − LFY Cont% in percentage points>
 *
 * Cont% and pp Δ are BILL-COUNT based (not qty/val) for BOTH distributions
 * - the bucket column only decides the classification.  NO UPT / ABV / ASP.
 * Rows are dimension values (Brand selected -> one row per brand) with an
 * "(All)" genuine-re-aggregation total row on top.
 * ------------------------------------------------------------------------- */
function BucketCell({ cell }) {
  if (!cell) return <span className="text-xs text-text-muted">—</span>;
  
  // The backend was modified to return this in cell.growth_pct, but if the 
  // python server hasn't been restarted, it still serves the old % change.
  // Computing it safely here ensures the UI is immediately correct.
  const cfyPct = cell.share_cfy_pct ?? 0;
  const lfyPct = cell.share_lfy_pct ?? 0;
  const ppDelta = cfyPct - lfyPct;

  return (
    <div className="min-w-[130px] space-y-1 py-0.5">
      <div className="rounded-lg border border-border/60 bg-card-hover/40 px-2.5 py-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">CFY</span>
          <span className="text-sm font-semibold tabular-nums text-text-primary">
            {fmtQty(cell.cfy_bills)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <span className="text-[10px] uppercase tracking-wide text-text-muted">Cont%</span>
          <span className="text-[11px] tabular-nums text-text-secondary">{fmtPct(cell.share_cfy_pct ?? 0)}</span>
        </div>
      </div>
      <div className="rounded-lg border border-border/40 px-2.5 py-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">LFY</span>
          <span className="text-xs tabular-nums text-text-secondary">{fmtQty(cell.lfy_bills)}</span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <span className="text-[10px] uppercase tracking-wide text-text-muted">Cont%</span>
          <span className="text-[11px] tabular-nums text-text-muted">{fmtPct(cell.share_lfy_pct ?? 0)}</span>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 px-1">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">pp Δ</span>
        <PpPill value={ppDelta} />
      </div>
    </div>
  );
}

function DistributionTable({ result, labels, maxHeightClass = "max-h-[65vh]" }) {
  const [view, setView] = useState("chart");
  const rows = result?.rows || [];
  const buckets = result?.buckets || [];
  const dimLabel =
    result?.dim === "all" ? "All" : labels[result?.dim] || result?.dim || "Dimension";

  const columns = useMemo(() => {
    const cols = [
      {
        id: "dim",
        header: dimLabel,
        accessorFn: (r) => r.dim_value,
        enableSorting: false,
        minSize: 150,
        size: 210,
        cell: ({ row }) => {
          const v = row.original.dim_value;
          return <span className="font-medium">{v === "(All)" ? "All" : (v ?? "(blank)")}</span>;
        },
      },
    ];
    [...buckets, "All Bills"].forEach((bucket, i) => {
      cols.push({
        id: `b_${i}`,
        header:
          bucket === "All Bills" ? (
            <span className="font-semibold text-accent">{bucket}</span>
          ) : (
            bucket
          ),
        enableSorting: false,
        accessorFn: (r) => r.cells?.[bucket]?.cfy_bills ?? 0,
        size: 200,
        cell: ({ row }) => <BucketCell cell={row.original.cells?.[bucket]} />,
      });
    });
    return cols;
  }, [buckets, dimLabel]);

  const chartData = useMemo(() => {
    if (rows.length !== 1 || !buckets.length) return [];
    const cells = rows[0].cells || {};
    return buckets
      .map((bucket) => ({
        bucket,
        LFY: cells[bucket]?.lfy_bills ?? 0,
        CFY: cells[bucket]?.cfy_bills ?? 0,
      }))
      .filter((d) => d.LFY > 0 || d.CFY > 0);
  }, [rows, buckets]);

  // Chart-first for management: auto-fall back to the table when the current
  // selection cannot render a single-row comparison chart.
  useEffect(() => {
    setView(chartData.length ? "chart" : "table");
  }, [chartData.length]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end gap-1">
        {["table", "chart"].map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            disabled={v === "chart" && chartData.length === 0}
            className={clsx(
              "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors",
              view === v
                ? "bg-accent-soft text-accent border border-accent/30"
                : "text-text-secondary hover:text-text-primary border border-transparent",
              v === "chart" && chartData.length === 0 && "opacity-40 cursor-not-allowed"
            )}
          >
            {v === "table" ? <Table2 size={13} /> : <BarChart3 size={13} />}
            {v === "table" ? "Table" : "Chart"}
          </button>
        ))}
      </div>
      {view === "table" ? (
        <DataTable
          columns={columns}
          data={rows}
          globalSearch={false}
          columnVisibilityToggle={false}
          dense
          maxHeightClass={maxHeightClass}
          /* Freeze panes: dimension column + the "(All)" total row. */
          stickyFirstColumns={1}
          stickyFirstDataRow
          rowClassName={(data) =>
            data?.dim_value === "(All)" ? "bg-accent-soft/40 font-semibold" : ""
          }
        />
      ) : chartData.length === 0 ? (
        <p className="text-sm text-text-muted italic py-6 text-center">
          Chart is available when a single “All” row is selected.
        </p>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 18, right: 12, bottom: 4, left: 0 }} barCategoryGap="24%">
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fontSize: 11 }} interval={0} angle={-12} height={48} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(91, 124, 250, 0.06)" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="LFY" fill="#94a3b8" radius={[3, 3, 0, 0]} maxBarSize={46} />
              <Bar dataKey="CFY" fill="#5b7cfa" radius={[3, 3, 0, 0]} maxBarSize={46}>
                <LabelList
                  dataKey="CFY"
                  position="top"
                  style={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Top Bills: ranked by bill value (descending) with a server-side rank.  The
 * table is rank-LOCKED (no client-side column sorting) so rows ALWAYS appear
 * in rank order 1..n.  The backend enforces a deterministic tie-break
 * (earliest bill date, then internal_bill_id) - see _top_bill_rows.
 * A large bill can legitimately contain several brands: the optional Brand Mix
 * column lists every brand inside THAT bill with its share of the bill value.
 * ------------------------------------------------------------------------- */
function BrandMix({ parts }) {
  if (!parts || parts.length === 0) return <span className="text-xs text-text-muted">—</span>;
  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 py-0.5">
      {parts.map((p, i) => (
        <span key={`${p.brand}-${i}`} className="whitespace-nowrap text-[11px] leading-tight">
          <span className="font-semibold text-text-primary">{p.brand || "(no brand)"}</span>
          <span className="text-text-secondary"> - {fmtVal(p.bill_val)}</span>
          <span className="ml-0.5 font-semibold text-accent">[{fmtPct(p.contribution_pct)}]</span>
        </span>
      ))}
    </div>
  );
}

function TopBillsTable({ rows, showMix = false, dropBrandColumn = false, maxHeightClass = "" }) {
  const columns = useMemo(
    () => [
      {
        id: "rank",
        header: "#",
        accessorKey: "rank",
        enableSorting: false,
        size: 52,
        cell: ({ getValue }) => (
          <span
            className={clsx(
              "inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold tabular-nums",
              RANK_BADGE[getValue()] || "bg-card-hover text-text-muted border border-border/60"
            )}
          >
            {getValue()}
          </span>
        ),
      },
      {
        id: "bill",
        header: "Internal Bill No.",
        accessorKey: "internal_bill_id",
        enableSorting: false,
        minSize: 200,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-text-primary break-all">{getValue()}</span>
        ),
      },
      {
        id: "date",
        header: "Date",
        accessorKey: "bill_date",
        enableSorting: false,
        size: 96,
        cell: ({ getValue }) =>
          getValue() ? (
            <span className="tabular-nums text-xs">{fmtDate(getValue())}</span>
          ) : (
            <span className="text-xs text-text-muted">—</span>
          ),
      },
      { id: "retailer", header: "Retailer", accessorKey: "retailer_name", enableSorting: false, minSize: 150 },
      // The single "Brand" column is MISLEADING on a multi-brand bill (it names
      // only one of the brands inside the bill), so when Retailer is the outer
      // Row-Hierarchy dimension it is dropped entirely - the dedicated
      // "Brand Mix · Bill Value [Cont%]" last column is the single source of
      // truth for which brands a bill contains and each one's share.
      ...(dropBrandColumn
        ? []
        : [{ id: "brand", header: "Brand", accessorKey: "brand", enableSorting: false, size: 110 }]),
      {
        id: "qty",
        header: "Qty",
        accessorKey: "qty",
        enableSorting: false,
        size: 70,
        cell: ({ getValue }) => <span className="tabular-nums">{fmtQty(getValue())}</span>,
      },
      {
        id: "bill_val",
        header: "Bill Value",
        accessorKey: "bill_val",
        enableSorting: false,
        size: 110,
        cell: ({ getValue }) => (
          <span className="tabular-nums font-medium">{fmtVal(getValue())}</span>
        ),
      },
      // Brand mix of THE BILL: `BRAND - value [cont% of the bill value]` for
      // every brand inside that bill (shown when a store filter is applied, or
      // when the returned bills genuinely mix brands).
      ...(showMix
        ? [
            {
              id: "brand_mix",
              header: "Brand Mix · Bill Value [Cont%]",
              enableSorting: false,
              size: 320,
              meta: { wrap: true },
              accessorFn: (r) =>
                (r.brand_contributions || [])
                  .map(
                    (p) =>
                      `${p.brand || "(no brand)"} - ${p.bill_val} [${p.contribution_pct?.toFixed(1) ?? "-"}%]`
                  )
                  .join("   "),
              cell: ({ row }) => <BrandMix parts={row.original.brand_contributions} />,
            },
          ]
        : []),
    ],
    [showMix, dropBrandColumn]
  );
  return (
    <DataTable
      columns={columns}
      data={rows}
      globalSearch={false}
      columnVisibilityToggle={false}
      dense
      maxHeightClass={maxHeightClass}
      /* Freeze panes: rank + bill id stay visible while scrolling right to the
         bill's brand mix. */
      stickyFirstColumns={2}
    />
  );
}

function TopBills({ topBills, storeScoped = false, retailerFirst = false, maxHeightClass = "" }) {
  const [side, setSide] = useState("both");
  const cfy = topBills?.cfy || [];
  const lfy = topBills?.lfy || [];
  // The Brand Mix column shows when a store filter is applied (the user asked
  // "for this big bill, which brands does it contain?"), whenever the returned
  // bills genuinely mix more than one brand, and ALWAYS when Retailer is the
  // outer row dimension (the plain Brand column is dropped in that case, so
  // the mix column is the only place brand detail lives).
  const showMix =
    storeScoped ||
    retailerFirst ||
    [...cfy, ...lfy].some((r) => (r.brand_contributions?.length || 0) > 1);
  if (!cfy.length && !lfy.length) {
    return (
      <p className="text-sm text-text-muted italic py-6 text-center">
        No bills for the selected period / filters.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1">
        {[
          ["both", "Side by side"],
          ["cfy", "CFY only"],
          ["lfy", "LFY only"],
        ].map(([key, lbl]) => (
          <button
            key={key}
            type="button"
            onClick={() => setSide(key)}
            className={clsx(
              "px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors",
              side === key
                ? "bg-accent-soft text-accent border border-accent/30"
                : "text-text-secondary hover:text-text-primary border border-transparent"
            )}
          >
            {lbl}
          </button>
        ))}
      </div>
      <div className={clsx("grid gap-4", side === "both" ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1")}>
        {side !== "lfy" && (
          <div>
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary mb-2">
              <Trophy size={12} className="text-accent" /> CFY · Top {topBills?.n}
            </p>
            <TopBillsTable rows={cfy} showMix={showMix} dropBrandColumn={retailerFirst} maxHeightClass={maxHeightClass} />
          </div>
        )}
        {side !== "cfy" && (
          <div>
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary mb-2">
              <Trophy size={12} className="text-text-muted" /> LFY · Top {topBills?.n}
            </p>
            <TopBillsTable rows={lfy} showMix={showMix} dropBrandColumn={retailerFirst} maxHeightClass={maxHeightClass} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Main component
 * ------------------------------------------------------------------------- */
const DIM_DEFAULTS = { hierarchy: ["brand"], distDim: "brand", topN: 25 };

export default function BillNoAnalysis({ filters, hierarchy = [], eyebrow }) {
  const [distDim, setDistDim] = useState(DIM_DEFAULTS.distDim);
  const [topN, setTopN] = useState(DIM_DEFAULTS.topN);
  const [topNInput, setTopNInput] = useState(String(DIM_DEFAULTS.topN));
  // Debounce the Top-N input so typing (e.g. "3" then "0") fires ONE query
  // for 30, not one per keystroke.
  const topNTimer = useRef(null);
  const commitTopN = (parsed) => {
    clearTimeout(topNTimer.current);
    if (Number.isInteger(parsed) && parsed > 0) {
      topNTimer.current = setTimeout(() => setTopN(parsed), 450);
    }
  };
  useEffect(() => () => clearTimeout(topNTimer.current), []);
  // Once the user explicitly picks a Distribution Dimension we stop syncing it
  // to the first selected row dimension.
  const distTouched = useRef(false);

  // Dimension catalog for the Distribution Dimension picker
  // (GET /bill-kpi/dimensions).
  const dimsQ = useQuery({
    queryKey: [eyebrow, "bill-kpi-dimensions"],
    queryFn: billKpiApi.dimensions,
  });

  const dimOptions = useMemo(() => dimsQ.data?.dimensions || [], [dimsQ.data]);

  // Row hierarchy: the PAGE-LEVEL Row Hierarchy is the single source of truth
  // for this tab too (exactly like Category Performance) - there is no second
  // picker here.  Nesting follows the user's own order, so "Brand then
  // Retailer" and "Retailer then Brand" both work.  Columns the bill engine does
  // not know are ignored, and an empty selection keeps the module's historical
  // Brand default.
  const rowHierarchy = useMemo(() => {
    const known = new Set(dimOptions.map((d) => d.column));
    const picked = (hierarchy || []).filter((d) => known.has(d)).slice(0, MAX_LEVELS);
    return picked.length ? picked : DIM_DEFAULTS.hierarchy;
  }, [hierarchy, dimOptions]);

  // Derive the default during render to avoid a duplicate request after hierarchy changes.
  const effectiveDistDim = distTouched.current ? distDim : (rowHierarchy[0] || "all");

  const q = useQuery({
    queryKey: [eyebrow, "bill-kpi-analysis", filters, rowHierarchy, effectiveDistDim, topN],
    queryFn: () => billKpiApi.analysis(filters, rowHierarchy, effectiveDistDim, topN),
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const labels = useMemo(
    () => Object.fromEntries(dimOptions.map((d) => [d.column, d.label])),
    [dimOptions]
  );

  // Distribution rows follow the row-hierarchy selection (req §6/§7/§8):
  // Brand selected -> brand-level distribution rows, unless the user has
  // explicitly chosen a distribution dimension in the picker.


  // The brand-mix column of the Top Bills table is store-scoped by request: it
  // appears as soon as ANY global slicer value is selected.
  const storeScoped = useMemo(
    () => Object.values(filters || {}).some((v) => (v?.length || 0) > 0),
    [filters]
  );
  const rowChain = rowHierarchy.map((d) => labels[d] || d).join(" > ");
  const distDimLabel = effectiveDistDim === "all" ? "All (overall buckets)" : labels[effectiveDistDim] || effectiveDistDim;
  const chain = (q.data?.summary?.dimensions || []).map((d) => labels[d] || d).join(" → ");
  const meta = q.data?.meta;

  return (
    <div className="space-y-5">
      {/* Global filter / configuration bar — drives every section reactively */}
      <Card className="p-4">
        <div className="flex flex-col gap-3">
          {/* NO hierarchy picker here - the page-level ROW HIERARCHY and the
              global slicers above are this tab's only inputs (both are part of
              the query key, and both drive every section below). */}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
            <span className="font-bold tracking-widest uppercase">Rows</span>
            <span className="px-2 py-0.5 rounded-full border border-border bg-surface font-semibold text-text-secondary">
              {rowChain}
            </span>
            {q.isFetching && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-soft text-accent font-semibold animate-pulse">
                <RefreshCw size={10} /> updating to your selection…
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <DimSelect
              label="Distribution Dimension"
              value={effectiveDistDim}
              onChange={(v) => {
                distTouched.current = true;
                setDistDim(v || "all");
              }}
              options={dimOptions}
              includeAll
            />
            <label className="flex flex-col gap-1 min-w-[130px]">
              <span className="text-[11px] font-semibold tracking-wide text-text-secondary uppercase">
                Top N Bills
              </span>
              <input
                type="number"
                min="1"
                step="1"
                inputMode="numeric"
                value={topNInput}
                onChange={(e) => {
                  const next = e.target.value;
                  setTopNInput(next);
                  commitTopN(Number(next));
                }}
                onBlur={() => {
                  clearTimeout(topNTimer.current);
                  const normalized = Math.max(1, Number.parseInt(topNInput, 10) || DIM_DEFAULTS.topN);
                  setTopNInput(String(normalized));
                  setTopN(normalized);
                }}
                aria-label="Number of top bills to show"
                className="h-9 rounded-lg border border-border bg-card px-2.5 text-sm text-text-primary focus:border-accent focus:outline-none"
              />
            </label>
          </div>
        </div>
      </Card>

      {q.isLoading ? (
        <Card>
          <LoadingState rows={10} />
        </Card>
      ) : q.isError ? (
        <Card>
          <ErrorState message={q.error.message} onRetry={() => q.refetch()} />
        </Card>
      ) : (
        <>
          {/* 1 · KPI cards — all KPIs, each with LFY + CFY + Growth in one card */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {(q.data.kpis || []).map((kpi, i) => (
              <KpiCard key={kpi.key} kpi={kpi} accent={CARD_ACCENTS[i] || "accent"} />
            ))}
          </div>

          {/* 2 · Row hierarchy — driven by the PAGE-LEVEL Row Hierarchy */}
          <SectionCard
            icon={Layers}
            title={`Drill-down hierarchy${chain ? ` · ${chain}` : ""}`}
            right={
              meta ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[11px] font-semibold tabular-nums text-text-secondary">
                  {fmtQty(meta.transaction_rows)} transactions → {fmtQty(meta.bill_count)} bills
                </span>
              ) : null
            }
          >
            {({ maximized }) => (
              <HierarchyTable
                hierarchy={{
                  dims: q.data.summary?.dimensions || [],
                  rows: (q.data.summary?.rows || []).map((r) => ({ ...r, _label: r.dim_value })),
                }}
                labels={labels}
                globalKpis={q.data.kpis}
                maxHeightClass={maximized ? "max-h-[calc(100vh-210px)]" : "max-h-[65vh]"}
              />
            )}
          </SectionCard>

          {/* 3a · Quantity distribution — buckets as column headers */}
          <SectionCard
            icon={BarChart3}
            title={`Qty Distribution Analysis · ${distDimLabel}`}
          >
            {({ maximized }) => (
              <DistributionTable
                result={q.data.qty_distribution}
                labels={labels}
                maxHeightClass={maximized ? "max-h-[calc(100vh-210px)]" : "max-h-[65vh]"}
              />
            )}
          </SectionCard>

          {/* 3b · Bill value distribution — buckets as column headers */}
          <SectionCard
            icon={Table2}
            title={`Bill Value Distribution Analysis · ${distDimLabel}`}
          >
            {({ maximized }) => (
              <DistributionTable
                result={q.data.value_distribution}
                labels={labels}
                maxHeightClass={maximized ? "max-h-[calc(100vh-210px)]" : "max-h-[65vh]"}
              />
            )}
          </SectionCard>

          {/* 4 · Top bills (LFY vs CFY) */}
          <SectionCard
            icon={Trophy}
            title={`Top Bills · Top ${q.data.top_bills?.n}`}
          >
            {({ maximized }) => (
              <TopBills
                topBills={q.data.top_bills}
                storeScoped={storeScoped}
                retailerFirst={rowHierarchy[0] === "retailer_name"}
                maxHeightClass={maximized ? "max-h-[calc(100vh-260px)]" : ""}
              />
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}