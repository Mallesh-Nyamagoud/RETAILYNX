import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
} from "@tanstack/react-table";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import clsx from "clsx";

const MIN_COL_WIDTH = 60;

/**
 * Sortable data table with global search, column visibility toggles and
 * USER-ADJUSTABLE COLUMN WIDTHS (drag the right edge of any header cell).
 * Widths persist per column id for the lifetime of the component instance.
 */
export default function DataTable({
  columns,
  data,
  globalSearch = true,
  columnVisibilityToggle = true,
  manualPagination = false,
  pageCount,
  page = 1,
  pageSize = 50,
  onPageChange,
  manualSorting = false,
  sorting: controlledSorting,
  onSortingChange,
  rowClassName,
  stickyFirstColumns = 0,
  /** Optional max-height utility class for the internal scroll pane
   *  (e.g. "max-h-[65vh]" or "max-h-[calc(100vh-180px)]" in large view).
   *  When set, header/parent-row pinning works INSIDE the pane (Excel-style
   *  frozen pane) instead of against the page scroll. */
  maxHeightClass = "",
  /** Pin the first data row (row index 0) directly beneath the sticky header
   *  so it stays visible as the user scrolls through remaining rows. */
  stickyFirstDataRow = false,
  /** Pin EVERY row whose `_level === 1` (the PARENT dimension of a nested
   *  hierarchy) directly beneath the sticky header - Excel-style group headers -
   *  so the parent row of the group you are scrolling through always stays
   *  visible.  Only activates when the data actually contains deeper levels
   *  (a flat table is never affected). */
  stickyParentRows = false,
  emptyTitle,
  emptyDescription,
  dense = false,
  footerRow = null,
}) {
  const [internalSorting, setInternalSorting] = useState([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState({});
  const [showColMenu, setShowColMenu] = useState(false);
  // User-dragged widths keyed by column id; unset columns fall back to auto.
  const [colWidths, setColWidths] = useState({});
  const dragState = useRef(null);
  const headerRef = useRef(null);
  const firstRowRef = useRef(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [firstRowHeight, setFirstRowHeight] = useState(0);
  // Left offsets of the frozen columns, measured from the rendered header.
  const [stickyLefts, setStickyLefts] = useState([]);

  // Measure the header height (so the sticky first data row can sit right
  // beneath it) AND the accumulated rendered width of every frozen column, so
  // the 2nd/3rd frozen column is offset by its REAL width instead of a guess.
  useEffect(() => {
    if ((!stickyFirstDataRow && !stickyFirstColumns) || !headerRef.current) return undefined;
    const el = headerRef.current;
    const update = () => {
      setHeaderHeight(el.getBoundingClientRect().height);
      const firstRow = el.querySelector("tr");
      const lefts = [];
      let acc = 0;
      for (const th of firstRow ? firstRow.children : []) {
        lefts.push(acc);
        acc += th.getBoundingClientRect().width;
      }
      setStickyLefts((prev) =>
        prev.length === lefts.length && prev.every((v, i) => Math.abs(v - lefts[i]) < 0.5)
          ? prev
          : lefts
      );
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [stickyFirstDataRow, stickyFirstColumns, columns, data]);

  // Measure the pinned first data row so pinned PARENT rows can be stacked
  // directly underneath it (never overlapping it).
  useEffect(() => {
    if (!stickyFirstDataRow || !firstRowRef.current) return undefined;
    const el = firstRowRef.current;
    const update = () => setFirstRowHeight(el.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stickyFirstDataRow, stickyParentRows, columns, data]);

  // Parent-row pinning only makes sense for a nested (drill-down) table: a flat
  // table has no `_level` > 1 rows, so nothing is ever pinned.
  const hasNestedRows = useMemo(
    () => stickyParentRows && (data || []).some((r) => (r?._level ?? 0) > 1),
    [stickyParentRows, data]
  );

  const sorting = manualSorting ? controlledSorting : internalSorting;
  const setSorting = manualSorting ? onSortingChange : setInternalSorting;

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      globalFilter: globalSearch ? globalFilter : undefined,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: manualSorting ? undefined : getSortedRowModel(),
    getFilteredRowModel: globalSearch && !manualPagination ? getFilteredRowModel() : undefined,
    manualSorting,
    manualPagination: true, // we always render our own pager below
  });

  const rows = table.getRowModel().rows;

  // ---- Column resize (drag handle on each header cell's right edge) -------
  const onResizeStart = useCallback((e, colId) => {
    e.preventDefault();
    e.stopPropagation();
    const th = e.currentTarget.closest("th");
    const startWidth = th ? th.getBoundingClientRect().width : 160;
    dragState.current = { colId, startX: e.clientX, startWidth };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    if (!dragState.current) return undefined;
    const onMove = (e) => {
      const st = dragState.current;
      if (!st) return;
      const delta = e.clientX - st.startX;
      const next = Math.max(MIN_COL_WIDTH, Math.round(st.startWidth + delta));
      setColWidths((prev) => (prev[st.colId] === next ? prev : { ...prev, [st.colId]: next }));
    };
    const onUp = () => {
      dragState.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  // Effective column width: a user-dragged width wins, otherwise fall back to
  // the column's declared `size` (drives `table-fixed` layouts so each column
  // is sized by content rather than split equally -> months/headers stay legible).
  const widthFor = (col) => colWidths[col.id] ?? col.columnDef?.size;

  return (
    <div className="flex flex-col gap-3">
      {(globalSearch || columnVisibilityToggle) && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          {globalSearch && !manualPagination ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong bg-surface w-64">
              <Search size={13} className="text-text-muted" />
              <input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder="Search table…"
                className="bg-transparent text-sm outline-none w-full text-text-primary placeholder:text-text-muted"
              />
            </div>
          ) : (
            <span />
          )}
          {columnVisibilityToggle && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowColMenu((v) => !v)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border-strong text-xs font-medium text-text-secondary hover:text-text-primary"
              >
                <SlidersHorizontal size={13} />
                Columns
              </button>
              {showColMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setShowColMenu(false)} />
                  <div className="absolute z-20 right-0 mt-1 w-56 max-h-72 overflow-y-auto bg-card border border-border rounded-lg shadow-panel-lg py-1 animate-fadeIn">
                    {table.getAllLeafColumns().map((col) => (
                      <label
                        key={col.id}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-primary hover:bg-card-hover cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={col.getIsVisible()}
                          onChange={col.getToggleVisibilityHandler()}
                        />
                        <span className="truncate">
                          {typeof col.columnDef.header === "string" ? col.columnDef.header : col.id}
                        </span>
                      </label>
                    ))}
                    {Object.keys(colWidths).length > 0 && (
                      <button
                        type="button"
                        onClick={() => setColWidths({})}
                        className="w-full text-left px-3 py-1.5 text-xs text-text-secondary hover:text-negative border-t border-border mt-1"
                      >
                        Reset column widths
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      <div className={clsx("overflow-auto border border-border rounded-xl2 bg-card", maxHeightClass)}>
        <table className="min-w-full text-sm table-fixed">
          <colgroup>
            {table.getVisibleLeafColumns().map((col) => (
              <col key={col.id} style={widthFor(col) ? { width: widthFor(col) } : undefined} />
            ))}
          </colgroup>
          <thead ref={headerRef} className="sticky top-0 z-[4] bg-card-hover">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header, idx) => {
                  const isLeaf = header.subHeaders.length === 0;
                  const sortable = isLeaf && header.column.columnDef.enableSorting !== false;
                  const sorted = isLeaf ? header.column.getIsSorted() : false;
                  return (
                    <th
                      key={header.id}
                      colSpan={header.colSpan}
                      onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                      className={clsx(
                        "relative text-left px-3 font-semibold text-[11px] uppercase tracking-wide text-text-secondary whitespace-nowrap border-b border-border",
                        dense ? "py-2" : "py-2.5",
                        !isLeaf && "text-center border-l border-border/60",
                        sortable && "cursor-pointer select-none hover:text-text-primary",
                        idx < stickyFirstColumns && "sticky left-0 z-[5] bg-card-hover"
                      )}
                      style={{
                        ...(idx < stickyFirstColumns ? { left: stickyLefts[idx] ?? idx * 140 } : {}),
                        ...(widthFor(header.column)
                          ? {
                              width: widthFor(header.column),
                              minWidth: widthFor(header.column),
                            }
                          : {}),
                      }}
                    >
                      {header.isPlaceholder ? null : (
                        <span className="inline-flex items-center gap-1 overflow-hidden">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sortable &&
                            (sorted === "asc" ? (
                              <ArrowUp size={11} />
                            ) : sorted === "desc" ? (
                              <ArrowDown size={11} />
                            ) : (
                              <ArrowUpDown size={11} className="opacity-30" />
                            ))}
                        </span>
                      )}
                      {/* Drag handle to resize this column */}
                      <span
                        role="separator"
                        aria-label={`Resize ${header.column.id} column`}
                        onMouseDown={(e) => onResizeStart(e, header.column.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-accent/40 transition-colors"
                      />
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={table.getAllLeafColumns().length} className="py-14">
                  <div className="flex flex-col items-center justify-center text-center gap-2">
                    <p className="font-display text-sm font-medium text-text-primary">
                      {emptyTitle || "No rows match your current filters"}
                    </p>
                    <p className="text-xs text-text-secondary max-w-sm">
                      {emptyDescription ||
                        "Try widening your filters or choosing different dimensions."}
                    </p>
                  </div>
                </td>
              </tr>
            )}
            {rows.map((row, rowIdx) => {
              // Freeze panes: the first data row and (in a nested hierarchy)
              // every PARENT row stay pinned under the sticky header.  A later
              // parent row paints over the previous one - Excel-style pushing.
              const pinnedFirst = stickyFirstDataRow && rowIdx === 0;
              const pinnedParent = hasNestedRows && (row.original?._level ?? 0) === 1;
              const pinned = pinnedFirst || pinnedParent;
              const pinTop = pinnedFirst ? headerHeight : headerHeight + firstRowHeight;
              return (
                <tr
                  key={row.id}
                  ref={pinnedFirst ? firstRowRef : undefined}
                  className={clsx(
                    "border-b border-border/70 last:border-0 transition-colors",
                    "hover:bg-card-hover",
                    rowClassName?.(row.original),
                    pinned && "bg-card-hover font-bold shadow-lg"
                  )}
                  style={pinned ? { position: "sticky", top: pinTop, zIndex: 3 } : undefined}
                >
                  {row.getVisibleCells().map((cell, idx) => {
                    // A column can opt into wrapping when its cell holds a long
                    // value (e.g. the per-bill brand mix): `meta: { wrap: true }`.
                    const wraps = cell.column.columnDef.meta?.wrap === true;
                    return (
                    <td
                      key={cell.id}
                      className={clsx(
                        "px-4 py-3 tabular-nums text-text-primary font-semibold",
                        wraps ? "whitespace-normal align-top" : "whitespace-nowrap truncate max-w-[420px]",
                        dense ? "py-1.5" : "py-2",
                        idx < stickyFirstColumns && "sticky left-0 z-[1]",
                        idx < stickyFirstColumns && (pinned ? "bg-card-hover" : "bg-card"),
                        // Non-frozen cells of a pinned row need an opaque
                        // background too, otherwise scrolling rows show through.
                        pinned && idx >= stickyFirstColumns && "bg-card-hover"
                      )}
                      style={idx < stickyFirstColumns ? { left: stickyLefts[idx] ?? idx * 140 } : undefined}
                      title={typeof cell.getValue() === "string" ? cell.getValue() : undefined}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          {footerRow}
        </table>
      </div>

      {manualPagination && (
        <div className="flex items-center justify-between text-xs text-text-secondary">
          <span>
            Page {page} of {pageCount || 1}
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => onPageChange?.(page - 1)}
              className="p-1.5 rounded-md border border-border-strong disabled:opacity-30 hover:bg-card-hover"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              disabled={page >= (pageCount || 1)}
              onClick={() => onPageChange?.(page + 1)}
              className="p-1.5 rounded-md border border-border-strong disabled:opacity-30 hover:bg-card-hover"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}