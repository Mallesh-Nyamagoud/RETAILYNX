import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { sohApi } from "../api/client";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import { ExportButton } from "../components/common/ExportButton";
import { EmptyState, ErrorState, LoadingState } from "../components/common/LoadingState";

const FILTER_LABELS = {
  store: "Store",
  brand: "Brand",
  category: "Category",
  style: "Style",
  season: "Season",
};
const EMPTY_FILTERS = { store: "", brand: "", category: "", style: "", season: "" };
const ALL_LABELS = { store: "All stores", brand: "All brands", category: "All categories", style: "All styles", season: "All seasons" };
const COLUMNS = [
  ["Store", (row) => row.store],
  ["Brand", (row) => row.brand],
  ["Category", (row) => row.category],
  ["Style", (row) => row.style],
  ["Season", (row) => row.season],
  ["Opening SOH", (row) => row.opening_soh],
  ["Transferred Between", (row) => row.transferred_between],
  ["End SOH Month", (row) => row.ending_soh],
  ["End SOH Sizewise", (row) => row.end_soh_sizewise],
  ["Total Sale", (row) => row.total_sale],
  ["Sale", (row) => row.sale],
  ["ST%", (row) => `${(row.st_pct * 100).toFixed(1)}%`],
  ["Opening SOH Clearance", (row) => `${(row.opening_soh_clearance * 100).toFixed(1)}%`],
];

export default function SohAnalysis() {
  const [opening, setOpening] = useState("");
  const [ending, setEnding] = useState("");
  const [threshold, setThreshold] = useState(1);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const datesQ = useQuery({ queryKey: ["soh", "dates"], queryFn: sohApi.dates });
  const filtersQ = useQuery({ queryKey: ["soh", "filters"], queryFn: sohApi.filters });
  const dates = datesQ.data?.dates || [];
  const start = opening || dates[0] || "";
  const validEnds = dates.filter((date) => date >= start);
  const end = validEnds.includes(ending) ? ending : validEnds.at(-1) || "";
  const filterOptions = filtersQ.data?.filters || {};
  const selectedFilters = useMemo(
    () => Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    [filters],
  );
  const params = useMemo(
    () => ({ opening: start, ending: end, threshold, ...selectedFilters }),
    [start, end, threshold, selectedFilters],
  );
  const q = useQuery({
    queryKey: ["soh", "summary", params],
    enabled: !!start && !!end && !datesQ.isError && !filtersQ.isError,
    queryFn: () => sohApi.summary(params),
  });
  const updateFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const handleExport = async () => {
    setExporting(true);
    setExportError("");
    try {
      await sohApi.export(params);
    } catch (error) {
      setExportError(error.message || "Could not export SOH analysis.");
    } finally {
      setExporting(false);
    }
  };
  const rows = q.data?.rows || [];
  const sourceError = datesQ.error || filtersQ.error;

  return (
    <div className="space-y-5">
      <PageHeader
        title="SOH Analysis"
        description="Compare monthly store stock, sales, and sell-through by brand, category, style, and season."
        actions={<ExportButton onExport={handleExport} loading={exporting} disabled={!rows.length || q.isLoading} />}
      />
      <Card>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm">Opening month
            <select className="mt-1 w-full rounded border border-border bg-base p-2" value={start}
              onChange={(e) => { setOpening(e.target.value); if (end < e.target.value) setEnding(""); }}>
              {dates.map((date) => <option key={date} value={date}>{date}</option>)}
            </select>
          </label>
          <label className="text-sm">End month
            <select className="mt-1 w-full rounded border border-border bg-base p-2" value={end}
              onChange={(e) => setEnding(e.target.value)}>
              {validEnds.map((date) => <option key={date} value={date}>{date}</option>)}
            </select>
          </label>
          {Object.entries(FILTER_LABELS).map(([key, label]) => (
            <label className="text-sm" key={key}>{label}
              <select className="mt-1 w-full rounded border border-border bg-base p-2"
                value={filters[key]} onChange={(e) => updateFilter(key, e.target.value)}>
                <option value="">{ALL_LABELS[key]}</option>
                {(filterOptions[key] || []).map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          ))}
          <label className="text-sm">ST% threshold ({Math.round(threshold * 100)}%)
            <input className="mt-2 w-full" type="range" min="0" max="1" step=".05"
              value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
          </label>
        </div>
      </Card>
      {exportError && <p role="alert" className="text-sm text-red-500">{exportError}</p>}
      {datesQ.isLoading || filtersQ.isLoading || q.isLoading ? (
        <Card><LoadingState label="Loading SOH analysis" rows={6} /></Card>
      ) : sourceError ? (
        <Card><ErrorState message={sourceError.message} onRetry={() => { datesQ.refetch(); filtersQ.refetch(); }} /></Card>
      ) : q.isError ? (
        <Card><ErrorState message={q.error.message} onRetry={() => q.refetch()} /></Card>
      ) : rows.length === 0 ? (
        <Card><EmptyState title="No SOH rows match these selections" description="Adjust the month range, filters, or ST% threshold to see styles." /></Card>
      ) : (
        <Card>
          <div className="overflow-auto"><table className="w-full text-sm">
            <thead><tr>{COLUMNS.map(([label]) => <th className="p-2 text-left" key={label}>{label}</th>)}</tr></thead>
            <tbody>{rows.map((row, index) => <tr className="border-t border-border" key={`${row.store}-${row.brand}-${row.style}-${row.season}-${index}`}>
              {COLUMNS.map(([label, value]) => <td className="p-2 whitespace-nowrap" key={label}>{value(row) ?? "?"}</td>)}
            </tr>)}</tbody>
          </table></div>
          <p className="mt-3 text-xs text-text-muted">Transferred Between is calculated from stock movement and sales. No separate transfer ledger was supplied.</p>
        </Card>
      )}
    </div>
  );
}
