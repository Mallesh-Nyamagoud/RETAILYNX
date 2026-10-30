import SalesAnalysisModule from "../components/analysis/SalesAnalysisModule";
import { secondaryApi } from "../api/client";

const MONTHWISE_MEASURES = [
  { key: "qty", label: "Quantity" },
  { key: "val", label: "Taxable Value" },
];

export default function SecondaryAnalysis({ initialTab = "billing" }) {
  return (
    <SalesAnalysisModule
      title="Secondary Billing Analysis"
      api={secondaryApi}
      monthwiseMeasureOptions={MONTHWISE_MEASURES}
      monthwiseDefaultMeasure="val"
      initialTab={initialTab}
      valueUnitLabel="Taxable Value (₹)"
      valueUnitTag="₹ Taxable Value"
    />
  );
}
