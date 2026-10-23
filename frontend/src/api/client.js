import axios from "axios";

export const http = axios.create({
  baseURL: "/api",
  timeout: 90_000,
});

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      const detail = err?.response?.data?.detail;
      return Promise.reject(
        new Error(detail || "Session expired or unauthorized. Please log in again.")
      );
    }
    const message =
      err?.response?.data?.detail || err?.message || "Something went wrong. Please try again.";
    return Promise.reject(new Error(message));
  }
);

async function downloadBlob(promise, fallbackName) {
  const res = await promise;
  const blob = new Blob([res.data]);
  const disposition = res.headers["content-disposition"] || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackName;
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Meta / Schema Explorer
// ---------------------------------------------------------------------------
export const metaApi = {
  schemaTree: () => http.get("/meta/schema-tree").then((r) => r.data),
  databases: () => http.get("/meta/databases").then((r) => r.data),
  tables: (database) => http.get("/meta/tables", { params: { database } }).then((r) => r.data),
  columns: (database, table) =>
    http.get("/meta/columns", { params: { database, table } }).then((r) => r.data),
  sqlFunctions: () => http.get("/meta/sql-functions").then((r) => r.data),
  recomputeStoreStatus: () => http.post("/meta/recompute-store-status").then((r) => r.data),
  resetToSeed: () => http.post("/meta/reset-to-seed").then((r) => r.data),
};

// ---------------------------------------------------------------------------
// SQL Platform
// ---------------------------------------------------------------------------
export const sqlApi = {
  execute: (sql, limit) => http.post("/sql/execute", { sql, limit }).then((r) => r.data),
  exportCsv: (sql, filename) =>
    downloadBlob(
      http.post("/sql/export/csv", { sql, filename }, { responseType: "blob" }),
      `${filename || "query_results"}.csv`
    ),
  exportXlsx: (sql, filename) =>
    downloadBlob(
      http.post("/sql/export/xlsx", { sql, filename }, { responseType: "blob" }),
      `${filename || "query_results"}.xlsx`
    ),
};

// ---------------------------------------------------------------------------
// Secondary Sales Analysis
// ---------------------------------------------------------------------------
export const secondaryApi = {
  dimensions: () => http.get("/secondary/dimensions").then((r) => r.data),
  slicers: () => http.get("/secondary/slicers").then((r) => r.data),
  pivot: (dimensions, filters) =>
    http.post("/secondary/pivot", { dimensions, filters }).then((r) => r.data),
  monthwise: (dimensions, filters) =>
    http.post("/secondary/monthwise", { dimensions, filters }).then((r) => r.data),
  export: (dimensions, filters, include) =>
    downloadBlob(
      http.post(
        "/secondary/export",
        { dimensions, filters, include },
        { responseType: "blob" }
      ),
      "secondary_sales_analysis.xlsx"
    ),
};

// ---------------------------------------------------------------------------
// Tertiary Sales Analysis
// ---------------------------------------------------------------------------
export const tertiaryApi = {
  dimensions: () => http.get("/tertiary/dimensions").then((r) => r.data),
  slicers: () => http.get("/tertiary/slicers").then((r) => r.data),
  pivot: (dimensions, filters) =>
    http.post("/tertiary/pivot", { dimensions, filters }).then((r) => r.data),
  monthwise: (dimensions, filters) =>
    http.post("/tertiary/monthwise", { dimensions, filters }).then((r) => r.data),
  categoryAnalysis: (filters, hierarchy) =>
    http
      .post("/tertiary/category-analysis", { filters, hierarchy: hierarchy || [] })
      .then((r) => r.data),
  categoryBrandAnalysis: (filters) =>
    http.post("/tertiary/category-brand-analysis", { filters }).then((r) => r.data),
  billAnalysis: (filters, hierarchy, qtyDim, valueDim, topN) =>
    http
      .post("/tertiary/bill-analysis", {
        filters,
        hierarchy,
        qty_dim: qtyDim,
        value_dim: valueDim,
        top_n: topN,
      })
      .then((r) => r.data),
  export: (dimensions, filters, include) =>
    downloadBlob(
      http.post("/tertiary/export", { dimensions, filters, include }, { responseType: "blob" }),
      "tertiary_sales_analysis.xlsx"
    ),
};

// ---------------------------------------------------------------------------
// Bill_No Based KPI Analysis (Module V)
// Endpoints: GET /bill-kpi/dimensions, GET /bill-kpi/slicers,
// POST /bill-kpi/analysis - see backend/app/api/routes/bill_kpi.py.
// ---------------------------------------------------------------------------
export const billKpiApi = {
  dimensions: () => http.get("/bill-kpi/dimensions").then((r) => r.data),
  slicers: (filters) =>
    http
      .get("/bill-kpi/slicers", { params: { filters: JSON.stringify(filters || {}) } })
      .then((r) => r.data),
  analysis: (filters, dimension, distDim, topN, dateRange = null) =>
    http
      .post("/bill-kpi/analysis", {
        filters,
        dimension,
        dist_dim: distDim,
        top_n: topN,
        date_range: dateRange,
      })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// SOH Analysis
// ---------------------------------------------------------------------------
export const sohApi = {
  dates: () => http.get("/soh/dates").then((r) => r.data),
  filters: () => http.get("/soh/filters").then((r) => r.data),
  summary: (params) => http.get("/soh/summary", { params }).then((r) => r.data),
  export: (params) =>
    downloadBlob(
      http.get("/soh/export", { params, responseType: "blob" }),
      "soh_analysis.xlsx"
    ),
};

// ---------------------------------------------------------------------------
// Store Master
// ---------------------------------------------------------------------------
export const storeMasterApi = {
  columns: () => http.get("/store-master/columns").then((r) => r.data),
  slicers: () => http.get("/store-master/slicers").then((r) => r.data),
  kpis: (filters) =>
    http
      .get("/store-master/kpis", { params: { filters: JSON.stringify(filters || {}) } })
      .then((r) => r.data),
  table: ({ filters, search, sortBy, sortDir, page, pageSize }) =>
    http
      .get("/store-master/table", {
        params: {
          filters: JSON.stringify(filters || {}),
          search: search || undefined,
          sort_by: sortBy || undefined,
          sort_dir: sortDir || "asc",
          page: page || 1,
          page_size: pageSize || 50,
        },
      })
      .then((r) => r.data),
  update: (code, brand, updates, password) =>
    http.put(`/store-master/${encodeURIComponent(code)}/${encodeURIComponent(brand)}`, {
      updates,
      password,
    }).then((r) => r.data),
  create: (adonisStoreCode, brandCode, values, password) =>
    http.post("/store-master", { adonis_store_code: adonisStoreCode, brand_code: brandCode, values, password })
      .then((r) => r.data),
  remove: (code, brand, password) =>
    http.delete(`/store-master/${encodeURIComponent(code)}/${encodeURIComponent(brand)}`, {
      params: { password: password || undefined },
    }).then((r) => r.data),
  export: (filters, search) =>
    downloadBlob(
      http.get("/store-master/export", {
        params: { filters: JSON.stringify(filters || {}), search: search || undefined },
        responseType: "blob",
      }),
      "store_master.xlsx"
    ),
};

// ---------------------------------------------------------------------------
// CSS Stock Tracking
// ---------------------------------------------------------------------------
export const cssStockApi = {
  dimensions: () => http.get("/css-stock/dimensions").then((r) => r.data),
  seasons: () => http.get("/css-stock/seasons").then((r) => r.data),
  /** Cross-filter aware slicer options: each column's options respect every
   * OTHER applied filter so e.g. picking a state narrows retailer choices. */
  slicerOptions: (filters) =>
    http
      .get("/css-stock/slicer-options", { params: { filters: JSON.stringify(filters || {}) } })
      .then((r) => r.data),
  kpis: (season, filters) =>
    http
      .get("/css-stock/kpis", {
        params: { season, filters: JSON.stringify(filters || {}) },
      })
      .then((r) => r.data),
  summary: ({ season, dimensions, filters, statuses }) =>
    http.post("/css-stock/summary", { season, dimensions, filters, statuses }).then((r) => r.data),
  export: ({ season, dimensions, filters, statuses }) =>
    downloadBlob(
      http.post(
        "/css-stock/export",
        { season, dimensions, filters, statuses },
        { responseType: "blob" }
      ),
      "css_stock_tracking.xlsx"
    ),
};
