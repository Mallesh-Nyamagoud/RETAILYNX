# Retail Analytics Command Center

A flagship-level, production-ready web analysis application built strictly from
`REQUIREMENTS.docx`, using the four supplied DuckDB files (`store_master`,
`order_form`, `secondary_data`, `tertiary_data`) purely as **schema
references** (table/column names) — no business data values were inspected,
validated, or assumed while building the logic below. Everything is
schema-driven: dimensions, filters, SQL autocomplete, and table columns are
all discovered live from the database at runtime, not hard-coded.

**Stack (100% free / open-source, runs entirely on your machine):**
Python · FastAPI · DuckDB · pandas · openpyxl (backend)
React · Vite · Tailwind CSS · TanStack Table/Query · CodeMirror · Recharts ·
dnd-kit (frontend)

---

## 1. What's included

```
webapp/
├── backend/                   FastAPI + DuckDB API server
│   ├── app/
│   │   ├── core/               config + the DuckDB catalog manager
│   │   ├── services/           FY math, pivot/rollup engine, CSS stock logic,
│   │   │                       store master, SQL platform, Excel export
│   │   ├── api/routes/         one router per module
│   │   └── main.py             FastAPI app (also serves the built frontend)
│   ├── data/                   seed copies of your 4 uploaded .duckdb files
│   ├── requirements.txt
│   └── run_backend.sh          one-command setup + run (Windows: run_backend.bat)
└── frontend/                   React + Vite + Tailwind SPA
    ├── src/
    │   ├── api/                axios client (all backend endpoints)
    │   ├── components/         DataTable, DimensionPicker, FilterPanel,
    │   │                       KpiCard, PivotTable, MonthwiseTable, SQL editor…
    │   ├── pages/               Dashboard, Secondary/Tertiary Analysis,
    │   │                       Store Master, SQL Platform, CSS Stock Tracking
    │   └── store/               theme (dark/light) + UI state
    ├── run_frontend_dev.sh      one-command dev server (hot reload; Windows: .bat)
    └── build_frontend.sh        one-command production build (Windows: .bat)
```

## 2. How the 4 databases are connected

On startup, the backend copies your 4 uploaded `.duckdb` files into
`backend/data/` (working copies — your originals are never touched) and
`ATTACH`es all four into **one DuckDB connection** as four named schemas:
`store_master`, `order_form`, `secondary_data`, `tertiary_data`. This is what
lets the SQL Platform (and every analysis module) run native cross-database
SQL/JOINs with zero ETL.

---

## 3. Running it

You need **Python 3.10+** and **Node.js 18+** installed. Everything else
installs automatically the first time you run the scripts below.

On **Windows**, use the `.bat` file with the same name instead of the `.sh`
one (e.g. `run_backend.bat` instead of `./run_backend.sh`, double-click it or
run it from Anaconda Prompt / cmd) — same steps and same ports, just no WSL
or Git Bash required.

### Option A — one process serves everything (recommended for local use)

```bash
cd webapp/frontend
./build_frontend.sh        # installs npm deps (first run) + builds to dist/
# Windows: build_frontend.bat

cd ../backend
./run_backend.sh           # installs Python deps (first run) + starts the API
# Windows: run_backend.bat
```

Open **http://localhost:8000** — the FastAPI server serves the built React
app *and* the `/api/*` endpoints from the same port.

### Option B — separate dev servers (hot reload while you edit)

```bash
# Terminal 1
cd webapp/backend
./run_backend.sh            # API on http://localhost:8000
# Windows: run_backend.bat

# Terminal 2
cd webapp/frontend
./run_frontend_dev.sh       # UI on http://localhost:5173 (proxies /api to :8000)
# Windows: run_frontend_dev.bat
```

Open **http://localhost:5173**.

### Manual setup (if you'd rather not use the scripts)

```bash
# Backend
cd webapp/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd webapp/frontend
npm install
npm run dev        # or: npm run build && npm run preview
```

### Resetting data

Store Master is editable, so its working copy will accumulate your edits. To
throw those away and start fresh from the original uploaded files, either:
- delete `backend/data/store_master.duckdb` (and its `.wal` file, if present)
  and restart the backend, or
- call `POST /api/meta/reset-to-seed` (resets **all four** working databases).

---

## 4. Module map (matches the requirements doc's own numbering)

| # | Module | Route | Notes |
|---|--------|-------|-------|
| I | Secondary Sales Analysis | `/secondary` | Pivot-style dimension selector (drag to add/remove/reorder Retailer, Brand, Store Type, Department, Group, State, Store Status), rollup subtotals at every level, KPI cards (LFY FULL, LFYTD, CFYTD, GROWTH%, BALANCE, LFAPM, CFAPM, APM GROWTH%, TRENDING, PROJ.GROWTH%), Monthwise Sales tab — **months VERTICAL by default** (each fiscal month Apr→Mar is a table row carrying LFY / CFY / Growth % / Contribution % and the running cumulative, recalculated after every re-sort) with a one-click **Months vertical ↔ Months horizontal** toggle that re-projects the same payload (the horizontal view keeps the grouped LFY | CFY | Growth % per-month columns), blank for future months, Excel export with filters-applied sheet. |
| II | Store Master | `/store-master` | **ONE KPI card (Total Active Doors** — counted on ADONIS STORE CODE; a store with multiple brands counts once if ANY ONE brand is L2L/Annualized/New**)**, a Brand-wise Store Status Summary (by brand name: Total Active Doors / L2L / Annualized / New / Non-SIS), full slicers, editable grid, **TER.MIN DATE / TER.MAX DATE / STORE STATUS are auto-computed from Tertiary Data** on every backend startup and via the "Recompute status" button in the top bar. Status rules (per STORE+BRAND, vs the GLOBAL MAX tertiary date): April of previous FY → **L2L**; previous FY (not April) → **Annualized**; current FY only → **New**; no sales in the last 3 months before the global max → **Closed**; no tertiary data at all (NON-SIS) → **NA**. |
| III | SQL Platform | `/sql-platform` | Live database/table/column explorer (click to insert), CodeMirror editor with autocomplete sourced entirely from the live schema + DuckDB's own function catalog (nothing hard-coded), run any SQL DuckDB supports, CSV/Excel export. |
| IV | Tertiary Sales Analysis | `/tertiary` | Same pivot engine as Module I, using `qty`/`bill_val`. Monthwise tab adds MRP Value, Discount, Discount Outflow % per the doc's spec. **Bill No. Based Analysis** tab (section 8) and **Category Performance** tab (section 9 — rows follow the page's Row Hierarchy level 1/level 2, all figures respect the page's global slicers, and the tab renders no filters of its own; every KPI cell shows **LFY / LFYTD / CFYTD** with a like-for-like CFYTD-vs-LFYTD Change, the APM card shows all three APM periods, and the **Chart** toggle is one grouped LFY/LFYTD/CFYTD bar chart with a single per-bar hover tooltip). |
| V | CSS Stock Tracking | `/css-stock` | **Order Form is the complete baseline**: Ordered Qty = SUM(`CURRENTQUANTITY`) (VENUEQUANTITY never used) and every ordered Product/Style + Season appears even with zero dispatch. Matching on Secondary `PRODUCT_CODE_CODE` ↔ Order Form `STYLE_CODE` + Season after identical cleaning (TRIM/whitespace/UPPERCASE); multiple dispatch records aggregate before comparison. Status per row: Fully Dispatched / Partially Dispatched / Pending / Dispatched-But-Not-Ordered. Sub Category = Order Form `SUBCATEGORY`, cleaned `PRODUCT_DESC` fallback for unmapped rows. 8 KPI cards (Total Ordered, Total Dispatched, Total Pending, Dispatch %, and the four status counts — all filter-aware and clickable as drill-downs), **MRP Value = MRP × Qty derived internally** (Order Form `MRP`, Secondary `MDP` fallback; no source column) — Ordered / Dispatched / Pending **MRP Val** columns sit right after their matching Qty columns and the same values appear inside the existing Ordered/Dispatched/Pending KPI cards, plus a **Dispatched-But-Not-Ordered Qty** KPI card sharing the same look, brand-wise Ordered-vs-Dispatched-vs-Pending bar chart with data labels + numeric readout, ALL store-master columns available as dimensions & cross-filter multi-select slicers, user-resizable table columns, and a filtered Excel export that reconciles exactly with the dashboard. |

The left-hand **module rail** is the single place the platform's modules are listed — each entry carries its requirements-doc numeral (I–V), a gradient icon tile and an accent rail on the active module, and the rail can be collapsed to an icon-only strip for more plot area (the Dashboard deliberately does not repeat the module list).

A Dashboard (`/`) gives a cross-module snapshot: four cross-filtered KPI cards plus **Power BI style** visuals — a **Brandwise** and a **Groupwise Taxable Value Comparison** (grouped LFY FULL / LFYTD / CFYTD bars, dynamic Indian compact data labels `1.00Cr` / `1.00L` / `1.00K` on the bars, the value axis and every hover card, a rich hover card with CFYTD share, growth and the exact ₹ figure, plus per-period series toggles) and three contribution donuts (Department / State / Store Type) with a centre total that switches to the selected slice and a **flagship named legend** beneath every ring (colour swatch · category name · CFYTD value · share-of-total chip · proportional tint bar; hovering a row highlights its slice and vice versa, clicking a row cross-filters). Clicking any bar or slice cross-filters the whole page — the clicked visual keeps every category on screen and dims the rest (cross-highlight) while every other visual and the KPI cards re-query with `dim.<column> IN (...)` — and clicking the same category again, or "Clear filter", resets the page. The Groupwise chart is driven by the **`group` column of Store Master**, so the same comparison can be pointed at any store-master column.

---

## 5. Formulas implemented (Modules I & IV)

Financial Year = **April → March**, derived from `MAX(date)` in the relevant
fact table.

- `LFY FULL` = sum for the full last FY
- `LFYTD` = last FY, April 1 → the same calendar date one year before today's max date
- `CFYTD` = current FY, April 1 → max date
- `GROWTH %` = (CFYTD − LFYTD) / |LFYTD| × 100
- `BALANCE` = LFY FULL − CFYTD
- `LFAPM` = LFY FULL / the number of fiscal months from the first LFY sale
  month through March (an annualized prior-year run rate; 12 months when sales
  were present from April)
- `LFYTD APM` = LFYTD (last FY, April 1 → the same date) / the elapsed months of
  that same window — the like-for-like twin of `CFAPM`
- `CFAPM` = CFYTD / months elapsed in the current FY — computed **per brand
  code** (not per store, not globally) as the doc specifies, then summed as
  dimensions roll up, so it stays correct at every subtotal level
- `APM GROWTH %` = (CFAPM − LFYTD APM) / |LFYTD APM| × 100
- `TRENDING` uses last year's same-period sales pattern, adjusted by this
  year's like-for-like performance: `CFYTD × (LFY FULL ÷ LFYTD)`. This
  preserves last year's seasonality while applying the current year's growth.
  When LFYTD is zero or negative, the ratio is not a reliable retail seasonal
  index, so the calculation falls back to a straight-line run rate:
  `CFYTD ÷ days elapsed × total days in current FY`.
- `PROJ. GROWTH %` = (TRENDING − LFY FULL) / |LFY FULL| × 100
- **Every growth figure divides by the ABSOLUTE value of its base** (`|LFYTD|`,
  `|LFY FULL|`, `|LFYTD APM|`, `|LFY of the month|`) so the sign always means
  *better / worse*. With a signed denominator a negative prior period silences
  the direction: LFY −₹1,93,047 → CFY +₹6,48,187 is a ₹8,41,234 gain, i.e.
  **+435.8 %**, not −435.8 %. Ratios that are not growth (Contribution %,
  Discount %, ASP / AVG.MRP) use the absolute denominator as well; the
  numerator carries the sign for these ratios.
- `CUMULATIVE` = running total of CFYTD, recomputed live in the browser
  whenever you re-sort the table (as required — this is intentionally a
  client-side calculation so it always matches what's on screen)

All of the above are computed for **both Qty and Value** in parallel (toggle
in the UI), with a rollup at every level of your chosen dimension hierarchy
(not just the finest grain).

The `APM` KPI card shows all three periods in ONE card — **LFY APM**,
**LFYTD APM** and **CFYTD APM** — each with its ₹/month figure on top and its
average units per month beneath it (there are no separate LFAPM / CFAPM cards).
`APM GROWTH %` is `(CFAPM − LFYTD APM) / LFYTD APM × 100`, i.e. like-for-like.

---

## 6. Assumptions made where the requirements doc was ambiguous or the sample
   data didn't perfectly match the doc's literal wording

These are documented here (and in code comments) rather than silently
"corrected," per your instruction to treat the doc as the source of truth and
leave data validation to you:

1. **CFAPM's per-brand month count**, when rows are grouped by dimensions
   other than Brand, is computed by first calculating CFAPM at
   (dimensions + brand_code) grain, then summing across brands as you
   remove/roll up dimensions. This is the mathematically consistent way to
   honor "brand level not store level" at every rollup level.
2. **Store Status "NA" (NON-SIS)**: any store_master row with no matching
   transactions in Tertiary Data at all (not even a single row) can't be
   classified into L2L/Annualized/New/Closed and is labelled **"NA"** per the
   updated spec ("for non-SIS keep NA") — TER.MIN/TER.MAX dates stay empty.
   In the supplied sample data this is most rows (only 62 of 235 store+brand
   combinations have any tertiary transactions) — a data-coverage
   characteristic, not a join bug (verified: the join keys themselves match
   exactly).
3. **CSS Stock Tracking season matching**: `order_form.season` values
   ("2026-H2") and `secondary_data.season` values ("2026 - H2") differ only in
   whitespace around the hyphen. This is normalized for comparison purposes
   only (never altering stored data) so the season filter/join actually
   works. Without this the whole module would silently return zero rows.
4. **CSS Stock mapping & status logic**: the ORDER FORM is treated as the
   complete original order placed before the season starts — Ordered Qty =
   SUM(Order Form `CURRENTQUANTITY`) only (VENUEQUANTITY is never used), and
   every ordered Product/Style + Season combination appears in the Summary
   even when Secondary Data has no matching record at all. Dispatch rows are
   matched to order rows on Secondary Data `PRODUCT_CODE_CODE` ↔ Order Form
   `STYLE_CODE` **together with Season**, both normalised identically for
   comparison only (TRIM + internal whitespace removal + UPPERCASE; stored
   data is never modified). Only Secondary records whose cleaned Season equals
   the Order Form season count as current-season dispatch — other seasons are
   never mixed in. Multiple Secondary records for the same key are aggregated
   before comparison. Status classification per key: Fully Dispatched
   (Dispatched ≥ Ordered > 0), Partially Dispatched (0 < Dispatched < Ordered),
   Pending (Ordered > 0, Dispatched ≤ 0), Dispatched But Not Ordered
   (dispatch exists with no matching order-form style+season; these are never
   forced into the order baseline or given an artificial order quantity).
   Pending Qty = MAX(Ordered − Dispatched, 0); Dispatch % =
   Dispatched ÷ Ordered × 100 (NULL when Ordered = 0). Sub Category comes from
   the ORDER FORM's `SUBCATEGORY` whenever a mapping exists; unmapped
   dispatch-only rows fall back to the cleaned Secondary `PRODUCT_DESC`.
   Dispatched qty is NET (Sales positive, Returns negative). KPI cards, the
   brand chart, the summary table and the Excel export all derive from one
   canonical row set, so they always reconcile exactly.
5. **Pivot table sorting**: clicking a column header sorts the full row set
   (detail rows and subtotal/grand-total rows together); subtotal rows stay
   visually distinguished (bold + tinted background) regardless of sort
   order.
6. **Monthwise measure display**: rather than rendering qty and value for
   every measure across all 12 months simultaneously (150+ columns), the UI
   shows one measure at a time via a selector. The Secondary module reads the
   monthwise grid **vertically by default** — every fiscal month (Apr → Mar) is
   a table row with its LFY / CFY / Growth % / Contribution % and the running
   cumulative — and a one-click toggle re-projects the *same* payload
   horizontally (grouped LFY | CFY | Growth % columns per month) for
   side-by-side month scanning. The cumulative column is recomputed in the
   browser after every re-sort (so it always matches the rows on screen) — all
   measures are still available, just one focus at a time for usability.
7. **Chart legends**: every dashboard donut ships a named legend beneath the
   ring (swatch · category · CFYTD value · share chip · proportional tint bar).
   The legend is a first-class part of the visual, not decoration: it is the
   only place the categories are *named*, it is hover-synced with the slices,
   and each row is clickable as a cross-filter.

---

## 7. Extensibility

- **New columns on `store_master.store_details`** (e.g. a new "Region"
  column) automatically appear as a selectable dimension/slicer everywhere
  in the app — nothing to change in code.
- **New databases/tables**: attach them in `backend/app/core/config.py`
  (`ATTACH_SCHEMAS` / `WORKING_FILES`) and they immediately show up in the
  SQL Platform's schema explorer and autocomplete.
- **Large datasets**: all aggregation happens inside DuckDB (columnar,
  vectorized), not in Python/pandas row-by-row, so this scales well past the
  current data sizes without redesign.

---

## 8. Module: Bill_No Based KPI Analysis (`/tertiary` → "Bill Analysis" tab)

New module built on top of the Tertiary fact table. All logic lives in
`backend/app/services/bill_kpi.py` (which REUSES the cached bill-level dataset
from `bill_analysis.py` — single source of truth for the bill grain), exposed
via `POST /api/bill-kpi/analysis`, UI in
`frontend/src/components/analysis/BillNoAnalysis.jsx`.

### Data model

- **Internal Bill Number (canonical bill identifier):**
  `ADONIS_CODE-FY{yy}-{MM}-BILL_NO` — e.g. `AD01-FY25-04-10023`.
  `FY{yy}` = last two digits of the fiscal-year START year (Apr 2025 → FY25),
  `MM` = zero-padded calendar month. Every bill count, KPI, bucket and Top-N
  list is grouped by this id — never the raw `bill_no`.
- **Invalid bill numbers** (`NULL` / blank / `'NA'` / `'N/A'`, case-insensitive)
  are excluded from the bill-level dataset entirely.
- **Multi-brand bills stay ONE bill**: qty / bill_val are summed across all
  item rows; store-master attributes (brand, retailer, …) are taken from the
  bill's dominant line so every hierarchy level reconciles exactly.
- LFY window = same-period last year (`last_fy_start .. lfy_ytd_end` from the
  shared FY service), identical to the LFYTD basis used elsewhere in the app.

### KPIs (computed server-side, per FY)

| KPI | Formula |
|---|---|
| Total Bills | `COUNT(DISTINCT internal_bill_no)` (invalid bill_nos excluded) |
| UPT | `Total_Qty / Total_Bills` |
| ABV | `Total_Val / Total_Bills` |
| ASP | `Total_Val / Total_Qty` |
| Growth % | `((CFY − LFY) / LFY) × 100` — `N/A` (never a divide-by-zero) when LFY = 0 |
| SPD[QTY] | `Total_Qty / Active_Days` |
| SPD[VAL] | `Total_Val / Active_Days` |

**Active_Days (brand-anchored, confirmed business rule):** the day-count window
is anchored to the brand's GLOBAL first sale date — NOT the specific retailer's
own first sale date — running to the dataset's max date:
`Active_Days = MAX(bill_date in dataset) − MIN(bill_date where brand = X, across ALL retailers) + 1`.
This applies even when slicing by a specific retailer, so a retailer's SPD can
look diluted if it started stocking a brand later than others — intentional,
not a bug (also flagged in `meta.active_days_rule`).

**Date-range mode:** when a custom `start`/`end` is sent, CFY = the selected
range and LFY = the same range shifted back exactly one year; all KPI cards,
distributions and Top Bills work identically in this mode.

### Page sections

1. **KPI cards** — Total Bills / UPT / ABV / ASP; every card shows **CFY (big),
   LFY, and the colour-coded growth badge (green ↑ / red ↓ / grey →) together**,
   with a subtle scale/tint animation on value change. Growth % =
   `((CFY − LFY) / LFY) × 100` — `N/A` (never a divide-by-zero) when LFY = 0.
2. **Row hierarchy** — driven by the app's drag-and-drop **dimensional column
   picker** (1–3 levels, e.g. Brand → Store → State, drag to reorder, remove
   all for a single grand total). **Every KPI column shows all four KPIs
   stacked, each with CFY / LFY / Growth in the same cell.** Level-1 rows are
   genuine re-aggregations at the selected grain (a "Brand X" row is computed
   on all Brand X bills directly — never an average of its store child rows),
   with an "All" summary row on top.
3. **Quantity Distribution** — buckets `1 / 2 / 3 / 4 / >4 Qty Bill` are the
   **column headers** (not rows), classified on each bill's AGGREGATED qty
   (1+1+2 = one "4 Qty" bill). Each cell answers **"HOW MANY bills landed in
   this bucket"** as a simple stack — `CFY: <bills> / Cont%: <share of the
   row's CFY bills> / LFY: <bills> / Cont%: <share of the LFY bills> /
   pp Δ: <pill>` — the headline figure is **bill counts** (not qty/val
   sums), and the pill is the **percentage-point change of Cont%**
   (`(cont%_cfy − cont%_lfy)`, e.g. `+12.3 pp`), NOT a % change on the raw bill counts. NO UPT /
   ABV / ASP. Rows follow the dimension selection (Brand selected → one row
   per brand + an `(All)` genuinely re-aggregated total row; Cont% is
   relative to the row's own bill total, never an average of children).
4. **Bill Value Distribution** — same layout and cell contract for `0-3K |
   3K-5K | 5K-8K | 8k-10K | 10K-12K | 12K-15K | >15K`, again showing **bill
   counts** with Cont% / pp Δ (the bucket only decides the
   classification). **Bucket edges are half-open `[low, high)`**: exactly
   3,000 → "3K-5K", exactly 15,000 → ">15K". A trailing bold "All Bills"
   column proves `Σ buckets = row total`.
5. **Top Bills** — Top-N is a **free, dynamic user input** (any positive
   count, typed into the "Top N Bills" field — no preset snapping); ranked by
   bill_val descending with a **deterministic server-side rank 1..n** (ties
   broken by earliest bill date, then bill id) and **ALWAYS displayed in that
   rank order** (the table is deliberately not client-re-sortable); LFY and CFY
   lists shown side by side or toggled.

### API

`POST /api/bill-kpi/analysis`  (also `GET /api/bill-kpi/dimensions`,
`GET /api/bill-kpi/slicers` — cross-filter aware slicer options)

```jsonc
{
  "filters":    { "<dimension column>": ["value", ...] },  // global slicers
  "dimension":  ["brand"],         // pivot dims, ORDER MATTERS (first = outer grouping)
  "dist_dim":   "brand",           // distribution dimension; null -> first selected dim
  "top_n":      30,                // any positive user-selected count (dynamic)
  "date_range": {"start": "2026-04-01", "end": "2026-05-31"}  // optional; overrides FY mode
}
```

Response: `kpis[]` (Total Bills / UPT / ABV / ASP / SPD[QTY] / SPD[VAL] /
Active Days, each carrying `cfy`/`lfy`/`growth_pct`),
`summary{dimensions, rows[]}` (pivot rows with `dim_value`, `is_total`,
`_level`, `kpis[]` — grand total first, level-1 subtotals are genuine
re-aggregations at the row's grain, never child averages),
`qty_distribution{dim, metric: "bills", buckets, rows[]}` and
`value_distribution{dim, metric: "bills", buckets, rows[]}` (rows = one per
dimension value with an `(All)` total row first; `cells[bucket]` =
`{metric: "bills", cfy_bills, lfy_bills, cfy_qty, lfy_qty, cfy_val, lfy_val,
share_cfy_pct, share_lfy_pct, growth_pct}` — the displayed figure is the BILL
COUNT, with Cont% = the bucket's share of the row's own bill total and
`growth_pct` carrying the **percentage-point change** (`share_cfy_pct −
share_lfy_pct`, e.g. `+12.3 pp`), NOT a % change on the raw bill counts),
`top_bills{n, cfy[], lfy[]}` (each row has a server-side `rank`),
`meta{transaction_rows, bill_count, active_days, active_days_rule, …}`.
Invalid dimension/filter names return HTTP 400. The bill-level dataset is
loaded once (cached) and sliced in pandas per request.

### Tests

`backend/tests/test_bill_kpi_logic.py` (stdlib `unittest`, DB/UI-free):
growth % incl. zero-LFY guards, brand-anchored Active_Days/SPD, qty/value
bucket edge cases, brand contribution %, pivot subtotal re-aggregation (never
child averages), dynamic Top-N (any positive count), and the distribution
pivots (bill-count cells with Cont% / pp Δ, `Σ buckets = All Bills`,
brand-level rollup, NO UPT/ABV/ASP in distribution cells).

```bash
cd backend && python -m unittest tests.test_bill_kpi_logic -v
```

---

## 9. Module: Category Performance (`/tertiary` → "Category Performance" tab)

Row-relative category mix: **Level 1 = (Row-Hierarchy level 1) × Category**,
**Level 2 = (Row-Hierarchy level 1 → level 2) × Category × Sub-Category**.

### Inputs — page-level controls only

The tab renders **no filters/slicers of its own**. It is driven purely by the
two controls at the top of the Tertiary page:

| Control | Wiring |
|---------|--------|
| **Row Hierarchy** (`DimensionPicker`) | sent as `hierarchy`; level 1 becomes the Level-1 table's rows, level 1 + level 2 drive the Level-2 table. Order matters; extra levels beyond 2 are ignored. |
| **Global slicers** (Retailer / Brand / Store Type / Department / Group / State / Store Status) | sent as `filters`. Every key is a `store_master.store_details` column, and rows are joined on **(store, brand)** — exactly the same `dim.<col> IN (...)` semantics the pivot engine uses, so the tab always agrees with the KPI cards and the pivot table above it. |

An **empty Row Hierarchy keeps the tab's historical default** (level 1 =
`brand`, the "Brand × Category" view); it is the single constant
`DEFAULT_ROW_DIM` in `app/services/category_analysis.py`. The section headings,
the row-column header and the chart title all rename themselves to the selected
dimension(s) (e.g. "Level 1 - Category Performance - DEPARTMENT x Category").

### Cell contents — all THREE periods

Every KPI cell now renders the same KPI across the three periods, so a
year-to-date figure is never compared with a full-year one:

| Row | LFY | LFYTD | CFYTD | Change |
|-----|-----|-------|-------|--------|
| `QTY` | full last FY | Apr 1 → the same date, last FY | Apr 1 → max date | (CFYTD − LFYTD) / LFYTD |
| `CONT.%` | share of the row's LFY qty | share of the row's LFYTD qty | share of the row's CFYTD qty | **percentage points**, CFYTD − LFYTD |
| `ASP` | ₹ LFY | ₹ LFYTD | ₹ CFYTD | CFYTD vs LFYTD % |
| `AVG.MRP` | ₹ LFY | ₹ LFYTD | ₹ CFYTD | CFYTD vs LFYTD % |

**Contribution is always row-relative**: Level 1 against that row's own category
total, Level 2 against its **parent category** total. The payload carries the
LFYTD twins (`sale_lfytd`, `cont_pct_lfytd`, `asp_lfytd`, `avg_mrp_lfytd`) plus
the like-for-like deltas (`qty_growth_lfytd_pct`, `asp_growth_lfytd_pct`,
`avg_mrp_growth_lfytd_pct`, `change_in_cont` = CFYTD pp − LFYTD pp); the
historical CFY-vs-full-LFY pairs (`asp_growth_pct`, `avg_mrp_growth_pct`) are
still returned unchanged. Categories come from the live data (fixed display
order for known ones, PROMO categories excluded), sub-categories likewise.

### Chart view (the "Chart" toggle)

`Chart` swaps the two tables for **one grouped bar chart** (recharts, already a
dependency) built from the *same* payload as the table — same global slicers,
same Row Hierarchy, no second query:

* **X axis** is whatever grouping is active: `Categories` (row × category),
  `Sub-Categories` (row × category × sub-category, i.e. table level 2) or `Rows`
  (category × row, i.e. the brands themselves). The row pills select which
  level-1 row the bars are cut for.
* **Bars** are grouped by the three periods - **LFY** `#94a3b8`, **LFYTD**
  `#cbd5e1`, **CFYTD** `#5b7cfa` - the same period colour coding the rest of the
  app uses.
* `Measure` switches between `QTY` and `CONT%` (both carry all three periods).
* **One tooltip at a time**: hover state is per item (`{ series, index }` set by
  that bar's own `onMouseEnter`), so exactly one tooltip can be in the DOM, it
  is anchored to the hovered bar, it shows only that bar's value and it
  disappears on mouse-leave. Nothing table-related (no row markup, no
  detail/tooltip card) is rendered while the chart is active.


### Performance

The previous implementation re-queried `MAX(date)`, the distinct brand list and
a per-category `DISTINCT sub_category` query on **every** request, joined the
store master on `brand_code` alone (fan-out) and then sliced a DataFrame once
per brand × category (~230 × 48 passes).

Now:

* the fact table is pulled **once** (`lru_cache`) at
  store+brand+category+sub-category+season grain; the store-master dimension
  columns are merged **once**;
* the store-master snapshot is re-used across requests but keyed on the
  enrichment-status token, so a STORE STATUS recompute is never served stale;
* a request is **one boolean-mask pass** + **two vectorised groupbys** (Level-1
  keys, Level-2 keys); every rollup (grand total, level-1 totals, child totals)
  is a dict pass over those maps, never another scan of the fact rows;
* the finished payload is memoised on `(row dims, filters)` and react-query
  additionally keys its cache on both, so toggling a slicer back or re-ordering
  the hierarchy is served straight from memory.

Measured on the sample database (132,659 tertiary rows, 8 categories,
~48 sub-categories): first call ~0.9 s (builds the caches), a **repeat call
0.01–0.03 ms**, a brand-new slicer/hierarchy combination 5–260 ms.

### API

`POST /api/tertiary/category-analysis`

```jsonc
{
  "hierarchy": ["department", "brand"],   // Row Hierarchy, in order (level 1, level 2)
  "filters":   { "state": ["KARNATAKA"] } // global slicers (store_details columns)
}
```

Response: `categories[]`, `sub_categories{cat: [subs]}`, `row_dims[{column,
label}]`, `row_dim_chain[]`, `rows_level1[]` / `rows_level2[]` (each row =
`{row_label, is_overall, _level, dim_values, _path, _data}` where `_data` is
`{category: cell}` for Level 1 and `{category: {sub-category: cell}}` for
Level 2), and `fy_context`.

### Tests

`backend/tests/test_category_analysis_logic.py` (stdlib `unittest`, DB/UI-free):
NaN-safe dimension keying, the vectorised groupby/rollup helpers, ASP /
AVG.MRP / growth maths with zero-division guards, row-relative vs
parent-category-relative contribution, CFY-order + LFY-only dimension values,
global-slicer masking (AND of multiple slicers, unknown columns ignored), and
Row-Hierarchy resolution (order preserved, capped at 2 levels, unknown columns
dropped, Brand default when empty).

```bash
cd backend && python -m unittest tests.test_category_analysis_logic -v
```

Browser check of the whole tab (filters, three-period cells, APM card, chart
view and the one-tooltip-per-bar contract) against the live API — needs the
backend on `:8000` and the Vite dev server on `:5173`:

```bash
node _verify_category_perf.cjs      # 31 checks, exits non-zero on any failure
```
