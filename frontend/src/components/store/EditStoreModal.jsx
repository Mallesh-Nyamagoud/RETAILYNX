import { useState } from "react";
import { X, Save } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Button from "../common/Button";
import { storeMasterApi } from "../../api/client";
import { statusTone } from "../common/Badge";
import Badge from "../common/Badge";

const ADMIN_PASSWORD = "ADONIS@13719";
const READ_ONLY_COLUMNS = new Set([
  "adonis_store_code",
  "brand_code",
  "ter_min_date",
  "ter_max_date",
  "store_status",
]);

export default function EditStoreModal({ row, columns, onClose }) {
  const [values, setValues] = useState(() => {
    const initial = {};
    for (const c of columns) {
      if (!READ_ONLY_COLUMNS.has(c.name)) initial[c.name] = row[c.name] ?? "";
    }
    return initial;
  });
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => {
      if (password !== ADMIN_PASSWORD) {
        throw new Error("Admin password required to make changes.");
      }
      return storeMasterApi.update(row.adonis_store_code, row.brand_code, values, password);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["store-master"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-card border border-border rounded-xl2 shadow-panel-lg w-full max-w-lg animate-fadeIn max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div>
            <p className="font-display font-semibold text-text-primary">Edit Store</p>
            <p className="text-xs text-text-muted mt-0.5">
              {row.adonis_store_code} · {row.brand_code}
            </p>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3 overflow-y-auto">
          <div className="flex items-center gap-2 p-3 rounded-lg bg-surface border border-border text-xs">
            <span className="text-text-muted">Store Status (auto-computed):</span>
            <Badge tone={statusTone(row.store_status)}>{row.store_status || "Unknown"}</Badge>
            <span className="text-text-muted ml-auto">
              {row.ter_min_date || "—"} → {row.ter_max_date || "—"}
            </span>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide mb-1 text-text-secondary">
              Admin password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setPasswordError("");
              }}
              placeholder="Enter admin password"
              className="w-full px-3 py-2 rounded-lg border border-border-strong bg-surface text-sm text-text-primary outline-none focus:border-accent"
            />
            {password && password !== ADMIN_PASSWORD && (
              <p className="mt-1 text-[11px] text-negative">Password incorrect</p>
            )}
          </div>

          {columns
            .filter((c) => !READ_ONLY_COLUMNS.has(c.name))
            .map((c) => (
              <div key={c.name}>
                <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wide mb-1">
                  {c.name.replace(/_/g, " ")}
                </label>
                <input
                  value={values[c.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [c.name]: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg border border-border-strong bg-surface text-sm text-text-primary outline-none focus:border-accent"
                />
              </div>
            ))}

          {passwordError && <p className="text-xs text-negative">{passwordError}</p>}
          {mutation.isError && <p className="text-xs text-negative">{mutation.error.message}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-border shrink-0">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            icon={Save}
            loading={mutation.isPending}
            onClick={() => {
              if (password !== ADMIN_PASSWORD) {
                setPasswordError("Admin password required to make changes.");
                return;
              }
              mutation.mutate();
            }}
          >
            Save changes
          </Button>
        </div>
      </div>
    </div>
  );
}
