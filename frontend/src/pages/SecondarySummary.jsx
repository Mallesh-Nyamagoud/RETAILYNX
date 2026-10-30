import { useState } from "react";
import { BarChart3, Store, UsersRound } from "lucide-react";
import SalesAnalysisModule from "../components/analysis/SalesAnalysisModule";
import PageHeader from "../components/layout/PageHeader";
import { secondaryApi } from "../api/client";

const views = [
  { dimension: "brand", label: "Brand comparison", icon: BarChart3 },
  { dimension: "store_type", label: "Store type performance", icon: Store },
  { dimension: "store_status", label: "Store status performance", icon: UsersRound },
];
const measures = [
  { key: "qty", label: "Quantity" },
  { key: "val", label: "Taxable Value" },
];

export default function SecondarySummary() {
  const [active, setActive] = useState("brand");
  const selected = views.find((view) => view.dimension === active) || views[0];
  return <main className="space-y-5">
    <PageHeader eyebrow="SECONDARY SALES" title="Secondary Sales Summary" description="Compare brand, store type, and store status performance across fiscal years." />
    <nav aria-label="Secondary summary views" className="flex gap-1 overflow-x-auto border-b border-border">
      {views.map(({ dimension, label, icon: Icon }) => <button key={dimension} type="button" onClick={() => setActive(dimension)} className={"inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold " + (active === dimension ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-primary")}>
        <Icon size={15}/>{label}
      </button>)}
    </nav>
    <SalesAnalysisModule
      key={selected.dimension}
      eyebrow="SECONDARY SALES SUMMARY"
      title={selected.label}
      description="Fiscal year comparison using secondary taxable value and quantity."
      api={secondaryApi}
      monthwiseMeasureOptions={measures}
      monthwiseDefaultMeasure="val"
      valueUnitLabel="Taxable Value (₹)"
      valueUnitTag="₹ Taxable Value"
      fixedDimensions={[selected.dimension]}
      hideTabs
      showPageHeader={false}
    />
  </main>;
}
