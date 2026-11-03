import { lazy, Suspense, useEffect, useRef, useState, type ComponentType } from "react";
import type * as Charts from "./charts";

/** Charts load Recharts (~400 KB) only when they scroll near the screen, so text and numbers
 *  render first and phones don't parse chart code during the initial load. The placeholder keeps
 *  the chart's height so nothing shifts when it arrives. */
function lazyChart<K extends keyof typeof Charts>(name: K, defaultHeight: number) {
  const L = lazy(() => import("./charts").then((m) => ({ default: m[name] as unknown as ComponentType<object> })));
  return function LazyChart<P extends object>(props: P & { height?: number }) {
    const h = props.height ?? defaultHeight;
    const ref = useRef<HTMLDivElement>(null);
    const [near, setNear] = useState(typeof IntersectionObserver === "undefined");
    useEffect(() => {
      if (near || !ref.current) return;
      const io = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) setNear(true); }, { rootMargin: "300px" });
      io.observe(ref.current);
      return () => io.disconnect();
    }, [near]);
    const placeholder = <div ref={ref} aria-hidden className="animate-pulse rounded-md bg-surface-2" style={{ height: h }} />;
    if (!near) return placeholder;
    return <Suspense fallback={placeholder}><L {...(props as object)} /></Suspense>;
  } as unknown as (typeof Charts)[K];
}

export const LineSeriesChart = lazyChart("LineSeriesChart", 240);
export const ColumnChart = lazyChart("ColumnChart", 220);
export const CalibrationChart = lazyChart("CalibrationChart", 280);
export const HBarChart = lazyChart("HBarChart", 200);
export const GroupScatter = lazyChart("GroupScatter", 300);
