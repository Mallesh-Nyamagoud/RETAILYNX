from __future__ import annotations
import argparse, os, re, shutil, tempfile
from pathlib import Path
import duckdb
import pandas as pd

# target column, Excel column position, DuckDB type. None creates an empty compatibility column.
MAPS = {
    'store_master_src.duckdb': ('STORE MASTER.xlsx', 'UPDATED MASTER SHEET', 1, 'store_details', [
        ('retailer_name',0,'VARCHAR'),('adonis_store_code',1,'VARCHAR'),('brand',2,'VARCHAR'),('brand_code',3,'VARCHAR'),('store_type',4,'VARCHAR'),('department',5,'VARCHAR'),('group',6,'VARCHAR'),('city',7,'VARCHAR'),('state',8,'VARCHAR'),('store_status',9,'VARCHAR'),('ter_min_date',10,'DATE'),('ter_max_date',11,'DATE')]),
    'soh_data_src.duckdb': ('SOH DATA.xlsx','SOH DATA',0,'data',[
        ('date',0,'TIMESTAMP'),('name',1,'VARCHAR'),('brand',2,'VARCHAR'),('code',3,'VARCHAR'),('ean_code',4,'VARCHAR'),('pc9',5,'VARCHAR'),('correct_size',6,'VARCHAR'),('qty',7,'BIGINT'),('mrp',8,'DOUBLE'),('top_bottom',9,'VARCHAR'),('bricks',10,'VARCHAR'),('gender',11,'VARCHAR'),('category_group',12,'VARCHAR'),('gc',13,'VARCHAR'),('season',14,'VARCHAR'),('mc_type',15,'VARCHAR'),('core_pb',16,'VARCHAR'),('fit',17,'VARCHAR')]),
    'secondary_data_src.duckdb': ('SECONDARY DATA.xlsx','DATA',0,'data',[
        ('bill_date',3,'TIMESTAMP'),('tran_type',4,'VARCHAR'),('bill_prefix',5,'VARCHAR'),('bill_no',6,'BIGINT'),('customer_name',7,'VARCHAR'),('adonis_store_code',0,'VARCHAR'),('brand_code',1,'VARCHAR'),('brand',2,'VARCHAR'),('season',None,'VARCHAR'),('stockno',8,'BIGINT'),('item_description',9,'VARCHAR'),('product_desc',10,'VARCHAR'),('brand_code_desc',11,'VARCHAR'),('brand_desc',12,'VARCHAR'),('product_code_code',13,'VARCHAR'),('edp_code_code',14,'VARCHAR'),('size',15,'VARCHAR'),('hsn_code',16,'BIGINT'),('mdp',17,'DOUBLE'),('doc_rate',18,'DOUBLE'),('qty',19,'BIGINT'),('value',20,'DOUBLE'),('addons',21,'VARCHAR'),('deduction',22,'VARCHAR'),('tax_perc',23,'DOUBLE'),('tax',24,'DOUBLE'),('item_discount',25,'DOUBLE'),('bill_discount',26,'DOUBLE'),('total_discount',27,'DOUBLE'),('customer_code',None,'VARCHAR'),('item_promo_code',None,'VARCHAR'),('bill_promo_code',None,'VARCHAR'),('remarks',28,'VARCHAR'),('old_bill_ref',29,'VARCHAR')]),
    'tertiary_data_src.duckdb': ('TERTIARY DATA.xlsx','DATA',0,'data',[
        ('Brand',0,'VARCHAR'),('brand_code',1,'VARCHAR'),('customer_name',2,'VARCHAR'),('adonis_store_code',3,'VARCHAR'),('bill_no',4,'VARCHAR'),('REFERENCE[OBN]',5,'VARCHAR'),('date',6,'DATE'),('LEVIS FY',None,'INTEGER'),('FY NEW',None,'INTEGER'),('FY',8,'VARCHAR'),('EAN',9,'VARCHAR'),('Style_Code',10,'VARCHAR'),('CORRECT SIZE',11,'VARCHAR'),('MRP',12,'DOUBLE'),('qty',13,'BIGINT'),('mrp_value',14,'DOUBLE'),('discount',15,'DOUBLE'),('bill_val',16,'DOUBLE'),('CG',17,'VARCHAR'),('category',18,'VARCHAR'),('sub_category',19,'VARCHAR'),('COLOUR',20,'VARCHAR'),('SEASON',21,'VARCHAR'),('MC TYPE',22,'VARCHAR'),('core/pb',23,'VARCHAR'),('FIT',24,'VARCHAR'),('FIT GROUP',25,'VARCHAR'),('FABRIC TYPE',26,'VARCHAR'),('month',7,'VARCHAR')])
}

EXPECTED_HEADERS = {
    'STORE MASTER.xlsx': ['CUSTOMER NAME','ADONIS_CODE','Brand','BRAND CODE','STORE TYPE','DEPARTMENT','GROUP','CITY','STATE','STORE STATUS','TER.MIN DATE','TER.MAX DATE'],
    'SOH DATA.xlsx': ['DATE','NAME','BRAND','CODE','EAN Code','pc9','CORRECT SIZE','Qty','MRP','CATEGORY','BRICKS','GENDER','CATEGORY GROUP','GC','SEASON','MC TYPE','core/pb','FIT'],
    'SECONDARY DATA.xlsx': ['ADONIS CODE','BRAND CODE','BRAND','Bill Date','Tran Type','Bill Prefix','Bill No',' Customer Name','StockNo','Item Description','product Code ','brand Code ','BRAND','product code Code ','edp code Code ','size','HSN Code','MDP','Doc Rate','Qty','Value','Addons','Deduction','Tax Perc.','Tax','Item - Discount','Bill - Discount','Total - Discount','REMARKS','Old Bill Ref.'],
    'TERTIARY DATA.xlsx': ['Brand','BRAND CODE','CUSTOMER NAME','ADONIS_CODE','Bill_No','REFERENCE[OBN]','DATE','MONTH','FY ','EAN','Style_Code','CORRECT SIZE','MRP','Qty','MRP_VALUE','Discount','Bill_Val','CG','CATEGORY','SUB CATEGORY','COLOUR','SEASON','MC TYPE','core/pb','FIT','FIT GROUP','FABRIC TYPE'],
}

def quote(s): return '"'+s.replace('"','""')+'"'
def _header_key(value): return re.sub(r'[^a-z0-9]', '', str(value or '').lower())
def read_mapped(xlsx, sheet, header, mapping):
    raw_header = pd.read_excel(xlsx, sheet_name=sheet, header=None, nrows=header + 1, dtype=object, engine='openpyxl').iloc[header].tolist()
    expected = EXPECTED_HEADERS[xlsx.name]
    if len(raw_header) != len(expected) or [_header_key(v) for v in raw_header] != [_header_key(v) for v in expected]:
        raise ValueError(f'{xlsx.name}: source columns do not match the reviewed mapping; no data was replaced')
    source = pd.read_excel(xlsx, sheet_name=sheet, header=header, dtype=object, engine='openpyxl')
    columns = {}
    for target, idx, kind in mapping:
        if idx is None:
            values = pd.Series([None] * len(source), index=source.index, dtype=object)
        else:
            if idx >= source.shape[1]: raise ValueError(f'{xlsx.name}: column {idx} required for {target}; found {source.shape[1]} columns')
            values = source.iloc[:,idx]
            if kind == 'VARCHAR':
                values = values.map(lambda v: None if pd.isna(v) or not str(v).strip() else str(v).strip())
            elif kind in ('DATE','TIMESTAMP'): values = pd.to_datetime(values, errors='coerce')
            else: values = pd.to_numeric(values, errors='coerce')
        columns[target] = values
    result = pd.DataFrame(columns)
    if sheet == 'UPDATED MASTER SHEET':
        result = result[result.retailer_name.notna() & result.brand_code.notna()].reset_index(drop=True)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--only', choices=MAPS.keys(), help='Rebuild one seed only')
    args=parser.parse_args()
    sources = {args.only: MAPS[args.only]} if args.only else MAPS
    for filename,(xlsx,sheet,header,table,mapping) in sources.items():
        if not (args.input_dir/xlsx).is_file(): raise FileNotFoundError(args.input_dir/xlsx)
        if not (args.data_dir/filename).is_file(): raise FileNotFoundError(args.data_dir/filename)
    args.data_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='latest_seed_',dir=args.data_dir) as temp:
        temp=Path(temp); staged={}; counts={}
        for filename,(xlsx,sheet,header,table,mapping) in sources.items():
            source=args.input_dir/xlsx
            frame=read_mapped(source,sheet,header,mapping)
            for required in ({'date','name','code','qty'} if filename.startswith('soh') else {'date','qty','brand_code','adonis_store_code'} if filename.startswith('tertiary') else {'bill_date','qty','brand_code','adonis_store_code'} if filename.startswith('secondary') else {'retailer_name','brand_code'}):
                if required not in frame: raise ValueError(f'{filename}: required mapped column missing: {required}')
                if frame[required].isna().all(): raise ValueError(f'{filename}: required column {required} is entirely blank')
            stage=temp/filename
            con=duckdb.connect(str(stage))
            try:
                con.register('source_rows',frame)
                expr=', '.join(f'CAST({quote(c)} AS {kind}) AS {quote(c)}' for c,_,kind in mapping)
                con.execute(f'CREATE TABLE {quote(table)} AS SELECT {expr} FROM source_rows')
                count=con.execute(f'SELECT COUNT(*) FROM {quote(table)}').fetchone()[0]
                null_dates=0
                date_col='bill_date' if filename.startswith('secondary') else 'date' if filename.startswith(('soh','tertiary')) else None
                if date_col: null_dates=con.execute(f'SELECT COUNT(*) FROM {quote(table)} WHERE {quote(date_col)} IS NULL').fetchone()[0]
                if count != len(frame) or count == 0 or null_dates:
                    raise ValueError(f'{filename}: validation failed: rows {count}/{len(frame)}, null dates {null_dates}')
                con.execute('CHECKPOINT')
            finally: con.close()
            staged[args.data_dir/filename]=stage; counts[filename]=count
            print(f'Staged {filename}: {count:,} rows; {len(mapping)} mapped columns; dates validated')
        backup=temp/'backup'; backup.mkdir(); replaced=[]
        try:
            for target,stage in staged.items():
                shutil.copy2(target,backup/target.name)
                os.replace(stage,target); replaced.append(target)
        except Exception:
            for target in reversed(replaced): shutil.copy2(backup/target.name,target)
            raise
    print(f'REPLACED {len(counts)} selected seed database(s) (no append):')
    for f,n in counts.items(): print(f'  {f}: {n:,}')

if __name__=='__main__': main()

