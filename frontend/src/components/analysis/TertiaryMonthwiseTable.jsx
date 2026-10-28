import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown } from "lucide-react";
import { fmtNumber, fmtPct, fmtQty, fmtVal } from "../../utils/format";

const MEASURES = [
  { key: "qty", label: "QTY", format: fmtQty },
  { key: "mrp_value", label: "MRP VALUE", format: fmtVal },
  { key: "discount", label: "DISCOUNT", format: fmtVal },
  { key: "discount_pct", label: "DISCOUNT OUTFLOW %", format: fmtPct },
  { key: "bill_val", label: "BILL VALUE", format: fmtVal },
];

const HISTORY_MEASURES = [
  { key: "qty", label: "QTY", format: fmtQty },
  { key: "mrp_value", label: "MRP VALUE", format: fmtVal },
  { key: "discount", label: "DISCOUNT", format: fmtVal },
  { key: "discount_outflow", label: "DISCOUNT OUTFLOW %", format: fmtPct },
  { key: "val", label: "BILL VALUE", format: fmtVal },
];

const ratio = (discount, mrp) => mrp ? (discount / mrp) * 100 : null;
const changePct = (value, base) => base ? ((value - base) / Math.abs(base)) * 100 : null;
const fyLabel = (year) => "FY" + year + "-" + String(Number(year) + 1).slice(-2);
const pointChange = (value) => value == null ? "—" : (value > 0 ? "+" : "") + value.toFixed(1) + " pp";
const outflowTone = (value) => value == null ? "text-text-secondary" : value <= 0 ? "text-positive" : "text-negative";
const growthTone = (value) => value == null ? "text-text-secondary" : value >= 0 ? "text-positive" : "text-negative";

function SortHeader({ label, id, sorting, open, onToggle, onSort, align = "right" }) {
  const active = sorting?.id === id;
  const Icon = active ? (sorting.direction === "asc" ? ArrowUp : ArrowDown) : ChevronDown;
  return <div className={"relative flex items-center " + (align === "left" ? "justify-start" : "justify-end")}>
    <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={onToggle} className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-card-hover hover:text-accent">
      <span>{label}</span><Icon size={12} className={active ? "text-accent" : "text-text-muted"}/>
    </button>
    {open && <div role="menu" className="absolute left-0 top-full z-50 mt-1 min-w-48 rounded-lg border border-border bg-surface p-1 text-left normal-case shadow-xl">
      <button type="button" role="menuitem" onClick={() => onSort(id, "asc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{id === "month_order" || id === "label" ? "Sort A to Z" : "Sort Smallest to Largest"}</button>
      <button type="button" role="menuitem" onClick={() => onSort(id, "desc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{id === "month_order" || id === "label" ? "Sort Z to A" : "Sort Largest to Smallest"}</button>
    </div>}
  </div>;
}

export function summarizeMonthwise(rows = []) {
  const total = (key) => rows.reduce((sum, row) => sum + (Number(row[key]) || 0), 0);
  const hasCurrent = (key) => rows.some((row) => row[key] !== null && row[key] !== undefined);
  const qty = total("qty"); const qtyLy = total("qty_ly");
  const bill = total("bill_val"); const billLy = total("bill_val_ly");
  const mrp = total("mrp_value"); const discount = total("discount"); const discountLy = total("discount_ly"); const mrpLy = total("mrp_value_ly");
  const currentOutflow = ratio(discount, mrp); const previousOutflow = ratio(discountLy, mrpLy);
  return {
    qty: hasCurrent("qty") ? qty : null,
    qtyGrowth: hasCurrent("qty") ? changePct(qty, qtyLy) : null,
    bill: hasCurrent("bill_val") ? bill : null,
    billGrowth: hasCurrent("bill_val") ? changePct(bill, billLy) : null,
    discount: hasCurrent("discount") ? discount : null,
    discountOutflow: hasCurrent("discount") ? currentOutflow : null,
    discountOutflowPp: currentOutflow != null && previousOutflow != null ? currentOutflow - previousOutflow : null,
  };
}

function HistorySection({ title, headers, rows, type }) {
  return <article className="min-w-0 overflow-hidden rounded-xl border border-border bg-base/40">
    <h3 className="border-b border-border px-4 py-3 text-xs font-bold uppercase tracking-[.12em] text-text-secondary">{title}</h3>
    <div className="overflow-x-auto">
      <table className="w-full min-w-[380px] border-separate border-spacing-0 text-left text-xs">
        <thead className="bg-base text-[10px] font-semibold uppercase tracking-wide text-text-secondary"><tr>{headers.map((header) => <th key={header} className="px-3 py-2.5">{header}</th>)}</tr></thead>
        <tbody>{rows.length ? rows.map((row) => {
          const discount = type === "outflow";
          const change = row.change;
          return <tr key={row.key} className={row.current ? "bg-accent-soft/30" : "bg-surface"}>
            <th scope="row" className="whitespace-nowrap border-t border-border px-3 py-2.5 text-left font-medium text-text-primary">{row.label}</th>
            <td className="whitespace-nowrap border-t border-border px-3 py-2.5 text-right font-semibold tabular-nums text-text-primary">{row.value == null ? "—" : row.formatted}</td>
            <td className={"whitespace-nowrap border-t border-border px-3 py-2.5 text-right font-semibold tabular-nums " + (change == null ? "text-text-muted" : discount ? outflowTone(change) : growthTone(change))}>{discount ? pointChange(change) : change == null ? "—" : (change > 0 ? "+" : "") + change.toFixed(1) + "%"}</td>
          </tr>;
        }) : <tr><td colSpan="3" className="px-3 py-6 text-center text-text-muted">No historical data available.</td></tr>}</tbody>
      </table>
    </div>
  </article>;
}

function makeHistoryRows(payload, metric, selectedMonths, maxDate) {
  const anchor = payload?.anchor;
  if (anchor == null) return [];
  const years = (payload?.years || []).filter((year) => year <= anchor).sort((a, b) => b - a);
  const totals = payload?.totals || {};
  const currentPartial = Boolean(payload?.current_fy_partial && anchor === payload?.current_fy);
  const previousYear = anchor - 1;
  const current = totals[String(anchor)] || {};
  const previous = totals[String(previousYear)] || {};
  const selectedMonthCount = selectedMonths.length > 0 && selectedMonths.length < 12 ? selectedMonths.length : 0;
  let elapsedMonths = selectedMonthCount;
  if (!elapsedMonths && maxDate) {
    const month = new Date(maxDate).getUTCMonth() + 1;
    elapsedMonths = month >= 4 ? month - 3 : month + 9;
  }
  elapsedMonths = elapsedMonths || 12;

  const isOutflow = metric === "discount_outflow";
  const isQty = metric === "qty";
  const isValue = metric === "val";
  const read = (values, prefix = "") => {
    const value = values[prefix + metric];
    if (isOutflow) return value == null ? null : Number(value);
    return Number(value) || 0;
  };
  const fmt = (value) => {
    if (value == null) return "—";
    if (isOutflow) return fmtPct(value);
    if (isQty) return fmtNumber(value);
    if (isValue) return fmtVal(value);
    return fmtVal(value);
  };
  const apm = (value, divisor) => (isQty || isValue) && divisor ? value / divisor : value;
  const currentBase = currentPartial
    ? (selectedMonthCount ? read(previous) : read(previous, "lfytd_"))
    : read(previous);
  const averageMonths = selectedMonthCount || 12;
  const currentDivisor = currentPartial ? elapsedMonths : averageMonths;
  const currentValue = apm(read(current), currentDivisor);
  const comparisonValue = apm(currentBase, currentDivisor);
  const currentChange = isOutflow
    ? (currentValue == null || comparisonValue == null ? null : currentValue - comparisonValue)
    : changePct(currentValue, comparisonValue);

  const rows = [{
    key: "current-" + anchor,
    label: fyLabel(anchor),
    current: true,
    value: currentValue,
    formatted: fmt(currentValue),
    change: currentChange,
  }];

  if (currentPartial && totals[String(previousYear)]) {
    const previousValue = selectedMonthCount ? read(previous) : read(previous, "lfytd_");
    const adjustedPrevious = apm(previousValue, elapsedMonths);
    rows.push({
      key: "lfytd-" + previousYear,
      label: fyLabel(previousYear) + (selectedMonthCount ? " selected months" : " LFYTD"),
      value: adjustedPrevious,
      formatted: fmt(adjustedPrevious),
      change: null,
    });
  }

  years.filter((year) => year < anchor).forEach((year) => {
    const values = totals[String(year)] || {};
    const baseValues = totals[String(year - 1)] || {};
    const averageMonths = selectedMonthCount || 12;
    const value = apm(read(values), averageMonths);
    const base = apm(read(baseValues), averageMonths);
    const change = isOutflow
      ? (value == null || read(baseValues) == null ? null : value - read(baseValues))
      : changePct(value, base);
    rows.push({
      key: "full-" + year,
      label: fyLabel(year) + (currentPartial && year === previousYear ? " FULL" : ""),
      value,
      formatted: fmt(value),
      change,
    });
  });
  return rows;
}

export function MonthwiseHistoryKpis({ payload, selectedMonths = [], maxDate }) {
  const qtyRows = makeHistoryRows(payload, "qty", selectedMonths, maxDate);
  const valueRows = makeHistoryRows(payload, "val", selectedMonths, maxDate);
  const outflowRows = makeHistoryRows(payload, "discount_outflow", selectedMonths, maxDate);
  return <section className="overflow-hidden rounded-xl border border-border bg-surface">
    <header className="border-b border-border px-4 py-3 sm:px-5"><h2 className="font-display text-base font-semibold text-text-primary">Historical KPIs</h2><p className="mt-1 text-xs text-text-muted">Monthly averages and discount outflow for the selected filters</p></header>
    <div className="grid gap-3 p-3 sm:p-4 xl:grid-cols-3">
      <HistorySection title="APM QTY" headers={["FY", "APM", "GROWTH%"]} rows={qtyRows} type="growth"/>
      <HistorySection title="APM VAL" headers={["FY", "APM", "GROWTH%"]} rows={valueRows} type="growth"/>
      <HistorySection title="DISCOUNT OUTFLOW" headers={["FY", "DISCOUNT%", "P.P CHANGE"]} rows={outflowRows} type="outflow"/>
    </div>
  </section>;
}

function sortedRows(rows, sorting, getValue) {
  if (!sorting) return rows;
  return [...rows].sort((a, b) => {
    const av = getValue(a, sorting.id); const bv = getValue(b, sorting.id);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const comparison = typeof av === "string" ? av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" }) : Number(av) - Number(bv);
    return sorting.direction === "asc" ? comparison : -comparison;
  });
}

export function MonthwiseDimensionTable({ payload, dimension, search, setSearch }) {
  const [sorting, setSorting] = useState(null);
  const [openSort, setOpenSort] = useState(null);
  const anchor = payload?.anchor;
  const currentPartial = Boolean(payload?.current_fy_partial && anchor === payload?.current_fy);
  const years = (payload?.years || []).filter((year) => anchor == null || year <= anchor).sort((a, b) => a - b);
  const totals = payload?.totals || {};
  const allRows = payload?.rows || [];
  const rows = allRows.filter((row) => String(row.label).toLowerCase().includes(search.toLowerCase()));
  const changeId = (year, key) => "growth-" + year + "-" + key;
  const valueId = (year, mode, key) => "year-" + year + "-" + mode + "-" + key;

  const valueAt = (record, year, mode, metric) => {
    const values = record?.years?.[String(year)] || {};
    if (metric.key === "discount_outflow") return values[(mode === "lfytd" ? "lfytd_" : "") + "discount_outflow"];
    return values[(mode === "lfytd" ? "lfytd_" : "") + metric.key];
  };
  const totalAt = (year, mode, metric) => valueAt({ years: totals }, year, mode, metric);
  const growthAt = (record, year, metric) => {
    const values = record?.years?.[String(year)] || {};
    const baseMode = currentPartial && year === anchor ? "lfytd_" : "";
    const current = valueAt(record, year, "", metric);
    const previous = valueAt(record, year - 1, baseMode, metric);
    if (metric.key === "discount_outflow") return current == null || previous == null ? null : current - previous;
    return changePct(current, previous);
  };
  const totalGrowthAt = (year, metric) => growthAt({ years: totals }, year, metric);

  const groups = years.flatMap((year, index) => {
    const yearGroup = {
      type: "year",
      year,
      modes: currentPartial && year === anchor - 1 ? ["full", "lfytd"] : ["full"],
    };
    if (index === 0) return [yearGroup];
    return [yearGroup, { type: "growth", year }];
  });

  const getSortValue = (record, id) => {
    if (id === "label") return record.label;
    const parts = id.split("-");
    if (parts[0] === "year") return valueAt(record, Number(parts[1]), parts[2], HISTORY_MEASURES.find((metric) => metric.key === parts.slice(3).join("-")) || HISTORY_MEASURES[0]);
    if (parts[0] === "growth") {
      const metric = HISTORY_MEASURES.find((item) => item.key === parts.slice(2).join("-")) || HISTORY_MEASURES[0];
      return growthAt(record, Number(parts[1]), metric);
    }
    return null;
  };
  const displayedRows = useMemo(() => sortedRows(rows, sorting, getSortValue), [rows, sorting, anchor, currentPartial]);

  const changeSort = (id, direction) => { setSorting({ id, direction }); setOpenSort(null); };
  const header = (label, id, align = "right") => <SortHeader label={label} id={id} sorting={sorting} open={openSort === id} onToggle={() => setOpenSort((current) => current === id ? null : id)} onSort={changeSort} align={align}/>;
  const renderValue = (value, metric) => {
    if (value == null) return <span className="text-text-muted">—</span>;
    return <span className="whitespace-nowrap">{metric.format(value)}</span>;
  };
  const renderGrowth = (value, metric) => {
    if (value == null) return <span className="text-text-muted">—</span>;
    if (metric.key === "discount_outflow") return <span className={outflowTone(value)}>{pointChange(value)}</span>;
    return <span className={growthTone(value)}>{(value > 0 ? "+" : "") + value.toFixed(1) + "%"}</span>;
  };

  return <section className="overflow-hidden rounded-xl border border-border bg-surface">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
      <div><h2 className="font-display font-semibold text-text-primary">{dimension} analysis</h2><p className="mt-1 text-xs text-text-muted">{allRows.length.toLocaleString("en-IN")} rows | fiscal years in chronological order</p></div>
      <div><label className="sr-only" htmlFor="monthwise-dimension-search">Search {dimension.toLowerCase()} rows</label><input id="monthwise-dimension-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={"Search " + dimension.toLowerCase() + " rows"} className="rounded-lg border border-border bg-base px-3 py-2 text-sm text-text-primary"/></div>
    </header>
    <div className="overflow-auto">
      <table className="w-full min-w-max border-separate border-spacing-0 text-right text-xs">
        <thead className="sticky top-0 z-30 bg-base text-[10px] font-bold uppercase tracking-wide text-text-secondary">
          <tr>
            <th rowSpan="3" className="sticky left-0 z-40 min-w-[170px] border-b border-r border-border bg-base px-4 py-3 text-left">{header(dimension, "label", "left")}</th>
            {groups.map((group, index) => group.type === "year"
              ? <th key={"year-" + group.year} colSpan={group.modes.length * HISTORY_MEASURES.length} className="border-b border-border px-3 py-2.5 text-center">{fyLabel(group.year)}{currentPartial && group.year === anchor ? " (CURRENT YTD)" : ""}</th>
              : <th key={"growth-" + index} colSpan="3" rowSpan="3" className="border-b border-l-2 border-accent/40 bg-accent-soft/40 px-3 py-2.5 text-center text-accent">GROWTH</th>)}
          </tr>
          <tr>{groups.filter((group) => group.type === "year").flatMap((group) => group.modes.map((mode) => <th key={group.year + "-" + mode} colSpan={HISTORY_MEASURES.length} className="border-b border-border px-3 py-2 text-center">{mode === "lfytd" ? "LFYTD" : currentPartial && group.year === anchor ? "YEAR TO DATE" : "FY FULL"}</th>))}</tr>
          <tr>{groups.flatMap((group) => group.type === "year"
            ? group.modes.flatMap((mode) => HISTORY_MEASURES.map((metric) => <th key={group.year + "-" + mode + "-" + metric.key} className="border-b border-border px-3 py-2 text-right">{header(metric.label, valueId(group.year, mode, metric.key))}</th>))
            : [["QTY GROWTH %", "qty"], ["VALUE GROWTH %", "val"], ["DISCOUNT OUTFLOW P.P", "discount_outflow"]].map(([label, key]) => <th key={group.year + "-" + key} rowSpan="1" className="border-b border-l border-accent/20 bg-accent-soft/30 px-3 py-2 text-right">{header(label, changeId(group.year, key))}</th>))}</tr>
        </thead>
        <tbody>{displayedRows.length ? displayedRows.map((row, index) => <tr key={row.label} className={"hover:bg-accent-soft/30 " + (index % 2 ? "bg-base/40" : "bg-surface")}>
          <th scope="row" className="sticky left-0 z-20 border-b border-r border-border bg-surface px-4 py-2.5 text-left font-semibold text-text-primary">{row.label}</th>
          {groups.flatMap((group) => group.type === "year"
            ? group.modes.flatMap((mode) => HISTORY_MEASURES.map((metric) => <td key={group.year + "-" + mode + "-" + metric.key} className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums text-text-primary">{renderValue(valueAt(row, group.year, mode, metric), metric)}</td>))
            : [["qty", HISTORY_MEASURES[0]], ["val", HISTORY_MEASURES[4]], ["discount_outflow", HISTORY_MEASURES[3]]].map(([key, metric]) => <td key={group.year + "-" + key} className="whitespace-nowrap border-b border-l border-accent/20 px-3 py-2.5 text-right tabular-nums">{renderGrowth(growthAt(row, group.year, metric), metric)}</td>))}
        </tr>) : <tr><td colSpan={1 + groups.reduce((sum, group) => sum + (group.type === "year" ? group.modes.length * HISTORY_MEASURES.length : 3), 0)} className="px-4 py-10 text-center text-sm text-text-muted">No rows match these filters.</td></tr>}</tbody>
        {years.length > 0 && <tfoot><tr className="bg-surface font-bold text-text-primary">
          <th className="sticky left-0 z-20 border-t-2 border-r border-accent bg-surface px-4 py-3 text-left">Grand Total</th>
          {groups.flatMap((group) => group.type === "year"
            ? group.modes.flatMap((mode) => HISTORY_MEASURES.map((metric) => <td key={group.year + "-" + mode + "-" + metric.key} className="whitespace-nowrap border-t-2 border-accent px-3 py-3 text-right tabular-nums">{renderValue(totalAt(group.year, mode, metric), metric)}</td>))
            : [["qty", HISTORY_MEASURES[0]], ["val", HISTORY_MEASURES[4]], ["discount_outflow", HISTORY_MEASURES[3]]].map(([key, metric]) => <td key={group.year + "-" + key} className="whitespace-nowrap border-t-2 border-l border-accent/20 px-3 py-3 text-right tabular-nums">{renderGrowth(totalGrowthAt(group.year, metric), metric)}</td>))}
        </tr></tfoot>}
      </table>
    </div>
  </section>;
}

export default function TertiaryMonthwiseTable({ result }) {
  const [sorting, setSorting] = useState({ id: "month_order", direction: "asc" });
  const [openSort, setOpenSort] = useState(null);
  const rows = result?.rows || [];
  const sorted = useMemo(() => rows.map((row) => ({
    ...row,
    discount_pct_ly: ratio(row.discount_ly, row.mrp_value_ly),
    discount_outflow_pp: ratio(row.discount, row.mrp_value) == null || ratio(row.discount_ly, row.mrp_value_ly) == null
      ? null
      : ratio(row.discount, row.mrp_value) - ratio(row.discount_ly, row.mrp_value_ly),
  })), [rows]);
  const sortedRows = useMemo(() => sortedRowsByColumn(sorted, sorting), [sorted, sorting]);
  const totals = useMemo(() => summarizeMonthwise(rows), [rows]);
  const sum = (key) => rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  const fy = result?.fy_context || {};
  const changeSort = (id, direction) => { setSorting({ id, direction }); setOpenSort(null); };
  const header = (label, id, align) => <SortHeader label={label} id={id} sorting={sorting} open={openSort === id} onToggle={() => setOpenSort((current) => current === id ? null : id)} onSort={changeSort} align={align}/>;
  const renderMeasure = (row, measure, previous) => measure.key === "discount_pct"
    ? ratio(row[previous ? "discount_ly" : "discount"], row[previous ? "mrp_value_ly" : "mrp_value"])
    : row[previous ? measure.key + "_ly" : measure.key];
  const cell = (row, measure, previous, key) => {
    const value = renderMeasure(row, measure, previous);
    return <td key={key} className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums text-text-primary">{value == null ? <span className="text-text-muted">—</span> : measure.format(value)}</td>;
  };
  const growthCells = (row) => {
    const outflowChange = row.discount_outflow_pp;
    return <>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{row.qty_growth_pct == null ? <span className="text-text-muted">—</span> : <span className={growthTone(row.qty_growth_pct)}>{fmtPct(row.qty_growth_pct)}</span>}</td>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{row.bill_val_growth_pct == null ? <span className="text-text-muted">—</span> : <span className={growthTone(row.bill_val_growth_pct)}>{fmtPct(row.bill_val_growth_pct)}</span>}</td>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{outflowChange == null ? <span className="text-text-muted">—</span> : <span className={outflowTone(outflowChange)}>{pointChange(outflowChange)}</span>}</td>
    </>;
  };
  const totalGrowthQty = totals.qtyGrowth; const totalGrowthVal = totals.billGrowth;
  const totalOutflowPp = totals.discountOutflowPp;

  return <div className="overflow-hidden rounded-xl border border-border">
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1500px] border-separate border-spacing-0 text-xs">
        <thead className="sticky top-0 z-30 bg-base text-[10px] font-bold uppercase tracking-wide text-text-secondary">
          <tr>
            <th rowSpan="2" className="sticky left-0 z-40 w-[144px] min-w-[144px] border-b border-r border-border bg-base px-4 py-3 text-left">{header("MONTH", "month_order", "left")}</th>
            <th colSpan="5" className="border-b border-border px-3 py-2.5 text-center">{fy.last_fy_label || "LAST FY"}</th>
            <th rowSpan="2" aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"><span className="sr-only">Fiscal year section gap</span></th>
            <th colSpan="5" className="border-b border-border px-3 py-2.5 text-center">{fy.current_fy_label || "CURRENT FY"}</th>
            <th rowSpan="2" aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"><span className="sr-only">Growth section gap</span></th>
            <th colSpan="3" className="border-b border-l-2 border-accent/40 bg-accent-soft/40 px-3 py-2.5 text-center text-accent">GROWTH</th>
          </tr>
          <tr>
            {MEASURES.map((measure) => <th key={"last-" + measure.key} className="border-b border-border px-3 py-2 text-right">{header(measure.label, measure.key + "_ly")}</th>)}
            {MEASURES.map((measure) => <th key={"current-" + measure.key} className="border-b border-border px-3 py-2 text-right">{header(measure.label, measure.key)}</th>)}
            {[["QTY GROWTH %", "qty_growth_pct"], ["VALUE GROWTH %", "bill_val_growth_pct"], ["DISCOUNT OUTFLOW P.P", "discount_outflow_pp"]].map(([label, key]) => <th key={key} className="border-b border-l border-accent/20 bg-accent-soft/30 px-3 py-2 text-right">{header(label, key)}</th>)}
          </tr>
        </thead>
        <tbody>{sortedRows.length ? sortedRows.map((row, index) => <tr key={row.month} className={"hover:bg-accent-soft/30 " + (index % 2 ? "bg-base/40" : "bg-surface")}>
          <th scope="row" className="sticky left-0 z-20 w-[144px] min-w-[144px] border-b border-r border-border bg-surface px-4 py-2.5 text-left font-semibold uppercase text-text-primary shadow-md">{row.month}</th>
          {MEASURES.map((measure) => cell(row, measure, true, "last-" + measure.key))}
          <td aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"></td>
          {MEASURES.map((measure) => cell(row, measure, false, "current-" + measure.key))}
          <td aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"></td>
          {growthCells(row)}
        </tr>) : <tr><td colSpan="16" className="px-4 py-10 text-center text-sm text-text-muted">No monthwise data for these filters.</td></tr>}</tbody>
        {rows.length > 0 && <tfoot><tr className="bg-surface font-bold text-text-primary">
          <th scope="row" className="sticky left-0 z-20 w-[144px] min-w-[144px] border-t-2 border-r border-accent bg-surface px-4 py-3 text-left shadow-md">Grand Total</th>
          {MEASURES.map((measure) => {
            const value = measure.key === "discount_pct" ? ratio(sum("discount_ly"), sum("mrp_value_ly")) : (rows.some((row) => row[measure.key + "_ly"] != null) ? sum(measure.key + "_ly") : null);
            return <td key={"total-last-" + measure.key} className="whitespace-nowrap border-t-2 border-accent px-3 py-3 text-right tabular-nums">{value == null ? "—" : measure.format(value)}</td>;
          })}
          <td aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"></td>
          {MEASURES.map((measure) => {
            const value = measure.key === "discount_pct" ? (totals.discountOutflow == null ? null : ratio(sum("discount"), sum("mrp_value"))) : (rows.some((row) => row[measure.key] != null) ? sum(measure.key) : null);
            return <td key={"total-current-" + measure.key} className="whitespace-nowrap border-t-2 border-accent px-3 py-3 text-right tabular-nums">{value == null ? "—" : measure.format(value)}</td>;
          })}
          <td aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"></td>
          <td className={"whitespace-nowrap border-t-2 border-l border-accent/20 px-3 py-3 text-right " + growthTone(totalGrowthQty)}>{totalGrowthQty == null ? "—" : fmtPct(totalGrowthQty)}</td>
          <td className={"whitespace-nowrap border-t-2 border-l border-accent/20 px-3 py-3 text-right " + growthTone(totalGrowthVal)}>{totalGrowthVal == null ? "—" : fmtPct(totalGrowthVal)}</td>
          <td className={"whitespace-nowrap border-t-2 border-l border-accent/20 px-3 py-3 text-right " + outflowTone(totalOutflowPp)}>{pointChange(totalOutflowPp)}</td>
        </tr></tfoot>}
      </table>
    </div>
  </div>;
}

function sortedRowsByColumn(rows, sorting) {
  if (!sorting) return rows;
  return sortedRows(rows, sorting, (row, id) => row[id]);
}
