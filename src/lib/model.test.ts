import { describe, expect, it } from "vitest";
import { normCdf, simulateGame } from "./model";
import { fmt, ordinal, signed, spreadLabel } from "./format";

describe("normCdf", () => {
  it("matches known values", () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6);
    expect(normCdf(1)).toBeCloseTo(0.841345, 5);
    expect(normCdf(-1.96)).toBeCloseTo(0.024998, 5);
  });
});

describe("simulateGame (mirrors model/simulate.py)", () => {
  it("is deterministic for a seed and matches the analytic win probability", () => {
    const a = simulateGame(4, 52, 16, 16, 0.05, 20000, 7);
    const b = simulateGame(4, 52, 16, 16, 0.05, 20000, 7);
    expect(a).toEqual(b);
    expect(a.winProb).toBeCloseTo(normCdf(4 / 16), 1);
    expect(Math.abs(a.winProb - normCdf(4 / 16))).toBeLessThan(0.015);
  });
  it("produces a full, tie-free distribution with team means consistent with the inputs", () => {
    const s = simulateGame(-7, 48, 16, 16, 0, 20000, 1);
    const total = s.marginHist.reduce((t, h) => t + h.share, 0);
    expect(total).toBeCloseTo(1, 6);
    expect(s.marginHist.find((h) => h.value === 0)).toBeUndefined();
    expect(s.teamMean - s.oppMean).toBeGreaterThan(-9);
    expect(s.teamMean - s.oppMean).toBeLessThan(-5);
    expect(s.p10).toBeLessThan(s.p50);
    expect(s.p50).toBeLessThan(s.p90);
  });
});

describe("format helpers", () => {
  it("formats values and missing data", () => {
    expect(fmt(0.4512, "%")).toBe("45.1%");
    expect(fmt(null, "%")).toBe("—");
    expect(fmt(0.1589, "pts/play")).toBe("0.159");
    expect(signed(2.04)).toBe("+2.0");
    expect(ordinal(1)).toBe("1st");
    expect(ordinal(22)).toBe("22nd");
    expect(ordinal(113)).toBe("113th");
    expect(spreadLabel(-6.5)).toBe("TEN -6.5");
    expect(spreadLabel(3)).toBe("TEN +3");
    expect(spreadLabel(0)).toBe("PK");
  });
});
