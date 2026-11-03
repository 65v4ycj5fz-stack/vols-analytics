import { useState } from "react";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { DATASETS, dataUrl, useDataset, type SiteMeta } from "../lib/data";
import { ago } from "../lib/format";

export default function DataPage() {
  const meta = useDataset<SiteMeta>("meta");
  const [copied, setCopied] = useState<string | null>(null);
  if (meta.status === "loading") return <Loading />;
  if (meta.status === "error") return <ErrorState error={meta.error} />;
  const abs = (name: string) => new URL(dataUrl(name, "csv"), window.location.href.split("#")[0]).href;
  const copy = async (name: string) => {
    const f = `=IMPORTDATA("${abs(name)}")`;
    try { await navigator.clipboard.writeText(f); setCopied(name); } catch { setCopied(null); window.prompt("Copy this formula:", f); }
  };
  return (
    <>
      <PageHeader title="Data" subtitle={<>Every table on this site as CSV. Last refreshed {new Date(meta.data.last_refreshed).toLocaleString()} ({ago(meta.data.last_refreshed)}).</>} />
      <Card title="Downloads" subtitle="CSV files open in Excel, Numbers or Google Sheets.">
        <ul className="divide-y divide-line">
          {DATASETS.map((d) => (
            <li key={d.name} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span>{d.label} <code className="text-xs text-ink-3">{d.name}.csv</code></span>
              <span className="flex gap-2">
                <a href={dataUrl(d.name, "csv")} download className="rounded-md bg-brand px-3 py-1 text-xs font-semibold text-on-brand no-underline hover:opacity-90">Download CSV</a>
                <button type="button" onClick={() => copy(d.name)} className="rounded-md border border-line px-3 py-1 text-xs hover:bg-surface-2">
                  {copied === d.name ? "Copied!" : "Copy Sheets formula"}</button>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="mt-4" title="Mirror in Google Sheets">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Open a new Google Sheet.</li>
          <li>Click "Copy Sheets formula" next to a dataset above and paste it into cell A1 of a tab.</li>
          <li>Sheets re-fetches the file about once an hour, so the tab stays in sync with this site's daily refresh.</li>
        </ol>
        <p className="mt-2 text-xs text-ink-3">Example: <code>=IMPORTDATA("{abs("schedule")}")</code></p>
      </Card>
      <Card className="mt-4" title="Sources & credits">
        <p className="text-sm">Game, stat, play-by-play, player, ratings and betting-line data come from
          {" "}<a href="https://collegefootballdata.com" rel="noopener">CollegeFootballData.com</a>. Game-time weather is from
          {" "}<a href="https://open-meteo.com" rel="noopener">Open-Meteo</a> (CC BY 4.0). Depth chart, injuries and scheme notes are manual entries; each row lists its source.
          Every JSON file includes when its data was fetched.</p>
      </Card>
    </>
  );
}
