import { useLatest, useSeries } from "../api/hooks";
import { ChartCard } from "../components/charts";
import { IconClock, IconDrop, IconThermo } from "../components/icons";
import { Card, ErrorState, PageHeader, Segmented, Tile } from "../components/ui";
import { findMetric, indexLatest } from "../lib/latest";
import { usePreset } from "../lib/usePreset";
import { useTrends } from "../lib/useTrends";

const CURVE = [
  { equipment: "dhw", metric: "dhw_temperature" },
  { equipment: "dhw", metric: "dhw_setpoint" },
];

export function Dhw() {
  const latest = useLatest();
  const index = indexLatest(latest.data);
  const period = usePreset("24h");
  const { series, loading, error } = useSeries(CURVE, period.range);
  const trends = useTrends(CURVE.slice(0, 1));
  const pending = latest.isPending;

  return (
    <>
      <PageHeader
        title="Eau chaude sanitaire"
        subtitle="Ballon de la pompe à chaleur"
        actions={<Segmented label="Période" options={period.options} value={period.id} onChange={period.setId} />}
      />
      {(latest.isError || error) && <ErrorState error={latest.error ?? error} />}
      <div className="stack">
        <div className="grid-tiles">
          <Tile
            label="Température"
            icon={<IconThermo size={16} />}
            value={findMetric(index, "dhw_temperature")}
            trend={trends.get("dhw/dhw_temperature")}
            loading={pending}
          />
          <Tile label="Consigne" icon={<IconDrop size={16} />} value={findMetric(index, "dhw_setpoint")} loading={pending} />
          <Tile label="Production" icon={<IconClock size={16} />} value={findMetric(index, "dhw_status")} loading={pending} />
          <Tile label="Charge cible (V40)" value={findMetric(index, "dhw_charge_setpoint")} loading={pending} />
        </div>
        <ChartCard
          title="Température du ballon"
          subtitle="Moyenne pondérée par la durée, consigne en pointillé"
          series={series}
          loading={loading}
          height={300}
        />
        <Card title="Cycles de chauffe" subtitle="Durée et fréquence des montées en température">
          <div className="empty-state">
            <IconClock size={28} />
            <strong style={{ color: "var(--text-2)" }}>Pas encore disponible</strong>
            <span style={{ maxWidth: 520 }}>
              La détection des cycles s'appuiera sur l'état de production du ballon. Elle sera ajoutée quand
              quelques jours de collecte auront confirmé quelle mesure les signale de façon fiable.
            </span>
          </div>
        </Card>
      </div>
    </>
  );
}
