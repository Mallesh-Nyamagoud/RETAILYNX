import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Search, SlidersHorizontal, ArrowUpDown, TrendingUp, TrendingDown, Minus } from "lucide-react";
import * as XLSX from "xlsx";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import { tertiaryApi } from "../api/client";

const pages = [["brand", "Brands comparison"], ["store", "Brand-store performance"], ["department", "Department-wise performance"], ["state", "State-wise performance"], ["group", "Group-wise performance"]];
const filterOrder = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const display = (s) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const pct = (a, b) => !b ? null : (a - b) / Math.abs(b) * 100;
const fyName = (y) => `FY${y}-${String(y + 1).slice(-2)}`;
function GrowthBadge({ value, large = false }) {
  if (value == null) return <span className="inline-flex items-center gap-1 rounded-full bg-base px-2 py-1 text-[11px] font-semibold text-text-muted">New</span>;
  const positive = value > 0; const neutral = value === 0;
  const Icon = neutral ? Minus : positive ? TrendingUp : TrendingDown;
  const colors = neutral ? "bg-base text-text-secondary" : positive ? "bg-positive-soft text-positive" : "bg-negative-soft text-negative";
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold tabular-nums ${large ? "text-sm" : "text-[11px]"} ${colors}`}><Icon size={large ? 15 : 12} strokeWidth={2.5}/>{Math.abs(value).toFixed(1)}%</span>;
}

function MultiFilter({ name, options, selected, onChange }) {
  const [open, setOpen] = useState(false); const [query, setQuery] = useState("");
  const visible = options.filter((v) => String(v.label).toLowerCase().includes(query.toLowerCase()));
  return <div className="relative min-w-[150px]">
    <button type="button" onClick={() => setOpen(!open)} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">{display(name)} <span className="float-right text-text-muted">{selected.length ? `${selected.length} selected` : "All"}</span></button>
    {open && <div className="absolute z-30 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl">
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs" />
      <div className="mb-2 flex justify-between text-xs"><button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((o) => String(o.value))])])}>Select all</button><button type="button" onClick={() => onChange([])}>Clear</button></div>
      {visible.map((opt) => <label key={opt.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs"><input type="checkbox" checked={selected.includes(String(opt.value))} onChange={() => onChange(selected.includes(String(opt.value)) ? selected.filter((v) => v !== String(opt.value)) : [...selected, String(opt.value)])} />{opt.label}</label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs text-white" onClick={() => setOpen(false)}>Done</button>
    </div>}
  </div>;
}

export default function TertiarySummary() {
  const [config, setConfig] = useState(null), [filters, setFilters] = useState({}), [page, setPage] = useState("brand");
  const [payload, setPayload] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key: "label", direction: 1 });
  const scrollRef = useRef(null); const [scrollTop, setScrollTop] = useState(0); const rowHeight = 38;

  useEffect(() => { setScrollTop(0); if (scrollRef.current) scrollRef.current.scrollTop = 0; }, [filters, page, search]);
  useEffect(() => { let active = true; const t = setTimeout(() => tertiaryApi.summaryConfig(filters).then((data) => active && setConfig(data)).catch((e) => active && setError(e.message)), 80); return () => { active = false; clearTimeout(t); }; }, [filters]);
  useEffect(() => { let active = true; const t = setTimeout(() => { setBusy(true); tertiaryApi.summary(page, filters).then((data) => { if (active) { setPayload(data); setError(""); } }).catch((e) => active && setError(e.message)).finally(() => active && setBusy(false)); }, 80); return () => { active = false; clearTimeout(t); }; }, [page, filters]);

  const anchor = payload?.anchor ?? 0;
  const currentPartial = Boolean(payload?.current_fy_partial && anchor === payload?.current_fy);
  const years = [...(payload?.years || [])].sort((a, b) => currentPartial ? (a === anchor ? 1 : b === anchor ? -1 : b - a) : (a === anchor ? -1 : b === anchor ? 1 : a <= anchor && b <= anchor ? b - a : a <= anchor ? -1 : b <= anchor ? 1 : a - b));
  const baseYear = years[years.indexOf(anchor) + 1];
  const dataRows = payload?.rows || [];
  const rows = useMemo(() => dataRows.filter((r) => r.label.toLowerCase().includes(search.toLowerCase())).sort((a, b) => {
    if (sort.key === "label") return a.label.localeCompare(b.label) * sort.direction;
    const av = a.years[String(sort.key)]?.val || 0, bv = b.years[String(sort.key)]?.val || 0;
    return (av - bv) * sort.direction;
  }), [payload, search, sort]);
  const total = payload?.totals?.[String(anchor)] || { qty: 0, val: 0 };
  const previous = currentPartial ? { qty: total.lfytd_qty || 0, val: total.lfytd_val || 0 } : (payload?.totals?.[String(baseYear)] || { qty: 0, val: 0 });
  const top = [...dataRows].sort((a, b) => (b.years[String(anchor)]?.val || 0) - (a.years[String(anchor)]?.val || 0))[0];

  // Show complete years first. Compare the current partial FY to the prior completed FY's LFYTD.
  const previousCompletedYear = currentPartial ? anchor - 1 : null;
  const groups = years.flatMap((y) => {
    const isPreviousCompleted = currentPartial && y === previousCompletedYear;
    const cols = isPreviousCompleted ? ["qty", "lfytd_qty", "val", "lfytd_val"] : ["qty", "val"];
    const group = [{ type: "year", year: y, cols }];
    if (isPreviousCompleted) group.push({ type: "growth", year: anchor, base: y, mode: "lfytd", cols: ["qty", "val"] });
    else if (!currentPartial && years.includes(y - 1)) group.push({ type: "growth", year: y, base: y - 1, cols: ["qty", "val"] });
    else if (currentPartial && y !== anchor && years.includes(y - 1)) group.push({ type: "growth", year: y, base: y - 1, cols: ["qty", "val"] });
    return group;
  });
  const grandGrowth = (field) => pct(total[field] || 0, previous[field] || 0);
  const start = Math.min(Math.max(0, Math.floor(scrollTop / rowHeight) - 8), Math.max(0, rows.length - 42)); const end = Math.min(rows.length, start + 42); const visibleRows = rows.slice(start, end); const columnCount = 1 + groups.reduce((n, g) => n + g.cols.length, 0);
  const spark = (field) => [...(payload?.years || [])].sort((a,b)=>a-b).map((y)=>({value:payload?.totals?.[String(y)]?.[field]||0}));

  const exportExcel = () => {
    const h1 = [display(page)], h2 = [""], h3 = [""];
    groups.forEach((g) => {
      if (g.type === "year") {
        h1.push(fyName(g.year), ...Array(g.cols.length - 1).fill(""));
        if (g.cols.length === 4) { h2.push("QTY", "", "VAL", ""); h3.push("FY FULL", "LFYTD", "FY FULL", "LFYTD"); }
        else { h2.push("QTY", "VAL"); h3.push("", ""); }
      } else { h1.push("GROWTH", ""); h2.push("QTY", "VAL"); h3.push("", ""); }
    });
    const body = rows.map((r) => [r.label, ...groups.flatMap((g) => g.type === "year" ? g.cols.map((c) => r.years[String(g.year)]?.[c] || 0) : ["qty", "val"].map((m) => { const d = r.years[String(g.year)] || {}, b = r.years[String(g.base)] || {}; const base = g.mode === "lfytd" ? b[`lfytd_${m}`] : b[m]; return pct(d[m] || 0, base || 0) ?? "New"; }))]);
    const gt = ["Grand Total", ...groups.flatMap((g) => g.type === "year" ? g.cols.map((c) => payload?.totals?.[String(g.year)]?.[c] || 0) : ["qty", "val"].map((m) => { const d = payload?.totals?.[String(g.year)] || {}, b = payload?.totals?.[String(g.base)] || {}; const base = g.mode === "lfytd" ? b[`lfytd_${m}`] : b[m]; return pct(d[m] || 0, base || 0) ?? "New"; }))];
    const sheet = XLSX.utils.aoa_to_sheet([h1, h2, h3, ...body, gt]);
    let col = 1; groups.forEach((g) => { const span = g.cols.length; sheet["!merges"] ||= []; sheet["!merges"].push({ s: { r: 0, c: col }, e: { r: 0, c: col + span - 1 } }); if (g.type === "year") { if (span === 2) { sheet["!merges"].push({ s: { r: 1, c: col }, e: { r: 2, c: col } }, { s: { r: 1, c: col + 1 }, e: { r: 2, c: col + 1 } }); } else { sheet["!merges"].push({ s: { r: 1, c: col }, e: { r: 1, c: col + 1 } }, { s: { r: 1, c: col + 2 }, e: { r: 1, c: col + 3 } }); } } else sheet["!merges"].push({ s: { r: 1, c: col }, e: { r: 2, c: col } }, { s: { r: 1, c: col + 1 }, e: { r: 2, c: col + 1 } }); col += span; });
    sheet["!merges"].push({ s: { r: 0, c: 0 }, e: { r: 2, c: 0 } }); sheet["!cols"] = [{ wch: 28 }, ...Array(groups.reduce((n, g) => n + g.cols.length, 0)).fill({ wch: 14 })];
    const book = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(book, sheet, "Tertiary Summary"); XLSX.writeFile(book, "tertiary-sales-summary.xlsx");
  };

  const setFilter = (key, values) => setFilters((old) => ({ ...old, [key]: values }));
  return <main className="space-y-5 p-5 lg:p-7">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[.18em] text-accent">Retail sell-out · Levi’s</p><h1 className="mt-1 font-display text-2xl font-bold text-text-primary">Tertiary Sales Summary</h1><p className="mt-1 text-sm text-text-muted">Fiscal year comparison across stores, brands and markets</p></div><button onClick={exportExcel} disabled={!payload} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><Download size={16}/>Export Excel</button></div>
    <section className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3"><span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14}/>Filters</span>{config && filterOrder.filter((f) => f === "month" || f === "fy" || config.fields[f]).map((name) => {
      const options = name === "month" ? config.months : name === "fy" ? (config.year_options || config.years).map((y) => ({ value: y, label: fyName(y) })) : (config.options[name] || []).map((v) => ({ value: v, label: v }));
      return <MultiFilter key={name} name={name} options={options} selected={(filters[name] || []).map(String)} onChange={(v) => setFilter(name, v)}/>;
    })}</section>
    <nav className="flex gap-1 overflow-x-auto border-b border-border">{pages.filter(([k]) => k === "brand" || config?.fields[k]).map(([k, label]) => <button key={k} onClick={() => setPage(k)} className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold ${page === k ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary"}`}>{label}</button>)}</nav>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Total quantity", fmt.format(total.qty)], ["Total value", `₹${fmt.format(total.val)}`], ["Quantity growth", grandGrowth("qty")], ["Value growth", grandGrowth("val")], ["Top performer", top?.label || "—"]].map(([label, val]) => <div key={label} className="rounded-xl border border-border bg-surface p-4"><p className="text-xs font-medium text-text-muted">{label}</p><p className="mt-2 truncate font-display text-xl font-bold text-text-primary">{typeof val === "number" ? <GrowthBadge value={val} large /> : val}</p>{(label === "Total quantity" || label === "Total value") && <div className="mt-2 h-8 w-28"><ResponsiveContainer width="100%" height="100%"><LineChart data={spark(label === "Total quantity" ? "qty" : "val")}><Line type="monotone" dataKey="value" stroke="var(--color-accent)" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>}{label.includes("growth") && <p className="mt-1 text-[11px] text-text-muted">vs {currentPartial ? `${fyName(previousCompletedYear)} LFYTD` : baseYear ? fyName(baseYear) : "previous FY"}</p>}</div>)}</section>
    <section className="overflow-hidden rounded-xl border border-border bg-surface"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4"><div><h2 className="font-display font-semibold text-text-primary">{pages.find(([k]) => k === page)?.[1]}</h2><p className="mt-1 text-xs text-text-muted">{rows.length.toLocaleString("en-IN")} rows · {anchor ? fyName(anchor) : ""} anchor year</p></div><div className="relative"><Search size={15} className="absolute left-3 top-2.5 text-text-muted"/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search rows" className="rounded-lg border border-border bg-base py-2 pl-9 pr-3 text-sm"/></div></div>
      {error && <p className="p-4 text-sm text-negative">{error}</p>}<div ref={scrollRef} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)} className="max-h-[62vh] overflow-auto"><table className="w-full min-w-max border-separate border-spacing-0 text-right text-xs"><thead className="sticky top-0 z-10 bg-base text-text-secondary"><tr><th rowSpan="3" onClick={() => setSort((s) => ({ key: "label", direction: -s.direction }))} className="sticky left-0 z-20 min-w-48 cursor-pointer border-b border-r border-border bg-base px-4 py-3 text-left uppercase">{display(page)} <ArrowUpDown size={12} className="inline"/></th>{groups.map((g, i) => <th key={i} colSpan={g.cols.length} className="border-b border-border px-3 py-2 text-center">{g.type === "year" ? <button onClick={() => setSort({ key: g.year, direction: -sort.direction })}>{fyName(g.year)}</button> : "GROWTH"}</th>)}</tr><tr>{groups.flatMap((g, i) => g.type === "growth" ? [<th key={`${i}gq`} rowSpan="2" className="border-b border-border px-3 py-2">QTY</th>, <th key={`${i}gv`} rowSpan="2" className="border-b border-border px-3 py-2">VAL</th>] : g.cols.length === 4 ? [<th key={`${i}q`} colSpan="2" className="border-b border-border px-3 py-2">QTY</th>, <th key={`${i}v`} colSpan="2" className="border-b border-border px-3 py-2">VAL</th>] : [<th key={`${i}q`} rowSpan="2" className="border-b border-border px-3 py-2">QTY</th>, <th key={`${i}v`} rowSpan="2" className="border-b border-border px-3 py-2">VAL</th>])}</tr><tr>{groups.flatMap((g, i) => g.type === "year" && g.cols.length === 4 ? [<th key={`${i}qf`} className="border-b border-border px-3 py-2">FY FULL</th>, <th key={`${i}ql`} className="border-b border-border px-3 py-2">LFYTD</th>, <th key={`${i}vf`} className="border-b border-border px-3 py-2">FY FULL</th>, <th key={`${i}vl`} className="border-b border-border px-3 py-2">LFYTD</th>] : [])}</tr></thead><tbody>{start > 0 && <tr aria-hidden="true"><td colSpan={columnCount} style={{ height: start * rowHeight, padding: 0, border: 0 }} /></tr>}{visibleRows.map((r) => <tr key={r.label} className="h-[38px] odd:bg-surface even:bg-base/60 hover:bg-accent-soft/50"><th className="sticky left-0 border-b border-r border-border bg-inherit px-4 py-2 text-left font-medium text-text-primary">{r.label}</th>{groups.flatMap((g, i) => g.type === "year" ? g.cols.map((c) => { const v = r.years[String(g.year)]?.[c] || 0; return <td key={`${i}-${c}`} className="border-b border-border px-3 py-2 tabular-nums">{c.includes("val") ? "₹" : ""}{fmt.format(v)}</td>; }) : ["qty", "val"].map((m) => { const base = g.mode === "lfytd" ? r.years[String(g.base)]?.[`lfytd_${m}`] : r.years[String(g.base)]?.[m]; const v = pct(r.years[String(g.year)]?.[m] || 0, base || 0); return <td key={`${i}-${m}`} className={`border-b border-border px-3 py-2 font-semibold tabular-nums ${v == null ? "text-text-muted" : v >= 0 ? "text-positive" : "text-negative"}`}><GrowthBadge value={v}/></td>; }))}</tr>)}{end < rows.length && <tr aria-hidden="true"><td colSpan={columnCount} style={{ height: (rows.length - end) * rowHeight, padding: 0, border: 0 }} /></tr>}<tr className="sticky bottom-0 z-[5] bg-accent-soft font-bold text-text-primary"><th className="sticky left-0 bg-accent-soft px-4 py-3 text-left">Grand Total</th>{groups.flatMap((g) => g.type === "year" ? g.cols.map((c) => { const v = payload?.totals?.[String(g.year)]?.[c] || 0; return <td key={`${g.year}-${c}`} className="px-3 py-3">{c.includes("val") ? "₹" : ""}{fmt.format(v)}</td>; }) : ["qty", "val"].map((m) => { const base = g.mode === "lfytd" ? payload?.totals?.[String(g.base)]?.[`lfytd_${m}`] : payload?.totals?.[String(g.base)]?.[m]; const v = pct(payload?.totals?.[String(g.year)]?.[m] || 0, base || 0); return <td key={`${g.year}-gt-${m}`} className="px-3 py-3"><GrowthBadge value={v}/></td>; }))}</tr></tbody></table></div>{busy && <div className="border-t border-border px-4 py-2 text-xs text-text-muted">Updating report…</div>}</section>
  </main>;
}
