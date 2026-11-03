import { useId, useState, type ReactNode } from "react";
import type { LoadState, Meta } from "../lib/data";
import { ago } from "../lib/format";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, subtitle, children, className = "", actions }:
  { title?: ReactNode; subtitle?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode }) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, sub, accent = false }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className={`rounded-lg border border-line p-3 ${accent ? "bg-surface-2" : "bg-surface"}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className="tabular mt-1 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

export function Loading({ label = "Loading data…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="animate-pulse rounded-xl border border-line bg-surface p-6 text-sm text-ink-3">
      {label}
    </div>
  );
}

export function ErrorState({ error }: { error: string }) {
  return (
    <div role="alert" className="rounded-xl border border-critical/40 bg-edge-bad p-4 text-sm">
      <strong>Couldn't load data.</strong> {error}. The data files are produced by the pipeline (<code>make data</code>);
      if this is a fresh deploy, the scheduled refresh may not have run yet.
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-surface-2 p-4 text-sm text-ink-2">
      <div className="font-medium text-ink">{title}</div>
      {children && <div className="mt-1">{children}</div>}
    </div>
  );
}

/** Renders loading/error states and passes ready data to children. */
export function Gate<T>({ state, children, label }: { state: LoadState<T>; children: (data: T, meta: Meta) => ReactNode; label?: string }) {
  if (state.status === "loading") return <Loading label={label} />;
  if (state.status === "error") return <ErrorState error={state.error} />;
  return <>{children(state.data, state.meta)}</>;
}

export function SourceNote({ meta, extra }: { meta?: Meta; extra?: ReactNode }) {
  if (!meta) return null;
  const srcs = [...new Set(meta.sources.map((s) => s.source))].join(", ") || "derived";
  return (
    <p className="mt-2 text-xs text-ink-3">
      Source: {srcs}. Data as of {meta.data_as_of ? new Date(meta.data_as_of).toLocaleString() : "—"} ({ago(meta.data_as_of)}).
      {extra && <> {extra}</>}
    </p>
  );
}

/** Info icon with an accessible popover listing a dataset's sources and notes. */
export function InfoTip({ meta, children }: { meta?: Meta; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-block">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full border border-line text-[11px] font-semibold text-ink-2 hover:bg-surface-2"
        aria-label="About this data">i</button>
      {open && (
        <span id={id} role="dialog"
          className="absolute right-0 z-30 mt-2 block w-72 rounded-lg border border-line bg-surface p-3 text-left text-xs font-normal text-ink-2 shadow-lg">
          {children}
          {meta && (
            <>
              <span className="block font-medium text-ink">{meta.description}</span>
              <span className="mt-1 block">Sources: {meta.sources.map((s) => `${s.source} ${s.endpoint}`).join("; ") || "derived"}</span>
              <span className="mt-1 block">As of: {meta.data_as_of ? new Date(meta.data_as_of).toLocaleString() : "—"}</span>
              {meta.notes.map((n) => <span key={n} className="mt-1 block">• {n}</span>)}
            </>
          )}
        </span>
      )}
    </span>
  );
}

/** Every chart: title, subtitle with units, source tooltip, and a "show table" toggle. */
export function ChartFrame({ title, subtitle, meta, table, children, note }:
  { title: string; subtitle: string; meta?: Meta; table?: ReactNode; children: ReactNode; note?: ReactNode }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="rounded-xl border border-line bg-surface p-4 shadow-sm sm:p-5">
      <figcaption className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold">{title}<InfoTip meta={meta} /></div>
          <div className="text-xs text-ink-3">{subtitle}</div>
        </div>
        {table && (
          <button type="button" onClick={() => setShowTable(!showTable)} aria-pressed={showTable}
            className="shrink-0 rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:bg-surface-2">
            {showTable ? "Chart" : "Table"}
          </button>
        )}
      </figcaption>
      {showTable ? <div className="max-h-96 overflow-auto" tabIndex={0} role="region" aria-label={`${title} (table)`}>{table}</div> : children}
      {note && <div className="mt-2 text-xs text-ink-3">{note}</div>}
    </figure>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <ul className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="Legend">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4" style={{ background: i.dashed ? "none" : i.color,
            borderTop: i.dashed ? `2px dashed ${i.color}` : undefined }} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

const STATUS: Record<string, { cls: string; icon: string }> = {
  out: { cls: "bg-critical text-white", icon: "✕" },
  doubtful: { cls: "bg-serious text-ink", icon: "!" },
  questionable: { cls: "bg-warning text-ink", icon: "?" },
  probable: { cls: "bg-good text-white", icon: "✓" },
  available: { cls: "bg-good text-white", icon: "✓" },
};
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status.toLowerCase()] ?? { cls: "bg-surface-2 text-ink", icon: "•" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${s.cls}`}>
      <span aria-hidden>{s.icon}</span>{status}
    </span>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "bad" | "brand" }) {
  const cls = { neutral: "bg-surface-2 text-ink-2", good: "bg-edge-good text-ink", bad: "bg-edge-bad text-ink",
                brand: "bg-brand text-on-brand" }[tone];
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}

export function Select<T extends string>({ label, value, onChange, options }:
  { label: string; value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs font-medium text-ink-2">
      {label}
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as T)}
        className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-sm">
      <thead><tr>{head.map((h) => <th key={h} scope="col" className="border-b border-line px-2 py-1 text-left text-xs text-ink-2">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-line">{r.map((c, j) =>
        <td key={j} className="tabular px-2 py-1">{c}</td>)}</tr>)}</tbody>
    </table>
  );
}
