import { useEffect, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import clsx from "clsx";
import Card from "./Card";

/** Locks body scroll while the large view overlay is open. */
function BodyScrollLock() {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);
  return null;
}

/**
 * Analysis section card with a professional LARGE-VIEW (full screen) toggle.
 *
 * Every analysis section (row hierarchy, distributions, top bills, category
 * tables) renders inside one of these, so the user can expand any single
 * section to a distraction-free full-screen working view:
 *   - normal  : the standard bordered card, exactly like before
 *   - maximized : fixed inset-0 overlay, sticky header, Esc to close
 *
 * `children` may be a render-function `({ maximized }) => node` so tables can
 * switch to a taller internal scroll pane when maximized.
 */
export default function SectionCard({
  title,
  icon: Icon,
  /** small colored dot before the title (section identity color) */
  dot,
  right,
  className,
  children,
}) {
  const [maximized, setMaximized] = useState(false);

  // Esc exits the large view - standard, expected fullscreen behaviour.
  useEffect(() => {
    if (!maximized) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setMaximized(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [maximized]);

  const content = typeof children === "function" ? children({ maximized }) : children;

  const header = (
    <div
      className={clsx(
        "flex items-start justify-between gap-4 px-4 py-3 border-b border-border bg-gradient-to-r from-card to-surface",
        maximized && "sticky top-0 z-20 backdrop-blur-sm"
      )}
    >
      <div className="flex items-start gap-2.5 min-w-0">
        {Icon && (
          <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
            <Icon size={14} />
          </span>
        )}
        {dot && <span className={clsx("mt-2.5 h-2 w-2 shrink-0 rounded-full", dot)} />}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-primary truncate">{title}</h3>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {right}
        <button
          type="button"
          onClick={() => setMaximized((v) => !v)}
          title={maximized ? "Exit large view (Esc)" : "View this section in large view"}
          className={clsx(
            "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-semibold transition-colors",
            maximized
              ? "border-accent/40 bg-accent-soft text-accent"
              : "border-border text-text-secondary hover:text-accent hover:border-accent/50"
          )}
        >
          {maximized ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          {maximized ? "Exit large view" : "Large view"}
        </button>
      </div>
    </div>
  );

  if (maximized) {
    return (
      <>
        <BodyScrollLock />
        <div className="fixed inset-0 z-50 bg-surface overflow-y-auto animate-fadeIn">
          {header}
          <div className="p-4">{content}</div>
        </div>
      </>
    );
  }

  return (
    <Card padded={false} className={clsx("overflow-hidden", className)}>
      {header}
      <div className="p-4">{content}</div>
    </Card>
  );
}