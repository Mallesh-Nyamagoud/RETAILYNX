import { useState } from "react";
import { BarChart3, CalendarRange, Store, UsersRound } from "lucide-react";
import SalesAnalysisModule from "../components/analysis/SalesAnalysisModule";
import { secondaryApi } from "../api/client";
import PageHeader from "../components/layout/PageHeader";

const views = [
  { dimension: null, label: "Monthwise Analysis", icon: CalendarRange },
  { dimension: "brand", label: "Brandwise Analysis", icon: BarChart3 },
  { dimension: "retailer_name", label: "Storewise Analysis", icon: Store },
  { dimension: "department", label: "Departmentwise Analysis", icon: BarChart3 },
  { dimension: "state", label: "Statewise Analysis", icon: Store },
  { dimension: "store_type", label: "Store Type Performance", icon: Store },
  { dimension: "store_status", label: "Store Status Performance", icon: UsersRound },
];
const measures = [
  { key: "qty", label: "Quantity" },
  { key: "val", label: "Taxable Value" },
];

export default function SecondaryMonthwise() {
  const [active, setActive] = useState(null);
  const selected = views.find((view) => view.dimension === active) || views[0];
  const dimensions = selected.dimension ? [selected.dimension] : [];

  return (
    <main className="space-y-5">
      <PageHeader eyebrow="SECONDARY SALES" title="Secondary Monthwise Analysis" description="Review monthly quantity and taxable value by brand, store, department, state, store type, or store status." />
      <nav aria-label="Secondary monthwise views" className="flex gap-1 overflow-x-auto border-b border-border">
        {views.map(({ dimension, label, icon: Icon }) => (
          <button
            key={dimension || "monthwise"}
            type="button"
            onClick={() => setActive(dimension)}
            className={"inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold " + (active === dimension ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}
          >
            <Icon size={15} />{label}
          </button>
        ))}
      </nav>
      <SalesAnalysisModule
        key={selected.dimension || "monthwise"}
        eyebrow="SECONDARY SALES"
        title={selected.label}
        description="Monthly secondary sales by quantity and taxable value."
        api={secondaryApi}
        monthwiseMeasureOptions={measures}
        monthwiseDefaultMeasure="val"
        initialTab="monthwise"
        fixedDimensions={dimensions}
        hideTabs
        showPageHeader={false}
        valueUnitLabel="Taxable Value (₹)"
        valueUnitTag="₹ Taxable Value"
      />
    </main>
  );
}
