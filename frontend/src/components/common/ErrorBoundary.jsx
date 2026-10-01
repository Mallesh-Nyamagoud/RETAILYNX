import React from "react";

/**
 * Global error boundary. Without this, any runtime error anywhere in the tree
 * unmounts React and leaves a completely blank page with no clue as to why.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info?.componentStack);
    this.setState({ info });
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;
    return (
      <div style={{ padding: 32, fontFamily: "monospace", color: "#e2e8f0", background: "#0b1120", minHeight: "100vh" }}>
        <h1 style={{ color: "#f87171", fontSize: 20, marginBottom: 12 }}>Something crashed while rendering</h1>
        <pre style={{ color: "#fca5a5", whiteSpace: "pre-wrap", fontSize: 13 }}>{String(error && (error.stack || error.message || error))}</pre>
        {info?.componentStack ? (
          <pre style={{ color: "#94a3b8", whiteSpace: "pre-wrap", fontSize: 12, marginTop: 16 }}>{info.componentStack}</pre>
        ) : null}
        <button
          onClick={() => { this.setState({ error: null, info: null }); window.location.href = "/"; }}
          style={{ marginTop: 20, padding: "8px 16px", background: "#4f6ef7", color: "white", border: "none", borderRadius: 6, cursor: "pointer" }}
        >
          Reload app
        </button>
      </div>
    );
  }
}
