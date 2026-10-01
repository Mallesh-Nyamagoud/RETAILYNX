const fs = require('fs');
const path = 'src/pages/CssStockTracking.jsx';
const text = fs.readFileSync(path, 'utf8');

const oldStr = \<div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-6">
            <KpiCard
              label="Total Ordered"
              qty={k.total_ordered}
              metaVal={k.ordered_mrp_val}
              metaLabel="MRP Val"
              accent="accent"
              hint={\\\SUM(Order Form CURRENTQUANTITY)\\\\\\}
            />
            <KpiCard
              label="Total Dispatched"
              qty={k.total_dispatched}
              metaVal={k.dispatched_mrp_val}
              metaLabel="MRP Val"
              accent="teal"
              hint="Net Secondary qty · matched season"
            />
            <KpiCard
              label="Total Pending"
              qty={k.total_pending}
              metaVal={k.pending_mrp_val}
              metaLabel="MRP Val"
              accent="warn"
              hint="MAX(Ordered − Dispatched, 0)"
            />
            <KpiCard
              label="Dispatched But Not Ordered"
              qty={k.dbno_qty}
              metaVal={k.dbno_mrp_val}
              metaLabel="MRP Val"
              accent="negative"
              hint="Dispatch qty with no order-form style+season"
            />
            <KpiCard
              label="Dispatch %"
              pct={k.dispatch_pct}
              accent="positive"
              hint="Dispatched ÷ Ordered × 100"
            />
          </div>\;

const newStr = \          {/* Top Overview: Flagship Gauge Chart + KPIs */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 mb-6">
            <Card className="xl:col-span-4 p-5 flex flex-col justify-between border-border shadow-sm bg-gradient-to-br from-card to-card-hover relative overflow-hidden">
              <div className="absolute top-4 left-5 text-[11px] font-bold text-text-muted uppercase tracking-wider">
                Overall Performance
              </div>
              <div className="flex-1 flex items-center justify-center mt-6">
                <GaugeChart value={k.dispatch_pct} label="Dispatch %" />
              </div>
            </Card>

            <div className="xl:col-span-8 grid grid-cols-2 gap-4">
              <KpiCard
                label="Total Ordered"
                qty={k.total_ordered}
                metaVal={k.ordered_mrp_val}
                metaLabel="MRP Val"
                accent="accent"
                hint={\\\SUM(Order Form CURRENTQUANTITY)\\\\\\}
              />
              <KpiCard
                label="Total Dispatched"
                qty={k.total_dispatched}
                metaVal={k.dispatched_mrp_val}
                metaLabel="MRP Val"
                accent="teal"
                hint="Net Secondary qty � matched season"
              />
              <KpiCard
                label="Total Pending"
                qty={k.total_pending}
                metaVal={k.pending_mrp_val}
                metaLabel="MRP Val"
                accent="warn"
                hint="MAX(Ordered - Dispatched, 0)"
              />
              <KpiCard
                label="Dispatched But Not Ordered"
                qty={k.dbno_qty}
                metaVal={k.dbno_mrp_val}
                metaLabel="MRP Val"
                accent="negative"
                hint="Dispatch qty with no order-form style+season"
              />
            </div>
          </div>\;

fs.writeFileSync(path, text.replace(oldStr, newStr));
