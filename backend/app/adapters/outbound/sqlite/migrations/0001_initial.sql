-- Schéma initial (PLAN.md §7). Les PRAGMA sont posés par connection.py.

CREATE TABLE equipment (
  equipment_id   TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,
  device_id      INTEGER,
  model_id       INTEGER,
  product_id     INTEGER,
  slot           TEXT,
  zone_id        INTEGER,
  label          TEXT,
  first_seen     INTEGER NOT NULL,
  last_seen      INTEGER NOT NULL,
  available      INTEGER
);

CREATE TABLE measurement (
  id            INTEGER PRIMARY KEY,
  ts            INTEGER NOT NULL,
  polled_at     INTEGER NOT NULL,
  equipment_id  TEXT NOT NULL REFERENCES equipment(equipment_id),
  metric_key    TEXT NOT NULL,
  source_state  TEXT NOT NULL,
  value_type    TEXT NOT NULL,
  value_num     REAL,
  value_text    TEXT,
  origin        TEXT NOT NULL DEFAULT 'live',
  UNIQUE (equipment_id, metric_key, ts)
);
CREATE INDEX idx_measurement_lookup ON measurement(equipment_id, metric_key, ts);

CREATE TABLE measurement_hourly (
  equipment_id TEXT NOT NULL, metric_key TEXT NOT NULL,
  hour_ts INTEGER NOT NULL,
  avg_w REAL, min REAL, max REAL, last REAL, delta REAL, samples INTEGER,
  PRIMARY KEY (equipment_id, metric_key, hour_ts)
);

CREATE TABLE energy_daily (
  day      TEXT NOT NULL,
  category INTEGER NOT NULL,
  tariff   TEXT NOT NULL,
  kwh      REAL NOT NULL,
  cost     REAL,
  origin   TEXT NOT NULL DEFAULT 'backfill',
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (day, category, tariff)
);

CREATE TABLE capability_catalogue (
  capability_id INTEGER PRIMARY KEY,
  name TEXT, type INTEGER, unit TEXT, resolution REAL, enum_json TEXT,
  fetched_at INTEGER NOT NULL
);

CREATE TABLE poll_log (
  ts INTEGER NOT NULL, ok INTEGER NOT NULL, duration_ms INTEGER,
  error_kind TEXT, error TEXT
);

CREATE TABLE gap (
  id INTEGER PRIMARY KEY,
  from_ts INTEGER NOT NULL, to_ts INTEGER NOT NULL,
  cause TEXT NOT NULL,
  recovered INTEGER NOT NULL DEFAULT 0
);
