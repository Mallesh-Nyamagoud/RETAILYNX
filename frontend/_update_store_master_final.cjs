const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

// 1. Clean the header and description
code = code.replace(/eyebrow="Module II \· Store Master"\s*/, '');
code = code.replace(/description="TER\.MIN\/TER\.MAX and Store Status are auto-derived from Tertiary Data \(L2L, Annualized, New, Closed \— NA for non-SIS\)\. Everything else is editable\."/, 'description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."');

// 2. Replace the old single KPI card with the new layout
code = code.replace(
  /<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">[\s\S]*?<\/div>\s*<Card className="mb-6">/,
  \<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <Card padded={false} className="relative overflow-hidden">
              <div className="absolute left-0 top-0 h-full w-2 bg-gradient-to-b from-accent to-accent-hover rounded-l-xl" />
              <div className="pl-6 pr-4 py-4">
                <p className="text-sm font-bold tracking-wider text-text-secondary uppercase">
                  Total Active Doors
                </p>
                <div className="mt-2">
                  <p className="font-display text-3xl font-bold tabular-nums leading-tight text-text-primary">
                    {kpis.total_active_doors?.toLocaleString() || 0}
                  </p>
                  <div className="mt-2 flex flex-col gap-1">
                    <p className="text-[13px] text-text-secondary tabular-nums font-medium">
                      <span className="text-text-muted font-semibold uppercase tracking-wide">SIS: </span>
                      <span className="text-teal">
                        {((kpis.by_status?.L2L || 0) + (kpis.by_status?.Annualized || 0) + (kpis.by_status?.New || 0)).toLocaleString()}
                      </span>
                    </p>
                    <p className="text-[13px] text-text-secondary tabular-nums font-medium">
                      <span className="text-text-muted font-semibold uppercase tracking-wide">NON-SIS: </span>
                      <span className="text-warn">
                        {(kpis.by_status?.NA || 0).toLocaleString()}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <Card className="mb-6">\
);

// 3. Update the summary table style
code = code.replace(
  /<table className="min-w-full text-left text-sm">[\s\S]*?<\/table>/,
  \<table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b-2 border-border text-text-secondary bg-surface/50">
                    <th className="py-3 px-4 font-semibold text-left rounded-tl-lg">Brand</th>
                    <th className="py-3 px-4 font-semibold text-right">Total Active Doors</th>
                    <th className="py-3 px-4 font-semibold text-right text-teal">L2L</th>
                    <th className="py-3 px-4 font-semibold text-right text-accent">Annualized</th>
                    <th className="py-3 px-4 font-semibold text-right text-positive">New</th>
                    <th className="py-3 px-4 font-semibold text-right rounded-tr-lg">Non-SIS</th>
                  </tr>
                </thead>
                <tbody>
                  {(kpis.brand_summary || []).map((row) => (
                    <tr key={row.brand} className="border-b border-border/40 hover:bg-card-hover transition-colors group">
                      <td className="py-3 px-4 font-semibold text-text-primary group-hover:text-accent transition-colors">{row.brand || "Unknown"}</td>
                      <td className="py-3 px-4 tabular-nums text-right font-medium">{row.total_active_doors ?? 0}</td>
                      <td className="py-3 px-4 tabular-nums text-right text-text-secondary">{row.l2l ?? 0}</td>
                      <td className="py-3 px-4 tabular-nums text-right text-text-secondary">{row.annualized ?? 0}</td>
                      <td className="py-3 px-4 tabular-nums text-right text-text-secondary">{row.new ?? 0}</td>
                      <td className="py-3 px-4 tabular-nums text-right text-text-secondary">{row.non_sis ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>\
);

fs.writeFileSync(file, code);
