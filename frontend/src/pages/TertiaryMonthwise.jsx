import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";
import { ErrorState, LoadingState } from "../components/common/LoadingState";
import {
  MonthwiseDimensionTable,
  MonthwiseHistoryKpis,
  default as TertiaryMonthwiseTable,
} from "../components/analysis/TertiaryMonthwiseTable";

const FILTER_ORDER = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const DIMENSIONS = [
  ["brand", "Brandwise Analysis"],
  ["store", "Storewise Analysis"],
  ["department", "Departmentwise Analysis"],
  ["state", "Statewise Analysis"],
];
const display = (value) => value.replaceAll("_", " ").split(" ").map((word) => word ? word[0].toUpperCase() + word.slice(1) : word).join(" ");
const fyLabel = (year) => "FY" + year + "-" + String(Number(year) + 1).slice(-2);

function MultiFilter({ name, options, selected, onChange, open, onToggle, onClose }) {
  const [query, setQuery] = useState("");
  const visible = options.filter((option) => String(option.label).toLowerCase().includes(query.toLowerCase()));
  return <div className="relative min-w-[150px]">
    <button type="button" onClick={onToggle} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">{display(name)} <span className="float-right text-text-muted">{selected.length ? selected.length + " selected" : "All"}</span></button>
    {open && <div className={"absolute z-40 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl " + (name === "month" || name === "fy" ? "right-0" : "left-0")}>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs text-text-primary" />
      <div className="mb-2 flex justify-between text-xs text-text-secondary"><button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((option) => String(option.value))])])}>Select all</button><button type="button" onClick={() => onChange([])}>Clear</button></div>
      {visible.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs text-text-primary"><input type="checkbox" checked={selected.includes(String(option.value))} onChange={() => onChange(selected.includes(String(option.value)) ? selected.filter((value) => value !== String(option.value)) : [...selected, String(option.value)])} />{option.label}</label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs font-semibold text-white" onClick={onClose}>Done</button>
    </div>}
  </div>;
}

export default function TertiaryMonthwise() {
  const [filters, setFilters] = useState({});
  const [openFilter, setOpenFilter] = useState(null);
  const [activeDimension, setActiveDimension] = useState("brand");
  const [search, setSearch] = useState("");
  const configQ = useQuery({ queryKey: ["tertiary-monthwise", "filter-config", filters], queryFn: () => tertiaryApi.summaryConfig(filters) });
  const monthwiseQ = useQuery({ queryKey: ["tertiary-monthwise", filters], queryFn: () => tertiaryApi.monthwise([], filters) });
  const analysisQ = useQuery({ queryKey: ["tertiary-monthwise", "dimension", activeDimension, filters], queryFn: () => tertiaryApi.summary(activeDimension, filters) });
  const config = configQ.data;
  const filterNames = FILTER_ORDER.filter((name) => name === "month" || name === "fy" || config?.fields?.[name]);
  const availableDimensions = DIMENSIONS.filter(([key]) => key === "brand" || config?.fields?.[key]);
  const optionsFor = (name) => name === "month" ? (config?.months || []) : name === "fy" ? (config?.year_options || config?.years || []).map((year) => ({ value: year, label: fyLabel(year) })) : (config?.options?.[name] || []).map((value) => ({ value, label: value }));
  const setFilter = (name, values) => setFilters((current) => { const next = { ...current }; if (values.length) next[name] = values; else delete next[name]; return next; });
  const selectedMonths = (filters.month || []).map(Number);

  return <main className="space-y-5 p-5 lg:p-7">
    <header><p className="text-xs font-semibold uppercase tracking-[.18em] text-accent">Retail sell-out</p><h1 className="mt-1 font-display text-2xl font-bold text-text-primary">Tertiary Monthwise Analysis</h1><p className="mt-1 text-sm text-text-muted">Monthly performance and historical breakdowns across quantity, value, discount, and discount outflow</p></header>
    <section className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3"><span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14}/>Filters</span>{configQ.isLoading ? <LoadingState rows={1}/> : configQ.isError ? <ErrorState message={configQ.error.message} onRetry={() => configQ.refetch()}/> : <>{filterNames.map((name) => <MultiFilter key={name} name={name} options={optionsFor(name)} selected={(filters[name] || []).map(String)} onChange={(values) => setFilter(name, values)} open={openFilter === name} onToggle={() => setOpenFilter((current) => current === name ? null : name)} onClose={() => setOpenFilter(null)}/>)}{Object.keys(filters).length > 0 && <button type="button" onClick={() => setFilters({})} className="px-2 text-xs font-medium text-text-muted hover:text-negative">Reset filters</button>}</>}</section>

    {analysisQ.isLoading ? <section className="rounded-xl border border-border bg-surface p-4"><LoadingState rows={3}/></section> : analysisQ.isError ? <section className="rounded-xl border border-border bg-surface p-4"><ErrorState message={analysisQ.error.message} onRetry={() => analysisQ.refetch()}/></section> : <MonthwiseHistoryKpis payload={analysisQ.data} selectedMonths={selectedMonths} maxDate={monthwiseQ.data?.fy_context?.max_date}/>}

    <section className="overflow-hidden rounded-xl border border-border bg-surface">
      <nav aria-label="Monthwise analysis dimensions" className="flex gap-1 overflow-x-auto border-b border-border px-2">
        {availableDimensions.map(([key, label]) => <button key={key} type="button" onClick={() => { setActiveDimension(key); setSearch(""); }} className={"whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold " + (activeDimension === key ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}>{label}</button>)}
      </nav>
      {analysisQ.isLoading ? <div className="p-4"><LoadingState rows={8}/></div> : analysisQ.isError ? <div className="p-4"><ErrorState message={analysisQ.error.message} onRetry={() => analysisQ.refetch()}/></div> : <MonthwiseDimensionTable payload={analysisQ.data} dimension={activeDimension} search={search} setSearch={setSearch} selectedMonths={selectedMonths}/>}
    </section>

    <section className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
        <div><h2 className="font-display text-base font-semibold text-text-primary">Monthwise Performance Consolidated</h2><p className="mt-1 text-xs text-text-muted">Fiscal months April to March, filtered by the selections above</p></div>
        {monthwiseQ.data?.fy_context?.current_fy_label && <span className="text-xs text-text-secondary">Current FY: {monthwiseQ.data.fy_context.current_fy_label}</span>}
      </div>
      {monthwiseQ.isLoading ? <div className="space-y-4 p-4"><LoadingState rows={1}/><LoadingState rows={8}/></div> : monthwiseQ.isError ? <div className="p-4"><ErrorState message={monthwiseQ.error.message} onRetry={() => monthwiseQ.refetch()}/></div> : <div className="p-4"><TertiaryMonthwiseTable result={monthwiseQ.data}/></div>}
    </section>
  </main>;
}
