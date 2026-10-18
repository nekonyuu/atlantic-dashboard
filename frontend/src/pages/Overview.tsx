import { useEquipment, useHealth, useLatest } from "../api/hooks";
import type { Latest } from "../api/types";
import { IconGauge, IconOutdoor, IconPump, IconThermo, IconWave } from "../components/icons";
import { Card, ErrorState, Freshness, PageHeader, Status, type Tone, Tile, ValueText } from "../components/ui";
import { formatAge, formatBytes, formatDuration, formatLatest, formatNumber, GAP_CAUSES } from "../lib/format";
import { findMetric, indexLatest } from "../lib/latest";
import { useTrends } from "../lib/useTrends";

const TREND_REQUESTS = [
  { equipment: "heat_pump", metric: "outdoor_temperature" },
  { equipment: "room_1", metric: "room_temperature" },
  { equipment: "generator", metric: "flow_temperature" },
  { equipment: "generator", metric: "return_temperature" },
];

const KIND_ORDER = ["heat_pump", "generator", "dhw", "circuit", "room"];

// Échelle de la jauge du ballon (°C)
const TANK_MIN = 10;
const TANK_MAX = 65;

function tankLevel(t: number | null): number {
  if (t === null) return 0;
  return Math.min(Math.max((t - TANK_MIN) / (TANK_MAX - TANK_MIN), 0), 1);
}

function num(l: Latest | undefined): number | null {
  return l && typeof l.value === "number" ? l.value : null;
}

function DhwHero({ index }: { index: Map<string, Latest> }) {
  const temp = findMetric(index, "dhw_temperature");
  const setpoint = findMetric(index, "dhw_setpoint");
  const status = findMetric(index, "dhw_status");
  const boost = findMetric(index, "dhw_boost");
  const charge = findMetric(index, "dhw_charge_setpoint");
  const on = findMetric(index, "dhw_on");
  const t = num(temp);
  const sp = num(setpoint);
  const reached = t !== null && sp !== null && t >= sp - 2;

  return (
    <section className="card">
      <div className="hero">
        <div className="tank" role="img" aria-label={`Ballon : ${formatLatest(temp)} pour une consigne de ${formatLatest(setpoint)}`}>
          <div className="tank-fill" style={{ height: `${tankLevel(t) * 100}%` }} />
          {sp !== null && <div className="tank-mark" style={{ bottom: `${tankLevel(sp) * 100}%` }} title="Consigne" />}
        </div>
        <div>
          <div className="hero-label">
            Eau chaude sanitaire
            {on && on.value === false ? (
              <Status tone="critical">Désactivée</Status>
            ) : reached ? (
              <Status tone="good">Consigne atteinte</Status>
            ) : (
              <Status tone="info">En dessous de la consigne</Status>
            )}
          </div>
          <div className="hero-value">
            <ValueText value={temp} />
          </div>
          <Freshness value={temp} />
          <div className="hero-meta">
            <span>
              Consigne <b>{formatLatest(setpoint)}</b>
            </span>
            {status && (
              <span>
                Production <b>{formatLatest(status)}</b>
              </span>
            )}
            {charge && (
              <span>
                Charge cible <b>{formatLatest(charge)}</b>
              </span>
            )}
            {boost && boost.value !== null && (
              <span>
                Boost <b>{boost.value ? "actif" : "inactif"}</b>
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function HeatPumpCard({ index }: { index: Map<string, Latest> }) {
  const service = findMetric(index, "generator_status");
  const errors = findMetric(index, "active_errors");
  const errorCount = num(errors) ?? 0;
  const rows: [string, Latest | undefined][] = [
    ["Mode thermostat", findMetric(index, "thermostat_mode")],
    ["Programmation", findMetric(index, "setpoint_mode")],
    ["Chauffe en cours", findMetric(index, "heating_ongoing")],
    ["Pression du circuit", findMetric(index, "water_pressure")],
    ["Code unité extérieure", findMetric(index, "error_code")],
  ];
  const tone: Tone = errorCount > 0 ? "critical" : "good";
  return (
    <Card
      title="Pompe à chaleur"
      subtitle={service ? `Service en cours : ${formatLatest(service)}` : undefined}
      aside={<Status tone={tone}>{errorCount > 0 ? `${errorCount} erreur(s)` : "Aucune erreur"}</Status>}
    >
      <ul className="list">
        {rows
          .filter(([, v]) => v !== undefined)
          .map(([label, v]) => (
            <li key={label}>
              <span className="secondary">{label}</span>
              <span className="kv">{formatLatest(v)}</span>
            </li>
          ))}
      </ul>
    </Card>
  );
}

function EquipmentCard() {
  const { data } = useEquipment();
  return (
    <Card title="Équipements" subtitle="Disponibilité vue par le cloud Atlantic">
      <ul className="list">
        {[...(data ?? [])].sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)).map((e) => (
          <li key={e.id}>
            <span>
              <span className="primary">{e.label}</span>
              <br />
              <span className="secondary">{e.last_seen ? `vu ${formatAge(Date.now() / 1000 - e.last_seen)}` : "jamais vu"}</span>
            </span>
            {e.available === false ? (
              <Status tone="critical">Injoignable</Status>
            ) : e.available ? (
              <Status tone="good">En ligne</Status>
            ) : (
              <Status tone="neutral">Inconnu</Status>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CollectCard() {
  const { data } = useHealth();
  if (!data) return <div className="card skeleton" style={{ minHeight: 180 }} />;
  const gaps = data.recent_gaps;
  const errors = Object.values(data.errors.counts).reduce((a, b) => a + b, 0);
  return (
    <Card title="Collecte" subtitle="7 derniers jours">
      <ul className="list">
        <li>
          <span className="secondary">Dernière collecte réussie</span>
          <span className="kv">
            {data.poller.last_success ? formatAge(Date.now() / 1000 - data.poller.last_success) : "—"}
          </span>
        </li>
        <li>
          <span className="secondary">Interruptions</span>
          <span className="kv">
            {gaps.length === 0
              ? "Aucune"
              : `${gaps.length} · ${formatDuration(gaps.reduce((a, g) => a + g.duration_seconds, 0))}`}
          </span>
        </li>
        {gaps.slice(-2).map((g) => (
          <li key={g.start}>
            <span className="secondary">
              {GAP_CAUSES[g.cause] ?? g.cause}
              {g.ongoing ? " (en cours)" : ""}
            </span>
            <span className="kv">{formatDuration(g.duration_seconds)}</span>
          </li>
        ))}
        <li>
          <span className="secondary">Erreurs récentes</span>
          <span className="kv">{errors}</span>
        </li>
        <li>
          <span className="secondary">Base de données</span>
          <span className="kv">{formatBytes(data.db_size_bytes)}</span>
        </li>
      </ul>
    </Card>
  );
}

export function Overview() {
  const latest = useLatest();
  const index = indexLatest(latest.data);
  const trends = useTrends(TREND_REQUESTS);
  const loading = latest.isPending;
  const roomSetpoint = findMetric(index, "room_setpoint");
  const updated = latest.data?.length ? Math.min(...latest.data.map((l) => l.age_seconds)) : null;

  return (
    <>
      <PageHeader
        title="Vue d'ensemble"
        subtitle={updated !== null ? `Dernière mesure reçue ${formatAge(updated)}` : "En attente des premières mesures"}
      />
      {latest.isError && <ErrorState error={latest.error} />}
      <div className="stack">
        <div className="grid-hero">
          {loading ? <div className="card skeleton" style={{ minHeight: 200 }} /> : <DhwHero index={index} />}
          {loading ? <div className="card skeleton" style={{ minHeight: 200 }} /> : <HeatPumpCard index={index} />}
        </div>
        <div className="grid-tiles">
          <Tile
            label="Extérieur"
            icon={<IconOutdoor size={16} />}
            value={findMetric(index, "outdoor_temperature")}
            trend={trends.get("heat_pump/outdoor_temperature")}
            loading={loading}
          />
          <Tile
            label="Ambiance"
            icon={<IconThermo size={16} />}
            value={findMetric(index, "room_temperature")}
            trend={trends.get("room_1/room_temperature")}
            extra={roomSetpoint ? `Consigne ${formatLatest(roomSetpoint)}` : undefined}
            loading={loading}
          />
          <Tile
            label="Départ d'eau"
            icon={<IconWave size={16} />}
            value={findMetric(index, "flow_temperature")}
            trend={trends.get("generator/flow_temperature")}
            loading={loading}
          />
          <Tile
            label="Retour d'eau"
            icon={<IconPump size={16} />}
            value={findMetric(index, "return_temperature")}
            trend={trends.get("generator/return_temperature")}
            extra={(() => {
              const f = num(findMetric(index, "flow_temperature"));
              const r = num(findMetric(index, "return_temperature"));
              return f !== null && r !== null ? `Écart départ/retour ${formatNumber(f - r, "°C")}` : undefined;
            })()}
            loading={loading}
          />
        </div>
        <div className="grid-2">
          <EquipmentCard />
          <CollectCard />
        </div>
        <p className="note" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <IconGauge size={14} /> Les valeurs sont celles transmises par le cloud Atlantic ; elles ne changent que
          lorsque l'installation signale une évolution.
        </p>
      </div>
    </>
  );
}
