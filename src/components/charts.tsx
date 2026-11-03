import type { ReactNode } from "react";
import { C } from "./chartColors";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";

const axis = { stroke: C.grid, tick: { fill: C.ink3, fontSize: 11 }, tickLine: false };
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
// Recharts 3 types dataKey against the row type's paths; our keys are already checked as keyof T.
const dk = (k: string) => k as never;

export function TipBox({ title, rows }: { title?: ReactNode; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-md">
      {title && <div className="mb-0.5 font-semibold text-ink">{title}</div>}
      {rows.map(([k, v], i) => (
        <div key={i} className="flex justify-between gap-4 text-ink-2"><span>{k}</span><span className="tabular text-ink">{v}</span></div>
      ))}
    </div>
  );
}

type TipFn<T> = (row: T) => { title?: ReactNode; rows: [ReactNode, ReactNode][] };
function tooltip<T>(fn: TipFn<T>) {
  return (
    <Tooltip cursor={{ fill: "var(--surface-2)", stroke: C.grid }} isAnimationActive={false}
      content={({ active, payload }) => {
        if (!active || !payload?.length) return null;
        const t = fn(payload[0].payload as T);
        return <TipBox {...t} />;
      }} />
  );
}

export function LineSeriesChart<T extends object>({ data, x, series, yLabel, xLabel, height = 240, yDomain, refY, tip }: {
  data: T[]; x: keyof T & string; series: { key: keyof T & string; color: string; label: string; dashed?: boolean }[];
  yLabel: string; xLabel: string; height?: number; yDomain?: [number | string, number | string]; refY?: { y: number; label: string };
  tip: TipFn<T>;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey={dk(x)} {...axis} label={{ value: xLabel, position: "insideBottom", offset: -10, fill: C.ink3, fontSize: 11 }} />
        <YAxis {...axis} width={48} domain={yDomain ?? [(min: number) => Math.floor(min - Math.abs(min) * 0.02), (max: number) => Math.ceil(max + Math.abs(max) * 0.02)]} allowDecimals={false}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: C.ink3, fontSize: 11, dy: 40 }} />
        {refY && <ReferenceLine y={refY.y} stroke={C.neutral} strokeDasharray="4 3"
          label={{ value: refY.label, fill: C.ink3, fontSize: 10, position: "insideTopRight" }} />}
        {tooltip(tip)}
        {series.map((s) => (
          <Line key={s.key} type="linear" dataKey={dk(s.key)} name={s.label} stroke={s.color} strokeWidth={2}
            strokeDasharray={s.dashed ? "5 4" : undefined} dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: s.color }}
            activeDot={{ r: 6, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ColumnChart<T extends object>({ data, x, y, colorFor, yLabel, xLabel, height = 220, tip, refX, yFormat }: {
  data: T[]; x: keyof T & string; y: keyof T & string; colorFor: (row: T) => string; yLabel: string; xLabel: string;
  height?: number; tip: TipFn<T>; refX?: { x: number | string; label: string }; yFormat?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 4 }} barCategoryGap={1}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey={dk(x)} {...axis} interval="preserveStartEnd" minTickGap={16}
          label={{ value: xLabel, position: "insideBottom", offset: -10, fill: C.ink3, fontSize: 11 }} />
        <YAxis {...axis} width={44} tickFormatter={yFormat}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: C.ink3, fontSize: 11, dy: 40 }} />
        {refX && <ReferenceLine x={refX.x} stroke={C.ink3} label={{ value: refX.label, fill: C.ink3, fontSize: 10, position: "top" }} />}
        {tooltip(tip)}
        <Bar dataKey={dk(y)} radius={BAR_RADIUS} maxBarSize={24} isAnimationActive={false}>
          {data.map((d, i) => <Cell key={i} fill={colorFor(d)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CalibrationChart<T extends { mean_predicted: number; actual_rate: number; n: number }>({ data, color, tip, height = 280 }:
  { data: T[]; color: string; tip: TipFn<T>; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 22, left: 4 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis type="number" dataKey="mean_predicted" domain={[0, 1]} {...axis} tickFormatter={(v) => `${Math.round(v * 100)}%`}
          label={{ value: "Predicted home win probability", position: "insideBottom", offset: -12, fill: C.ink3, fontSize: 11 }} />
        <YAxis type="number" dataKey="actual_rate" domain={[0, 1]} {...axis} width={44} tickFormatter={(v) => `${Math.round(v * 100)}%`}
          label={{ value: "Actual home win rate", angle: -90, position: "insideLeft", fill: C.ink3, fontSize: 11, dy: 50 }} />
        <ZAxis type="number" dataKey="n" range={[60, 260]} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={C.neutral} strokeDasharray="4 3" />
        {tooltip(tip)}
        <Scatter data={data} fill={color} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars from a zero baseline (values may be negative). */
export function HBarChart<T extends object>({ data, y, x, colorFor, xLabel, tip, height, xFormat }: {
  data: T[]; y: keyof T & string; x: keyof T & string; colorFor: (row: T) => string; xLabel: string;
  tip: TipFn<T>; height?: number; xFormat?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(120, data.length * 30 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid stroke={C.grid} horizontal={false} />
        <XAxis type="number" {...axis} tickFormatter={xFormat}
          label={{ value: xLabel, position: "insideBottom", offset: -10, fill: C.ink3, fontSize: 11 }} />
        <YAxis type="category" dataKey={dk(y)} {...axis} width={110} />
        <ReferenceLine x={0} stroke={C.ink3} />
        {tooltip(tip)}
        <Bar dataKey={dk(x)} maxBarSize={20} radius={4} isAnimationActive={false}>
          {data.map((d, i) => <Cell key={i} fill={colorFor(d)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Scatter of discrete groups (e.g. 4th-down decisions), one color per group, legend outside. */
export function GroupScatter<T extends object>({ groups, x, y, xLabel, yLabel, tip, height = 300, xDomain, yDomain }: {
  groups: { label: string; color: string; data: T[] }[]; x: keyof T & string; y: keyof T & string;
  xLabel: string; yLabel: string; tip: TipFn<T>; height?: number; xDomain?: [number, number]; yDomain?: [number, number];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 22, left: 4 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis type="number" dataKey={dk(x)} domain={xDomain} {...axis}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: C.ink3, fontSize: 11 }} />
        <YAxis type="number" dataKey={dk(y)} domain={yDomain} {...axis} width={44} reversed
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: C.ink3, fontSize: 11, dy: 60 }} />
        {tooltip(tip)}
        {groups.map((g) => (
          <Scatter key={g.label} name={g.label} data={g.data} fill={g.color} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}
