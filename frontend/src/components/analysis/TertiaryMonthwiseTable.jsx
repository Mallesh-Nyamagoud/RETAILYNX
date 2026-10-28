import { useMemo, useState } from "react";
import { fmtPct, fmtQty, fmtVal } from "../../utils/format";

const MEASURES = [
  { key: "qty", label: "QTY", format: fmtQty },
  { key: "mrp_value", label: "MRP VALUE", format: fmtVal },
  { key: "discount", label: "DISCOUNT", format: fmtVal },
  { key: "discount_pct", label: "DISCOUNT OUTFLOW %", format: fmtPct },
  { key: "bill_val", label: "BILL VALUE", format: fmtVal },
];
const ratio = (discount, mrp) => mrp ? (discount / mrp) * 100 : null;
const pointChange = (value) => value == null ? "N/A" : (value > 0 ? "+" : "") + value.toFixed(1) + " pp";

function SortHeader({ label, id, sorting, open, onToggle, onSort, align = "right" }) {
  const active = sorting?.id === id;
  return <div className={"relative flex items-center " + (align === "left" ? "justify-start" : "justify-end")}>
    <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={onToggle} className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-card-hover hover:text-accent">
      {label}<span className={active ? "text-accent" : "text-text-muted"}>{active ? (sorting.direction === "asc" ? "UP" : "DOWN") : "v"}</span>
    </button>
    {open && <div role="menu" className="absolute left-0 top-full z-40 mt-1 min-w-48 rounded-lg border border-border bg-surface p-1 text-left normal-case shadow-xl">
      <button type="button" role="menuitem" onClick={() => onSort(id, "asc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{id === "month_order" ? "Sort A to Z" : "Sort Smallest to Largest"}</button>
      <button type="button" role="menuitem" onClick={() => onSort(id, "desc")} className="block w-full rounded px-3 py-2 text-left text-xs text-text-primary hover:bg-card-hover">{id === "month_order" ? "Sort Z to A" : "Sort Largest to Smallest"}</button>
    </div>}
  </div>;
}

export function summarizeMonthwise(rows = []) {
  const total = (key) => rows.reduce((sum, row) => sum + (Number(row[key]) || 0), 0);
  const hasCurrent = (key) => rows.some((row) => row[key] !== null && row[key] !== undefined);
  const qty = total("qty"); const qtyLy = total("qty_ly");
  const bill = total("bill_val"); const billLy = total("bill_val_ly");
  const mrp = total("mrp_value"); const discount = total("discount"); const discountLy = total("discount_ly"); const mrpLy = total("mrp_value_ly");
  return {
    qty: hasCurrent("qty") ? qty : null,
    qtyGrowth: hasCurrent("qty") && qtyLy ? ((qty - qtyLy) / Math.abs(qtyLy)) * 100 : null,
    bill: hasCurrent("bill_val") ? bill : null,
    billGrowth: hasCurrent("bill_val") && billLy ? ((bill - billLy) / Math.abs(billLy)) * 100 : null,
    discount: hasCurrent("discount") ? discount : null,
    discountOutflow: hasCurrent("discount") ? ratio(discount, mrp) : null,
    discountOutflowPp: hasCurrent("discount") ? (ratio(discount, mrp) ?? 0) - (ratio(discountLy, mrpLy) ?? 0) : null,
  };
}

export function MonthwiseKpis({ result }) {
  const rows = result?.rows || [];
  const summary = summarizeMonthwise(rows);
  const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const cards = [
    { label: "TOTAL QUANTITY", value: summary.qty == null ? "N/A" : number.format(summary.qty), growth: summary.qtyGrowth, caption: "Current FY vs same months last FY", accent: "accent" },
    { label: "TOTAL BILL VALUE", value: summary.bill == null ? "N/A" : fmtVal(summary.bill), growth: summary.billGrowth, caption: "Current FY vs same months last FY", accent: "teal" },
    { label: "TOTAL DISCOUNT", value: summary.discount == null ? "N/A" : fmtVal(summary.discount), caption: "Current FY discount amount", accent: "warn" },
    { label: "DISCOUNT OUTFLOW", value: summary.discountOutflow == null ? "N/A" : fmtPct(summary.discountOutflow), growth: summary.discountOutflowPp, caption: "Percentage point change vs last FY", accent: "positive", pp: true },
  ];
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    {cards.map((card) => <article key={card.label} className="rounded-xl border border-border bg-surface px-4 py-4 shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-[.12em] text-text-muted">{card.label}</p>
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2"><p className="font-display text-2xl font-bold tabular-nums text-text-primary">{card.value}</p>{card.growth != null && <span className={"rounded-full px-2 py-1 text-[10px] font-bold tabular-nums " + (card.growth >= 0 ? "bg-positive-soft text-positive" : "bg-negative-soft text-negative")}>{card.growth > 0 ? "+" : ""}{card.growth.toFixed(1)}{card.pp ? " pp" : "%"}</span>}</div>
      <p className="mt-1 text-[10px] text-text-muted">{card.caption}</p>
    </article>)}
  </div>;
}

export default function TertiaryMonthwiseTable({ result }) {
  const [sorting, setSorting] = useState({ id: "month_order", direction: "asc" });
  const [openSort, setOpenSort] = useState(null);
  const rows = result?.rows || [];
  const sortedRows = useMemo(() => rows.map((row) => ({ ...row, discount_pct_ly: ratio(row.discount_ly, row.mrp_value_ly), discount_outflow_pp: (ratio(row.discount, row.mrp_value) ?? 0) - (ratio(row.discount_ly, row.mrp_value_ly) ?? 0) })).sort((a, b) => {
    const av = a[sorting.id]; const bv = b[sorting.id];
    if (av == null && bv == null) return 0; if (av == null) return 1; if (bv == null) return -1;
    const compare = typeof av === "string" ? av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" }) : Number(av) - Number(bv);
    return sorting.direction === "asc" ? compare : -compare;
  }), [rows, sorting]);
  const totals = useMemo(() => summarizeMonthwise(rows), [rows]);
  const sum = (key) => rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  const fy = result?.fy_context || {};
  const changeSort = (id, direction) => { setSorting({ id, direction }); setOpenSort(null); };
  const header = (label, id, align) => <SortHeader label={label} id={id} sorting={sorting} open={openSort === id} onToggle={() => setOpenSort((current) => current === id ? null : id)} onSort={changeSort} align={align}/>;
  const renderMeasure = (row, measure, previous) => {
    if (measure.key === "discount_pct") return ratio(row[previous ? "discount_ly" : "discount"], row[previous ? "mrp_value_ly" : "mrp_value"]);
    const value = row[previous ? measure.key + "_ly" : measure.key];
    return value;
  };
  const cell = (row, measure, previous, key) => {
    const value = renderMeasure(row, measure, previous);
    return <td key={key} className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums text-text-primary">{value == null ? <span className="text-text-muted">?</span> : measure.format(value)}</td>;
  };
  const growthCells = (row) => {
    const previousOutflow = ratio(row.discount_ly, row.mrp_value_ly);
    const currentOutflow = ratio(row.discount, row.mrp_value);
    const outflowChange = currentOutflow == null ? null : currentOutflow - (previousOutflow || 0);
    return <>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{row.qty_growth_pct == null ? <span className="text-text-muted">?</span> : <span className={row.qty_growth_pct >= 0 ? "text-positive" : "text-negative"}>{fmtPct(row.qty_growth_pct)}</span>}</td>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{row.bill_val_growth_pct == null ? <span className="text-text-muted">?</span> : <span className={row.bill_val_growth_pct >= 0 ? "text-positive" : "text-negative"}>{fmtPct(row.bill_val_growth_pct)}</span>}</td>
      <td className="whitespace-nowrap border-b border-border px-3 py-2.5 text-right tabular-nums">{outflowChange == null ? <span className="text-text-muted">?</span> : <span className={outflowChange >= 0 ? "text-positive" : "text-negative"}>{pointChange(outflowChange)}</span>}</td>
    </>;
  };
  const totalGrowthQty = totals.qtyGrowth; const totalGrowthVal = totals.billGrowth;
  const totalOutflowPp = totals.discountOutflowPp;

  return <div className="overflow-hidden rounded-xl border border-border">
    <div className="overflow-auto">
      <table className="w-full min-w-[1500px] border-separate border-spacing-0 text-xs">
        <thead className="sticky top-0 z-20 bg-base text-[10px] font-bold uppercase tracking-wide text-text-secondary">
          <tr>
            <th rowSpan="2" className="sticky left-0 z-30 min-w-32 border-b border-r border-border bg-base px-4 py-3 text-left">{header("MONTH", "month_order", "left")}</th>
            <th colSpan="5" className="border-b border-border px-3 py-2.5 text-center">{fy.last_fy_label || "LAST FY"}</th>
            <th rowSpan="2" aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"><span className="sr-only">Fiscal year section gap</span></th>
            <th colSpan="5" className="border-b border-border px-3 py-2.5 text-center">{fy.current_fy_label || "CURRENT FY"}</th>
            <th rowSpan="2" aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"><span className="sr-only">Growth section gap</span></th>
            <th colSpan="3" className="border-b border-l-2 border-accent/40 bg-accent-soft/40 px-3 py-2.5 text-center text-accent">GROWTH</th>
          </tr>
          <tr>{MEASURES.map((measure) => <th key={"last-" + measure.key} className="border-b border-border px-3 py-2 text-right">{header(measure.label, measure.key + "_ly")}</th>)}
            <th aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"></th>
            {MEASURES.map((measure) => <th key={"current-" + measure.key} className="border-b border-border px-3 py-2 text-right">{header(measure.label, measure.key)}</th>)}
            <th aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"></th>
            {[ ["QTY GROWTH %", "qty_growth_pct"], ["VALUE GROWTH %", "bill_val_growth_pct"], ["DISCOUNT OUTFLOW P.P", "discount_outflow_pp"] ].map(([label, key]) => <th key={key} className="border-b border-border border-l border-accent/20 bg-accent-soft/30 px-3 py-2 text-right">{header(label, key)}</th>)}
          </tr>
        </thead>
        <tbody>{sortedRows.length ? sortedRows.map((row, index) => <tr key={row.month} className={"hover:bg-accent-soft/30 " + (index % 2 ? "bg-base/40" : "bg-surface")}>
          <th className="sticky left-0 z-10 border-b border-r border-border bg-inherit px-4 py-2.5 text-left font-semibold uppercase text-text-primary">{row.month}</th>
          {MEASURES.map((measure) => cell(row, measure, true, "last-" + measure.key))}
          <td aria-hidden="true" className="w-6 min-w-6 border-none bg-base p-0"></td>
          {MEASURES.map((measure) => cell(row, measure, false, "current-" + measure.key))}
          <td aria-hidden="true" className="w-10 min-w-10 border-none bg-base p-0"></td>
          {growthCells(row)}
        </tr>) : <tr><td colSpan="16" className="px-4 py-10 text-center text-sm text-text-muted">No monthwise data for these filters.</td></tr>}</tbody>
        {rows.length > 0 && <tfoot><tr className="border-t-2 border-accent bg-surface font-bold text-text-primary">
          <th className="sticky left-0 z-10 border-t-2 border-r border-accent bg-surface px-4 py-3 text-left">Grand Total</th>
          {MEASURES.map((measure) => { const key = measure.key + "_ly"; const value = measure.key === "discount_pct" ? ratio(sum("discount_ly"), sum("mrp_value_ly")) : sum(key); return <td key={"total-last-" + key} className="border-t-2 border-accent px-3 py-3 text-right tabular-nums">{value == null ? "N/A" : measure.format(value)}</td>; })}
          <td className="w-6 min-w-6 border-none bg-base p-0"></td>
          {MEASURES.map((measure) => { const value = measure.key === "discount_pct" ? (totals.discountOutflow == null ? null : ratio(sum("discount"), sum("mrp_value"))) : (rows.some((row) => row[measure.key] != null) ? sum(measure.key) : null); return <td key={"total-current-" + measure.key} className="border-t-2 border-accent px-3 py-3 text-right tabular-nums">{value == null ? "N/A" : measure.format(value)}</td>; })}
          <td className="w-10 min-w-10 border-none bg-base p-0"></td>
          <td className="border-t-2 border-l border-accent/20 px-3 py-3 text-right text-positive">{totalGrowthQty == null ? "N/A" : fmtPct(totalGrowthQty)}</td><td className="border-t-2 border-l border-accent/20 px-3 py-3 text-right text-positive">{totalGrowthVal == null ? "N/A" : fmtPct(totalGrowthVal)}</td><td className="border-t-2 border-l border-accent/20 px-3 py-3 text-right">{totalOutflowPp == null ? "N/A" : pointChange(totalOutflowPp)}</td>
        </tr></tfoot>}
      </table>
    </div>
  </div>;
}
