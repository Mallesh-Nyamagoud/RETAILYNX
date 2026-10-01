import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  LabelList,
} from "recharts";
import { Clock, PackageX, CheckCircle2, Loader } from "lucide-react";
import clsx from "clsx";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import KpiCard from "../components/common/KpiCard";
import DimensionPicker from "../components/common/DimensionPicker";
import FilterPanel from "../components/common/FilterPanel";
import GaugeChart from "../components/common/GaugeChart";
import DataTable from "../components/common/DataTable";
import Badge from "../components/common/Badge";
import { ExportButton } from "../components/common/ExportButton";
import { LoadingState, KpiSkeleton, ErrorState, EmptyState } from "../components/common/LoadingState";
import { cssStockApi } from "../api/client";
import { fmtPct, fmtQty } from "../utils/format";

const BRAND_LABEL_MAX = 16;
const truncateBrand = (name) =>
  typeof name === "string" && name.length > BRAND_LABEL_MAX
    ? `${name.slice(0, BRAND_LABEL_MAX - 1)}…`
    : name;

// Status tabs: null = all statuses; otherwise an array of status keys.
const STATUS_TABS = [
  { key: null, label: "All", icon: null },
  { key: ["fully_dispatched"], label: "Fully Dispatched", icon: CheckCircle2 },
  { key: ["partially_dispatched"], label: "Partially Dispatched", icon: Loader },
  { key: ["pending"], label: "Pending", icon: Clock },
  { key: ["dbno"], label: "Dispatched But Not Ordered", icon: PackageX },
];

const STATUS_TONE = {
  fully_dispatched: "positive",
  partially_dispatched: "warn",
  pending: "neutral",
  dbno: "negative",
};

export default function CssStockTracking() {
  const [season, setSeason] = useState(null);
  const [statuses, setStatuses] = useState(null); // null = ALL
  // Default hierarchy: style-level detail with sub-category grouping.
  const [dimensions, setDimensions] = useState(["product_style"]);
  const [filters, setFilters] = useState({});

  const seasonsQ = useQuery({ queryKey: ["css", "seasons"], queryFn: cssStockApi.seasons });
  const dimsQ = useQuery({ queryKey: ["css", "dimensions"], queryFn: cssStockApi.dimensions });

  const effectiveSeason = season ?? seasonsQ.data?.seasons?.[0] ?? null;

  // Cross-filter aware slicer options (server narrows by every OTHER filter).
  const slicerQ = useQuery({
    queryKey: ["css", "slicer-options", filters],
    queryFn: () => cssStockApi.slicerOptions(filters),
    enabled: !!dimsQ.data,
    keepPreviousData: true,
  });

  // Drop any filter selections that are no longer valid option values after
  // a cross-filter change (e.g. picking a state removed some retailers).
  useEffect(() => {
    const opts = slicerQ.data?.slicers;
    if (!opts) return;
    setFilters((prev) => {
      let changed = false;
      const next = {};
      for (const [col, vals] of Object.entries(prev)) {
        const kept = (vals || []).filter((v) => (opts[col] || []).includes(v));
        if (kept.length !== (vals || []).length) changed = true;
        if (kept.length) next[col] = kept;
      }
      return changed ? next : prev;
    });
  }, [slicerQ.data]);

  // KPIs respond to season AND store-master filters.
  const kpisQ = useQuery({
    queryKey: ["css", "kpis", effectiveSeason, filters],
    queryFn: () => cssStockApi.kpis(effectiveSeason, filters),
    enabled: !!seasonsQ.data,
  });

  const summaryQ = useQuery({
    queryKey: ["css", "summary", effectiveSeason, dimensions, filters, statuses],
    queryFn: () =>
      cssStockApi.summary({
        season: effectiveSeason,
        dimensions,
        filters,
        statuses,
      }),
    enabled: !!seasonsQ.data,
  });

  const dimensionLabels = useMemo(() => {
    const cat = dimsQ.data?.dimensions || [];
    // Sub Category / Product Style are analysis keys of this module (not
    // store-master columns) - offered in the hierarchy alongside them.
    const special = [
      { column: "subcategory", label: "SUB CATEGORY" },
      { column: "product_style", label: "PRODUCT / STYLE" },
    ];
    return Object.fromEntries([...cat, ...special].map((d) => [d.column, d.label]));
  }, [dimsQ.data]);

  const dimensionCatalog = useMemo(() => {
    const cat = dimsQ.data?.dimensions || [];
    const special = [
      { column: "subcategory", label: "SUB CATEGORY" },
      { column: "product_style", label: "PRODUCT / STYLE" },
    ];
    return [...cat, ...special];
  }, [dimsQ.data]);

  // Merge cross-filtered server options with current selections so active
  // picks never vanish from their dropdown while narrowing everything else.
  const cssSlicers = useMemo(() => {
    const server = slicerQ.data?.slicers || {};
    const merged = {};
    for (const col of Object.keys(dimensionLabels)) {
      const opts = server[col] || [];
      const sel = filters[col] || [];
      merged[col] = Array.from(new Set([...opts, ...sel])).sort((a, b) =>
        String(a).localeCompare(String(b))
      );
    }
    return merged;
  }, [slicerQ.data, dimensionLabels, filters]);

  const wantSubcat = dimensions.includes("subcategory");
  const wantStyle = dimensions.includes("product_style");

  const columns = useMemo(() => {
    // Store-master dims become their own columns; the two special keys map
    // onto the standard Sub Category / Product-Style columns.
    const dimCols = dimensions
      .filter((d) => d !== "subcategory" && d !== "product_style")
      .map((d) => ({
        accessorKey: d,
        header: dimensionLabels[d] || d.toUpperCase(),
      }));
    const cols = [
      ...dimCols,
      {
        accessorKey: "brand",
        header: "Brand",
        cell: ({ getValue }) => <span className="font-medium">{getValue() ?? "—"}</span>,
      },
      {
        accessorKey: "season",
        header: "Season",
      },
    ];
    if (wantSubcat) {
      cols.push({
        accessorKey: "subcategory",
        header: "Sub Category",
        cell: ({ getValue }) => getValue() ?? "—",
      });
    }
    if (wantStyle) {
      cols.push({
        accessorKey: "product_style",
        header: "Product / Style",
        cell: ({ getValue }) => <span className="font-medium">{getValue() ?? "—"}</span>,
      });
      cols.push({
        accessorKey: "mrp",
        header: "MRP",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          return <span className="tabular-nums">₹{fmtQty(v)}</span>;
        },
      });
    }
    cols.push(
      {
        accessorKey: "ordered_qty",
        header: "Ordered Qty",
        cell: ({ getValue }) => fmtQty(getValue()),
      },
      {
        accessorKey: "ordered_mrp_val",
        header: "Ordered MRP Val",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          return <span className="tabular-nums font-medium text-accent">₹{fmtQty(v)}</span>;
        },
      },
      {
        accessorKey: "dispatched_qty",
        header: "Dispatched Qty",
        cell: ({ getValue }) => <span className="font-semibold">{fmtQty(getValue())}</span>,
      },
      {
        accessorKey: "dispatched_mrp_val",
        header: "Dispatched MRP Val",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          return <span className="tabular-nums font-semibold text-teal">₹{fmtQty(v)}</span>;
        },
      },
      {
        accessorKey: "pending_qty",
        header: "Pending Qty",
        cell: ({ getValue }) => {
          const v = getValue();
          const tone =
            v > 0 ? "text-warn" : v <= 0 ? "text-positive" : "text-text-secondary";
          return <span className={clsx("font-medium tabular-nums", tone)}>{fmtQty(v)}</span>;
        },
      },
      {
        accessorKey: "pending_mrp_val",
        header: "Pending MRP Val",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          const tone = v > 0 ? "text-warn" : "text-positive";
          return <span className={clsx("font-medium tabular-nums", tone)}>₹{fmtQty(v)}</span>;
        },
      },
      {
        accessorKey: "dispatch_pct",
        header: "Dispatch %",
        cell: ({ getValue }) => {
          const v = getValue();
          if (v === null || v === undefined) return <span className="text-text-muted">—</span>;
          const toneClass =
            v >= 100 ? "text-positive" : v > 0 ? "text-warn" : "text-text-secondary";
          return (
            <span className={clsx("font-semibold tabular-nums", toneClass)}>
              {v >= 100 ? "✓ " : ""}
              {fmtPct(v)}
            </span>
          );
        },
      },
      {
        accessorKey: "status_key",
        header: "Status",
        cell: ({ row }) => (
          <Badge tone={STATUS_TONE[row.original.status_key] || "neutral"}>
            {row.original.status}
          </Badge>
        ),
      }
    );
    return cols;
  }, [dimensions, dimensionLabels, wantSubcat, wantStyle]);

  // Chart data: Ordered vs Dispatched vs Pending per brand (brands with zero
  // dispatch still appear because the Order Form baseline is always included).
  const chartData = useMemo(
    () =>
      (kpisQ.data?.by_brand || []).map((b) => ({
        ...b,
        brand_short: truncateBrand(b.brand),
      })),
    [kpisQ.data]
  );
  const chartHeight = Math.max(180, chartData.length * 40 + 60);

  const k = kpisQ.data;

  return (
    <div>
      <PageHeader
        title="Order-to-Transformation Tracker"
        actions={
          <ExportButton
            onExport={() =>
              cssStockApi.export({
                season: effectiveSeason,
                dimensions,
                filters,
                statuses,
              })
            }
          />
        }
      />

      {/* Global Filters: Season + Store Master / Slicers */}
      <Card className="mb-6">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">Season</span>
            <div className="inline-flex items-center rounded-lg border border-border-strong p-0.5 bg-surface flex-wrap">
              {(seasonsQ.data?.seasons || []).map((s) => (
                <button
                  key={s}
                  onClick={() => setSeason(s)}
                  className={clsx(
                    "px-3 py-1 text-xs font-semibold rounded-md transition-colors",
                    effectiveSeason === s
                      ? "bg-accent text-white"
                      : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          {Object.keys(cssSlicers).length > 0 && (
            <FilterPanel
              slicers={cssSlicers}
              dimensionLabels={dimensionLabels}
              value={filters}
              onChange={setFilters}
            />
          )}
        </div>
      </Card>

      {kpisQ.isError ? (
        <Card className="mb-6">
          <ErrorState message={kpisQ.error.message} onRetry={() => kpisQ.refetch()} />
        </Card>
      ) : kpisQ.isLoading || !k ? (
        <div className="mb-6">
          <KpiSkeleton count={4} />
        </div>
      ) : (
        <>
          {/* KPI cards — all respond to season + store-master filters and
              reconcile exactly with the summary table below */}
          {/* Top Overview: Flagship Gauge Chart + KPIs */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 mb-6">
            <Card className="xl:col-span-4 p-5 flex flex-col justify-between border-border shadow-sm bg-gradient-to-b from-card/80 to-card hover:bg-card-hover transition-colors relative overflow-hidden h-full min-h-[300px]">
              <div className="absolute top-4 left-5 text-[11px] font-bold text-text-muted uppercase tracking-wider">
                Overall Performance
              </div>
              <div className="flex-1 flex items-center justify-center mt-10">
                <GaugeChart value={k.dispatch_pct} label="Dispatch %" />
              </div>
            </Card>

            <div className="xl:col-span-8 grid grid-cols-2 gap-4">
              <KpiCard
                label="Total Ordered"
                qty={k.total_ordered}
                metaVal={k.ordered_mrp_val}
                metaLabel="MRP Val"
                accent="accent"
              />
              <KpiCard
                label="Total Dispatched"
                qty={k.total_dispatched}
                metaVal={k.dispatched_mrp_val}
                metaLabel="MRP Val"
                accent="teal"
              />
              <KpiCard
                label="Total Pending"
                qty={k.total_pending}
                metaVal={k.pending_mrp_val}
                metaLabel="MRP Val"
                accent="warn"
              />
              <KpiCard
                label="Dispatched But Not Ordered"
                qty={k.dbno_qty}
                metaVal={k.dbno_mrp_val}
                metaLabel="MRP Val"
                accent="negative"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {[
              {
                key: ["fully_dispatched"],
                label: "Fully Dispatched",
                value: k.fully_dispatched,
                icon: CheckCircle2,
                tone: "text-positive bg-positive-soft",
              },
              {
                key: ["partially_dispatched"],
                label: "Partially Dispatched",
                value: k.partially_dispatched,
                icon: Loader,
                tone: "text-warn bg-warn-soft",
              },
              {
                key: ["pending"],
                label: "Pending",
                value: k.pending,
                icon: Clock,
                tone: "text-text-secondary bg-border/50",
              },
              {
                key: ["dbno"],
                label: "Dispatched But Not Ordered",
                value: k.dispatched_but_not_ordered,
                icon: PackageX,
                tone: "text-negative bg-negative-soft",
              },
            ].map((c) => {
              const active =
                statuses !== null &&
                c.key.length === statuses.length &&
                c.key.every((s) => statuses.includes(s));
              return (
                <button
                  key={c.key[0]}
                  type="button"
                  onClick={() => setStatuses(active ? null : c.key)}
                  className={clsx(
                    "relative overflow-hidden rounded-xl2 border bg-card shadow-panel transition-all text-left group",
                    active
                      ? "border-accent ring-1 ring-accent/40"
                      : "border-border hover:border-border-strong"
                  )}
                >
                  <div className="pl-5 pr-4 py-4 flex items-center gap-3">
                    <span className={clsx("p-2 rounded-lg shrink-0", c.tone)}>
                      <c.icon size={18} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold tracking-wide text-text-secondary uppercase truncate">
                        {c.label}
                      </p>
                      <p className="font-display text-xl font-semibold tabular-nums leading-tight mt-0.5">
                        {fmtQty(c.value)}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Brand-wise Ordered vs Dispatched vs Pending */}
          <Card className="mb-6">
            <div className="flex items-start justify-between flex-wrap gap-2 mb-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                Brand-wise Ordered vs Dispatched vs Pending
              </p>
              <div className="flex items-center gap-3 text-[11px] text-text-muted">
                <span className="inline-flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-accent inline-block" /> Ordered
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-teal inline-block" /> Dispatched
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm bg-warn inline-block" /> Pending
                </span>
              </div>
            </div>
            {chartData.length === 0 ? (
              <EmptyState title="No order-form rows" />
            ) : (
              <ResponsiveContainer width="100%" height={chartHeight}>
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ top: 8, right: 120, bottom: 4, left: 8 }}
                  barGap={2}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
                  <XAxis type="number" hide />
                  <YAxis
                    dataKey="brand_short"
                    type="category"
                    width={130}
                    tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--color-card-hover)", opacity: 0.5 }}
                    formatter={(value, name) => [fmtQty(value), name]}
                    labelFormatter={(label) =>
                      (chartData.find((d) => d.brand_short === label) || {}).brand || label
                    }
                    contentStyle={{
                      background: "var(--color-card)",
                      border: "1px solid var(--color-border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="ordered_qty" name="Ordered" fill="var(--color-accent)" radius={[0, 4, 4, 0]} barSize={10}>
                    <LabelList
                      dataKey="ordered_qty"
                      position="right"
                      style={{ fill: "var(--color-text-secondary)", fontSize: 10, fontWeight: 600 }}
                      formatter={(v) => fmtQty(v)}
                    />
                  </Bar>
                  <Bar dataKey="dispatched_qty" name="Dispatched" fill="var(--color-teal)" radius={[0, 4, 4, 0]} barSize={10}>
                    <LabelList
                      dataKey="dispatched_qty"
                      position="right"
                      style={{ fill: "var(--color-text-secondary)", fontSize: 10, fontWeight: 600 }}
                      formatter={(v) => fmtQty(v)}
                    />
                  </Bar>
                  <Bar dataKey="pending_qty" name="Pending" fill="var(--color-warn)" radius={[0, 4, 4, 0]} barSize={10}>
                    <LabelList
                      dataKey="pending_qty"
                      position="right"
                      style={{ fill: "var(--color-text-secondary)", fontSize: 10, fontWeight: 600 }}
                      formatter={(v) => fmtQty(v)}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
            {/* Numerical readout so every chart value is exact */}
            {chartData.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-xs tabular-nums">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wide text-text-muted border-b border-border">
                      <th className="py-1.5 pr-3 font-semibold">Brand</th>
                      <th className="py-1.5 px-3 font-semibold text-right">Ordered</th>
                      <th className="py-1.5 px-3 font-semibold text-right">Dispatched</th>
                      <th className="py-1.5 px-3 font-semibold text-right">Pending</th>
                      <th className="py-1.5 pl-3 font-semibold text-right">Dispatch %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((b) => (
                      <tr key={b.brand} className="border-b border-border/50 last:border-0">
                        <td className="py-1.5 pr-3 text-text-primary font-medium">{b.brand}</td>
                        <td className="py-1.5 px-3 text-right text-accent font-semibold">
                          {fmtQty(b.ordered_qty)}
                        </td>
                        <td className="py-1.5 px-3 text-right text-teal font-semibold">
                          {fmtQty(b.dispatched_qty)}
                        </td>
                        <td className="py-1.5 px-3 text-right text-warn font-semibold">
                          {fmtQty(b.pending_qty)}
                        </td>
                        <td className="py-1.5 pl-3 text-right text-positive font-semibold">
                          {b.dispatch_pct === null ? "—" : fmtPct(b.dispatch_pct)}
                        </td>
                      </tr>
                    ))}
                    <tr className="border-t border-border font-semibold">
                      <td className="py-1.5 pr-3">Total</td>
                      <td className="py-1.5 px-3 text-right text-accent">{fmtQty(k.total_ordered)}</td>
                      <td className="py-1.5 px-3 text-right text-teal">{fmtQty(k.total_dispatched)}</td>
                      <td className="py-1.5 px-3 text-right text-warn">{fmtQty(k.total_pending)}</td>
                      <td className="py-1.5 pl-3 text-right text-positive">
                        {k.dispatch_pct === null ? "—" : fmtPct(k.dispatch_pct)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {/* Dimensions, cross-filters and status tabs */}
      <Card className="mb-5">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mr-1">
              Status
            </span>
            {STATUS_TABS.map((t) => {
              const active =
                t.key === null
                  ? statuses === null
                  : statuses !== null &&
                    t.key.length === statuses.length &&
                    t.key.every((s) => statuses.includes(s));
              const Icon = t.icon;
              return (
                <button
                  key={t.label}
                  onClick={() => setStatuses(t.key)}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
                    active
                      ? "bg-accent text-white"
                      : "bg-surface text-text-secondary hover:text-text-primary border border-border-strong"
                  )}
                >
                  {Icon && <Icon size={13} />}
                  {t.label}
                </button>
              );
            })}
          </div>
          {dimsQ.data && (
            <DimensionPicker
              dimensions={dimensionCatalog}
              value={dimensions}
              onChange={setDimensions}
            />
          )}
        </div>
      </Card>

      {/* Summary table — includes ALL ordered products even with zero dispatch */}
      <Card padded={false}>
        <div className="p-4">
          {summaryQ.isError ? (
            <ErrorState message={summaryQ.error.message} onRetry={() => summaryQ.refetch()} />
          ) : summaryQ.isLoading || !summaryQ.data ? (
            <LoadingState rows={8} />
          ) : (summaryQ.data.rows || []).length === 0 ? (
            <EmptyState
              title="No rows for this view"
              />
          ) : (
            <DataTable
              columns={columns}
              data={summaryQ.data.rows}
              stickyFirstColumns={Math.min(dimensions.length, 2)}
            />
          )}
        </div>
      </Card>
    </div>
  );
}