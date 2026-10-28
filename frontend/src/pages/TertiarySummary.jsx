import { useEffect, useRef, useState } from "react";
import { Boxes, ChevronDown, IndianRupee, Search, SlidersHorizontal } from "lucide-react";
import { tertiaryApi } from "../api/client";

const pages = [["brand", "Brands comparison"], ["store", "Brand-store performance"], ["department", "Department-wise performance"], ["state", "State-wise performance"], ["group", "Group-wise performance"]];
const filterOrder = ["store", "department", "store_status", "store_type", "brand", "state", "group", "month", "fy"];
const display = (s) => s.replaceAll("_", " ").split(" ").map((word) => word ? word[0].toUpperCase() + word.slice(1) : word).join(" ");
const fmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const pct = (a, b) => !b ? null : (a - b) / Math.abs(b) * 100;
const fyName = (y) => "FY" + y + "-" + String(y + 1).slice(-2);

function MultiFilter({ name, options, selected, onChange, open, onToggle, onClose }) {
  const [query, setQuery] = useState("");
  const visible = options.filter((v) => String(v.label).toLowerCase().includes(query.toLowerCase()));
  return <div className="relative min-w-[150px]">
    <button type="button" onClick={onToggle} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs text-text-primary">{display(name)} <span className="float-right text-text-muted">{selected.length ? selected.length + " selected" : "All"}</span></button>
    {open && <div className={"absolute z-30 mt-1 max-h-72 w-64 overflow-auto rounded-xl border border-border bg-surface p-3 shadow-xl " + (name === "month" || name === "fy" ? "right-0" : "left-0")}>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" className="mb-2 w-full rounded border border-border bg-base px-2 py-1.5 text-xs" />
      <div className="mb-2 flex justify-between text-xs"><button type="button" onClick={() => onChange([...new Set([...selected, ...visible.map((o) => String(o.value))])])}>Select all</button><button type="button" onClick={() => onChange([])}>Clear</button></div>
      {visible.map((opt) => <label key={opt.value} className="flex cursor-pointer items-center gap-2 py-1 text-xs"><input type="checkbox" checked={selected.includes(String(opt.value))} onChange={() => onChange(selected.includes(String(opt.value)) ? selected.filter((v) => v !== String(opt.value)) : [...selected, String(opt.value)])} />{opt.label}</label>)}
      <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1 text-xs text-white" onClick={onClose}>Done</button>
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

function HistoryTable({ title, metric, rows, total, growth, rangeLabel }) {
  const isQuantity = metric === "qty";
  const label = isQuantity ? "TOTAL QUANTITY (VOLUME)" : "TOTAL VALUE (REVENUE)";
  return <article className="rounded-xl border border-border bg-base/40 p-4 sm:p-5">
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2.5"><span className={"flex h-8 w-8 shrink-0 items-center justify-center rounded-lg " + (isQuantity ? "bg-accent-soft text-accent" : "bg-positive-soft text-positive")}>{isQuantity ? <Boxes size={16}/> : <IndianRupee size={16}/>}</span><h3 className="truncate text-xs font-bold tracking-wide text-text-secondary">{label}</h3></div>
      <span className={"shrink-0 rounded border px-2 py-1 text-[10px] font-semibold " + (isQuantity ? "border-accent/30 text-accent" : "border-positive/30 text-positive")}>{isQuantity ? "Unit Basis" : <>INR (&#8377;)</>}</span>
    </div>
    <div className="mb-4 mt-2 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Overall total</p><p className="font-display text-3xl font-bold tracking-tight tabular-nums text-text-primary">{!isQuantity && <span>&#8377;</span>}{fmt.format(total || 0)}</p><p className="mt-0.5 text-[11px] text-text-muted">Across {rangeLabel}</p></div><div className="pb-1 text-right"><GrowthValue value={growth} pill/><p className="mt-1 text-[10px] text-text-muted">Current FY growth</p></div></div>
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

function SortControl({ label, descriptor, sortId, sorting, openSort, setOpenSort, onSort, className = "" }) {
  const active = sorting?.id === sortId;
  const open = openSort === sortId;
  return <div className={"relative inline-flex items-center " + className}>
    <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpenSort(open ? null : sortId)} className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-card-hover hover:text-accent focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent">
      <span>{label}</span><ChevronDown size={12} className={active ? "text-accent" : "text-text-muted"}/>{active && <span className="text-[9px] text-accent">{sorting.direction === "asc" ? "ASC" : "DESC"}</span>}
    </button>
    {open && <div role="menu" className="absolute left-0 top-full z-40 mt-1 min-w-48 rounded-lg border border-border bg-surface p-1 text-left normal-case shadow-xl">
      <button type="button" role="menuitem" onClick={() => onSort(descriptor, sortId, "asc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{descriptor.type === "label" ? "Sort A to Z" : "Sort Smallest to Largest"}</button>
      <button type="button" role="menuitem" onClick={() => onSort(descriptor, sortId, "desc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{descriptor.type === "label" ? "Sort Z to A" : "Sort Largest to Smallest"}</button>
    </div>}
  </div>;
}

function ComparisonTable({ dimension, rows, groups, totals, anchor, currentPartial, search, setSearch }) {
  const [sorting, setSorting] = useState(null);
  const [openSort, setOpenSort] = useState(null);
  const columnCount = 1 + groups.reduce((count, group) => count + group.cols.length, 0);
  const onSort = (descriptor, id, direction) => { setSorting({ ...descriptor, id, direction }); setOpenSort(null); };
  const sortValue = (row, descriptor) => {
    if (descriptor.type === "label") return row.label;
    if (descriptor.type === "year") return row.years[String(descriptor.year)]?.[descriptor.column] ?? 0;
    const group = descriptor.group;
    const current = row.years[String(group.year)]?.[descriptor.metric] || 0;
    const baseRow = row.years[String(group.base)] || {};
    const base = group.mode === "lfytd" ? baseRow["lfytd_" + descriptor.metric] : baseRow[descriptor.metric];
    return pct(current, base || 0);
  };
  const sortedRows = sorting ? [...rows].sort((a, b) => {
    const av = sortValue(a, sorting); const bv = sortValue(b, sorting);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const comparison = typeof av === "string" ? av.localeCompare(bv, undefined, { sensitivity: "base", numeric: true }) : Number(av) - Number(bv);
    return sorting.direction === "asc" ? comparison : -comparison;
  }) : rows;
  const control = (label, descriptor, id, extra = "") => <SortControl label={label} descriptor={descriptor} sortId={id} sorting={sorting} openSort={openSort} setOpenSort={setOpenSort} onSort={onSort} className={extra}/>;
  const renderCells = (row) => groups.flatMap((group, groupIndex) => {
    if (group.type === "year") return group.cols.map((column) => {
      const value = row.years[String(group.year)]?.[column] || 0;
      const denominator = totals[String(group.year)]?.[column] || 0;
      const share = denominator > 0 ? (value / denominator) * 100 : null;
      return <td key={groupIndex + "-" + column} className="border-b border-border px-3 py-2 tabular-nums text-text-primary"><span>{column.includes("val") ? "\u20B9" : ""}{fmt.format(value)}</span><span className="ml-1 whitespace-nowrap text-text-muted">{share == null ? "" : "| " + share.toFixed(1) + "%"}</span></td>;
    });
    return ["qty", "val"].map((metric) => {
      const baseRow = row.years[String(group.base)] || {};
      const base = group.mode === "lfytd" ? baseRow["lfytd_" + metric] : baseRow[metric];
      const value = pct(row.years[String(group.year)]?.[metric] || 0, base || 0);
      return <td key={groupIndex + "-" + metric} className="border-b border-border px-3 py-2"><GrowthValue value={value}/></td>;
    });
  });


  return <section className="overflow-hidden rounded-xl border border-border bg-surface">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4"><div><h2 className="font-display font-semibold text-text-primary">{dimension} comparison</h2><p className="mt-1 text-xs text-text-muted">{rows.length.toLocaleString("en-IN")} rows | fiscal years in chronological order{sorting ? " | sorted " + (sorting.direction === "asc" ? "ascending" : "descending") : ""}</p></div><div className="relative"><Search size={15} className="absolute left-3 top-2.5 text-text-muted"/><input aria-label="Search comparison rows" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={"Search " + dimension.toLowerCase() + " rows"} className="rounded-lg border border-border bg-base py-2 pl-9 pr-3 text-sm text-text-primary"/></div></header>
    <div className="max-h-[62vh] overflow-auto"><table className="w-full min-w-max border-separate border-spacing-0 text-right text-xs">
      <thead className="sticky top-0 z-10 bg-base text-text-secondary">
        <tr><th rowSpan="3" className="sticky left-0 z-20 min-w-48 border-b border-r border-border bg-base px-4 py-3 text-left uppercase">{control(dimension, { type: "label" }, "label")}</th>{groups.map((group, index) => <th key={index} colSpan={group.cols.length} className="border-b border-border px-3 py-2 text-center">{group.type === "year" ? fyName(group.year) + (currentPartial && group.year === anchor ? " (CURRENT YTD)" : "") : "GROWTH"}</th>)}</tr>
        <tr>{groups.flatMap((group, index) => {
          if (group.type === "growth") return [<th key={index + "gq"} rowSpan="2" className="border-b border-border px-3 py-2">{control("QTY", { type: "growth", group, metric: "qty" }, index + "-growth-qty")}</th>, <th key={index + "gv"} rowSpan="2" className="border-b border-border px-3 py-2">{control("VAL", { type: "growth", group, metric: "val" }, index + "-growth-val")}</th>];
          if (group.cols.length === 4) return [<th key={index + "q"} colSpan="2" className="border-b border-border px-3 py-2">QTY</th>, <th key={index + "v"} colSpan="2" className="border-b border-border px-3 py-2">VAL</th>];
          return [<th key={index + "q"} rowSpan="2" className="border-b border-border px-3 py-2">{control("QTY", { type: "year", year: group.year, column: group.cols[0] }, index + "-" + group.cols[0])}</th>, <th key={index + "v"} rowSpan="2" className="border-b border-border px-3 py-2">{control("VAL", { type: "year", year: group.year, column: group.cols[1] }, index + "-" + group.cols[1])}</th>];
        })}</tr>
        <tr>{groups.flatMap((group, index) => group.type === "year" && group.cols.length === 4 ? [<th key={index + "qf"} className="border-b border-border px-3 py-2">{control("FY FULL", { type: "year", year: group.year, column: "qty" }, index + "-qty")}</th>, <th key={index + "ql"} className="border-b border-border px-3 py-2">{control("LFYTD", { type: "year", year: group.year, column: "lfytd_qty" }, index + "-lfytd_qty")}</th>, <th key={index + "vf"} className="border-b border-border px-3 py-2">{control("FY FULL", { type: "year", year: group.year, column: "val" }, index + "-val")}</th>, <th key={index + "vl"} className="border-b border-border px-3 py-2">{control("LFYTD", { type: "year", year: group.year, column: "lfytd_val" }, index + "-lfytd_val")}</th>] : [])}</tr>
      </thead>
      <tbody>{sortedRows.length ? sortedRows.map((row) => <tr key={row.label} className="h-[38px] odd:bg-surface even:bg-base/60 hover:bg-accent-soft/50"><th className="sticky left-0 border-b border-r border-border bg-inherit px-4 py-2 text-left font-medium text-text-primary">{row.label}</th>{renderCells(row)}</tr>) : <tr><td colSpan={columnCount} className="px-4 py-8 text-center text-sm text-text-muted">No comparison rows match these filters.</td></tr>}</tbody>
      <tfoot><tr className="border-t-2 border-accent bg-surface font-bold text-text-primary"><th className="border-t-2 border-accent px-4 py-3 text-left">Grand Total</th>{groups.flatMap((group, groupIndex) => group.type === "year" ? group.cols.map((column) => { const value = totals[String(group.year)]?.[column] || 0; return <td key={groupIndex + "-" + column} className="border-t-2 border-accent px-3 py-3 tabular-nums"><span>{column.includes("val") && <span>&#8377;</span>}{fmt.format(value)}</span>{value > 0 && <span className="ml-1 whitespace-nowrap text-text-muted">| 100.0%</span>}</td>; }) : ["qty", "val"].map((metric) => { const baseRow = totals[String(group.base)] || {}; const base = group.mode === "lfytd" ? baseRow["lfytd_" + metric] : baseRow[metric]; const value = pct(totals[String(group.year)]?.[metric] || 0, base || 0); return <td key={groupIndex + "-" + metric} className="border-t-2 border-accent px-3 py-3"><GrowthValue value={value}/></td>; }))}</tr></tfoot>
    </table></div>
  </section>;
}

export default function TertiarySummary() {
  const [config, setConfig] = useState(null);
  const [filters, setFilters] = useState({});
  const [page, setPage] = useState("brand");
  const [payload, setPayload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [openFilter, setOpenFilter] = useState(null);
  const filterPanelRef = useRef(null);

  useEffect(() => {
    if (!openFilter) return undefined;
    const closeOnOutside = (event) => { if (!filterPanelRef.current?.contains(event.target)) setOpenFilter(null); };
    const closeOnEscape = (event) => { if (event.key === "Escape") setOpenFilter(null); };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("pointerdown", closeOnOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, [openFilter]);

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
  const chronologicalYears = [...(payload?.years || [])].filter((year) => anchor == null || year <= anchor).sort((a, b) => a - b);
  const overallTotals = chronologicalYears.reduce((sum, year) => ({ qty: sum.qty + (totals[String(year)]?.qty || 0), val: sum.val + (totals[String(year)]?.val || 0) }), { qty: 0, val: 0 });
  const overallRange = chronologicalYears.length ? fyName(chronologicalYears[0]) + " to " + fyName(chronologicalYears[chronologicalYears.length - 1]) : "available fiscal years";
  const comparisonGroups = chronologicalYears.flatMap((year, index) => {
    const cols = currentPartial && year === anchor - 1 ? ["qty", "lfytd_qty", "val", "lfytd_val"] : ["qty", "val"];
    const yearGroup = { type: "year", year, cols };
    if (index === 0) return [yearGroup];
    const isCurrentYtd = currentPartial && year === anchor;
    return [yearGroup, { type: "growth", year, base: year - 1, mode: isCurrentYtd ? "lfytd" : "full", cols: ["qty", "val"] }];
  });
  const dataRows = (payload?.rows || []).filter((row) => String(row.label).toLowerCase().includes(search.toLowerCase()));
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
    <section ref={filterPanelRef} className="flex flex-wrap gap-2 rounded-xl border border-border bg-surface p-3"><span className="flex items-center gap-1 self-center px-2 text-xs font-bold uppercase text-text-muted"><SlidersHorizontal size={14}/>Filters</span>{config && filterOrder.filter((f) => f === "month" || f === "fy" || config.fields[f]).map((name) => {
      const options = name === "month" ? config.months : name === "fy" ? (config.year_options || config.years).map((y) => ({ value: y, label: fyName(y) })) : (config.options[name] || []).map((v) => ({ value: v, label: v }));
      return <MultiFilter key={name} name={name} options={options} selected={(filters[name] || []).map(String)} onChange={(v) => setFilter(name, v)} open={openFilter === name} onToggle={() => setOpenFilter((current) => current === name ? null : name)} onClose={() => setOpenFilter(null)} />;
    })}</section>
    <nav aria-label="Summary dimensions" className="flex gap-1 overflow-x-auto border-b border-border">{pages.filter(([key]) => key === "brand" || config?.fields[key]).map(([key, label]) => <button key={key} type="button" onClick={() => setPage(key)} className={"whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold " + (page === key ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}>{label}</button>)}</nav>
    <section className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5"><div><h2 className="font-display text-base font-semibold text-text-primary">Historical Performance Consolidated</h2><p className="mt-1 text-xs text-text-muted">{anchor != null ? fyName(anchor) + (currentPartial ? " current year to date" : " selected anchor year") : "Select filters to view fiscal-year totals"}</p></div>{busy && <span role="status" className="text-xs text-text-muted">Updating performance...</span>}</div>
      {error && <p role="alert" className="border-b border-border px-4 py-3 text-sm text-negative">{error}</p>}
      <div className="grid gap-4 p-4 sm:p-5 xl:grid-cols-2"><HistoryTable title="QTY" metric="qty" rows={historicalRows} total={overallTotals.qty} growth={historicalRows[0]?.qtyGrowth} rangeLabel={overallRange}/><HistoryTable title="VALUE" metric="val" rows={historicalRows} total={overallTotals.val} growth={historicalRows[0]?.valGrowth} rangeLabel={overallRange}/></div>
    </section>
    <ComparisonTable dimension={display(page)} rows={dataRows} groups={comparisonGroups} totals={totals} anchor={anchor} currentPartial={currentPartial} search={search} setSearch={setSearch}/>
  </main>;
}
