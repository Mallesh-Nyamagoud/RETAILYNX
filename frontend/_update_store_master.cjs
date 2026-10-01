const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

// 1. Remove eyebrow and clean up description in PageHeader
code = code.replace(/eyebrow="Module II \· Store Master"\s*/, '');
code = code.replace(/description="TER\.MIN\/TER\.MAX and Store Status are auto-derived from Tertiary Data \(L2L, Annualized, New, Closed \— NA for non-SIS\)\. Everything else is editable\."/, 'description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."');

// 2. Remove hint from KPI card
code = code.replace(/hint="Distinct store codes with at least one brand L2L \/ Annualized \/ New \(counted once per store, irrespective of brands\)"/, '');

// 3. Upgrade the Brand-wise Summary Table
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
