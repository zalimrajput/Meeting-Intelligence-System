"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "@/lib/theme-context";

interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
}

export function ThemeToggle({ className = "", showLabel = false }: ThemeToggleProps) {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        className={`h-9 w-9 rounded-lg border border-slate-700/50 bg-slate-800/40 ${className}`}
        aria-hidden="true"
      />
    );
  }

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`group relative flex items-center gap-2 rounded-lg border transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 ${
        isDark
          ? "border-slate-700/60 bg-slate-800/80 text-amber-300 hover:border-slate-600 hover:bg-slate-700/80"
          : "border-slate-200 bg-white text-indigo-600 shadow-sm hover:border-slate-300 hover:bg-slate-50"
      } ${showLabel ? "px-3 py-1.5 text-xs font-medium" : "p-2"} ${className}`}
      title={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
      aria-label={isDark ? "Switch to Light Theme" : "Switch to Dark Theme"}
    >
      <span className="relative flex h-5 w-5 items-center justify-center">
        {isDark ? (
          /* Sun Icon for Dark Mode (click to make light) */
          <svg
            className="h-4 w-4 transition-transform duration-300 group-hover:rotate-45"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="5" fill="currentColor" fillOpacity="0.2" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        ) : (
          /* Moon Icon for Light Mode (click to make dark) */
          <svg
            className="h-4 w-4 transition-transform duration-300 group-hover:-rotate-12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path
              d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
              fill="currentColor"
              fillOpacity="0.15"
            />
          </svg>
        )}
      </span>

      {showLabel && (
        <span className={isDark ? "text-slate-300" : "text-slate-700"}>
          {isDark ? "Light Mode" : "Dark Mode"}
        </span>
      )}
    </button>
  );
}
