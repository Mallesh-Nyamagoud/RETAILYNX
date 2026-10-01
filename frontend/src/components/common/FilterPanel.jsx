import { useMemo, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import clsx from "clsx";

function MultiSelectFilter({ label, options, selected = [], onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filteredOptions = useMemo(() => {
    if (!query) return options;
    const q = query.toLowerCase();
    return options.filter((o) => String(o).toLowerCase().includes(q));
  }, [options, query]);

  function toggle(opt) {
    if (selected.includes(opt)) onChange(selected.filter((v) => v !== opt));
    else onChange([...selected, opt]);
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors",
          selected.length > 0
            ? "border-accent/40 bg-accent-soft text-accent"
            : "border-border-strong text-text-secondary hover:text-text-primary"
        )}
      >
        {label}
        {selected.length > 0 && (
          <span className="bg-accent text-white rounded-full px-1.5 text-[10px] leading-4">
            {selected.length}
          </span>
        )}
        <ChevronDown size={13} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute z-20 mt-1 left-0 w-64 bg-card border border-border rounded-lg shadow-panel-lg animate-fadeIn overflow-hidden">
            <div className="p-2 border-b border-border flex items-center gap-2">
              <Search size={13} className="text-text-muted shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${label.toLowerCase()}…`}
                className="w-full bg-transparent text-sm outline-none text-text-primary placeholder:text-text-muted"
              />
            </div>
            <div className="max-h-64 overflow-y-auto py-1">
              {filteredOptions.length === 0 && (
                <p className="px-3 py-3 text-xs text-text-muted">No matches</p>
              )}
              {filteredOptions.map((opt) => (
                <label
                  key={opt}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-primary hover:bg-card-hover cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(opt)}
                    onChange={() => toggle(opt)}
                    className="accent-[color:var(--color-accent)]"
                  />
                  <span className="truncate">{opt}</span>
                </label>
              ))}
            </div>
            {selected.length > 0 && (
              <div className="border-t border-border p-1.5">
                <button
                  type="button"
                  onClick={() => onChange([])}
                  className="w-full text-xs text-text-secondary hover:text-negative py-1"
                >
                  Clear {label.toLowerCase()}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Cross-filter aware slicers (multi-select).
 *
 * slicers:         {column: [values...]} - the AVAILABLE options per column,
 *                  already narrowed server-side by every OTHER applied filter
 *                  (cross-filtering), so picking e.g. a state immediately
 *                  narrows the retailer/brand/store-type option lists.
 * dimensionLabels: {column: label}
 * value:           {column: [selected values]} - multi-select per column.
 */
export default function FilterPanel({ slicers = {}, dimensionLabels = {}, value = {}, onChange }) {
  const columns = Object.keys(slicers);
  if (columns.length === 0) return null;

  function setColumn(col, values) {
    const next = { ...value };
    if (values.length === 0) delete next[col];
    else next[col] = values;
    onChange(next);
  }

  const activeCount = Object.values(value).reduce((acc, v) => acc + (v?.length || 0), 0);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {columns.map((col) => (
        <MultiSelectFilter
          key={col}
          label={dimensionLabels[col] || col}
          options={slicers[col] || []}
          selected={value[col] || []}
          onChange={(vals) => setColumn(col, vals)}
        />
      ))}
      {activeCount > 0 && (
        <button
          type="button"
          onClick={() => onChange({})}
          className="flex items-center gap-1 text-xs text-text-muted hover:text-negative"
        >
          <X size={12} />
          Clear all filters
        </button>
      )}
    </div>
  );
}