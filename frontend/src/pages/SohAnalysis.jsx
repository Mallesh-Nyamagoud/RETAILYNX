import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { http } from "../api/client";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";

const FILTER_LABELS = {
  store: "Store",
  brand: "Brand",
  category: "Category",
  style: "Style",
  season: "Season",
};
const EMPTY_FILTERS = { store: "", brand: "", category: "", style: "", season: "" };
const ALL_LABELS = { store: "All stores", brand: "All brands", category: "All categories", style: "All styles", season: "All seasons" };

export default function SohAnalysis() {
  const [opening, setOpening] = useState("");
  const [ending, setEnding] = useState("");
  const [threshold, setThreshold] = useState(1);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const datesQ = useQuery({
    queryKey: ["soh", "dates"],
    queryFn: () => http.get("/soh/dates").then((r) => r.data),
  });
  const filtersQ = useQuery({
    queryKey: ["soh", "filters"],
    queryFn: () => http.get("/soh/filters").then((r) => r.data),
  });
  const dates = datesQ.data?.dates || [];
  const start = opening || dates[0] || "";
  const validEnds = dates.filter((date) => date >= start);
  const end = validEnds.includes(ending) ? ending : validEnds.at(-1) || "";
  const filterOptions = filtersQ.data?.filters || {};
  const selectedFilters = useMemo(
    () => Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    [filters],
  );
  const q = useQuery({
    queryKey: ["soh", start, end, threshold, selectedFilters],
    enabled: !!start && !!end && !datesQ.isError && !filtersQ.isError,
    queryFn: () => http.get("/soh/summary", {
      params: { opening: start, ending: end, threshold, ...selectedFilters },
    }).then((r) => r.data),
  });
  const updateFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }));

  return (
    <div className="space-y-5">
      <PageHeader title="SOH Analysis" subtitle="Monthly store stock by brand, category, style and season." />
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
      {datesQ.isLoading || filtersQ.isLoading || q.isLoading ? <p>Loading SOH data?</p> : null}
      {q.isError && <p className="text-red-500">{q.error.message}</p>}
      {!q.isLoading && !q.isError && <Card>
        <div className="overflow-auto"><table className="w-full text-sm">
          <thead><tr>{["Store", "Brand", "Category", "Style", "Season", "Opening SOH", "Net Transfers*", "End SOH", "End SOH Sizewise", "Total Sale", "Sale", "ST%", "Opening SOH Clearance"].map((label) => <th className="p-2 text-left" key={label}>{label}</th>)}</tr></thead>
          <tbody>{(q.data?.rows || []).map((row, index) => <tr className="border-t border-border" key={`${row.store}-${row.style}-${row.season}-${index}`}>
            {[row.store, row.brand, row.category, row.style, row.season, row.opening_soh, row.transferred_between, row.ending_soh, row.end_soh_sizewise, row.total_sale, row.sale, `${(row.st_pct * 100).toFixed(1)}%`, `${(row.opening_soh_clearance * 100).toFixed(1)}%`].map((value, cell) => <td className="p-2 whitespace-nowrap" key={cell}>{value ?? "?"}</td>)}
          </tr>)}</tbody>
        </table></div>
        <p className="mt-3 text-xs text-text-muted">*Calculated stock balance movement. The supplied workbook contains no sales or transfer ledger.</p>
      </Card>}
    </div>
  );
}
