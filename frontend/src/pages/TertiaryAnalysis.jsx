import { useEffect, useMemo, useState } from "react";
import { Download, Search, SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";

const pages = [
  ["brand", "Brands comparison"], ["store", "Brand × store performance"],
  ["department", "Department-wise performance"], ["state", "State-wise performance"], ["group", "Group-wise performance"],
];
const filterOrder = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const title = (s) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const pct = (a, b) => !b ? null : (a - b) / Math.abs(b) * 100;
function MultiFilter({ name, options, selected, onChange }) {
  const [open, setOpen] = useState(false); const [query, setQuery] = useState("");
  const visible = (options || []).filter((v) => String(v).toLowerCase().includes(query.toLowerCase()));
  return <div className="relative min-w-[145px]">
    <button onClick={() => setOpen(!open)} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">{title(name)} <span className="float-right text-text-muted">{selected.length ? `${selected.length} selected` : "All ▾"}</span></button>
    {open && <div className="absolute z-30 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs" />
      <div className="mb-2 flex justify-between text-xs"><button onClick={() => onChange(visible.map(String))}>Select all</button><button onClick={() => onChange([])}>Clear</button></div>
      {visible.map((v) => <label key={v} className="flex cursor-pointer items-center gap-2 py-1 text-xs"><input type="checkbox" checked={selected.includes(String(v))} onChange={() => onChange(selected.includes(String(v)) ? selected.filter((x) => x !== String(v)) : [...selected, String(v)])} />{v}</label>)}
      <button className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs text-white" onClick={() => setOpen(false)}>Done</button>
    </div>}
  </div>;
}
export default function TertiaryAnalysis() {
  const [config, setConfig] = useState(null), [filters, setFilters] = useState({}), [page, setPage] = useState("brand");
  const [payload, setPayload] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [search, setSearch] = useState("");
  useEffect(() => { tertiaryApi.summaryConfig().then(setConfig).catch((e) => setError(e.message)); }, []);
  useEffect(() => { if (!config) return; let live = true; setBusy(true); const timer = setTimeout(() => tertiaryApi.summary(page, filters).then((d) => { if (live) { setPayload(d); setError(""); } }).catch((e) => live && setError(e.message)).finally(() => live && setBusy(false)), 70); return () => { live = false; clearTimeout(timer); }; }, [config, page, filters]);
  const years = [...(payload?.years || [])].reverse();
  const rows = useMemo(() => (payload?.rows || []).filter((r) => r.label.toLowerCase().includes(search.toLowerCase())), [payload, search]);
  const anchor = years[0]; const base = years[1];
  const total = payload?.totals?.[String(anchor)] || { qty: 0, val: 0 }; const prior = payload?.totals?.[String(base)] || { qty: 0, val: 0 };
  const top = [...(payload?.rows || [])].sort((a,b) => (b.years[String(anchor)]?.val || 0) - (a.years[String(anchor)]?.val || 0))[0];
  const exportCsv = () => {
    const head = [title(page), ...years.flatMap((y) => ["FY"+y+" QTY", "FY"+y+" VAL"]), ...years.slice(0,-1).flatMap((y,i) => ["Growth QTY", "Growth VAL"])];
    const lines = [head, ...rows.map((r) => [r.label, ...years.flatMap((y) => [r.years[String(y)]?.qty || 0, r.years[String(y)]?.val || 0]), ...years.slice(0,-1).flatMap((y,i) => { const c=r.years[String(y)]||{}, b=r.years[String(years[i+1])]||{}; return [pct(c.qty||0,b.qty||0) ?? "New", pct(c.val||0,b.val||0) ?? "New"]; })]), ["Grand Total", ...years.flatMap((y) => [payload?.totals?.[String(y)]?.qty||0,payload?.totals?.[String(y)]?.val||0])]];
    const csv = lines.map((line) => line.map((v) => `"${String(v).replaceAll('"','""')}"`).join(",")).join("\r\n"); const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"})); a.download="tertiary-sales-summary.csv"; a.click(); URL.revokeObjectURL(a.href);
  };
  return <main className="space-y-5 p-5 lg:p-7">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[.18em] text-accent">Retail sell-out · Levi’s</p><h1 className="mt-1 font-display text-2xl font-bold text-text-primary">Tertiary Sales Summary</h1><p className="mt-1 text-sm text-text-muted">Fiscal year performance across stores, brands and markets</p></div><button onClick={exportCsv} disabled={!payload} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><Download size={16}/>Export CSV</button></div>
    <section className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3"><span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14}/>Filters</span>{config && filterOrder.filter((f) => f === "month" || f === "fy" || config.fields[f]).map((name) => {
      const opts = name === "month" ? config.months.map((m) => ({value:m.value,label:m.label})) : name === "fy" ? config.years.map((y) => ({value:y,label:`FY${y}-${String(y+1).slice(-2)}`})) : (config.options[name]||[]).map((v) => ({value:v,label:v}));
      return <MultiFilter key={name} name={name} options={opts.map(o=>o.label)} selected={(filters[name]||[]).map(v => { const opt=opts.find(o=>String(o.value)===String(v)); return opt ? String(opt.label) : String(v); })} onChange={(labels) => setFilters((old) => ({...old,[name]: labels.map(label => String(opts.find(o=>String(o.label)===label)?.value ?? label))}))}/>;
    })}</section>
    <nav className="flex gap-1 overflow-x-auto border-b border-border">{pages.filter(([key]) => key === "brand" || config?.fields[key]).map(([key,label])=><button key={key} onClick={()=>setPage(key)} className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold ${page===key?"border-accent text-accent":"border-transparent text-text-muted hover:text-text-primary"}`}>{label}</button>)}</nav>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Total quantity",inr.format(total.qty)], ["Total value",`₹${inr.format(total.val)}`], ["Quantity growth",pct(total.qty,prior.qty)], ["Value growth",pct(total.val,prior.val)], ["Top performer",top?.label||"—"]].map(([label,value])=><div key={label} className="rounded-xl border border-border bg-surface p-4"><p className="text-xs font-medium text-text-muted">{label}</p><p className="mt-2 truncate font-display text-xl font-bold text-text-primary">{typeof value==="number"?`${value>=0?"↑":"↓"} ${value.toFixed(1)}%`:value}</p>{label.includes("growth")&&<p className="mt-1 text-[11px] text-text-muted">vs {base?`FY${base}-${String(base+1).slice(-2)}`:"previous FY"}</p>}</div>)}</section>
    <section className="overflow-hidden rounded-xl border border-border bg-surface"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4"><div><h2 className="font-display font-semibold text-text-primary">{pages.find(([k])=>k===page)?.[1]}</h2><p className="mt-1 text-xs text-text-muted">{rows.length.toLocaleString("en-IN")} rows · grouped by financial year</p></div><div className="relative"><Search size={15} className="absolute left-3 top-2.5 text-text-muted"/><input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="Search rows" className="rounded-lg border border-border bg-base py-2 pl-9 pr-3 text-sm"/></div></div>
      {error&&<p className="p-4 text-sm text-negative">{error}</p>}<div className="max-h-[62vh] overflow-auto"><table className="w-full min-w-max border-separate border-spacing-0 text-right text-xs"><thead className="sticky top-0 z-10 bg-base text-text-secondary"><tr><th rowSpan="2" className="sticky left-0 z-20 min-w-48 border-b border-r border-border bg-base px-4 py-3 text-left uppercase">{title(page)}</th>{years.map((y,i)=><th key={y} colSpan="2" className="border-b border-border px-3 py-2 text-center">FY{y}-{String(y+1).slice(-2)}</th>)}{years.slice(0,-1).map((y,i)=><th key={'g'+y} colSpan="2" className="border-b border-border px-3 py-2 text-center">Growth</th>)}</tr><tr>{years.flatMap(y=>["QTY","VAL"]).concat(years.slice(0,-1).flatMap(()=>["QTY","VAL"])).map((x,i)=><th key={i} className="border-b border-border px-3 py-2">{x}</th>)}</tr></thead><tbody>{rows.map((r)=><tr key={r.label} className="odd:bg-surface even:bg-base/60 hover:bg-accent-soft/50"><th className="sticky left-0 border-b border-r border-border bg-inherit px-4 py-2 text-left font-medium text-text-primary">{r.label}</th>{years.flatMap(y=>[<td key={y+'q'} className="border-b border-border px-3 py-2 tabular-nums">{inr.format(r.years[String(y)]?.qty||0)}</td>,<td key={y+'v'} className="border-b border-border px-3 py-2 tabular-nums">₹{inr.format(r.years[String(y)]?.val||0)}</td>])}{years.slice(0,-1).flatMap((y,i)=>{const c=r.years[String(y)]||{},b=r.years[String(years[i+1])]||{};return [pct(c.qty||0,b.qty||0),pct(c.val||0,b.val||0)].map((v,j)=><td key={`${y}g${j}`} className={`border-b border-border px-3 py-2 font-semibold tabular-nums ${v==null?"text-text-muted":v>=0?"text-positive":"text-negative"}`}>{v==null?"New":`${v>=0?"↑":"↓"} ${Math.abs(v).toFixed(1)}%`}</td>)})}</tr>)}
      <tr className="sticky bottom-0 z-[5] bg-accent-soft font-bold text-text-primary"><th className="sticky left-0 bg-accent-soft px-4 py-3 text-left">Grand Total</th>{years.flatMap(y=>[<td key={y+'tq'} className="px-3 py-3">{inr.format(payload?.totals?.[String(y)]?.qty||0)}</td>,<td key={y+'tv'} className="px-3 py-3">₹{inr.format(payload?.totals?.[String(y)]?.val||0)}</td>])}{years.slice(0,-1).flatMap((y,i)=>["qty","val"].map((m)=><td key={`${y}gt${m}`} className="px-3 py-3">{pct(payload?.totals?.[String(y)]?.[m]||0,payload?.totals?.[String(years[i+1])]?.[m]||0)?.toFixed(1)??"—"}%</td>))}</tr></tbody></table></div>{busy&&<div className="border-t border-border px-4 py-2 text-xs text-text-muted">Updating report…</div>}</section>
  </main>;
}
