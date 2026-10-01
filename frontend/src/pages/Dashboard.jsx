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
  const storeTypeQ = useQuery({
    queryKey: ["dashboard", "store_type", storeTypeFilters],
    queryFn: () => secondaryApi.pivot(["store_type"], storeTypeFilters),
  });

  const secondaryTotal = secondaryQ.data?.rows?.[0];
  const tertiaryTotal = tertiaryQ.data?.rows?.[0];
  const loading =
    secondaryQ.isLoading || tertiaryQ.isLoading || storeQ.isLoading || cssQ.isLoading;
  const chartsLoading =
    brandQ.isLoading || groupQ.isLoading || deptQ.isLoading || stateQ.isLoading || storeTypeQ.isLoading;

  const brandData = useMemo(() => toComparisonData(brandQ.data?.rows, "brand"), [brandQ.data]);
  const groupData = useMemo(() => toComparisonData(groupQ.data?.rows, "group"), [groupQ.data]);
  const deptData = useMemo(() => toDonutData(deptQ.data?.rows, "department"), [deptQ.data]);
  const stateData = useMemo(() => toDonutData(stateQ.data?.rows, "state"), [stateQ.data]);
  const storeTypeData = useMemo(
    () => toDonutData(storeTypeQ.data?.rows, "store_type"),
    [storeTypeQ.data]
  );

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
          />
        </div>
      )}

      {chartsLoading ? (
        <Card className="flex h-64 items-center justify-center">
          <LoadingState />
        </Card>
      ) : (
        <div className="space-y-6">
          <ComparisonBarChart
            title="Brandwise Taxable Value Comparison"
            eyebrow="Secondary Sales · Taxable Value"
            dataTestId="dash-brand-comparison"
            data={brandData}
            {...crossFilterProps("brand")}
          />

          <ComparisonBarChart
            title="Groupwise Taxable Value Comparison"
            eyebrow="Secondary Sales · Taxable Value"
            dataTestId="dash-group-comparison"
            data={groupData}
            {...crossFilterProps("group")}
          />

          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            <ContributionDonutChart
              title="Departmentwise Cont %"
              dataTestId="dash-dept-donut"
              data={deptData}
              {...crossFilterProps("department")}
            />
            <ContributionDonutChart
              title="Statewise Cont %"
              dataTestId="dash-state-donut"
              data={stateData}
              {...crossFilterProps("state")}
            />
            <ContributionDonutChart
              title="Store Type Cont %"
              dataTestId="dash-store-type-donut"
              data={storeTypeData}
              {...crossFilterProps("store_type")}
            />
          </div>
        </div>
      )}

    </div>
  );
}


