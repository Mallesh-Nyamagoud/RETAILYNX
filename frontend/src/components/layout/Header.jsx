import { Moon, Sun, RefreshCw, User, LogOut, Users } from "lucide-react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import { useMutation } from "@tanstack/react-query";
import { useAppStore } from "../../store/useAppStore";
import { metaApi } from "../../api/client";
import { useState, useRef, useEffect } from "react";
import { useAuthStore } from "../../store/useAuthStore";

export default function Header() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const [justRecomputed, setJustRecomputed] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const menuRef = useRef(null);
  
  const { user, logout } = useAuthStore();

  const recompute = useMutation({
    mutationFn: metaApi.recomputeStoreStatus,
    onSuccess: () => {
      setJustRecomputed(true);
      setTimeout(() => setJustRecomputed(false), 2200);
    },
  });

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowUserMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="w-full bg-card border border-border rounded-xl shadow-sm px-6 py-5 flex items-center justify-between">
      <div className="flex items-center gap-5 md:gap-6">
        <div className="w-16 h-16 md:w-20 md:h-20 shrink-0 flex items-center justify-center">
          <img
            src="/logo.png"
            alt="RETAILYNX"
            className="max-w-full max-h-full object-contain drop-shadow-md"
            onError={(e) => (e.currentTarget.style.display = 'none')}
          />
        </div>
        <div className="flex flex-col">
          <h1 className="text-[28px] md:text-4xl font-display font-bold text-text-primary tracking-wide leading-tight">
            RETAILYNX
          </h1>
          <p className="text-sm md:text-base font-medium text-accent mt-1 md:mt-0.5 tracking-wide">
            Retail Intelligence & Analysis Platform
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          title="Recompute TER.MIN/TER.MAX/STORE STATUS from Tertiary Data"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide uppercase text-text-secondary hover:text-text-primary hover:bg-card-hover transition-colors disabled:opacity-50 border border-transparent hover:border-border"
        >
          <RefreshCw size={14} className={recompute.isPending ? "animate-spin" : ""} />
          {justRecomputed ? "Recomputed ✓" : "Sync Data"}
        </button>
        <div className="w-px h-6 bg-border"></div>
        <button
          onClick={toggleTheme}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-text-secondary hover:text-text-primary hover:bg-card-hover transition-colors"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        
        <div className="relative" ref={menuRef}>
          <button 
            onClick={() => setShowUserMenu(!showUserMenu)}
            title="Account"
            aria-label="Account menu"
            aria-haspopup="menu"
            aria-expanded={showUserMenu}
            className="w-9 h-9 rounded-full bg-accent text-white flex items-center justify-center shadow-sm hover:ring-2 hover:ring-accent/30 transition-all focus:outline-none"
          >
            <User size={18} />
          </button>

          {showUserMenu && (
            <div className="absolute right-0 mt-2 w-60 bg-surface border border-border rounded-lg shadow-panel z-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-border bg-base/50">
                <div className="text-sm font-medium text-text-primary truncate" title={user?.username}>
                  {user?.username || "User"}
                </div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-accent mt-1">
                  {user?.role || "USER"}
                </div>
              </div>

              {user?.role === "ADMIN" && (
                <div className="p-1 border-b border-border">
                  <div className="px-3 pt-1.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    Admin
                  </div>
                  <NavLink
                    to="/admin/users"
                    onClick={() => setShowUserMenu(false)}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors",
                        isActive
                          ? "bg-accent-soft text-accent"
                          : "text-text-secondary hover:text-text-primary hover:bg-card-hover"
                      )
                    }
                  >
                    <Users size={16} />
                    User Access
                  </NavLink>
                </div>
              )}

              <div className="p-1">
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-negative hover:bg-negative-soft rounded-md transition-colors"
                >
                  <LogOut size={16} />
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}