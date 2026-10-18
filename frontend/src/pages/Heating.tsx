import { useLatest, useSeries } from "../api/hooks";
import { ChartCard } from "../components/charts";
import { IconGauge, IconOutdoor, IconThermo, IconWave } from "../components/icons";
import { Card, ErrorState, PageHeader, Segmented, Tile } from "../components/ui";
import { formatLatest } from "../lib/format";
import { findMetric, indexLatest } from "../lib/latest";
import { usePreset } from "../lib/usePreset";
import { useTrends } from "../lib/useTrends";

const HOUSE = [
  { equipment: "room_1", metric: "room_temperature" },
  { equipment: "room_1", metric: "room_setpoint" },
  { equipment: "heat_pump", metric: "outdoor_temperature" },
];
const WATER = [
  { equipment: "generator", metric: "flow_temperature" },
  { equipment: "generator", metric: "return_temperature" },
  { equipment: "circuit_1", metric: "flow_setpoint" },
];
const PRESSURE = [{ equipment: "generator", metric: "water_pressure" }];

export function Heating() {
  const latest = useLatest();
  const index = indexLatest(latest.data);
  const period = usePreset("24h");
  const house = useSeries(HOUSE, period.range);
  const water = useSeries(WATER, period.range);
  const pressure = useSeries(PRESSURE, period.range);
  const trends = useTrends([HOUSE[0], HOUSE[2], WATER[0], PRESSURE[0]]);
  const pending = latest.isPending;
  const error = latest.error ?? house.error ?? water.error;

  return (
    <>
      <PageHeader
        title="Chauffage"
        subtitle="Circuit de chauffage et pièce de référence"
        actions={<Segmented label="Période" options={period.options} value={period.id} onChange={period.setId} />}
      />
      {error && <ErrorState error={error} />}
      <div className="stack">
        <div className="grid-tiles">
          <Tile
            label="Ambiance"
            icon={<IconThermo size={16} />}
            value={findMetric(index, "room_temperature")}
            trend={trends.get("room_1/room_temperature")}
            extra={`Consigne ${formatLatest(findMetric(index, "room_setpoint"))}`}
            loading={pending}
          />
          <Tile
            label="Extérieur"
            icon={<IconOutdoor size={16} />}
            value={findMetric(index, "outdoor_temperature")}
            trend={trends.get("heat_pump/outdoor_temperature")}
            loading={pending}
          />
          <Tile
            label="Départ d'eau"
            icon={<IconWave size={16} />}
            value={findMetric(index, "flow_temperature")}
            trend={trends.get("generator/flow_temperature")}
            extra={`Consigne ${formatLatest(findMetric(index, "flow_setpoint"))}`}
            loading={pending}
          />
          <Tile
            label="Pression"
            icon={<IconGauge size={16} />}
            value={findMetric(index, "water_pressure")}
            trend={trends.get("generator/water_pressure")}
            loading={pending}
          />
        </div>
        <div className="grid-2">
          <ChartCard title="Maison" subtitle="Ambiance, consigne et extérieur" series={house.series} loading={house.loading} />
          <ChartCard
            title="Eau du circuit"
            subtitle="Départ, retour et consigne de départ"
            series={water.series}
            loading={water.loading}
          />
        </div>
        <div className="grid-2">
          <ChartCard title="Pression du circuit" series={pressure.series} loading={pressure.loading} height={200} />
          <Card title="Réglages en cours">
            <ul className="list">
              {(
                [
                  ["Mode du thermostat", "thermostat_mode"],
                  ["Programmation", "setpoint_mode"],
                  ["Chauffe en cours", "heating_ongoing"],
                  ["Service de la PAC", "generator_status"],
                  ["Modulation", "modulation"],
                  ["Mode secours", "emergency_mode"],
                ] as const
              ).map(([label, key]) => (
                <li key={key}>
                  <span className="secondary">{label}</span>
                  <span className="kv">{formatLatest(findMetric(index, key))}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
