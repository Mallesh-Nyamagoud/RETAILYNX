def build_store_brand_rank(filters, config, report):
    cfg = config(filters)
    if not {"store", "brand"}.issubset(cfg["fields"]):
        raise ValueError("Store and brand fields are required")
    brands = [b for b in cfg["options"].get("brand", []) if not filters.get("brand") or b in filters["brand"]]
    stores = {}; totals = {}; anchor = None; partial = False
    for brand in brands:
        result = report("store", {**filters, "brand": [brand]})
        full_result = report("store", {**filters, "brand": [brand], "month": []}) if filters.get("month") else result
        full_rows = {row["label"]: row for row in full_result["rows"]}
        anchor = result["anchor"]
        partial = result["current_fy_partial"] and anchor == result["current_fy"]
        previous_key = "lfytd_val" if partial else "val"
        totals[brand] = {"current": result["totals"].get(str(anchor), {}).get("val", 0),
                         "previous": result["totals"].get(str(anchor-1), {}).get(previous_key, 0)} if anchor else {"current":0,"previous":0}
        totals[brand]["full"] = full_result["totals"].get(str(anchor-1), {}).get("val", 0) if anchor else 0
        for row in result["rows"]:
            current = row["years"].get(str(anchor), {}).get("val", 0)
            previous = row["years"].get(str(anchor-1), {}).get(previous_key, 0) if anchor else 0
            stores.setdefault(row["label"], {})[brand] = {"current": current, "previous": previous,
                "full": full_rows.get(row["label"], {}).get("years", {}).get(str(anchor-1), {}).get("val", 0) if anchor else 0}
    rows = []
    periods = ("current", "previous", "full")
    overall_totals = {key: sum(values[key] for values in totals.values()) for key in periods}
    overall = overall_totals["current"]
    brands.sort(key=lambda brand: (-totals[brand]["current"], brand))
    for name, cells in stores.items():
        store_totals = {key: sum(cell[key] for cell in cells.values()) for key in periods}
        ranked = sorted(cells.values(), key=lambda cell: cell["current"], reverse=True)
        last = None
        for index, cell in enumerate(ranked):
            if cell["current"] != last:
                rank = index + 1
                last = cell["current"]
            cell["rank"] = rank
            for key in periods:
                cell[key + "_cont"] = cell[key] / store_totals[key] * 100 if store_totals[key] else None
        rows.append({"label": name, "cells": cells, "totals": store_totals,
                     "contribution": store_totals["current"] / overall * 100 if overall else None,
                     "contributions": {key: store_totals[key] / overall_totals[key] * 100 if overall_totals[key] else None for key in periods}})
    rows.sort(key=lambda row: (-row["totals"]["current"], row["label"]))
    return {"anchor": anchor, "partial": partial, "brands": brands, "totals": totals, "overall_totals": overall_totals, "rows": rows}
