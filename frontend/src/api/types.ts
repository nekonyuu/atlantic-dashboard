// Contrat JSON de l'API (backend/app/adapters/inbound/http). Instants en secondes epoch UTC.

export type BucketSize = "5m" | "1h" | "1d";

export interface Gap {
  start: number;
  end: number;
  duration_seconds: number;
  cause: "downtime" | "provider_error" | "credentials" | "unknown";
  recovered: boolean;
  ongoing: boolean;
}

export interface Health {
  status: "ok";
  poller: {
    running: boolean;
    stale: boolean;
    stopped_reason: string | null;
    last_success: number | null;
    consecutive_failures: number;
    next_poll_in_seconds: number | null;
  };
  errors: {
    counts: Record<string, number>;
    last: Record<string, { at: number; message: string | null }>;
  };
  equipment: { id: string; available: boolean | null }[];
  db_size_bytes: number;
  recent_gaps: Gap[];
}

export interface MetricMeta {
  key: string;
  label: string;
  unit: string | null;
  cumulative: boolean;
  enum: Record<string, string>;
}

export interface Equipment {
  id: string;
  label: string;
  kind: string;
  available: boolean | null;
  last_seen: number | null;
  metrics: MetricMeta[];
}

export type Value = number | string | boolean | null | Record<string, unknown> | unknown[];

export interface Latest {
  equipment: string;
  metric: string;
  label: string;
  unit: string | null;
  value: Value;
  value_type: string;
  display: string | null;
  at: number;
  age_seconds: number;
  polled_at: number;
}

export interface Point {
  start: number;
  end: number;
  avg: number | null;
  min: number | null;
  max: number | null;
  last: number | null;
  samples: number;
  covered_seconds: number;
  delta: number | null;
  delta_spans_gap: boolean;
}

export interface Series {
  equipment: string;
  metric: string;
  label: string;
  unit: string | null;
  cumulative: boolean;
  bucket: BucketSize;
  from: number;
  to: number;
  points: Point[];
  gaps: Gap[];
}

export interface EnergyDay {
  day: string;
  category: number;
  tariff: "peak" | "off_peak" | "unknown";
  kwh: number;
  cost: number | null;
}
