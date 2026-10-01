from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PivotRequest(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)


class MonthwiseRequest(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)


class CategoryAnalysisRequest(BaseModel):
    """Category Performance Analysis (Tertiary Sales Analysis, Module IV).

    Both fields are supplied by the PAGE-LEVEL controls (this section has no
    filters of its own):

    hierarchy: the Row Hierarchy, in order - level 1 becomes the Level-1
               table's rows, level 1 + level 2 drive the Level-2 table.
    filters:   the global slicers (Retailer / Brand / Store Type / Department /
               Group / State / Store Status).
    """
    filters: dict[str, list[str]] = Field(default_factory=dict)
    hierarchy: list[str] = Field(default_factory=list)


class CategoryBrandAnalysisRequest(BaseModel):
    filters: dict[str, list[str]] = Field(default_factory=dict)



class BillAnalysisRequest(BaseModel):
    filters: dict[str, list[str]] = Field(default_factory=dict)
    hierarchy: list[str] = Field(default_factory=list)
    qty_dim: str | None = None
    value_dim: str | None = None
    top_n: int = 25


class BillKpiRequest(BaseModel):
    """Bill_No Based KPI Analysis request.

    filters:    {column: [values]} global slicers (Retailer/Brand/State/
                Department/etc + Internal Month).
    dimension:  dimension(s) for the pivot summary table - ORDER MATTERS (first
                = outer/parent grouping).  Single string accepted too.
    date_range: {"start": iso, "end": iso} - overrides FY mode (req §5).
    top_n:      any positive user-selected count of ranked bills.
    dist_dim:   dimension for the qty/value distribution tables ("all" default).
    """
    filters: dict[str, list[str]] = Field(default_factory=dict)
    dimension: list[str] | str | None = None
    date_range: dict | None = None
    top_n: int = 25
    dist_dim: str | None = None


class ExportRequest(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    include: list[str] = Field(default_factory=lambda: ["billing", "monthwise"])


class SqlExecuteRequest(BaseModel):
    sql: str
    limit: int | None = None


class SqlExportRequest(BaseModel):
    sql: str
    filename: str | None = "query_results"


class StoreUpdateRequest(BaseModel):
    updates: dict[str, Any]
    password: str | None = None


class StoreCreateRequest(BaseModel):
    adonis_store_code: str
    brand_code: str
    values: dict[str, Any] = Field(default_factory=dict)
    password: str | None = None


class CssSummaryRequest(BaseModel):
    season: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    statuses: list[str] | None = None
