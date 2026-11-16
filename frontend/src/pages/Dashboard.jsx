import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Filter, X } from "lucide-react";
import KpiCard from "../components/common/KpiCard";
import { KpiSkeleton, LoadingState } from "../components/common/LoadingState";
import Card from "../components/common/Card";
import ComparisonBarChart from "../components/charts/ComparisonBarChart";
import ContributionDonutChart from "../components/charts/ContributionDonutChart";
import { secondaryApi, tertiaryApi, storeMasterApi, cssStockApi } from "../api/client";

/**
 * Dashboard - the cross-module snapshot page.
 *
 * POWER BI STYLE INTERACTION
 * --------------------------
 * Every visual on this page shares ONE cross-filter (`{ column, value }`).
 * Clicking a bar or a donut slice sets it, and then:
 *
 *   · the visual that was clicked keeps ALL of its categories on screen and
 *     dims the ones that are not selected (cross-HIGHLIGHTING),
 *   · every other visual - the other comparison bar chart, the three donuts
 *     and the four KPI cards - re-queries with that filter applied
 *     (cross-FILTERING),
 *   · clicking the same category again, or "Clear filter", resets the page.
 *
 * Every figure is rendered through the shared dynamic Indian compact formatter
 * ("1.00Cr" / "1.00L" / "1.00K"), in the bar data labels, the value axes, the
 * donut labels/centres and the hover cards - one report-wide visual language.
 */

/** Store-master dimensions this page can cross-filter on, keyed by column. */
const CROSS_FILTER_DIMENSIONS = {
  brand: "Brand",
  group: "Group",
  department: "Department",
  state: "State",
  store_type: "Store Type",
};

/** Pivot rows -> grouped comparison series [{ name, LFY, LFYTD, CFYTD }]. */
function toComparisonData(rows, key) {
  return (rows || [])
    .filter((row) => !row._is_total && row[key])
    .map((row) => ({
      name: String(row[key]),
      LFY: row.lfy_full_val || 0,
      LFYTD: row.lfytd_val || 0,
      CFYTD: row.cfytd_val || 0,
    }))
    .sort((a, b) => b.CFYTD - a.CFYTD);
}

/** Pivot rows -> contribution donut slices [{ name, value, percent }]. */
function toDonutData(rows, key) {
  const valid = (rows || []).filter((row) => !row._is_total && row[key]);
  const total = valid.reduce((sum, row) => sum + (row.cfytd_val || 0), 0);
  return valid
    .map((row) => ({
      name: String(row[key]),
      value: row.cfytd_val || 0,
      percent: total > 0 ? (row.cfytd_val || 0) / total : 0,
    }))
    .sort((a, b) => b.value - a.value);
}

export default function Dashboard() {
  /** The single page-wide cross-filter: { column, value } | null. */
  const [crossFilter, setCrossFilter] = useState(null);
  const [salesPage, setSalesPage] = useState("secondary");
  const [storeLimit, setStoreLimit] = useState(10);

  /** The filter a visual sitting on `column` RECEIVES - a visual never filters
   *  itself, which is what keeps all of its own categories on screen. */
  const filtersFor = (column) =>
    crossFilter && crossFilter.column !== column
      ? { [crossFilter.column]: [crossFilter.value] }
      : {};

  const brandFilters = filtersFor("brand");
  const groupFilters = filtersFor("group");
  const deptFilters = filtersFor("department");
  const stateFilters = filtersFor("state");
  const storeTypeFilters = filtersFor("store_type");
  const pageFilters = crossFilter ? { [crossFilter.column]: [crossFilter.value] } : {};

  // KPI cards follow the cross-filter like every visual in a report page.
  const secondaryQ = useQuery({
    queryKey: ["dashboard", "secondary", pageFilters],
    queryFn: () => secondaryApi.pivot([], pageFilters),
  });
  const tertiaryQ = useQuery({
    queryKey: ["dashboard", "tertiary", pageFilters],
    queryFn: () => tertiaryApi.pivot([], pageFilters),
  });
  const storeQ = useQuery({
    queryKey: ["dashboard", "store-master-kpis", pageFilters],
    queryFn: () => storeMasterApi.kpis(pageFilters),
  });
  const cssQ = useQuery({
    queryKey: ["dashboard", "css-kpis", pageFilters],
    queryFn: () => cssStockApi.kpis(null, pageFilters),
  });

  const brandQ = useQuery({
    queryKey: ["dashboard", "brand", brandFilters],
    queryFn: () => secondaryApi.pivot(["brand"], brandFilters),
  });
  const groupQ = useQuery({
    queryKey: ["dashboard", "group", groupFilters],
    queryFn: () => secondaryApi.pivot(["group"], groupFilters),
  });
  const deptQ = useQuery({
    queryKey: ["dashboard", "department", deptFilters],
    queryFn: () => secondaryApi.pivot(["department"], deptFilters),
  });
  const stateQ = useQuery({
    queryKey: ["dashboard", "state", stateFilters],
    queryFn: () => secondaryApi.pivot(["state"], stateFilters),
  });
  const tertiaryBrandQ = useQuery({
    queryKey: ["dashboard", "tertiary-brand", brandFilters],
    queryFn: () => tertiaryApi.pivot(["brand"], brandFilters),
  });
  const tertiaryGroupQ = useQuery({
    queryKey: ["dashboard", "tertiary-group", groupFilters],
    queryFn: () => tertiaryApi.pivot(["group"], groupFilters),
  });
  const storeTypeQ = useQuery({
    queryKey: ["dashboard", "secondary-store_type", storeTypeFilters],
    queryFn: () => secondaryApi.pivot(["store_type"], storeTypeFilters),
  });
  const tertiaryDeptQ = useQuery({
    queryKey: ["dashboard", "tertiary-department", deptFilters],
    queryFn: () => tertiaryApi.pivot(["department"], deptFilters),
  });
  const tertiaryStateQ = useQuery({
    queryKey: ["dashboard", "tertiary-state", stateFilters],
    queryFn: () => tertiaryApi.pivot(["state"], stateFilters),
  });
  const tertiaryStoreTypeQ = useQuery({
    queryKey: ["dashboard", "tertiary-store_type", storeTypeFilters],
    queryFn: () => tertiaryApi.pivot(["store_type"], storeTypeFilters),
  });
  const secondaryStoresQ = useQuery({
    queryKey: ["dashboard", "secondary-store-growth", pageFilters],
    queryFn: () => secondaryApi.pivot(["retailer_name"], pageFilters),
  });
  const tertiaryStoresQ = useQuery({
    queryKey: ["dashboard", "tertiary-store-growth", pageFilters],
    queryFn: () => tertiaryApi.pivot(["retailer_name"], pageFilters),
  });

  const secondaryTotal = secondaryQ.data?.rows?.[0];
  const tertiaryTotal = tertiaryQ.data?.rows?.[0];
  const loading =
    secondaryQ.isLoading || tertiaryQ.isLoading || storeQ.isLoading || cssQ.isLoading;
  const chartsLoading =
    brandQ.isLoading || groupQ.isLoading || tertiaryBrandQ.isLoading || tertiaryGroupQ.isLoading || deptQ.isLoading || stateQ.isLoading || storeTypeQ.isLoading || tertiaryDeptQ.isLoading || tertiaryStateQ.isLoading || tertiaryStoreTypeQ.isLoading || secondaryStoresQ.isLoading || tertiaryStoresQ.isLoading;

  const brandData = useMemo(() => toComparisonData(brandQ.data?.rows, "brand"), [brandQ.data]);
  const groupData = useMemo(() => toComparisonData(groupQ.data?.rows, "group"), [groupQ.data]);
  const tertiaryBrandData = useMemo(() => toComparisonData(tertiaryBrandQ.data?.rows, "brand"), [tertiaryBrandQ.data]);
  const tertiaryGroupData = useMemo(() => toComparisonData(tertiaryGroupQ.data?.rows, "group"), [tertiaryGroupQ.data]);
  const deptData = useMemo(() => toDonutData(deptQ.data?.rows, "department"), [deptQ.data]);
  const stateData = useMemo(() => toDonutData(stateQ.data?.rows, "state"), [stateQ.data]);
  const storeTypeData = useMemo(
    () => toDonutData(storeTypeQ.data?.rows, "store_type"),
    [storeTypeQ.data]
  );
  const tertiaryDeptData = useMemo(() => toDonutData(tertiaryDeptQ.data?.rows, "department"), [tertiaryDeptQ.data]);
  const tertiaryStateData = useMemo(() => toDonutData(tertiaryStateQ.data?.rows, "state"), [tertiaryStateQ.data]);
  const tertiaryStoreTypeData = useMemo(() => toDonutData(tertiaryStoreTypeQ.data?.rows, "store_type"), [tertiaryStoreTypeQ.data]);
  const selectedStoreRows = useMemo(() => {
    const payload = salesPage === "secondary" ? secondaryStoresQ.data : tertiaryStoresQ.data;
    return (payload?.rows || []).filter((row) => !row._is_total && row.retailer_name)
      .map((row) => ({ name: String(row.retailer_name), growth: Number(row.growth_pct_val) }))
      .filter((row) => Number.isFinite(row.growth));
  }, [salesPage, secondaryStoresQ.data, tertiaryStoresQ.data]);
  const growingStores = selectedStoreRows.filter((row) => row.growth > 0).sort((a, b) => b.growth - a.growth).slice(0, storeLimit);
  const decliningStores = selectedStoreRows.filter((row) => row.growth < 0).sort((a, b) => a.growth - b.growth).slice(0, storeLimit);

  const toggleCrossFilter = (column, value) =>
    setCrossFilter((prev) =>
      prev && prev.column === column && prev.value === value ? null : { column, value }
    );
  const clearCrossFilter = () => setCrossFilter(null);

  /** The props every visual shares: own selection, filter received, clear-all. */
  const crossFilterProps = (column) => ({
    selectedValue: crossFilter?.column === column ? crossFilter.value : null,
    onSelect: (value) => toggleCrossFilter(column, value),
    receivingFilter:
      crossFilter && crossFilter.column !== column
        ? {
            label: CROSS_FILTER_DIMENSIONS[crossFilter.column] || crossFilter.column,
            value: crossFilter.value,
          }
        : null,
    onClearFilters: clearCrossFilter,
  });

  return (
    <div className="space-y-6">
      {crossFilter && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-accent/40 bg-accent-soft px-4 py-3 text-xs">
          <Filter size={14} className="shrink-0 text-accent" />
          <span className="font-bold uppercase tracking-wider text-text-secondary">Cross-filter</span>
          <span className="rounded-md border border-border bg-surface px-2 py-0.5 font-bold text-text-primary">
            {CROSS_FILTER_DIMENSIONS[crossFilter.column] || crossFilter.column} = {crossFilter.value}
          </span>
          <button
            type="button"
            onClick={clearCrossFilter}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 font-semibold text-text-secondary transition-colors hover:text-text-primary"
          >
            <X size={12} /> Clear filter
          </button>
        </div>
      )}

      {loading ? (
        <div className="mb-8">
          <KpiSkeleton count={3} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 mb-8 sm:grid-cols-2 lg:grid-cols-3">
          <KpiCard
            label="Secondary CFYTD"
            val={secondaryTotal?.cfytd_val}
            qty={secondaryTotal?.cfytd_qty}
            growthPct={secondaryTotal?.growth_pct_val}
            accent="accent"
          />
          <KpiCard
            label="Tertiary CFYTD"
            val={tertiaryTotal?.cfytd_val}
            qty={tertiaryTotal?.cfytd_qty}
            growthPct={tertiaryTotal?.growth_pct_val}
            accent="teal"
          />
          <KpiCard
            label="Total Active Doors"
            qty={storeQ.data?.total_active_doors}
            accent="positive"
            hint={`SIS ${storeQ.data?.sis_doors ?? 0} · Non-SIS ${storeQ.data?.non_sis_doors ?? 0}`}
          />
        </div>
      )}

      <div className="flex gap-2 border-b border-border" role="tablist" aria-label="Sales dashboard">
        {[{ key: "secondary", label: "Secondary Sales" }, { key: "tertiary", label: "Tertiary Sales" }].map((item) => (
          <button key={item.key} type="button" role="tab" aria-selected={salesPage === item.key} onClick={() => setSalesPage(item.key)}
            className={`border-b-2 px-4 py-3 text-sm font-semibold transition-colors ${salesPage === item.key ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary"}`}>
            {item.label}
          </button>
        ))}
      </div>

      {chartsLoading ? (
        <Card className="flex h-64 items-center justify-center"><LoadingState /></Card>
      ) : (
        <div className="space-y-6" role="tabpanel" aria-label={`${salesPage} sales charts`}>
          {salesPage === "secondary" ? <>
            <ComparisonBarChart title="Brandwise Taxable Value Comparison" eyebrow="Secondary Sales · Taxable Value" dataTestId="dash-brand-comparison" data={brandData} {...crossFilterProps("brand")} />
            <ComparisonBarChart title="Groupwise Taxable Value Comparison" eyebrow="Secondary Sales · Taxable Value" dataTestId="dash-group-comparison" data={groupData} {...crossFilterProps("group")} />
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <ContributionDonutChart title="Departmentwise Cont %" dataTestId="dash-dept-donut" data={deptData} {...crossFilterProps("department")} />
              <ContributionDonutChart title="Statewise Cont %" dataTestId="dash-state-donut" data={stateData} {...crossFilterProps("state")} />
              <ContributionDonutChart title="Store Type Cont %" dataTestId="dash-store-type-donut" data={storeTypeData} {...crossFilterProps("store_type")} />
            </div>
          </> : <>
            <ComparisonBarChart title="Brandwise Taxable Value Comparison" eyebrow="Tertiary Sales · Taxable Value" dataTestId="dash-tertiary-brand-comparison" data={tertiaryBrandData} {...crossFilterProps("brand")} />
            <ComparisonBarChart title="Groupwise Taxable Value Comparison" eyebrow="Tertiary Sales · Taxable Value" dataTestId="dash-tertiary-group-comparison" data={tertiaryGroupData} {...crossFilterProps("group")} />
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <ContributionDonutChart title="Departmentwise Cont %" dataTestId="dash-tertiary-dept-donut" data={tertiaryDeptData} {...crossFilterProps("department")} />
              <ContributionDonutChart title="Statewise Cont %" dataTestId="dash-tertiary-state-donut" data={tertiaryStateData} {...crossFilterProps("state")} />
              <ContributionDonutChart title="Store Type Cont %" dataTestId="dash-tertiary-store-type-donut" data={tertiaryStoreTypeData} {...crossFilterProps("store_type")} />
            </div>
          </>}
          <Card padded>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="text-sm font-bold uppercase tracking-wide text-text-primary">Top store growth</h2><p className="mt-1 text-xs text-text-muted">Current CFYTD versus LFYTD, filtered by your dashboard selection.</p></div>
              <label className="flex items-center gap-2 text-xs font-semibold text-text-secondary">Stores to show
                <select aria-label="Number of stores to show" value={storeLimit} onChange={(event) => setStoreLimit(Number(event.target.value))} className="rounded-md border border-border bg-surface px-3 py-2 text-text-primary">{[5, 10, 20, 50].map((count) => <option key={count} value={count}>{count}</option>)}</select>
              </label>
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              {[{ title: "Top growing stores", rows: growingStores, positive: true }, { title: "Top declining stores", rows: decliningStores, positive: false }].map((section) => (
                <section key={section.title} className="overflow-hidden rounded-lg border border-border">
                  <h3 className={`border-b border-border px-4 py-3 text-xs font-bold uppercase tracking-wide ${section.positive ? "text-positive" : "text-negative"}`}>{section.title}</h3>
                  {section.rows.length ? <ol className="divide-y divide-border">{section.rows.map((row, index) => <li key={`${row.name}-${index}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm"><span className="min-w-0 truncate text-text-primary">{index + 1}. {row.name}</span><span className={`shrink-0 font-bold tabular-nums ${section.positive ? "text-positive" : "text-negative"}`}>{row.growth > 0 ? "+" : ""}{row.growth.toFixed(1)}%</span></li>)}</ol> : <p className="px-4 py-5 text-sm text-text-muted">No stores in this group for the current filters.</p>}
                </section>
              ))}
            </div>
          </Card>
        </div>
      )}

    </div>
  );
}


