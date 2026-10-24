import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarRange, ChevronDown, ChevronUp, Layers3 } from "lucide-react";
import { baseStockApi } from "../api/client";
import Card from "../components/common/Card";
import DimensionPicker from "../components/common/DimensionPicker";
import { EmptyState, ErrorState, LoadingState } from "../components/common/LoadingState";
import FilterPanel from "../components/common/FilterPanel";
import PageHeader from "../components/layout/PageHeader";

const NUMBER = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const PERCENT = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const MEASURES = [
  { key: "total_sales", label: "Total Sales" },
  { key: "total_sales_contribution_pct", label: "Cont.%", percent: true },
  { key: "last_6m_sales", label: "Last 6M Sales" },
  { key: "last_6m_contribution_pct", label: "Cont.%", percent: true },
  { key: "current_stock", label: "Current Stock" },
  { key: "current_stock_contribution_pct", label: "Cont.%", percent: true },
  { key: "st_pct", label: "ST%", percent: true },
  { key: "f4m_requirement", label: "F4M Requirement" },
  { key: "requirement", label: "Stock - F4M Requirement" },
];

function formatDateDdMmYyyy(value) {
  if (!value) return "-";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return [day, month, year].join("/");
}

function showNumber(value) {
  return NUMBER.format(Number(value) || 0);
}

function showPercent(value) {
  return PERCENT.format(Number(value) || 0) + "%";
}

export default function BaseStockAnalysis() {
  const [dimensions, setDimensions] = useState(["category_group", "category", "subcategory"]);
  const [filters, setFilters] = useState({});
  const [queryFilters, setQueryFilters] = useState({});
  const [sort, setSort] = useState({ key: "total_sales_contribution_pct", direction: "desc" });
  useEffect(() => {
    const timer = window.setTimeout(() => setQueryFilters(filters), 350);
    return () => window.clearTimeout(timer);
  }, [filters]);
  const dimensionsQ = useQuery({
    queryKey: ["base-stock", "dimensions"],
    queryFn: baseStockApi.dimensions,
  });
  const slicersQ = useQuery({
    queryKey: ["base-stock", "slicers"],
    queryFn: baseStockApi.slicers,
  });
  const analysisQ = useQuery({
    queryKey: ["base-stock", "analysis", dimensions, queryFilters],
    queryFn: () => baseStockApi.analysis(dimensions, queryFilters),
    placeholderData: (previousData) => previousData,
  });

  const catalog = dimensionsQ.data?.dimensions || [];
  const pickerDimensions = useMemo(() => [
    { column: "category", label: "Category", type: "VARCHAR" },
    ...catalog.filter((dimension) => dimension.column !== "category"),
  ], [catalog]);
  const labels = useMemo(() => ({
    ...Object.fromEntries(pickerDimensions.map(({ column, label }) => [column, label])),
    retailer_name: "Store",
    store_status: "Store Status",
    category_group: "Category Group",
    subcategory: "Subcategory",
    season: "Season",
  }), [pickerDimensions]);
  const rows = useMemo(() => {
    const result = [...(analysisQ.data?.rows || [])];
    return result.sort((a, b) => {
      const contributionOrder = (Number(b[sort.key]) || 0) - (Number(a[sort.key]) || 0);
      if (contributionOrder) return sort.direction === "desc" ? contributionOrder : -contributionOrder;
      for (const key of dimensions) {
        const order = String(a[key] ?? "").localeCompare(String(b[key] ?? ""), undefined, { numeric: true, sensitivity: "base" });
        if (order) return order;
      }
      return 0;
    });
  }, [analysisQ.data, dimensions, sort]);
  const rowLabels = dimensions.map((column) => labels[column] || column);
  const toggleContributionSort = (key) => setSort((current) => ({
    key,
    direction: current.key === key && current.direction === "desc" ? "asc" : "desc",
  }));
  const sortLabel = {
    total_sales_contribution_pct: "Total Sales Cont.%",
    last_6m_contribution_pct: "Last 6M Sales Cont.%",
    current_stock_contribution_pct: "Current Stock Cont.%",
  }[sort.key];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="SOH ANALYSIS"
        title="Base Stock Analysis"
        description="Review category sales, current stock, sell-through, and four-month stock cover. Add row dimensions to drill into the category view."
      />

      <Card padded>
        <div className="flex flex-col gap-4">
          {dimensionsQ.isLoading ? <LoadingState rows={1} /> : (
            <div>
              <DimensionPicker
                dimensions={pickerDimensions}
                value={dimensions}
                onChange={(next) => setDimensions(next.includes("category") ? next : [...next, "category"])}
              />
              <p className="mt-2 flex items-center gap-1.5 text-xs text-text-muted">
                <Layers3 size={13} /> Category, Category Group, and Subcategory are mapped from the sales data; add or reorder row dimensions as needed.
              </p>
            </div>
          )}
          {slicersQ.data?.slicers && (
            <FilterPanel
              slicers={slicersQ.data.slicers}
              dimensionLabels={labels}
              value={filters}
              onChange={setFilters}
            />
          )}
        </div>
      </Card>

      {analysisQ.data && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-text-secondary">
          <span className="flex items-center gap-1.5"><CalendarRange size={14} className="text-accent" />Tertiary as of <strong className="text-text-primary">{formatDateDdMmYyyy(analysisQ.data.tertiary_as_of)}</strong></span>
          {analysisQ.data.last_6m_start && <span>Last 6M starts <strong className="text-text-primary">{formatDateDdMmYyyy(analysisQ.data.last_6m_start)}</strong></span>}
          {analysisQ.data.stock_as_of && <span>SOH as of <strong className="text-text-primary">{formatDateDdMmYyyy(analysisQ.data.stock_as_of)}</strong></span>}
        </div>
      )}

      {(analysisQ.data?.warnings || []).map((warning) => (
        <p key={warning} role="status" className="rounded border border-warn/30 bg-warn/10 px-3 py-2 text-sm text-warn">{warning}</p>
      ))}

      {analysisQ.isLoading ? (
        <Card><LoadingState label="Loading base stock analysis" rows={8} /></Card>
      ) : analysisQ.isError ? (
        <Card><ErrorState message={analysisQ.error.message} onRetry={() => analysisQ.refetch()} /></Card>
      ) : rows.length === 0 ? (
        <Card><EmptyState title="No base stock rows found" description="Try changing the store, brand, or status filters." /></Card>
      ) : (
        <Card>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Category Stock Position {analysisQ.isFetching && <span className="ml-2 text-xs font-normal text-text-muted">Updating…</span>}</h2>
              <p className="mt-1 text-xs text-text-muted">{rows.length.toLocaleString()} rows | sorted by {sortLabel} ({sort.direction === "desc" ? "highest first" : "lowest first"})</p>
            </div>
            <p className="text-xs text-text-muted">F4M = (Last 6M Sales / 6) * 4</p>
          </div>
          <div className="max-h-[70vh] min-h-[360px] overflow-auto rounded-xl border border-border bg-card">
            <table className="w-full min-w-[1500px] text-sm">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr>
                  {rowLabels.map((label, index) => (
                    <th key={label + index} rowSpan={2} className="border-b border-r border-border px-3 py-3 text-left font-semibold text-text-primary">{label}</th>
                  ))}
                  <th colSpan={2} className="border-b border-r border-border px-3 py-2 text-center text-xs font-bold uppercase tracking-wide text-text-secondary">Total Sales</th>
                  <th colSpan={2} className="border-b border-r border-border px-3 py-2 text-center text-xs font-bold uppercase tracking-wide text-text-secondary">Last 6M Sales</th>
                  <th colSpan={2} className="border-b border-r border-border px-3 py-2 text-center text-xs font-bold uppercase tracking-wide text-text-secondary">Current Stock</th>
                  <th rowSpan={2} className="border-b border-r border-border px-3 py-3 text-right font-semibold text-text-primary">ST%</th>
                  <th rowSpan={2} className="border-b border-r border-border px-3 py-3 text-right font-semibold text-text-primary">F4M Requirement</th>
                  <th rowSpan={2} className="border-b border-border px-3 py-3 text-right font-semibold text-text-primary">Stock - F4M Requirement</th>
                </tr>
                <tr>
                  {MEASURES.slice(0, 6).map((measure, index) => (
                    <th key={measure.key + index} className="border-b border-r border-border px-3 py-2 text-right text-xs font-medium text-text-muted">
                      {measure.percent ? (
                        <button type="button" onClick={() => toggleContributionSort(measure.key)} className="inline-flex items-center gap-1 hover:text-accent" aria-label={"Sort by " + measure.key}>
                          Cont.%{sort.key === measure.key ? (sort.direction === "desc" ? <ChevronDown size={13} /> : <ChevronUp size={13} />) : <ChevronDown size={13} className="opacity-30" />}
                        </button>
                      ) : "Qty"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={[row.category, ...dimensions.map((dimension) => row[dimension]), rowIndex].join("|")} className="border-b border-border/70 odd:bg-white/[0.025] hover:bg-white/[0.06]">
                    {dimensions.map((column, index) => (
                      <td key={column + index} className="whitespace-nowrap border-r border-border/60 px-3 py-2.5 text-text-primary">{row[column] ?? "-"}</td>
                    ))}
                    {MEASURES.map((measure, index) => (
                      <td key={measure.key + index} className="whitespace-nowrap border-r border-border/60 px-3 py-2.5 text-right tabular-nums text-text-secondary">
                        {measure.percent ? showPercent(row[measure.key]) : showNumber(row[measure.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-text-muted">ST% = Last 6M Sales / Current Stock. Stock - F4M Requirement is positive when stock is above four-month demand and negative when it is below.</p>
        </Card>
      )}
    </div>
  );
}
