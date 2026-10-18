import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { BucketSize, Series } from "./types";

export const REFRESH_MS = 60_000;

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health });
export const useEquipment = () => useQuery({ queryKey: ["equipment"], queryFn: api.equipment });
export const useLatest = () => useQuery({ queryKey: ["latest"], queryFn: () => api.latest() });

export interface SeriesRequest {
  equipment: string;
  metric: string;
}

export interface Range {
  from: number;
  to: number;
  bucket?: BucketSize;
}

/** Plusieurs séries sur la même période ; ne renvoie que celles déjà chargées. */
export function useSeries(requests: SeriesRequest[], range: Range) {
  const results = useQueries({
    queries: requests.map((r) => ({
      queryKey: ["series", r.equipment, r.metric, range.from, range.to, range.bucket],
      queryFn: () => api.series(r.equipment, r.metric, range.from, range.to, range.bucket),
      placeholderData: keepPreviousData,
    })),
  });
  return {
    series: results.map((r) => r.data).filter((s): s is Series => s !== undefined),
    loading: results.some((r) => r.isPending),
    error: results.find((r) => r.error)?.error ?? null,
  };
}

export const useEnergy = (from: string, to: string) =>
  useQuery({ queryKey: ["energy", from, to], queryFn: () => api.energy(from, to) });
