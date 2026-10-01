import { useState } from "react";
import { ChevronRight, ChevronDown, Database, Table2, Columns3 } from "lucide-react";
import clsx from "clsx";

function TableNode({ table, dbName, onInsert }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-card-hover text-left group"
      >
        {open ? <ChevronDown size={12} className="text-text-muted shrink-0" /> : <ChevronRight size={12} className="text-text-muted shrink-0" />}
        <Table2 size={13} className="text-teal shrink-0" />
        <span
          className="text-xs font-medium text-text-primary truncate flex-1"
          title={table.fq_name}
          onDoubleClick={(e) => {
            e.stopPropagation();
            onInsert(`${dbName}.${table.name}`);
          }}
        >
          {table.name}
        </span>
        <span className="text-[10px] text-text-muted opacity-0 group-hover:opacity-100">
          {table.columns.length}
        </span>
      </button>
      {open && (
        <div className="ml-5 border-l border-border pl-2 py-0.5">
          {table.columns.map((c) => (
            <button
              key={c.name}
              onClick={() => onInsert(c.name)}
              className="w-full flex items-center gap-1.5 px-1.5 py-1 rounded hover:bg-card-hover text-left"
              title={`Insert ${c.name}`}
            >
              <Columns3 size={11} className="text-text-muted shrink-0" />
              <span className="text-[11px] text-text-secondary truncate">{c.name}</span>
              <span className="text-[10px] text-text-muted ml-auto shrink-0">{c.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DatabaseNode({ db, onInsert, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-card-hover text-left"
      >
        {open ? <ChevronDown size={13} className="text-text-muted shrink-0" /> : <ChevronRight size={13} className="text-text-muted shrink-0" />}
        <Database size={14} className="text-accent shrink-0" />
        <span className="text-xs font-semibold text-text-primary truncate">{db.name}</span>
        <span className="text-[10px] text-text-muted ml-auto">{db.tables.length}</span>
      </button>
      {open && (
        <div className="ml-4 border-l border-border pl-1.5">
          {db.tables.map((t) => (
            <TableNode key={t.fq_name} table={t} dbName={db.name} onInsert={onInsert} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function SchemaExplorer({ databases = [], onInsert }) {
  if (!Array.isArray(databases)) {
    return <div className="text-red-500 text-xs">Error: databases is not an array</div>;
  }
  
  if (databases.length === 0) {
    return <div className="text-gray-400 text-xs py-2 px-3">No databases found</div>;
  }

  return (
    <div className="py-2 px-1">
      {databases.map((db, idx) => (
        <DatabaseNode key={db.name} db={db} onInsert={onInsert} defaultOpen={idx === 0} />
      ))}
    </div>
  );
}
