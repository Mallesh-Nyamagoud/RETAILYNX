import SalesAnalysisModule from "../components/analysis/SalesAnalysisModule";
import { tertiaryApi } from "../api/client";

export default function TertiaryAnalysis() {
  return (
    <SalesAnalysisModule
      title="Tertiary Sales Analysis"
      api={tertiaryApi}
      monthwiseVariant="rows"
      enableBillAnalysis
      enableCategoryPerformance
    />
  );
}
