import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarRange, SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import { ErrorState, LoadingState } from "../components/common/LoadingState";
import MonthwiseRowsTable from "../components/analysis/MonthwiseRowsTable";

const FILTER_ORDER = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const display = (value) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const fyLabel = (year) => "FY" + year + "-" + String(Number(year) + 1).slice(-2);

function FilterSelect({ name, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const visible = options.filter((option) => String(option.label).toLowerCase().includes(search.toLowerCase()));
  const toggle = (value) => onChange(selected.includes(String(value)) ? selected.filter((item) => item !== String(value)) : [...selected, String(value)]);
  return <div className="relative min-w-[140px]">
    <button type="button" onClick={() => setOpen(!open)} className="w-full rounded-lg border border-border-strong px-3 py-2 text-left text-xs text-text-primary hover:border-accent/50">{display(name)} <span className="float-right text-text-muted">{selected.length ? selected.length + " selected" : "All"}</span></button>
    {open && <div className="absolute left-0 z-30 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-card p-3 shadow-panel-lg">
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs text-text-primary" />
      <div className="mb-2 flex justify-between text-xs text-text-secondary"><button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((option) => String(option.value))])])}>Select visible</button><button type="button" onClick={() => onChange([])}>Clear</button></div>
      {visible.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs text-text-primary"><input type="checkbox" checked={selected.includes(String(option.value))} onChange={() => toggle(option.value)} />{option.label}</label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1.5 text-xs font-semibold text-white" onClick={() => setOpen(false)}>Done</button>
    </div>}
  </div>;
}

export default function TertiaryMonthwise() {
  const [filters, setFilters] = useState({});
  const [dimension, setDimension] = useState("brand");
  const configQ = useQuery({ queryKey: ["tertiary-monthwise", "filter-config", filters], queryFn: () => tertiaryApi.summaryConfig(filters) });
  const dimensionsQ = useQuery({ queryKey: ["tertiary-monthwise", "dimensions"], queryFn: tertiaryApi.dimensions });
  const monthwiseQ = useQuery({ queryKey: ["tertiary-monthwise", dimension, filters], queryFn: () => tertiaryApi.monthwise([dimension], filters), enabled: Boolean(dimension) });
  const dimensions = dimensionsQ.data?.dimensions || [];
  const activeDimension = dimensions.find((item) => item.column === dimension);
  const dimensionLabels = useMemo(() => Object.fromEntries(dimensions.map((item) => [item.column, item.label])), [dimensions]);
  const config = configQ.data;
  const filterNames = FILTER_ORDER.filter((name) => name === "month" || name === "fy" || config?.fields?.[name]);
  const optionsFor = (name) => name === "month" ? (config?.months || []) : name === "fy" ? (config?.year_options || config?.years || []).map((year) => ({ value: year, label: fyLabel(year) })) : (config?.options?.[name] || []).map((value) => ({ value, label: value }));

  return <main className="space-y-5 p-5 lg:p-7">
    <PageHeader eyebrow="Retail sell-out" title="Tertiary Monthwise Analysis" description="Month-by-month quantity, value, discount, and growth across the selected analysis dimension." />
    <Card padded>
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wide text-text-muted"><SlidersHorizontal size={14} /> Global filters</div>
      {configQ.isLoading ? <LoadingState rows={1} /> : configQ.isError ? <ErrorState message={configQ.error.message} onRetry={() => configQ.refetch()} /> : <div className="flex flex-wrap gap-2">{filterNames.map((name) => <FilterSelect key={name} name={name} options={optionsFor(name)} selected={filters[name] || []} onChange={(values) => setFilters((current) => { const next = { ...current }; if (values.length) next[name] = values; else delete next[name]; return next; })} />)}{Object.keys(filters).length > 0 && <button type="button" onClick={() => setFilters({})} className="px-3 text-xs font-medium text-text-muted hover:text-negative">Reset filters</button>}</div>}
    </Card>
    <section>
      <div className="mb-4 flex items-center gap-2 border-b border-border overflow-x-auto" role="tablist" aria-label="Analysis dimension">
        {dimensions.map((item) => <button key={item.column} type="button" role="tab" aria-selected={dimension === item.column} onClick={() => setDimension(item.column)} className={'flex shrink-0 items-center gap-1.5 border-b-2 px-4 py-3 text-sm font-semibold transition-colors ' + (dimension === item.column ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}><CalendarRange size={14} />{item.label}</button>)}
      </div>
      <Card padded={false} className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3"><div><h2 className="font-display font-semibold text-text-primary">{activeDimension?.label || display(dimension)} monthwise analysis</h2><p className="mt-1 text-xs text-text-muted">Quantity, MRP value, discount, discount outflow, and bill value by fiscal month</p></div>{monthwiseQ.data?.fy_context?.current_fy_label && <span className="text-xs text-text-secondary">Current FY: {monthwiseQ.data.fy_context.current_fy_label}</span>}</div>
        <div className="p-4">{dimensionsQ.isLoading || monthwiseQ.isLoading ? <LoadingState rows={8} /> : dimensionsQ.isError ? <ErrorState message={dimensionsQ.error.message} onRetry={() => dimensionsQ.refetch()} /> : monthwiseQ.isError ? <ErrorState message={monthwiseQ.error.message} onRetry={() => monthwiseQ.refetch()} /> : <MonthwiseRowsTable result={monthwiseQ.data} dimensionLabels={dimensionLabels} />}</div>
      </Card>
    </section>
  </main>;
}
