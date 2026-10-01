import urllib.request
import json

req = urllib.request.Request("http://localhost:8000/api/tertiary/category-analysis", data=json.dumps({"filters": {}, "hierarchy": ["brand"]}).encode(), headers={"Content-Type": "application/json"})
res = urllib.request.urlopen(req)
data = json.loads(res.read())
print("KEYS:", data.keys())
row1 = data.get("rows_level1", [])[1]
print(row1["row_label"])
cell_data = list(row1["_data"].values())[0]
print("cont_pct_cfy:", cell_data.get("cont_pct_cfy"))
print("cont_across_pct_cfy:", cell_data.get("cont_across_pct_cfy"))
