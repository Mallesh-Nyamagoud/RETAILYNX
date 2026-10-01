/**
 * Shared visual language for the Dashboard charts.
 *
 * Every chart on the page (period comparison bars, contribution donuts) reads
 * its colours from here, so one locale/theme change keeps the whole page
 * visually consistent - the same way a Power BI report theme drives every
 * visual of a report page at once.
 */
import { useAppStore } from "../../store/useAppStore";

/** The app's period colour coding: LFY is the slate "last year" tone, LFYTD the
 * same slate one step lighter ("last year so far") and CFYTD the accent blue of
 * the current year - identical semantics to the Bill No. / Category charts. */
export const PERIOD_SERIES = [
  { key: "LFY", label: "LFY", hint: "Last full FY" },
  { key: "LFYTD", label: "LFYTD", hint: "Last FY, same period" },
  { key: "CFYTD", label: "CFYTD", hint: "Current FY to date" },
];

const DARK = {
  series: { LFY: "#94a3b8", LFYTD: "#cbd5e1", CFYTD: "#38bdf8" },
  grid: "#4a5a6a",
  axis: "#94a3b8",
  label: "#cbd5e1",
  cursor: "rgba(255, 255, 255, 0.06)",
  tooltipBg: "rgba(30, 41, 59, 0.97)",
  tooltipBorder: "#4a5a6a",
  donut: ["#38bdf8", "#2dd4bf", "#818cf8", "#fbbf24", "#4ade80", "#f472b6", "#f87171", "#a78bfa"],
};

const LIGHT = {
  series: { LFY: "#94a3b8", LFYTD: "#cbd5e1", CFYTD: "#3f5eea" },
  grid: "#e5e7f2",
  axis: "#8791ac",
  label: "#566080",
  cursor: "rgba(15, 23, 42, 0.05)",
  tooltipBg: "rgba(255, 255, 255, 0.98)",
  tooltipBorder: "#e5e7f2",
  donut: ["#3f5eea", "#0e9488", "#6554c0", "#b45309", "#16a34a", "#db2777", "#e11d48", "#7c3aed"],
};

/** Light/dark palette for the current theme (re-renders when the user toggles). */
export function useChartPalette() {
  const theme = useAppStore((s) => s.theme);
  return theme === "light" ? LIGHT : DARK;
}
