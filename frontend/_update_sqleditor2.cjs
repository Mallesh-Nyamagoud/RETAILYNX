const fs = require('fs');
const file = 'src/components/sql/SqlEditor.jsx';

const code = \import { useMemo, useRef, useEffect } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { sql, SQLite } from "@codemirror/lang-sql";
import { autocompletion } from "@codemirror/autocomplete";
import { EditorView, keymap } from "@codemirror/view";
import { useAppStore } from "../../store/useAppStore";

/**
 * Builds the CodeMirror schema map for the native SQL parser.
 */
function buildSchema(databases) {
  const schema = {};
  for (const db of databases) {
    for (const t of db.tables) {
      schema[t.name] = t.columns.map((c) => c.name);
      schema[\\\\.\\\\] = t.columns.map((c) => c.name);
    }
  }
  return schema;
}

/** 
 * A dynamic autocomplete source that always reads the latest refs.
 * This completely avoids CodeMirror extension-reconciliation bugs because 
 * the source itself never needs to be recreated.
 */
function createDynamicCompletionSource(dbRef, funcRef, kwRef) {
  return (context) => {
    const word = context.matchBefore(/[\\w"]*/);
    if (!word || (word.from === word.to && !context.explicit)) return null;

    const databases = dbRef.current || [];
    const functions = funcRef.current || [];
    const keywords = kwRef.current || [];

    const tableNames = new Set();
    const columnNames = new Set();
    
    for (const db of databases) {
      for (const t of db.tables) {
        tableNames.add(t.name);
        for (const c of t.columns) {
          columnNames.add(c.name);
        }
      }
    }

    const options = [
      ...keywords.map((k) => ({ label: k, type: "keyword", boost: -1 })),
      ...functions.map((f) => ({ label: f, type: "function", detail: "DuckDB", boost: 0 })),
      ...Array.from(tableNames).map((t) => ({ label: t, type: "class", detail: "Table", boost: 3 })),
      ...Array.from(columnNames).map((c) => ({ label: c, type: "property", detail: "Column", boost: 2 })),
    ];

    return { from: word.from, options };
  };
}

export default function SqlEditor({ value, onChange, databases, functions, keywords, onRun }) {
  const theme = useAppStore((s) => s.theme);

  const dbRef = useRef(databases);
  const funcRef = useRef(functions);
  const kwRef = useRef(keywords);

  useEffect(() => {
    dbRef.current = databases;
    funcRef.current = functions;
    kwRef.current = keywords;
  }, [databases, functions, keywords]);

  const schema = useMemo(() => buildSchema(databases), [databases]);

  const extensions = useMemo(() => {
    const sqlExt = sql({ dialect: SQLite, schema, upperCaseKeywords: true });
    
    // We override the default completion so our aggressive fuzzy matcher takes over
    const extraCompletion = autocompletion({
      override: [createDynamicCompletionSource(dbRef, funcRef, kwRef)],
    });
    
    const runKeymap = keymap.of([
      {
        key: "Mod-Enter",
        run: () => {
          onRun?.();
          return true;
        },
      },
    ]);
    return [sqlExt, extraCompletion, runKeymap, EditorView.lineWrapping];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema, onRun]); // Intentionally omitting refs so it doesn't re-mount

  return (
    <CodeMirror
      value={value}
      height="100%"
      className="flex-1 overflow-auto text-sm"
      theme={theme === "dark" ? "dark" : "light"}
      extensions={extensions}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: true,
        autocompletion: true,
        bracketMatching: true,
        closeBrackets: true,
      }}
    />
  );
}
\

fs.writeFileSync(file, code);
