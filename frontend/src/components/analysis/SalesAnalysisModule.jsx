import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, CalendarRange, ReceiptText, TrendingUp } from "lucide-react";
import PageHeader from "../layout/PageHeader";
import Card from "../common/Card";
import DimensionPicker from "../common/DimensionPicker";
import FilterPanel from "../common/FilterPanel";
import { ExportButton } from "../common/ExportButton";
import { LoadingState, KpiSkeleton, ErrorState, EmptyState } from "../common/LoadingState";
import KpiCard from "../common/KpiCard";
import PivotTable from "./PivotTable";
import MonthwiseTable from "./MonthwiseTable";
import MonthwiseRowsTable from "./MonthwiseRowsTable";
import BillNoAnalysis from "./BillNoAnalysis";
import CategoryPerformance from "./CategoryPerformance";
import { fmtDate } from "../../utils/format";
import clsx from "clsx";

// Presentation-only metadata. Values come straight from the pivot grand total
// (`${key}_val` / `${key}_qty`) - no calculation happens here. `isPct` KPIs are
// percentages stored in the same _val/_qty pair and always render with "%".
// Labels mirror the backend measure meta exactly so the KPI cards and the
// summary/detailed table stay identical.
const KPI_DEFS = [
  { key: "lfy_full", label: "LFY Full", accent: "accent" },
  { key: "lfytd", label: "LFYTD", accent: "accent" },
  { key: "cfytd", label: "CFYTD", accent: "teal" },
  { key: "growth_pct", label: "Growth %", accent: "positive", isPct: true },
  { key: "balance", label: "Balance", accent: "warn" },
  { key: "apm", label: "APM", isApmCard: true },
  { key: "apm_growth_pct", label: "APM Growth %", accent: "positive", isPct: true },
  { key: "trending", label: "Trending (Proj. Full Year)", accent: "warn" },
  { key: "proj_growth_pct", label: "Proj. Growth %", accent: "positive", isPct: true },
];

function findGrandTotal(rows, hasDims) {
  if (!rows || rows.length === 0) return null;
  if (!hasDims) return rows[0];
  return rows.find((r) => r._is_total) || null;
}

export default function SalesAnalysisModule({
  eyebrow,
  title,
  description,
  api,
  monthwiseMeasureOptions,
  /** Label for the ₹ unit toggle in the detailed table (e.g. "Taxable Value (₹)") */
  valueUnitLabel = "Value (₹)",
  /** Small unit badge shown on monetary KPI cards (e.g. "₹ Taxable Value") */
  valueUnitTag = "₹ Value",
  /** Measure key selected by default in the Monthwise table */
  monthwiseDefaultMeasure,
  /** "columns" (LFY/CFY/Growth per month) or "rows" (months as rows with all
   * measures as columns) - Tertiary uses "rows". */
  monthwiseVariant = "columns",
  enableBillAnalysis = false,
  enableCategoryPerformance = false,
}) {
  const [tab, setTab] = useState("billing");
  const [dimensions, setDimensions] = useState([]);
  const [filters, setFilters] = useState({});

  const dimCatalogQ = useQuery({
    queryKey: [eyebrow, "dimensions"],
    queryFn: api.dimensions,
  });
  const slicersQ = useQuery({
    queryKey: [eyebrow, "slicers"],
    queryFn: api.slicers,
  });

  const pivotQ = useQuery({
    queryKey: [eyebrow, "pivot", dimensions, filters],
    queryFn: () => api.pivot(dimensions, filters),
  });

  const monthwiseQ = useQuery({
    queryKey: [eyebrow, "monthwise", dimensions, filters],
    queryFn: () => api.monthwise(dimensions, filters),
    enabled: tab === "monthwise",
  });

  const dimensionLabels = useMemo(() => {
    const cat = dimCatalogQ.data?.dimensions || [];
    return Object.fromEntries(cat.map((d) => [d.column, d.label]));
  }, [dimCatalogQ.data]);

  const grandTotal = findGrandTotal(pivotQ.data?.rows, dimensions.length > 0);
  const fyContext = pivotQ.data?.fy_context;

  const [exporting, setExporting] = useState(false);
  async function handleExport() {
    setExporting(true);
    try {
      await api.export(dimensions, filters, ["billing", "monthwise"]);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={<ExportButton onExport={handleExport} loading={exporting} />}
      />

      {fyContext && (
        <div className="flex items-center gap-4 mb-5 text-xs text-text-secondary flex-wrap">
          <span className="flex items-center gap-1.5">
            <CalendarRange size={13} className="text-accent" />
            Current FY: <span className="font-semibold text-text-primary">{fyContext.current_fy_label}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <TrendingUp size={13} className="text-teal" />
            Last FY: <span className="font-semibold text-text-primary">{fyContext.last_fy_label}</span>
          </span>
          <span>
            Data as of <span className="font-medium text-text-primary">{fmtDate(fyContext.max_date)}</span>
          </span>
        </div>
      )}

      <Card className="mb-5" padded>
        <div className="flex flex-col gap-4">
          {dimCatalogQ.isLoading ? (
            <LoadingState rows={1} />
          ) : (
            <DimensionPicker
              dimensions={dimCatalogQ.data?.dimensions || []}
              value={dimensions}
              onChange={setDimensions}
            />
          )}
          {slicersQ.data?.slicers && (
            <FilterPanel
              slicers={slicersQ.data.slicers}
              dimensionLabels={dimensionLabels}
              value={filters}
              onChange={setFilters}
            />
          )}
        </div>
      </Card>

      {/* KPI cards - flagship look; monetary KPIs showcase the taxable-value
          metric (with its Qty companion), growth KPIs always render "%" */}
      {pivotQ.isLoading ? (
        <div className="mb-6">
          <KpiSkeleton count={10} />
        </div>
      ) : pivotQ.isError ? (
        <Card className="mb-6">
          <ErrorState message={pivotQ.error.message} onRetry={() => pivotQ.refetch()} />
        </Card>
      ) : grandTotal ? (
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3 mb-6">
          {KPI_DEFS.map((k) =>
            k.isPct ? (
              <KpiCard
                key={k.key}
                label={k.label}
                pct={grandTotal[`${k.key}_val`]}
                qtyPct={grandTotal[`${k.key}_qty`]}
                accent={k.accent}
              />
            ) : k.isApmCard ? (
              <KpiCard
                key={k.key}
                label={k.label}
                isApmCard={true}
                unitTag={valueUnitTag}
                apmData={{
                  lfy: { val: grandTotal.pfapm_val, qty: grandTotal.pfapm_qty },
                  lfytd: { val: grandTotal.lfytd_apm_val, qty: grandTotal.lfytd_apm_qty },
                  cfytd: { val: grandTotal.cfapm_val, qty: grandTotal.cfapm_qty },
                }}
              />
            ) : (
              <KpiCard
                key={k.key}
                label={k.label}
                qty={grandTotal[`${k.key}_qty`]}
                val={grandTotal[`${k.key}_val`]}
                unitTag={valueUnitTag}
                accent={k.accent}
              />
            )
          )}
        </div>
      ) : (
        <Card className="mb-6">
          <EmptyState title="No data yet" description="Adjust filters to see KPI figures." />
        </Card>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {[
          { key: "billing", label: title, icon: BarChart3 },
          { key: "monthwise", label: "Monthwise Sales", icon: CalendarRange },
          ...(enableBillAnalysis ? [{ key: "bills", label: "Bill No. Based Analysis", icon: ReceiptText }] : []),
          ...(enableCategoryPerformance ? [{ key: "category", label: "Category Performance", icon: TrendingUp }] : []),
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.key
                ? "border-accent text-accent"
                : "border-transparent text-text-secondary hover:text-text-primary"
            )}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      <Card padded={false} className="overflow-hidden">
        <div className="p-4">
          {tab === "billing" &&
            (pivotQ.isLoading ? (
              <LoadingState rows={8} />
            ) : pivotQ.isError ? (
              <ErrorState message={pivotQ.error.message} onRetry={() => pivotQ.refetch()} />
            ) : (
              <PivotTable
                result={pivotQ.data}
                dimensionLabels={dimensionLabels}
                unitValLabel={valueUnitLabel}
              />
            ))}
          {enableBillAnalysis && tab === "bills" && (
            /* Row Hierarchy + global slicers are the ONLY inputs this section
               takes - it renders no filter/slicer/hierarchy controls of its
               own, exactly like Category Performance. */
            <BillNoAnalysis api={api} filters={filters} hierarchy={dimensions} eyebrow={eyebrow} />
          )}
          {enableCategoryPerformance && tab === "category" && (
            /* Row Hierarchy + global slicers are the ONLY inputs this section
               takes - it renders no filter/slicer controls of its own. */
            <CategoryPerformance
              api={api}
              filters={filters}
              hierarchy={dimensions}
              eyebrow={eyebrow}
            />
          )}
          {tab === "monthwise" &&
            (monthwiseVariant === "rows" ? (
              monthwiseQ.isLoading ? (
                <LoadingState rows={8} />
              ) : monthwiseQ.isError ? (
                <ErrorState message={monthwiseQ.error.message} onRetry={() => monthwiseQ.refetch()} />
              ) : (
                <MonthwiseRowsTable
                  result={monthwiseQ.data}
                  dimensionLabels={dimensionLabels}
                />
              )
            ) : monthwiseQ.isLoading ? (
              <LoadingState rows={8} />
            ) : monthwiseQ.isError ? (
              <ErrorState message={monthwiseQ.error.message} onRetry={() => monthwiseQ.refetch()} />
            ) : (
              <MonthwiseTable
                result={monthwiseQ.data}
                measureOptions={monthwiseMeasureOptions}
                dimensionLabels={dimensionLabels}
                defaultMeasure={monthwiseDefaultMeasure}
              />
            ))}
        </div>
      </Card>
    </div>
  );
}
