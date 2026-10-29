import { useQuery } from "@tanstack/react-query";
import { Activity, Clock3, LogIn, Users } from "lucide-react";
import { http } from "../api/client";

function stamp(value) {
  return value ? new Date(value * 1000).toLocaleString() : "—";
}

function duration(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function DataCard({ title, rows, loading }) {
  return (
    <section className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="font-semibold text-text-primary">{title}</h3>
        <p className="text-xs text-text-muted mt-1">Latest date available for each brand</p>
      </div>
      {loading ? <p className="p-5 text-sm text-text-muted">Loading brand dates…</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-base/50 text-[11px] uppercase tracking-wider text-text-muted">
              <tr><th className="px-5 py-3">Brand name</th><th className="px-5 py-3 text-right">Latest data date</th></tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {rows?.map((row) => <tr key={row.brand_name}>
                <td className="px-5 py-3 font-medium text-text-primary">{row.brand_name}</td>
                <td className="px-5 py-3 text-right text-text-secondary">{row.max_date ? String(row.max_date).slice(0, 10) : "—"}</td>
              </tr>)}
              {!rows?.length && <tr><td colSpan={2} className="px-5 py-6 text-center text-text-muted">No brand data available</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function AdminOverview() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => http.get("/auth/admin/overview").then((response) => response.data),
    refetchInterval: 60_000,
  });
  const sessions = data?.sessions || [];
  const active = sessions.filter((session) => session.is_active).length;
  const interactions = sessions.reduce((sum, session) => sum + session.interaction_count, 0);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-accent">Administration</p>
        <h2 className="text-2xl font-display font-bold text-text-primary mt-1">Usage overview</h2>
        <p className="text-sm text-text-secondary mt-1">Account activity and the latest dates represented in each sales dataset.</p>
      </div>

      {error && <div className="rounded-lg border border-negative/30 bg-negative-soft px-4 py-3 text-sm text-negative">Could not load admin activity: {error.message}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Accounts currently active", value: active, icon: Users },
          { label: "Recorded sessions", value: sessions.length, icon: LogIn },
          { label: "API interactions", value: interactions.toLocaleString(), icon: Activity },
        ].map(({ label, value, icon: Icon }) => <div key={label} className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center justify-between text-text-muted"><span className="text-xs font-semibold uppercase tracking-wider">{label}</span><Icon size={17} /></div>
          <div className="mt-3 text-3xl font-display font-bold text-text-primary">{value}</div>
        </div>)}
      </div>

      <section className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <div><h3 className="font-semibold text-text-primary">Login activity</h3><p className="text-xs text-text-muted mt-1">Latest 500 sessions · interaction count includes authenticated API requests</p></div>
          <Clock3 size={18} className="text-text-muted" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-base/50 text-[11px] uppercase tracking-wider text-text-muted">
              <tr><th className="px-5 py-3">Account</th><th className="px-5 py-3">Google email</th><th className="px-5 py-3">Method</th><th className="px-5 py-3">Login time</th><th className="px-5 py-3">Logout time</th><th className="px-5 py-3">Time used</th><th className="px-5 py-3 text-right">Interactions</th><th className="px-5 py-3">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {sessions.map((session) => <tr key={session.id} className="hover:bg-card-hover/40">
                <td className="px-5 py-3 font-medium text-text-primary">{session.username}</td>
                <td className="px-5 py-3 text-text-secondary">{session.google_email || "?"}</td>
                <td className="px-5 py-3 text-text-secondary capitalize">{session.auth_method || "password"}</td>
                <td className="px-5 py-3 text-text-secondary">{stamp(session.login_at)}</td>
                <td className="px-5 py-3 text-text-secondary">{stamp(session.logout_at)}</td>
                <td className="px-5 py-3 text-text-secondary">{duration(session.duration_seconds)}</td>
                <td className="px-5 py-3 text-right tabular-nums text-text-secondary">{session.interaction_count}</td>
                <td className="px-5 py-3"><span className={`px-2 py-1 rounded-full text-[11px] font-semibold ${session.is_active ? "bg-positive-soft text-positive" : "bg-base text-text-muted"}`}>{session.is_active ? "Active" : "Signed out"}</span></td>
              </tr>)}
              {!sessions.length && <tr><td colSpan={8} className="px-5 py-8 text-center text-text-muted">{isLoading ? "Loading activity…" : "No login activity recorded yet."}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <DataCard title="Tertiary data" rows={data?.tertiary} loading={isLoading} />
        <DataCard title="Secondary data" rows={data?.secondary} loading={isLoading} />
      </div>
    </div>
  );
}