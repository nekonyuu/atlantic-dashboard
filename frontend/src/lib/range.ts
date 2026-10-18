import type { BucketSize } from "../api/types";

export interface Preset {
  id: string;
  label: string;
  seconds: number;
  bucket: BucketSize;
}

export const PRESETS: Preset[] = [
  { id: "24h", label: "24 h", seconds: 86_400, bucket: "5m" },
  { id: "7j", label: "7 jours", seconds: 7 * 86_400, bucket: "1h" },
  { id: "30j", label: "30 jours", seconds: 30 * 86_400, bucket: "1h" },
  { id: "1an", label: "1 an", seconds: 365 * 86_400, bucket: "1d" },
];

/** Fin de période arrondie à la minute : la clé de cache reste stable entre deux rendus. */
export function rangeFor(preset: Preset, now = Date.now()) {
  const to = Math.floor(now / 60_000) * 60;
  return { from: to - preset.seconds, to, bucket: preset.bucket };
}

export function isoDay(epochMs: number): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Paris" }).format(new Date(epochMs));
}
