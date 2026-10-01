import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, Download, FileSpreadsheet, FileText, AlertCircle, Clock, Rows3 } from "lucide-react";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import DataTable from "../components/common/DataTable";
import { LoadingState, EmptyState, ErrorState } from "../components/common/LoadingState";
import SchemaExplorer from "../components/sql/SchemaExplorer";
import SqlEditor from "../components/sql/SqlEditor";
import { metaApi, sqlApi } from "../api/client";

const DEFAULT_SQL = `SELECT
    sm.retailer_name,
    sm.store_status,
    COUNT(*) AS doors
FROM store_master.store_details sm
GROUP BY 1, 2
ORDER BY doors DESC
LIMIT 20;`;

export default function SqlPlatform() {
  const [sqlText, setSqlText] = useState(DEFAULT_SQL);
  const [lastRunSql, setLastRunSql] = useState(null);

  const schemaQ = useQuery({ queryKey: ["meta", "schema-tree"], queryFn: metaApi.schemaTree });
  const functionsQ = useQuery({ queryKey: ["meta", "sql-functions"], queryFn: metaApi.sqlFunctions });

  const runMutation = useMutation({
    mutationFn: (sqlToRun) => sqlApi.execute(sqlToRun, 1000),
    onSuccess: (_, sqlToRun) => setLastRunSql(sqlToRun),
  });

  const [exporting, setExporting] = useState(null);
  async function exportAs(format) {
    setExporting(format);
    try {
      if (format === "csv") await sqlApi.exportCsv(lastRunSql || sqlText, "query_results");
      else await sqlApi.exportXlsx(lastRunSql || sqlText, "query_results");
    } finally {
      setExporting(null);
    }
  }

  function insertAtCursor(token) {
    setSqlText((prev) => (prev.endsWith(" ") || prev.length === 0 ? prev + token : prev + " " + token));
  }

  function runQuery() {
    if (!sqlText.trim()) return;
    runMutation.mutate(sqlText);
  }

  const columns = useMemo(() => {
    const cols = runMutation.data?.columns || [];
    return cols.map((c) => ({
      accessorKey: c.name,
      header: c.name,
      cell: ({ getValue }) => {
        const v = getValue();
        if (v === null || v === undefined) return <span className="text-text-muted italic">null</span>;
        if (typeof v === "object") return JSON.stringify(v);
        return String(v);
      },
    }));
  }, [runMutation.data]);

  return (
    <div>
      <PageHeader
        title="SQL IDE Platform"
      />

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5">
        <Card padded={false} className="lg:sticky lg:top-20 h-fit max-h-[70vh] overflow-y-auto">
          <div className="px-3 py-2.5 border-b border-border">
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
              Database Explorer
            </p>
          </div>
          {schemaQ.isLoading ? (
            <div className="p-3">
              <LoadingState rows={5} />
            </div>
          ) : schemaQ.isError ? (
            <div className="p-4 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-2 opacity-80" />
              <p className="text-sm font-medium text-text-primary">Failed to load schema</p>
              <p className="text-xs text-text-muted mt-1">{schemaQ.error?.message}</p>
            </div>
          ) : schemaQ.data?.databases?.length === 0 ? (
            <div className="p-4 text-center text-xs text-text-muted">
              No databases found.
            </div>
          ) : (
            <SchemaExplorer databases={schemaQ.data?.databases || []} onInsert={insertAtCursor} />
          )}
        </Card>

        <div className="space-y-4 min-w-0">
          <Card padded={false} className="overflow-hidden">
            <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                Query Editor
              </p>
              <span className="text-[11px] text-text-muted">⌘/Ctrl + Enter to run</span>
            </div>
            <SqlEditor
              value={sqlText}
              onChange={setSqlText}
              databases={schemaQ.data?.databases || []}
              functions={functionsQ.data?.functions || []}
              keywords={functionsQ.data?.keywords || []}
              onRun={runQuery}
            />
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <Button variant="primary" icon={Play} onClick={runQuery} loading={runMutation.isPending}>
                Run Query
              </Button>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={FileText}
                  onClick={() => exportAs("csv")}
                  loading={exporting === "csv"}
                  disabled={!runMutation.data}
                >
                  CSV
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={FileSpreadsheet}
                  onClick={() => exportAs("xlsx")}
                  loading={exporting === "xlsx"}
                  disabled={!runMutation.data}
                >
                  Excel
                </Button>
              </div>
            </div>
          </Card>

          <Card padded={false}>
            <div className="px-4 py-2.5 border-b border-border flex items-center justify-between flex-wrap gap-2">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Results</p>
              {runMutation.data && (
                <div className="flex items-center gap-3 text-[11px] text-text-muted">
                  <span className="flex items-center gap-1">
                    <Rows3 size={12} />
                    {runMutation.data.row_count.toLocaleString()} rows
                    {runMutation.data.truncated && ` (showing first ${runMutation.data.returned_rows})`}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    {runMutation.data.elapsed_ms} ms
                  </span>
                </div>
              )}
            </div>
            <div className="p-4">
              {runMutation.isPending ? (
                <LoadingState rows={6} />
              ) : runMutation.isError ? (
                <div className="flex items-start gap-2 p-4 rounded-lg bg-negative-soft border border-negative/30 text-negative text-sm">
                  <AlertCircle size={16} className="shrink-0 mt-0.5" />
                  <pre className="whitespace-pre-wrap font-mono text-xs">{runMutation.error.message}</pre>
                </div>
              ) : !runMutation.data ? (
                <EmptyState
                  title="Run a query to see results"
                  description="Double-click a table or column on the left to insert it, then hit Run Query."
                />
              ) : (
                <DataTable
                  columns={columns}
                  data={runMutation.data.rows}
                  emptyTitle="Query returned no rows"
                  emptyDescription="Your SQL executed successfully but returned an empty result set."
                />
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
