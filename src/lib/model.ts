/** Client-side recomputation for the Matchup sliders. Mirrors model/simulate.py. */

export function normCdf(x: number): number {
  // Abramowitz-Stegun 7.1.26 erf approximation (|error| < 1.5e-7)
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t
    * Math.exp(-(x * x) / 2);
  return x >= 0 ? (1 + y) / 2 : (1 - y) / 2;
}

/** Small, fast, seeded PRNG so the same inputs always give the same simulation. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(rand: () => number): [number, number] {
  const u = Math.max(rand(), 1e-12), v = rand();
  const r = Math.sqrt(-2 * Math.log(u));
  return [r * Math.cos(2 * Math.PI * v), r * Math.sin(2 * Math.PI * v)];
}

export interface SimResult {
  n: number; winProb: number; teamMean: number; oppMean: number;
  marginHist: { value: number; share: number }[];
  p10: number; p50: number; p90: number; oneScore: number;
}

export function simulateGame(margin: number, total: number, sigmaM: number, sigmaT: number, rho: number,
                             n = 10000, seed = 20261102): SimResult {
  const rand = mulberry32(seed);
  const pWin = normCdf(margin / sigmaM);
  const margins = new Float64Array(n);
  let wins = 0, tSum = 0, oSum = 0, one = 0;
  const counts = new Map<number, number>();
  for (let i = 0; i < n; i++) {
    const [z1, z2] = gauss(rand);
    const m = margin + sigmaM * z1;
    let t = total + sigmaT * (rho * z1 + Math.sqrt(1 - rho * rho) * z2);
    t = Math.max(t, Math.abs(m));
    let a = Math.max(Math.round((t + m) / 2), 0);
    let b = Math.max(Math.round((t - m) / 2), 0);
    if (a === b) { if (rand() < pWin) a += 7; else b += 7; } // simplified overtime
    const d = a - b;
    margins[i] = d;
    if (d > 0) wins++;
    if (Math.abs(d) <= 8) one++;
    tSum += a; oSum += b;
    const key = Math.max(-60, Math.min(60, d));
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const sorted = Array.from(margins).sort((x, y) => x - y);
  const q = (p: number) => sorted[Math.min(n - 1, Math.floor(p * n))];
  return {
    n, winProb: wins / n, teamMean: tSum / n, oppMean: oSum / n, oneScore: one / n,
    marginHist: [...counts.entries()].sort((x, y) => x[0] - y[0]).map(([value, c]) => ({ value, share: c / n })),
    p10: q(0.1), p50: q(0.5), p90: q(0.9),
  };
}
