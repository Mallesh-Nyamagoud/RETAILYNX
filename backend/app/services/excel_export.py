"""
Shared Excel export helper.

Every export in the app must "mention which all filters applied" per the
requirements doc, so every workbook produced here gets a dedicated
"Filters Applied" sheet in addition to the data sheet(s).
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def build_workbook(
    sheets: dict[str, pd.DataFrame],
    filters_meta: dict[str, Any] | None = None,
    title: str = "Analysis Export",
) -> io.BytesIO:
    buffer = io.BytesIO()
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False, startrow=0)
            ws = writer.sheets[safe_name]
            for col_idx, col_name in enumerate(df.columns, start=1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")
                max_len = max(
                    [len(str(col_name))] + [len(str(v)) for v in df[col_name].astype(str).head(200)]
                )
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 10), 40)
            ws.freeze_panes = "A2"

        meta_rows = [("Export generated", datetime.now().isoformat(timespec="seconds"))]  # noqa: DTZ005
        meta_rows.append(("Report", title))
        if filters_meta:
            for key, value in filters_meta.items():
                if isinstance(value, (list, tuple)):
                    value = ", ".join(map(str, value)) if value else "(none)"
                elif isinstance(value, dict):
                    if not value:
                        value = "(none)"
                    else:
                        value = "; ".join(
                            f"{k} = {', '.join(map(str, v)) if isinstance(v, (list, tuple)) else v}"
                            for k, v in value.items()
                        )
                meta_rows.append((key, value))
        meta_df = pd.DataFrame(meta_rows, columns=["Setting", "Value"])
        meta_df.to_excel(writer, sheet_name="Filters Applied", index=False)
        ws2 = writer.sheets["Filters Applied"]
        for col_idx in (1, 2):
            cell = ws2.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
        ws2.column_dimensions["A"].width = 28
        ws2.column_dimensions["B"].width = 70

    buffer.seek(0)
    return buffer
