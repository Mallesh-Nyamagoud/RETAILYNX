const fs = require('fs');
const file = 'src/components/sql/SqlEditor.jsx';

const code = \import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { sql, SQLite } from "@codemirror/lang-sql";
import { autocompletion } from "@codemirror/autocomplete";
import { EditorView, keymap } from "@codemirror/view";
import { useAppStore } from "../../store/useAppStore";

/**
 * Builds the CodeMirror \\\schema\\\ map from our live schema tree so
 * table/column completions are 100% dynamic.
 */
function buildSchema(databases) {
  const schema = {};
  for (const db of databases) {
    for (const t of db.tables) {
      // Register both bare and qualified table names for native resolution
      schema[t.name] = t.columns.map((c) => c.name);
      schema[\\\\.\\\\] = t.columns.map((c) => c.name);
    }
  }
  return schema;
}

/** 
 * A global fuzzy-match autocompletion source. IDEs like DBeaver don't just rely 
 * on perfect AST parsing to suggest columns—they aggressively suggest columns 
 * globally as you type. This combines DuckDB functions, keywords, AND our live schema.
 */
function globalCompletionSource(databases, functions, keywords) {
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
    ...keywords.map((k) => ({ label: k, type: "keyword", boost: 1 })),
    ...functions.map((f) => ({ label: f, type: "function", detail: "DuckDB function", boost: 2 })),
    ...Array.from(tableNames).map((t) => ({ label: t, type: "class", detail: "Table", boost: 3 })),
    ...Array.from(columnNames).map((c) => ({ label: c, type: "property", detail: "Column", boost: 4 })),
  ];

  return (context) => {
    const word = context.matchBefore(/[\\w"]*/);
    if (!word || (word.from === word.to && !context.explicit)) return null;
    return { from: word.from, options };
  };
}

export default function SqlEditor({ value, onChange, databases, functions, keywords, onRun }) {
  const theme = useAppStore((s) => s.theme);

  const schema = useMemo(() => buildSchema(databases), [databases]);

  const extensions = useMemo(() => {
    const sqlExt = sql({ dialect: SQLite, schema, upperCaseKeywords: true });
    
    // OVERRIDE default behavior with aggressive global fuzzy matcher
    const extraCompletion = autocompletion({
      override: [globalCompletionSource(databases, functions, keywords)],
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
  }, [schema, databases, functions, keywords, onRun]);

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
\;

fs.writeFileSync(file, code);
