// Smoke test: every page renders against the real generated data in public/data (run `make data` first).
import { cleanup, render, screen } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ComponentType } from "react";

const DATA = resolve(__dirname, "../../public/data");
const hasData = existsSync(resolve(DATA, "meta.json"));

beforeAll(() => {
  vi.stubGlobal("fetch", async (url: string) => {
    const name = String(url).split("/data/").pop()!;
    const path = resolve(DATA, name);
    if (!existsSync(path)) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => JSON.parse(readFileSync(path, "utf8")) };
  });
  // jsdom lacks these browser APIs used by charts/theme code
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never;
  window.scrollTo = () => {};
});
afterEach(cleanup);

const PAGES: [string, string, () => Promise<{ default: ComponentType }>, RegExp][] = [
  ["/", "/", () => import("./Dashboard"), /Next game|No upcoming games/],
  ["/matchup", "/matchup", () => import("./Matchup"), /Why the model says this/],
  ["/schedule", "/schedule", () => import("./Schedule"), /Regular-season win total/],
  ["/team", "/team", () => import("./TeamStats"), /All FBS teams/],
  ["/players", "/players", () => import("./Players"), /Season stats for Tennessee/],
  ["/depth", "/depth", () => import("./DepthChart"), /Estimated from game stats, not an official depth chart/],
  ["/injuries", "/injuries", () => import("./Injuries"), /Missing from the latest box score/],
  ["/tendencies", "/tendencies", () => import("./Tendencies"), /Pass rate by down & distance/],
  ["/model", "/model", () => import("./ModelPage"), /had a smaller average miss than this model in \d+ of \d+ seasons/],
  ["/data", "/data", () => import("./DataPage"), /Mirror in Google Sheets/],
];

describe.skipIf(!hasData)("pages render with real data", () => {
  for (const [route, path, load, expected] of PAGES) {
    it(route, async () => {
      const { default: Page } = await load();
      const errors = vi.spyOn(console, "error").mockImplementation(() => {});
      render(<MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={<Page />} /></Routes></MemoryRouter>);
      expect(await screen.findByText(expected, {}, { timeout: 4000 })).toBeTruthy();
      expect(screen.queryByText(/Couldn't load data/)).toBeNull();
      const real = errors.mock.calls.filter((c) => !String(c[0]).includes("width(") && !String(c[0]).includes("height("));
      errors.mockRestore();
      expect(real).toEqual([]);
    });
  }
});
