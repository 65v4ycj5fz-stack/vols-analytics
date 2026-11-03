export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function fmt(v: unknown, unit = "", digits?: number): string {
  if (!isNum(v)) return "—";
  if (unit === "%") return `${(v * 100).toFixed(digits ?? 1)}%`;
  if (unit === "pts/play" || unit === "EPA/play") return v.toFixed(digits ?? 3);
  return v.toFixed(digits ?? (Math.abs(v) >= 100 ? 0 : 1));
}

export const signed = (v: unknown, digits = 1): string => (isNum(v) ? `${v > 0 ? "+" : ""}${v.toFixed(digits)}` : "—");
export const pct = (v: unknown, digits = 0): string => (isNum(v) ? `${(v * 100).toFixed(digits)}%` : "—");

/** Spread convention: negative = team favored. "TEN -6.5", "TEN +3", "PK". */
export function spreadLabel(spread: unknown, team = "TEN"): string {
  if (!isNum(spread)) return "—";
  if (spread === 0) return "PK";
  return `${team} ${spread > 0 ? "+" : ""}${spread}`;
}

export function dateLabel(iso: string, withTime = false): string {
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" };
  if (withTime) Object.assign(opts, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  return d.toLocaleString(undefined, opts);
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export const ordinal = (n: unknown): string => {
  if (!isNum(n)) return "—";
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export const siteWord = (site: string) => (site === "home" ? "vs" : site === "away" ? "at" : "vs (N)");
