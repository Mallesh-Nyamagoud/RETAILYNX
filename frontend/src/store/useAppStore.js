import { create } from "zustand";

const THEME_KEY = "racc-theme"; // Retail Analytics Command Center

function getInitialTheme() {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* localStorage unavailable */
  }
  return "dark";
}

function applyThemeClass(theme) {
  const root = document.documentElement;
  if (theme === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

const initialTheme = getInitialTheme();
if (typeof document !== "undefined") applyThemeClass(initialTheme);

export const useAppStore = create((set, get) => ({
  theme: initialTheme,
  sidebarCollapsed: false,
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    applyThemeClass(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      /* ignore */
    }
    set({ theme: next });
  },
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
