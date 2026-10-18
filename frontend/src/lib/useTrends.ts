import { useMemo } from "react";

import { type SeriesRequest, useSeries } from "../api/hooks";
import type { Series } from "../api/types";

/** Tendances 24 h (buckets horaires) pour les sparklines, indexées « équipement/métrique ». */
export function useTrends(requests: SeriesRequest[]): Map<string, Series> {
  const to = Math.floor(Date.now() / 600_000) * 600; // stable 10 min : cache partagé entre pages
  const { series } = useSeries(requests, { from: to - 86_400, to, bucket: "1h" });
  return useMemo(() => new Map(series.map((s) => [`${s.equipment}/${s.metric}`, s])), [series]);
}
