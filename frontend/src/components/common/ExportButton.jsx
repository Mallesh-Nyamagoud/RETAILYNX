import { Download } from "lucide-react";
import Button from "./Button";
import clsx from "clsx";

export function ExportButton({ onExport, label = "Export to Excel", loading, disabled = false }) {
  return (
    <Button variant="primary" size="md" icon={Download} onClick={onExport} loading={loading} disabled={disabled}>
      {label}
    </Button>
  );
}

export function UnitToggle({ value, onChange, valLabel = "Value (₹)", qtyLabel = "Quantity" }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-border-strong p-0.5 bg-surface">
      {["val", "qty"].map((u) => (
        <button
          key={u}
          type="button"
          onClick={() => onChange(u)}
          className={clsx(
            "px-3 py-1 text-xs font-semibold rounded-md transition-colors",
            value === u ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary"
          )}
        >
          {u === "val" ? valLabel : qtyLabel}
        </button>
      ))}
    </div>
  );
}
