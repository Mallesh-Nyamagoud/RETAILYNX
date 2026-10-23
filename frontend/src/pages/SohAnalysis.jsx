import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { sohApi } from "../api/client";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import { ExportButton } from "../components/common/ExportButton";
import { EmptyState, ErrorState, LoadingState } from "../components/common/LoadingState";
import { canLoadSohSummary, getSohSourceError, hasSohSourceRefreshFailure } from "../utils/sohQueryState.js";

const COLUMNS = [
  { key: "store", label: "Store", value: (r) => r.store },
  { key: "brand", label: "Brand", value: (r) => r.brand },
  { key: "category", label: "Category", value: (r) => r.category },
  { key: "style", label: "Style Code", value: (r) => r.style },
  { key: "season", label: "Season", value: (r) => r.season },
  { key: "opening_soh", label: "Opening SOH", value: (r) => r.opening_soh },
  { key: "tertiary_net_sales", label: "Tertiary Net Sales", value: (r) => r.tertiary_net_sales },
  { key: "secondary_transfer_qty", label: "Secondary Transfer (+ Qty)", value: (r) => r.secondary_transfer_qty },
  { key: "secondary_return_qty", label: "Secondary Return (- Qty)", value: (r) => r.secondary_return_qty },
  { key: "total_style_net_sales", label: "Total Style Net Sales", value: (r) => r.total_style_net_sales },
  { key: "ending_soh", label: "End SOH Month", value: (r) => r.ending_soh },
  { key: "end_soh_sizewise", label: "End SOH Sizewise", value: (r) => r.end_soh_sizewise },
  { key: "st_pct", label: "ST%", value: (r) => `${(r.st_pct * 100).toFixed(1)}%` },
  { key: "opening_soh_clearance", label: "Start SOH Clearance %", value: (r) => `${(r.opening_soh_clearance * 100).toFixed(1)}%` },
];

export default function SohAnalysis() {
  const [opening, setOpening] = useState("");
  const [ending, setEnding] = useState("");
  const [columnFilters, setColumnFilters] = useState({});
  const [rangeFilters, setRangeFilters] = useState({});
  const [sort, setSort] = useState({ key: "style", direction: "asc" });
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const tableScrollRef = useRef(null);
  const datesQ = useQuery({ queryKey: ["soh", "dates"], queryFn: sohApi.dates });
  const dates = datesQ.data?.dates || [];
  const start = opening || dates[0] || "";
  const validEnds = dates.filter((date) => date >= start);
  const end = validEnds.includes(ending) ? ending : validEnds.at(-1) || "";
  const params = useMemo(() => ({ opening: start, ending: end, threshold: 1 }), [start, end]);
  const q = useQuery({
    queryKey: ["soh", "summary", params],
    enabled: canLoadSohSummary(datesQ, start, end),
    queryFn: () => sohApi.summary(params),
  });
  const handleExport = async () => {
    setExporting(true); setExportError("");
    try { await sohApi.export(params); }
    catch (error) { setExportError(error.message || "Could not export SOH analysis."); }
    finally { setExporting(false); }
  };
  const rows = q.data?.rows || [];
  const filterOptions = useMemo(() => Object.fromEntries(COLUMNS.map(({ key, value }) => [key, [...new Set(rows.map((row) => String(value(row) ?? "")).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }))])), [rows]);
  const visibleRows = useMemo(() => {
    const filtered = rows.filter((row) => COLUMNS.every(({ key, value }) => {
      if (key === "st_pct" || key === "opening_soh_clearance") {
        const percent = Number(row[key] || 0) * 100;
        const minText = rangeFilters[key]?.min ?? "";
        const maxText = rangeFilters[key]?.max ?? "";
        return (minText === "" || percent >= Number(minText))
          && (maxText === "" || percent <= Number(maxText));
      }
      const filter = (columnFilters[key] || "").trim().toLocaleLowerCase();
      return !filter || String(value(row) ?? "").toLocaleLowerCase().includes(filter);
    }));
    const column = COLUMNS.find(({ key }) => key === sort.key);
    if (!column) return filtered;
    return [...filtered].sort((a, b) => {
      const av = column.value(a) ?? ""; const bv = column.value(b) ?? "";
      const an = Number(av); const bn = Number(bv);
      const order = av !== "" && bv !== "" && Number.isFinite(an) && Number.isFinite(bn)
        ? an - bn : String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
      return sort.direction === "asc" ? order : -order;
    });
  }, [rows, columnFilters, rangeFilters, sort]);
  const sourceError = getSohSourceError(datesQ);
  const sourceRefreshFailed = hasSohSourceRefreshFailure(datesQ);
  const toggleSort = (key) => setSort((current) => ({
    key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
  }));

  return (
    <div className="space-y-5">
      <PageHeader title="SOH Analysis"
        description="Compare opening stock, tertiary net sales, signed secondary transfers and returns, closing stock by size, and sell-through."
        actions={<ExportButton onExport={handleExport} loading={exporting} disabled={!visibleRows.length || q.isLoading} />} />
      <Card><div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">Opening month<select className="mt-1 w-full rounded border border-border bg-base p-2" value={start}
          onChange={(e) => { setOpening(e.target.value); if (end < e.target.value) setEnding(""); }}>
          {dates.map((date) => <option key={date} value={date}>{date}</option>)}</select></label>
        <label className="text-sm">End month<select className="mt-1 w-full rounded border border-border bg-base p-2" value={end}
          onChange={(e) => setEnding(e.target.value)}>{validEnds.map((date) => <option key={date} value={date}>{date}</option>)}</select></label>
      </div></Card>
      {exportError && <p role="alert" className="text-sm text-red-500">{exportError}</p>}
      {(q.data?.warnings || []).map((warning) => <p key={warning} role="status" className="rounded border border-warn/30 bg-warn/10 px-3 py-2 text-sm text-warn">{warning}</p>)}
      {(q.isError && q.data) || sourceRefreshFailed ? <p role="alert" className="text-sm text-red-500">A refresh failed; showing the last loaded SOH results.</p> : null}
      {datesQ.isLoading || q.isLoading ? <Card><LoadingState label="Loading SOH analysis" rows={6} /></Card>
        : sourceError ? <Card><ErrorState message={sourceError.message} onRetry={() => datesQ.refetch()} /></Card>
        : q.data?.error ? <Card><ErrorState message={q.data.error} onRetry={() => q.refetch()} /></Card>
        : q.isError && !q.data ? <Card><ErrorState message={q.error.message} onRetry={() => q.refetch()} /></Card>
        : rows.length === 0 ? <Card><EmptyState title="No SOH rows for these months" description="Choose a different opening and end month." /></Card>
        : <Card>
          <div className="mb-2 flex items-center gap-2">
            <span className="mr-auto text-xs text-text-muted">Showing {visibleRows.length.toLocaleString()} of {rows.length.toLocaleString()} rows · Filter in each column; select a heading to sort.</span>
            <button type="button" aria-label="Scroll table left" title="Scroll left" className="rounded border border-border p-2" onClick={() => tableScrollRef.current?.scrollBy({ left: -520, behavior: "smooth" })}><ChevronLeft size={18} /></button>
            <button type="button" aria-label="Scroll table right" title="Scroll right" className="rounded border border-border p-2" onClick={() => tableScrollRef.current?.scrollBy({ left: 520, behavior: "smooth" })}><ChevronRight size={18} /></button>
          </div>
          <div ref={tableScrollRef} className="overflow-x-auto rounded border border-border scroll-smooth">{COLUMNS.filter(({ key }) => key !== "st_pct" && key !== "opening_soh_clearance").map(({ key }) => <datalist key={key} id={`soh-filter-${key}`}>{(filterOptions[key] || []).map((option) => <option key={option} value={option} />)}</datalist>)}<table className="w-full min-w-[1900px] text-sm">
            <thead className="sticky top-0 z-10 bg-surface"><tr>{COLUMNS.map(({ key, label }) => <th className="border-b border-border p-2 text-left" key={key}>
              <button type="button" className="inline-flex items-center gap-1 whitespace-nowrap font-semibold hover:text-accent" onClick={() => toggleSort(key)}>{label}{sort.key === key ? (sort.direction === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />) : <ChevronDown size={12} className="opacity-30" />}</button>
            </th>)}</tr><tr>{COLUMNS.map(({ key, label }) => <th className="border-b border-border p-2" key={key}>
              {key === "st_pct" || key === "opening_soh_clearance" ? (
                <div className="flex min-w-36 gap-1">
                  <input aria-label={`Minimum ${label}`} type="number" min="0" max="100" step="0.1" placeholder="Min %" className="w-1/2 min-w-16 rounded border border-border bg-base px-2 py-1 text-xs font-normal" value={rangeFilters[key]?.min ?? ""} onChange={(e) => setRangeFilters((current) => ({ ...current, [key]: { ...current[key], min: e.target.value } }))} />
                  <input aria-label={`Maximum ${label}`} type="number" min="0" max="100" step="0.1" placeholder="Max %" className="w-1/2 min-w-16 rounded border border-border bg-base px-2 py-1 text-xs font-normal" value={rangeFilters[key]?.max ?? ""} onChange={(e) => setRangeFilters((current) => ({ ...current, [key]: { ...current[key], max: e.target.value } }))} />
                </div>
              ) : (
                <input aria-label={`Filter ${label}`} title={`Filter ${label}`} list={`soh-filter-${key}`} className="w-full min-w-24 rounded border border-border bg-base px-2 py-1 text-xs font-normal" placeholder="Search or select..." value={columnFilters[key] || ""} onChange={(e) => setColumnFilters((current) => ({ ...current, [key]: e.target.value }))} />
              )}
            </th>)}</tr></thead>
            <tbody>{visibleRows.map((row, index) => <tr className="border-t border-border odd:bg-white/[0.03] hover:bg-white/[0.07]" key={`${row.store}-${row.brand}-${row.style}-${row.season}-${index}`}>
              {COLUMNS.map(({ key, value }) => <td className="p-2 whitespace-nowrap" key={key}>{value(row) ?? ""}</td>)}
            </tr>)}</tbody>
          </table></div>
          {visibleRows.length === 0 && <p className="py-8 text-center text-sm text-text-muted">No rows match these column filters. Clear a filter to see results.</p>}
          <p className="mt-3 text-xs text-text-muted">Tertiary net sales include signed returns. Secondary transfer and return quantities are separate; returns retain their negative sign. Start SOH clearance assumes opening stock sells first and is capped at 100%.</p>
        </Card>}
    </div>
  );
}
