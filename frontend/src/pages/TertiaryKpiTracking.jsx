import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";
import { ErrorState, LoadingState } from "../components/common/LoadingState";
import CategoryPerformance from "../components/analysis/CategoryPerformance";
import BillNoAnalysis from "../components/analysis/BillNoAnalysis";

const FILTER_ORDER = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const DIMENSIONS = [["store", "Storewise Analysis"], ["brand", "Brandwise Analysis"]];
const displayName = (value) => value.replaceAll("_", " ").split(" ").map((word) => word ? word[0].toUpperCase() + word.slice(1) : word).join(" ");
const numberFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const fyLabel = (year) => "FY" + year + "-" + String(Number(year) + 1).slice(-2);

function MultiFilter({ name, options, selected, onChange, open, onToggle, onClose }) {
  const [query, setQuery] = useState("");
  const visible = options.filter((option) => String(option.label).toLowerCase().includes(query.toLowerCase()));
  const chosen = options.filter((option) => selected.includes(String(option.value))).map((option) => String(option.label));
  const summary = chosen.length === 0 ? (selected.length ? selected.length + " selected" : "All") : chosen.length === 1 ? chosen[0] : chosen[0] + " +" + (chosen.length - 1);

  return <div className="relative min-w-[145px]">
    <button type="button" title={chosen.join(", ") || (selected.length ? selected.length + " selected" : "All")} onClick={onToggle} className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">
      <span>{displayName(name)}</span><span className="max-w-[7rem] truncate text-text-muted">{summary}</span>
    </button>
    {open && <div className={"absolute z-40 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl " + (name === "month" || name === "fy" ? "right-0" : "left-0")}>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs text-text-primary" />
      <div className="mb-2 flex justify-between text-xs text-text-secondary">
        <button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((option) => String(option.value))])])}>Select all</button>
        <button type="button" onClick={() => onChange([])}>Clear</button>
      </div>
      {visible.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs text-text-primary">
        <input type="checkbox" checked={selected.includes(String(option.value))} onChange={() => onChange(selected.includes(String(option.value)) ? selected.filter((value) => value !== String(option.value)) : [...selected, String(option.value)])} />
        {option.label}
      </label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs font-semibold text-white" onClick={onClose}>Done</button>
    </div>}
  </div>;
}

function Growth({ value, suffix = "%" }) {
  if (value == null || !Number.isFinite(Number(value))) return <span className="text-text-muted">—</span>;
  const numeric = Number(value);
  const tone = numeric > 0 ? "text-positive" : numeric < 0 ? "text-negative" : "text-text-secondary";
  return <span className={"whitespace-nowrap font-semibold tabular-nums " + tone}>{numeric > 0 ? "+" : ""}{numeric.toFixed(1)}{suffix}</span>;
}

function BucketCell({ value, growth = false }) {
  if (growth) return <div className="min-w-[138px] space-y-1 px-1">
    <div className="flex items-center justify-between gap-3 text-xs"><span className="text-[10px] uppercase tracking-wide text-text-muted">Bills</span><Growth value={value?.count_growth_pct} /></div>
    <div className="flex items-center justify-between gap-3 border-t border-border/70 pt-1 text-[11px]"><span className="text-[10px] uppercase tracking-wide text-text-muted">Share Δ</span><Growth value={value?.share_pp} suffix=" pp" /></div>
  </div>;

  return <div className="flex min-w-[138px] items-center justify-between gap-2 px-1">
    <span className="font-semibold tabular-nums text-text-primary">{numberFormat.format(value?.count || 0)}</span>
    <span className="border-l border-border pl-2 text-[11px] tabular-nums text-text-muted">{(value?.share_pct || 0).toFixed(1)}%</span>
  </div>;
}

function BucketTable({ title, dimensionLabel, buckets, rows, periodLabels, search, onSearch }) {
  const visibleRows = rows.filter((row) => row.label.toLowerCase().includes(search.toLowerCase()));
  const periods = [
    ["prior_full", periodLabels?.prior_full],
    ["matching", periodLabels?.matching],
    ["current", periodLabels?.current],
    ["growth", periodLabels?.growth],
  ];

  return <section className="overflow-hidden rounded-xl border border-border bg-surface">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
      <div><h3 className="font-display text-base font-semibold text-text-primary">{title}</h3><p className="mt-1 text-xs text-text-muted">Bill count and share of each row’s bills by bucket</p></div>
      <div className="relative"><Search size={14} className="absolute left-3 top-2.5 text-text-muted" /><input aria-label={"Search " + title} value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search rows" className="w-52 rounded-lg border border-border bg-base py-2 pl-9 pr-3 text-xs text-text-primary" /></div>
    </header>
    <div className="max-h-[62vh] overflow-auto">
      <table className="w-full min-w-max border-separate border-spacing-0 text-right text-xs">
        <thead className="text-text-secondary">
          <tr className="h-10">
            <th rowSpan="2" className="sticky left-0 top-0 z-30 min-w-[190px] border-b border-r border-border bg-base px-4 text-left font-semibold uppercase tracking-wide">{dimensionLabel}</th>
            {periods.map(([key, label]) => <th key={key} colSpan={buckets.length} className={"sticky top-0 z-20 border-b border-border bg-base px-3 text-center font-semibold uppercase tracking-wide " + (key === "growth" ? "border-l-4 border-l-accent/50 bg-accent-soft/40 text-accent" : "")}>{label || (key === "growth" ? "GROWTH" : "—")}</th>)}
          </tr>
          <tr className="h-10">
            {periods.flatMap(([key]) => buckets.map((bucket, index) => <th key={key + bucket} className={"sticky top-10 z-20 min-w-[148px] border-b border-border bg-base px-2 text-center text-[10px] font-semibold " + (key === "growth" ? (index === 0 ? "border-l-4 border-l-accent/50 " : "border-l border-border/70 ") + "bg-accent-soft/40 text-accent" : index === 0 ? "border-l border-border/70" : "")}>
              <div className="mb-1 text-text-primary">{bucket}</div>
              <div className="font-medium text-text-muted">{key === "growth" ? "BILL GROWTH | SHARE Δ" : "BILLS | CONT.%"}</div>
            </th>))}
          </tr>
        </thead>
        <tbody>
          {visibleRows.length ? visibleRows.map((row, index) => <tr key={row.label} className={"h-12 hover:bg-accent-soft/25 " + (row.is_total ? "bg-accent-soft/35 font-bold" : index % 2 ? "bg-base/35" : "bg-surface")}>
            <th className={"sticky left-0 z-10 border-b border-r border-border bg-surface px-4 text-left text-text-primary " + (row.is_total ? "border-t-2 border-t-accent font-bold" : "font-medium")}>{row.label}</th>
            {periods.flatMap(([key]) => buckets.map((bucket, columnIndex) => <td key={key + bucket} className={"border-b border-border px-2 " + (row.is_total ? "border-t-2 border-t-accent" : "") + (key === "growth" ? (columnIndex === 0 ? " border-l-4 border-l-accent/50 " : " border-l border-border/70 ") + "bg-accent-soft/10" : columnIndex === 0 ? " border-l border-border/70" : "")}>
              <BucketCell value={row.periods?.[key]?.[bucket]} growth={key === "growth"} />
            </td>))}
          </tr>) : <tr><td colSpan={1 + buckets.length * periods.length} className="px-4 py-10 text-center text-sm text-text-muted">{rows.length ? "No rows match this search." : "No bill data is available for these filters."}</td></tr>}
        </tbody>
      </table>
    </div>
    <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2.5 text-[10px] text-text-muted">
      <span>Contribution is calculated within each store or brand. Grand Total shows overall share.</span>
      <span>Growth = current period vs matching prior period; share change is in percentage points.</span>
    </footer>
  </section>;
}

export default function TertiaryKpiTracking() {
  const [filters, setFilters] = useState({});
  const [openFilter, setOpenFilter] = useState(null);
  const [section, setSection] = useState("quantity");
  const [dimensions, setDimensions] = useState({ quantity: "store", revenue: "store", category: "store", bills: "store" });
  const [qtySearch, setQtySearch] = useState("");
  const [revenueSearch, setRevenueSearch] = useState("");
  const filterPanelRef = useRef(null);

  const configQuery = useQuery({
    queryKey: ["tertiary-kpi-tracking", "config", filters],
    queryFn: () => tertiaryApi.summaryConfig(filters),
    staleTime: 5 * 60_000,
  });
  const dataQuery = useQuery({
    queryKey: ["tertiary-kpi-tracking", dimensions[section], filters],
    queryFn: () => tertiaryApi.kpiTracking(dimensions[section], filters),
    enabled: section === "quantity" || section === "revenue",
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey?.[1] === dimensions[section] ? previous : undefined,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!openFilter) return undefined;
    const closeOnOutside = (event) => { if (!filterPanelRef.current?.contains(event.target)) setOpenFilter(null); };
    const closeOnEscape = (event) => { if (event.key === "Escape") setOpenFilter(null); };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("pointerdown", closeOnOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, [openFilter]);

  const config = configQuery.data;
  const filterNames = FILTER_ORDER.filter((name) => name === "month" || name === "fy" || config?.fields?.[name]);
  const optionsFor = (name) => name === "month"
    ? (config?.months || [])
    : name === "fy"
      ? (config?.year_options || config?.years || []).map((year) => ({ value: year, label: fyLabel(year) }))
      : (config?.options?.[name] || []).map((value) => ({ value, label: value }));
  const setFilter = (name, values) => setFilters((current) => {
    const next = { ...current };
    if (values.length) next[name] = values;
    else delete next[name];
    return next;
  });

  const dimension = dimensions[section] || "store";
  const selectedDimension = dimension === "store"
    ? (config?.fields?.store || "adonis_store_code")
    : (config?.fields?.brand || "brand");
  const hierarchy = [selectedDimension];
  const categoryFilters = Object.fromEntries(Object.entries(filters)
    .filter(([, values]) => values?.length)
    .map(([key, values]) => [key === "month" || key === "fy" ? key : config?.fields?.[key] || key, values]));
  const billFilters = Object.fromEntries(Object.entries(filters)
    .filter(([key, values]) => key !== "fy" && key !== "month" && values?.length)
    .map(([key, values]) => [config?.fields?.[key] || key, values]));
  if (filters.month?.length) billFilters.month_num = filters.month.map(Number).filter(Number.isFinite);
  const anchorFy = (filters.fy || []).map(Number).filter(Number.isFinite).sort((a, b) => b - a)[0];
  const billDateRange = anchorFy ? { start: `${anchorFy}-04-01`, end: `${anchorFy + 1}-03-31` } : null;
  const setDimension = (value) => setDimensions((current) => ({ ...current, [section]: value }));
  const payload = dataQuery.data;
  const bucketNames = payload?.buckets || { quantity: [], revenue: [] };
  const rowsFor = (type) => type === "quantity" ? payload?.quantity_rows || [] : payload?.revenue_rows || [];
  const periodLabels = payload?.periods || {};

  return <main className="space-y-5 p-5 lg:p-7">
    <header>
      <p className="text-xs font-semibold uppercase tracking-[.18em] text-accent">Retail sell-out</p>
      <h1 className="mt-1 font-display text-2xl font-bold text-text-primary">Tertiary KPI Tracking</h1>
      <p className="mt-1 text-sm text-text-muted">Storewise and brandwise views for bill buckets, category performance, and top bills</p>
    </header>

    <section ref={filterPanelRef} className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3">
      <span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14} />Filters</span>
      {configQuery.isLoading ? <LoadingState rows={1} /> : configQuery.isError ? <ErrorState message={configQuery.error.message} onRetry={() => configQuery.refetch()} /> : <>
        {filterNames.map((name) => <MultiFilter key={name} name={name} options={optionsFor(name)} selected={(filters[name] || []).map(String)} onChange={(values) => setFilter(name, values)} open={openFilter === name} onToggle={() => setOpenFilter((current) => current === name ? null : name)} onClose={() => setOpenFilter(null)} />)}
        {Object.keys(filters).length > 0 && <button type="button" onClick={() => setFilters({})} className="px-2 text-xs font-medium text-text-muted hover:text-negative">Reset filters</button>}
      </>}
    </section>

    <section className="overflow-hidden rounded-xl border border-border bg-surface">
      <nav aria-label="Tertiary KPI analyses" className="flex flex-wrap gap-1 border-b border-border px-2">
        {[["quantity", "Quantity Bucket"], ["revenue", "Revenue Bucket"], ["category", "Category Performance"], ["bills", "Top N Bills"]].map(([key, label]) =>
          <button key={key} type="button" onClick={() => setSection(key)} className={"border-b-2 px-4 py-3 text-sm font-semibold transition-colors " + (section === key ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}>{label}</button>
        )}
      </nav>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-base/30 px-4 py-3">
        <div><p className="text-[10px] font-bold uppercase tracking-[.16em] text-accent">{section === "quantity" ? "Quantity Bucket Based Analysis" : section === "revenue" ? "Revenue Bucket Based Analysis" : section === "category" ? "Category Performance" : "Top N Bills"}</p><p className="mt-1 text-xs text-text-muted">Choose the row level for this analysis. Global filters above apply to the results.</p></div>
        <div role="group" aria-label="Analysis row level" className="inline-flex rounded-lg border border-border bg-surface p-1">
          {DIMENSIONS.map(([key, label]) => <button key={key} type="button" onClick={() => setDimension(key)} aria-pressed={dimension === key} className={"rounded-md px-3 py-1.5 text-xs font-semibold transition-colors " + (dimension === key ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary")}>{label}</button>)}
        </div>
      </div>

      {(section === "quantity" || section === "revenue") && (dataQuery.isLoading ? <div className="space-y-4 p-4"><LoadingState rows={1} /><LoadingState rows={8} /></div> : dataQuery.isError ? <div className="p-4"><ErrorState message={dataQuery.error.message} onRetry={() => dataQuery.refetch()} /></div> : <div className="p-4">
        <BucketTable title={section === "quantity" ? "Quantity Bucket Based Analysis" : "Revenue Bucket Based Analysis"} buckets={bucketNames[section]} rows={rowsFor(section)} dimensionLabel={dimension === "store" ? "STORE" : "BRAND"} periodLabels={periodLabels} search={section === "quantity" ? qtySearch : revenueSearch} onSearch={section === "quantity" ? setQtySearch : setRevenueSearch} />
      </div>)}
      {section === "category" && <div className="p-4"><CategoryPerformance api={tertiaryApi} filters={categoryFilters} hierarchy={hierarchy} eyebrow="Tertiary KPI Tracking" /></div>}
      {section === "bills" && <div className="p-4"><BillNoAnalysis filters={billFilters} hierarchy={hierarchy} eyebrow="Tertiary KPI Tracking" topBillsOnly dateRange={billDateRange} /></div>}
    </section>
  </main>;
}
