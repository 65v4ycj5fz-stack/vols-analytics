import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useDataset, type SiteMeta } from "../lib/data";
import { ago } from "../lib/format";

const NAV = [
  ["/", "Dashboard"], ["/matchup", "Matchup"], ["/schedule", "Schedule"], ["/team", "Team Stats"],
  ["/players", "Players"], ["/depth", "Depth Chart"], ["/injuries", "Injuries"], ["/tendencies", "Schemes & Tendencies"],
  ["/model", "Model"], ["/data", "Data"],
] as const;

function ThemeToggle() {
  const [theme, setTheme] = useState<string | undefined>(() => document.documentElement.dataset.theme);
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { if (theme) localStorage.setItem("theme", theme); else localStorage.removeItem("theme"); } catch { /* storage blocked */ }
  }, [theme]);
  const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const isDark = theme ? theme === "dark" : systemDark;
  return (
    <button type="button" onClick={() => setTheme(isDark ? "light" : "dark")}
      className="rounded-md border border-black/15 px-2 py-1 text-xs font-medium text-on-brand hover:bg-black/10"
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}>
      {isDark ? "☀ Light" : "☾ Dark"}
    </button>
  );
}

export function Layout() {
  const meta = useDataset<SiteMeta>("meta");
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        Skip to content
      </a>
      <header className="checker checker-on-brand sticky top-0 z-40 border-b border-black/10 bg-brand text-on-brand">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5">
          <NavLink to="/" className="text-lg font-extrabold tracking-tight text-on-brand no-underline">
            VOLS<span className="font-medium"> ANALYTICS</span>
          </NavLink>
          <div className="flex items-center gap-2">
            <span className="hidden text-xs sm:inline">
              {meta.status === "ready" ? `Updated ${ago(meta.data.last_refreshed)}` : ""}
            </span>
            <ThemeToggle />
            <button type="button" className="rounded-md border border-black/15 px-2 py-1 text-xs font-medium lg:hidden"
              aria-expanded={open} aria-controls="mainnav" onClick={() => setOpen(!open)}>Menu</button>
          </div>
        </div>
        <nav id="mainnav" aria-label="Main" className={`${open ? "block" : "hidden"} border-t border-black/10 bg-surface lg:block`}>
          <ul className="mx-auto flex max-w-7xl flex-col px-2 lg:flex-row lg:flex-wrap lg:px-4">
            {NAV.map(([to, label]) => (
              <li key={to}>
                <NavLink to={to} end={to === "/"}
                  className={({ isActive }) => `block px-3 py-2 text-sm no-underline ${isActive
                    ? "border-b-2 border-brand font-semibold text-ink" : "text-ink-2 hover:text-ink"}`}>
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="mx-auto min-h-screen w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto max-w-7xl px-4 py-5 text-xs text-ink-3">
          <p><strong className="text-ink-2">Unofficial fan project.</strong> Not affiliated with or endorsed by the
            University of Tennessee, its athletics department, or the SEC. No official logos or trademarks are used.</p>
          <p className="mt-1">Data: <a href="https://collegefootballdata.com" rel="noopener">CollegeFootballData.com</a> (CFBD).
            Weather data by <a href="https://open-meteo.com" rel="noopener">Open-Meteo.com</a> (CC BY 4.0).
            Injuries, depth chart and scheme notes are manual entries with their sources listed.</p>
          <p className="mt-1">Model outputs are estimates with stated uncertainty. This site has no wagering features.</p>
        </div>
      </footer>
    </div>
  );
}
