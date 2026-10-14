import { useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Pencil, Search } from "lucide-react";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import KpiCard from "../components/common/KpiCard";
import FilterPanel from "../components/common/FilterPanel";
import DataTable from "../components/common/DataTable";
import Badge, { statusTone } from "../components/common/Badge";
import { ExportButton } from "../components/common/ExportButton";
import { LoadingState, KpiSkeleton, ErrorState } from "../components/common/LoadingState";
import EditStoreModal from "../components/store/EditStoreModal";
import { storeMasterApi } from "../api/client";
import { fmtDate, fmtQty } from "../utils/format";

export default function StoreMaster() {
  const [filters, setFilters] = useState({});
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sorting, setSorting] = useState([]);
  const [editingRow, setEditingRow] = useState(null);
  const pageSize = 25;

  const columnsQ = useQuery({ queryKey: ["store-master", "columns"], queryFn: storeMasterApi.columns });
  const slicersQ = useQuery({ queryKey: ["store-master", "slicers"], queryFn: storeMasterApi.slicers });
  const kpisQ = useQuery({
    queryKey: ["store-master", "kpis", filters],
    queryFn: () => storeMasterApi.kpis(filters),
  });

  const sortBy = sorting[0]?.id;
  const sortDir = sorting[0]?.desc ? "desc" : "asc";
  const tableQ = useQuery({
    queryKey: ["store-master", "table", filters, search, sortBy, sortDir, page],
    queryFn: () =>
      storeMasterApi.table({ filters, search, sortBy, sortDir, page, pageSize }),
    placeholderData: keepPreviousData,
  });

  const dimensionLabels = useMemo(() => {
    const cols = columnsQ.data?.columns || [];
    return Object.fromEntries(cols.map((c) => [c.name, c.name.replace(/_/g, " ").toUpperCase()]));
  }, [columnsQ.data]);

  const columns = useMemo(() => {
    const cols = columnsQ.data?.columns || [];
    return [
      ...cols
        .filter((c) => !["ter_min_date", "ter_max_date"].includes(c.name))
        .map((c) => ({
          accessorKey: c.name,
          header: dimensionLabels[c.name],
          cell: ({ getValue }) => {
            const v = getValue();
            if (c.name === "store_status") {
              return v ? <Badge tone={statusTone(v)}>{v}</Badge> : <span className="text-text-muted">—</span>;
            }
            return v ?? "—";
          },
        })),
      {
        accessorKey: "ter_min_date",
        header: "TER.MIN DATE",
        cell: ({ getValue }) => fmtDate(getValue()),
      },
      {
        accessorKey: "ter_max_date",
        header: "TER.MAX DATE",
        cell: ({ getValue }) => fmtDate(getValue()),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <button
            onClick={() => setEditingRow(row.original)}
            className="flex items-center gap-1 text-accent hover:text-accent-hover text-xs font-medium"
          >
            <Pencil size={12} />
            Edit
          </button>
        ),
      },
    ];
  }, [columnsQ.data, dimensionLabels]);

  const kpis = kpisQ.data;
  const total = tableQ.data?.total || 0;
  const pageCount = Math.max(Math.ceil(total / pageSize), 1);

  return (
    <div>
      <PageHeader
        title="Store Master"
        description="Centralized retail directory. Store statuses are derived automatically; metadata is fully editable."
        actions={<ExportButton onExport={() => storeMasterApi.export(filters, search)} />}
      />

      {kpisQ.isLoading ? (
        <div className="mb-6">
          <KpiSkeleton count={1} />
        </div>
      ) : kpisQ.isError ? (
        <Card className="mb-6">
          <ErrorState message={kpisQ.error.message} onRetry={() => kpisQ.refetch()} />
        </Card>
      ) : (
        <>
          {/* ONE KPI card: Total Active Doors - active SIS and Non-SIS doors, counted once by ADONIS STORE CODE;
              a store with multiple brands counts ONCE if ANY ONE brand is
              L2L / Annualized / New, irrespective of how many brands exist. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
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
                        {(kpis.sis_doors || 0).toLocaleString()}
                      </span>
                    </p>
                    <p className="text-[13px] text-text-secondary tabular-nums font-medium">
                      <span className="text-text-muted font-semibold uppercase tracking-wide">NON-SIS: </span>
                      <span className="text-warn">
                        {(kpis.non_sis_doors || 0).toLocaleString()}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <Card className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display font-semibold text-text-primary">Brand-wise Store Status Summary</h3>
              <span className="text-[11px] uppercase tracking-wide text-text-muted">By brand name</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
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
              </table>
            </div>
          </Card>
        </>
      )}

      <Card className="mb-5">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border-strong bg-surface w-full md:w-80">
            <Search size={14} className="text-text-muted" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search stores…"
              className="bg-transparent text-sm outline-none w-full text-text-primary placeholder:text-text-muted"
            />
          </div>
          {slicersQ.data?.slicers && (
            <FilterPanel
              slicers={slicersQ.data.slicers}
              dimensionLabels={dimensionLabels}
              value={filters}
              onChange={(f) => {
                setFilters(f);
                setPage(1);
              }}
            />
          )}
        </div>
      </Card>

      <Card padded={false}>
        <div className="p-4">
          {tableQ.isLoading ? (
            <LoadingState rows={10} />
          ) : tableQ.isError ? (
            <ErrorState message={tableQ.error.message} onRetry={() => tableQ.refetch()} />
          ) : (
            <DataTable
              columns={columns}
              data={tableQ.data.rows}
              manualPagination
              manualSorting
              sorting={sorting}
              onSortingChange={(updater) => {
                setSorting(updater);
                setPage(1);
              }}
              page={page}
              pageCount={pageCount}
              onPageChange={setPage}
              globalSearch={false}
              stickyFirstColumns={1}
              emptyTitle="No stores match your filters"
            />
          )}
        </div>
      </Card>

      {editingRow && columnsQ.data && (
        <EditStoreModal
          row={editingRow}
          columns={columnsQ.data.columns}
          onClose={() => setEditingRow(null)}
        />
      )}
    </div>
  );
}
