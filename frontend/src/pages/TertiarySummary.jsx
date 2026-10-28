import { useEffect, useState } from "react";
import { Boxes, IndianRupee, SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";

const pages = [["brand", "Brands comparison"], ["store", "Brand-store performance"], ["department", "Department-wise performance"], ["state", "State-wise performance"], ["group", "Group-wise performance"]];
const filterOrder = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const display = (s) => s.replaceAll("_", " ").split(" ").map((word) => word ? word[0].toUpperCase() + word.slice(1) : word).join(" ");
const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const pct = (a, b) => !b ? null : (a - b) / Math.abs(b) * 100;
const fyName = (y) => "FY" + y + "-" + String(y + 1).slice(-2);

function MultiFilter({ name, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const visible = options.filter((v) => String(v.label).toLowerCase().includes(query.toLowerCase()));
  return <div className="relative min-w-[150px]">
    <button type="button" onClick={() => setOpen(!open)} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">{display(name)} <span className="float-right text-text-muted">{selected.length ? selected.length + " selected" : "All"}</span></button>
    {open && <div className="absolute z-30 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs" />
      <div className="mb-2 flex justify-between text-xs"><button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((o) => String(o.value))])])}>Select all</button><button type="button" onClick={() => onChange([])}>Clear</button></div>
      {visible.map((opt) => <label key={opt.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs"><input type="checkbox" checked={selected.includes(String(opt.value))} onChange={() => onChange(selected.includes(String(opt.value)) ? selected.filter((v) => v !== String(opt.value)) : [...selected, String(opt.value)])} />{opt.label}</label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs text-white" onClick={() => setOpen(false)}>Done</button>
    </div>}
  </div>;
}

function GrowthValue({ value, pill = false }) {
  if (value == null) return <span className="text-text-muted">&mdash;</span>;
  const positive = value > 0;
  const tone = positive ? "text-positive" : value < 0 ? "text-negative" : "text-text-secondary";
  const pillStyle = value > 0 ? "bg-positive-soft" : value < 0 ? "bg-negative-soft" : "bg-base";
  return <span className={"tabular-nums " + (pill ? "rounded-full px-2 py-1 text-xs font-semibold " + pillStyle + " " : "text-xs font-semibold ") + tone}>{value > 0 ? "+" : ""}{value.toFixed(1)}%{pill && " YoY"}</span>;
}

function HistoryTable({ title, metric, rows, total, growth }) {
  const isQuantity = metric === "qty";
  const label = isQuantity ? "TOTAL QUANTITY (VOLUME)" : "TOTAL VALUE (REVENUE)";
  return <article className="rounded-xl border border-border bg-base/40 p-4 sm:p-5">
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2.5"><span className={"flex h-8 w-8 shrink-0 items-center justify-center rounded-lg " + (isQuantity ? "bg-accent-soft text-accent" : "bg-positive-soft text-positive")}>{isQuantity ? <Boxes size={16}/> : <IndianRupee size={16}/>}</span><h3 className="truncate text-xs font-bold tracking-wide text-text-secondary">{label}</h3></div>
      <span className={"shrink-0 rounded border px-2 py-1 text-[10px] font-semibold " + (isQuantity ? "border-accent/30 text-accent" : "border-positive/30 text-positive")}>{isQuantity ? "Unit Basis" : <>INR (&#8377;)</>}</span>
    </div>
    <div className="mb-4 mt-2 flex flex-wrap items-center gap-3"><p className="font-display text-3xl font-bold tracking-tight tabular-nums text-text-primary">{!isQuantity && <span>₹</span>}{fmt.format(total || 0)}</p><GrowthValue value={growth} pill/></div>
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full border-separate border-spacing-0 text-left text-sm">
        <thead className="bg-base text-[10px] font-semibold uppercase tracking-wider text-text-secondary"><tr><th className="px-3 py-2.5 sm:px-4">FY</th><th className="px-3 py-2.5 text-right sm:px-4">{isQuantity ? "QTY" : "VALUE"}</th><th className="px-3 py-2.5 text-right sm:px-4">GROWTH%</th></tr></thead>
        <tbody>{rows.length ? rows.map((row, index) => <tr key={row.key} className={index % 2 ? "bg-base/40" : "bg-surface"}>
          <th scope="row" className="border-t border-border px-3 py-2.5 text-left font-medium text-text-primary sm:px-4">{row.label}</th>
          <td className="border-t border-border px-3 py-2.5 text-right font-semibold tabular-nums text-text-primary sm:px-4">{!isQuantity && <span className="mr-0.5">₹</span>}{fmt.format(row[metric] || 0)}</td>
          <td className="border-t border-border px-3 py-2.5 text-right sm:px-4"><GrowthValue value={row[growthKey(metric)]}/></td>
        </tr>) : <tr><td colSpan="3" className="px-4 py-6 text-center text-sm text-text-muted">No fiscal-year data for these filters.</td></tr>}</tbody>
      </table>
    </div>
  </article>;
}

function growthKey(metric) { return metric + "Growth"; }

export default function TertiarySummary() {
  const [config, setConfig] = useState(null);
  const [filters, setFilters] = useState({});
  const [page, setPage] = useState("brand");
  const [payload, setPayload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => tertiaryApi.summaryConfig(filters).then((data) => active && setConfig(data)).catch((e) => active && setError(e.message)), 80);
    return () => { active = false; clearTimeout(timer); };
  }, [filters]);

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      setBusy(true);
      tertiaryApi.summary(page, filters).then((data) => { if (active) { setPayload(data); setError(""); } }).catch((e) => active && setError(e.message)).finally(() => active && setBusy(false));
    }, 80);
    return () => { active = false; clearTimeout(timer); };
  }, [page, filters]);

  const anchor = payload?.anchor;
  const currentPartial = Boolean(payload?.current_fy_partial && anchor === payload?.current_fy);
  const totals = payload?.totals || {};
  const availableYears = [...(payload?.years || [])].sort((a, b) => b - a);
  const historicalRows = [];

  if (anchor != null && totals[String(anchor)]) {
    const previousYear = anchor - 1;
    const current = totals[String(anchor)] || {};
    const previous = totals[String(previousYear)] || {};
    const comparisonQty = currentPartial ? previous.lfytd_qty : previous.qty;
    const comparisonVal = currentPartial ? previous.lfytd_val : previous.val;
    historicalRows.push({ key: "current-" + anchor, label: fyName(anchor), current: true, qty: current.qty || 0, val: current.val || 0, qtyGrowth: pct(current.qty || 0, comparisonQty || 0), valGrowth: pct(current.val || 0, comparisonVal || 0) });

    if (currentPartial && availableYears.includes(previousYear)) {
      historicalRows.push({ key: "lfytd-" + previousYear, label: fyName(previousYear) + " LFYTD", qty: previous.lfytd_qty || 0, val: previous.lfytd_val || 0, qtyGrowth: null, valGrowth: null });
    }

    availableYears.filter((year) => year < anchor).forEach((year) => {
      const values = totals[String(year)] || {};
      const base = totals[String(year - 1)] || {};
      historicalRows.push({ key: "full-" + year, label: fyName(year) + (currentPartial && year === previousYear ? " (Full)" : ""), qty: values.qty || 0, val: values.val || 0, qtyGrowth: pct(values.qty || 0, base.qty || 0), valGrowth: pct(values.val || 0, base.val || 0) });
    });
  }

  const setFilter = (key, values) => setFilters((old) => ({ ...old, [key]: values }));

  return <main className="space-y-5 p-5 lg:p-7">
    <header><p className="text-xs font-semibold uppercase tracking-[.18em] text-accent">Retail sell-out</p><h1 className="mt-1 font-display text-2xl font-bold text-text-primary">Tertiary Sales Summary</h1><p className="mt-1 text-sm text-text-muted">Historical quantity and value performance across fiscal years</p></header>
    <section className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3"><span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14}/>Filters</span>{config && filterOrder.filter((f) => f === "month" || f === "fy" || config.fields[f]).map((name) => {
      const options = name === "month" ? config.months : name === "fy" ? (config.year_options || config.years).map((y) => ({ value: y, label: fyName(y) })) : (config.options[name] || []).map((v) => ({ value: v, label: v }));
      return <MultiFilter key={name} name={name} options={options} selected={(filters[name] || []).map(String)} onChange={(v) => setFilter(name, v)} />;
    })}</section>
    <nav aria-label="Summary dimensions" className="flex gap-1 overflow-x-auto border-b border-border">{pages.filter(([key]) => key === "brand" || config?.fields[key]).map(([key, label]) => <button key={key} type="button" onClick={() => setPage(key)} className={"whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold " + (page === key ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}>{label}</button>)}</nav>
    <section className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5"><div><h2 className="font-display text-base font-semibold text-text-primary">Historical Performance Consolidated</h2><p className="mt-1 text-xs text-text-muted">{anchor != null ? fyName(anchor) + (currentPartial ? " current year to date" : " selected anchor year") : "Select filters to view fiscal-year totals"}</p></div>{busy && <span role="status" className="text-xs text-text-muted">Updating performance...</span>}</div>
      {error && <p role="alert" className="border-b border-border px-4 py-3 text-sm text-negative">{error}</p>}
      <div className="grid gap-4 p-4 sm:p-5 xl:grid-cols-2"><HistoryTable title="QTY" metric="qty" rows={historicalRows} total={totals[String(anchor)]?.qty || 0} growth={historicalRows[0]?.qtyGrowth}/><HistoryTable title="VALUE" metric="val" rows={historicalRows} total={totals[String(anchor)]?.val || 0} growth={historicalRows[0]?.valGrowth}/></div>
    </section>
  </main>;
}
