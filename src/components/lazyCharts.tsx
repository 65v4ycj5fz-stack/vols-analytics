import { lazy, Suspense, type ComponentType } from "react";
import type * as Charts from "./charts";

/** Charts load Recharts on demand, so text and numbers render first. The placeholder keeps the
 *  chart's height so nothing shifts when it arrives. */
function lazyChart<K extends keyof typeof Charts>(name: K, defaultHeight: number) {
  const L = lazy(() => import("./charts").then((m) => ({ default: m[name] as unknown as ComponentType<object> })));
  return function LazyChart<P extends object>(props: P & { height?: number }) {
    const h = props.height ?? defaultHeight;
    return (
      <Suspense fallback={<div aria-hidden className="animate-pulse rounded-md bg-surface-2" style={{ height: h }} />}>
        <L {...(props as object)} />
      </Suspense>
    );
  } as unknown as (typeof Charts)[K];
}

export const LineSeriesChart = lazyChart("LineSeriesChart", 240);
export const ColumnChart = lazyChart("ColumnChart", 220);
export const CalibrationChart = lazyChart("CalibrationChart", 280);
export const HBarChart = lazyChart("HBarChart", 200);
export const GroupScatter = lazyChart("GroupScatter", 300);
