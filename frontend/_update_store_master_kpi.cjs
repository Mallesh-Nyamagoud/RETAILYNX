const fs = require('fs');
const file = 'src/pages/StoreMaster.jsx';
let code = fs.readFileSync(file, 'utf8');

// Replace the KPI Card section with the new dual-KPI layout
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

fs.writeFileSync(file, code);
