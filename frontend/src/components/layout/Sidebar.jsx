import { NavLink } from "react-router-dom";
import clsx from "clsx";
import {
  LayoutDashboard,
  TrendingUp,
  Store,
  TerminalSquare,
  BarChart3,
  PackageSearch,
  Boxes,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { useAppStore } from "../../store/useAppStore";

/**
 * Sidebar - the module rail. This is the ONE place the platform's modules are
 * listed (the Dashboard deliberately does not repeat them), so it carries the
 * flagship treatment: a titled header, icon tiles, the module numeral from the
 * requirements doc, an accent rail on the active module and a hover state that
 * lifts the item instead of just recolouring it.
 */
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, numeral: null },
  { to: "/secondary", label: "Secondary Sales Analysis", icon: TrendingUp, numeral: "I" },
  { to: "/store-master", label: "Store Master", icon: Store, numeral: "II" },
  { to: "/sql-platform", label: "SQL Platform", icon: TerminalSquare, numeral: "III" },
  { to: "/tertiary", label: "Tertiary Sales Analysis", icon: BarChart3, numeral: "IV" },
  { to: "/css-stock", label: "Order-to-Transformation Tracker", icon: PackageSearch, numeral: "V" },
  { to: "/soh", label: "SOH Analysis", icon: Boxes, numeral: "VI" },
];

export default function Sidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      aria-label="Module navigation"
      className={clsx(
        "h-full flex flex-col shrink-0 z-20 border-r border-border bg-gradient-to-b from-surface via-surface to-base",
        "transition-[width] duration-200 ease-out",
        collapsed ? "w-[68px]" : "w-64"
      )}
    >
      {/* Module header - a labelled section instead of a bare list. */}
      <div
        className={clsx(
          "shrink-0 border-b border-border/70",
          collapsed ? "flex justify-center px-2 py-3.5" : "px-4 py-3.5"
        )}
      >
        <div className={clsx("flex items-center gap-2.5", collapsed && "justify-center")}>
          <span className="h-8 w-1.5 shrink-0 rounded-full bg-gradient-to-b from-accent to-teal shadow-sm" />
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-text-muted">Analysis</p>
              <p className="font-display text-xs font-bold uppercase tracking-[0.16em] text-text-primary">
                Modules
              </p>
            </div>
          )}
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 py-3 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              clsx(
                "group relative flex items-center rounded-lg text-sm font-medium",
                "transition-all duration-200",
                collapsed ? "justify-center px-0 py-2.5" : "gap-3 px-2.5 py-2",
                isActive
                  ? "bg-accent-soft text-accent shadow-sm"
                  : "text-text-secondary hover:bg-card-hover hover:text-text-primary"
              )
            }
          >
            {({ isActive }) => (
              <>
                {/* Accent rail marking the module you are on. */}
                <span
                  className={clsx(
                    "absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r-full bg-accent transition-opacity duration-200",
                    isActive ? "opacity-100" : "opacity-0 group-hover:opacity-40"
                  )}
                />

                {/* Icon tile - gradient when active, quiet otherwise. */}
                <span
                  className={clsx(
                    "relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all duration-200",
                    isActive
                      ? "bg-gradient-to-br from-accent to-accent-hover text-white shadow-sm"
                      : "bg-base/70 text-text-muted group-hover:bg-card-hover group-hover:text-text-primary"
                  )}
                >
                  <item.icon size={15} />
                  {/* Collapsed rail: the requirement-doc numeral rides the tile. */}
                  {collapsed && item.numeral && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-border bg-surface font-display text-[8px] font-bold text-text-muted">
                      {item.numeral}
                    </span>
                  )}
                </span>

                {!collapsed && (
                  <>
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.numeral && (
                      <span
                        className={clsx(
                          "shrink-0 rounded-md border px-1.5 py-0.5 font-display text-[10px] font-bold tabular-nums transition-colors",
                          isActive
                            ? "border-accent/30 bg-surface/70 text-accent"
                            : "border-border/70 bg-base/60 text-text-muted group-hover:text-text-secondary"
                        )}
                      >
                        {item.numeral}
                      </span>
                    )}
                  </>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={toggleSidebar}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={clsx(
          "flex h-11 shrink-0 items-center gap-2 border-t border-border/70 text-xs font-semibold text-text-muted",
          "transition-colors hover:bg-card-hover hover:text-text-primary",
          collapsed ? "justify-center px-0" : "px-4"
        )}
      >
        {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
        {!collapsed && <span>Collapse</span>}
      </button>
    </aside>
  );
}
