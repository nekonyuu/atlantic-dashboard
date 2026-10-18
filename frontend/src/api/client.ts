import type { BucketSize, EnergyDay, Equipment, Gap, Health, Latest, Series } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) qs.set(k, String(v));
  const url = qs.size ? `${path}?${qs}` : path;
  let res: Response;
  try {
    res = await fetch(url, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, "Serveur injoignable");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Erreur HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/api/health"),
  equipment: () => get<Equipment[]>("/api/equipment"),
  latest: (equipment?: string) => get<Latest[]>("/api/latest", { equipment }),
  series: (equipment: string, metric: string, from: number, to: number, bucket?: BucketSize) =>
    get<Series>("/api/series", { equipment, metric, from, to, bucket }),
  gaps: (from: number, to: number) => get<Gap[]>("/api/gaps", { from, to }),
  energy: (from: string, to: string) => get<EnergyDay[]>("/api/energy", { from, to }),
};
