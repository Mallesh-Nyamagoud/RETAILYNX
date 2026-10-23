import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  { key: "category", label: "Category", value: (r) => r.category },
  { key: "style", label: "Style Code", value: (r) => r.style },
  { key: "season", label: "Season", value: (r) => r.season },
  { key: "brand", label: "Brand", value: (r) => r.brand },
  { key: "opening_soh", label: "Start SOH", value: (r) => r.opening_soh },
  { key: "ending_soh", label: "End SOH", value: (r) => r.ending_soh },
  { key: "end_soh_sizewise", label: "End SOH Sizewise", value: (r) => r.end_soh_sizewise },
  { key: "tertiary_period_sales", label: "Period Tertiary Net Sales", value: (r) => r.tertiary_period_sales },
  { key: "tertiary_total_sales", label: "Total Tertiary Net Sales (All Dates)", value: (r) => r.tertiary_total_sales },
  { key: "secondary_transfer_qty", label: "Secondary Transfer (+ Qty)", value: (r) => r.secondary_transfer_qty },
  { key: "secondary_return_qty", label: "Secondary Return (- Qty)", value: (r) => r.secondary_return_qty },
  { key: "st_pct", label: "ST%", value: (r) => `${(r.st_pct * 100).toFixed(1)}%` },
  { key: "opening_soh_clearance", label: "Start SOH Clearance %", value: (r) => `${(r.opening_soh_clearance * 100).toFixed(1)}%` },
];

const FROZEN_COLUMN_WIDTHS = { store: 220, category: 200, style: 160, season: 130 };
const FROZEN_OFFSETS = { store: 0, category: 220, style: 420, season: 580 };

function frozenColumnStyle(key, header = false) {
  const width = FROZEN_COLUMN_WIDTHS[key];
  if (!width) return undefined;
  return {
    position: "sticky",
    left: FROZEN_OFFSETS[key],
    width,
    minWidth: width,
    backgroundColor: header ? "var(--color-surface)" : "var(--color-card)",
    zIndex: header ? 40 : 10,
  };
}

function ColumnMultiFilter({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const filteredOptions = useMemo(() => options.filter((option) => option.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())), [options, search]);
  const shownOptions = filteredOptions.slice(0, 500);

  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => {
      if (!panelRef.current?.contains(event.target) && !triggerRef.current?.contains(event.target)) setOpen(false);
    };
    const closeEscape = (event) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [open]);

  const toggleOption = (option) => onChange(selected.includes(option)
    ? selected.filter((item) => item !== option)
    : [...selected, option]);
  const selectVisible = () => onChange([...new Set([...selected, ...shownOptions])]);
  const openMenu = () => {
    const rect = triggerRef.current.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 296)), top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 380)) });
    setOpen((current) => !current);
  };

  return (
    <>
      <button ref={triggerRef} type="button" aria-label={`Filter ${label}`} aria-expanded={open} onClick={openMenu}
        className="flex w-full min-w-28 items-center justify-between gap-2 rounded border border-border bg-base px-2 py-1 text-left text-xs font-normal hover:border-accent">
        <span className="truncate">{selected.length ? `${selected.length} selected` : "All"}</span><ChevronDown size={12} />
      </button>
      {open && createPortal(
        <div ref={panelRef} role="dialog" aria-label={`${label} filter options`} style={{ position: "fixed", left: position.left, top: position.top, width: 280 }}
          className="z-[1000] rounded-lg border border-border bg-surface p-3 shadow-2xl">
          <input autoFocus aria-label={`Search ${label} options`} placeholder={`Search ${label}...`} value={search} onChange={(event) => setSearch(event.target.value)}
            className="mb-2 w-full rounded border border-border bg-base px-2 py-2 text-sm" />
          <div className="mb-2 flex items-center justify-between gap-2 text-xs">
            <button type="button" className="text-accent hover:underline" onClick={selectVisible}>Select visible ({shownOptions.length})</button>
            <button type="button" className="text-text-muted hover:underline" onClick={() => onChange([])}>Clear</button>
          </div>
          <div className="max-h-64 overflow-y-auto border-y border-border py-1">
            {shownOptions.map((option) => <label key={option} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1.5 text-xs hover:bg-white/10">
              <input type="checkbox" checked={selected.includes(option)} onChange={() => toggleOption(option)} />
              <span className="truncate" title={option}>{option}</span>
            </label>)}
            {shownOptions.length === 0 && <p className="px-1 py-3 text-xs text-text-muted">No matching values.</p>}
          </div>
          <p className="pt-2 text-[11px] text-text-muted">{filteredOptions.length > shownOptions.length ? `Showing 500 of ${filteredOptions.length}; type to narrow.` : `${filteredOptions.length} values`}</p>
          <button type="button" className="mt-2 w-full rounded bg-accent px-2 py-1.5 text-xs font-semibold text-white" onClick={() => setOpen(false)}>Done</button>
        </div>, document.body,
      )}
    </>
  );
}
export default function SohAnalysis() {
  const [opening, setOpening] = useState("");
  const [ending, setEnding] = useState("");
  const [columnSelections, setColumnSelections] = useState({});
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
      const selected = columnSelections[key] || [];
      return selected.length === 0 || selected.includes(String(value(row) ?? ""));
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
  }, [rows, columnSelections, rangeFilters, sort]);
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
          <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-base/50 p-3">
            <div className="mr-auto min-w-48">
              <p className="text-sm font-semibold text-text-primary">SOH Summary</p>
              <p className="text-xs text-text-muted">Showing {visibleRows.length.toLocaleString()} of {rows.length.toLocaleString()} rows. Filter columns and select headings to sort.</p>
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1" aria-label="Summary navigation">
              <button type="button" aria-label="Scroll summary up" title="Scroll up" className="rounded p-2 hover:bg-card-hover" onClick={() => tableScrollRef.current?.scrollBy({ top: -420, behavior: "smooth" })}><ChevronUp size={18} /></button>
              <button type="button" aria-label="Scroll summary down" title="Scroll down" className="rounded p-2 hover:bg-card-hover" onClick={() => tableScrollRef.current?.scrollBy({ top: 420, behavior: "smooth" })}><ChevronDown size={18} /></button>
              <span className="mx-1 h-6 border-l border-border" />
              <button type="button" aria-label="Scroll summary left" title="Scroll left" className="rounded p-2 hover:bg-card-hover" onClick={() => tableScrollRef.current?.scrollBy({ left: -520, behavior: "smooth" })}><ChevronLeft size={18} /></button>
              <button type="button" aria-label="Scroll summary right" title="Scroll right" className="rounded p-2 hover:bg-card-hover" onClick={() => tableScrollRef.current?.scrollBy({ left: 520, behavior: "smooth" })}><ChevronRight size={18} /></button>
            </div>
          </div>
          <div ref={tableScrollRef} className="h-[68vh] min-h-[380px] max-h-[720px] overflow-auto overscroll-contain rounded-xl border border-border bg-card shadow-inner scroll-smooth"><table className="w-full min-w-[2400px] text-sm">
            <thead className="sticky top-0 z-30 bg-surface"><tr>{COLUMNS.map(({ key, label }) => <th className="border-b border-border p-2 text-left" style={frozenColumnStyle(key, true)} key={key}>
              <button type="button" className="inline-flex items-center gap-1 whitespace-nowrap font-semibold hover:text-accent" onClick={() => toggleSort(key)}>{label}{sort.key === key ? (sort.direction === "asc" ? <ChevronUp size={14} /> : <ChevronDown size={14} />) : <ChevronDown size={12} className="opacity-30" />}</button>
            </th>)}</tr><tr>{COLUMNS.map(({ key, label }) => <th className="border-b border-border p-2" style={frozenColumnStyle(key, true)} key={key}>
              {key === "st_pct" || key === "opening_soh_clearance" ? (
                <div className="flex min-w-36 gap-1">
                  <input aria-label={`Minimum ${label}`} type="number" step="0.1" placeholder="Min %" className="w-1/2 min-w-16 rounded border border-border bg-base px-2 py-1 text-xs font-normal" value={rangeFilters[key]?.min ?? ""} onChange={(e) => setRangeFilters((current) => ({ ...current, [key]: { ...current[key], min: e.target.value } }))} />
                  <input aria-label={`Maximum ${label}`} type="number" step="0.1" placeholder="Max %" className="w-1/2 min-w-16 rounded border border-border bg-base px-2 py-1 text-xs font-normal" value={rangeFilters[key]?.max ?? ""} onChange={(e) => setRangeFilters((current) => ({ ...current, [key]: { ...current[key], max: e.target.value } }))} />
                </div>
              ) : (
                <ColumnMultiFilter label={label} options={filterOptions[key] || []} selected={columnSelections[key] || []} onChange={(selected) => setColumnSelections((current) => ({ ...current, [key]: selected }))} />
              )}
            </th>)}</tr></thead>
            <tbody>{visibleRows.map((row, index) => <tr className="border-t border-border odd:bg-white/[0.03] hover:bg-white/[0.07]" key={`${row.store}-${row.brand}-${row.style}-${row.season}-${index}`}>
              {COLUMNS.map(({ key, value }) => <td className="p-2 whitespace-nowrap" style={frozenColumnStyle(key)} key={key}>{value(row) ?? ""}</td>)}
            </tr>)}</tbody>
          </table></div>
          {visibleRows.length === 0 && <p className="py-8 text-center text-sm text-text-muted">No rows match these column filters. Clear a filter to see results.</p>}
          <p className="mt-3 text-xs text-text-muted">Tertiary net sales include signed returns. Secondary transfer and return quantities are separate; returns retain their negative sign. ST% and Start SOH Clearance are each calculated as period tertiary net sales divided by Start SOH.</p>
        </Card>}
    </div>
  );
}
