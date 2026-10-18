import { describe, expect, it } from "vitest";

import type { Series } from "../api/types";
import { alignSeries, isEmpty, mergeGaps } from "./Chart";

const point = (start: number, avg: number | null) => ({
  start,
  end: start + 3600,
  avg,
  min: avg,
  max: avg,
  last: avg,
  samples: avg === null ? 0 : 1,
  covered_seconds: avg === null ? 0 : 3600,
  delta: null,
  delta_spans_gap: false,
});

const gap = { start: 3600, end: 7200, duration_seconds: 3600, cause: "downtime" as const, recovered: false, ongoing: false };

const series = (metric: string, points: ReturnType<typeof point>[], gaps = [gap]): Series => ({
  equipment: "dhw",
  metric,
  label: metric,
  unit: "°C",
  cumulative: false,
  bucket: "1h",
  from: 0,
  to: 10800,
  points,
  gaps,
});

describe("alignSeries", () => {
  it("aligne les séries sur un axe commun et garde les trous vides (null), sans interpolation", () => {
    const a = series("a", [point(0, 10), point(3600, null), point(7200, 12)]);
    const b = series("b", [point(7200, 20)]);
    expect(alignSeries([a, b])).toEqual([
      [0, 3600, 7200],
      [10, null, 12],
      [null, null, 20],
    ]);
  });

  it("fusionne les trous communs sans doublon", () => {
    expect(mergeGaps([series("a", []), series("b", [])])).toHaveLength(1);
  });

  it("détecte une période sans aucune valeur", () => {
    expect(isEmpty([series("a", [point(0, null)])])).toBe(true);
    expect(isEmpty([series("a", [point(0, 1)])])).toBe(false);
  });
});
