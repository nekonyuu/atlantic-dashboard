import { useMemo, useState } from "react";

import { useEnergy } from "../api/hooks";
import type { EnergyDay } from "../api/types";
import { type Column, ColumnChart } from "../components/ColumnChart";
import { IconChart, IconTable } from "../components/icons";
import { Card, ErrorState, PageHeader, Segmented } from "../components/ui";
import { formatDay, formatNumber } from "../lib/format";
import { ENERGY_CATEGORY } from "../lib/palette";
import { isoDay } from "../lib/range";

const PERIODS = [
  { id: "7", label: "7 jours" },
  { id: "31", label: "31 jours" },
  { id: "365", label: "1 an" },
];
const TARIFF = { peak: "heures pleines", off_peak: "heures creuses", unknown: "tarif inconnu" };

function sum(days: EnergyDay[], pick: (d: EnergyDay) => number | null): number {
  return days.reduce((a, d) => a + (pick(d) ?? 0), 0);
}

export function Energy() {
  const [period, setPeriod] = useState("31");
  const [asTable, setAsTable] = useState(false);
  const now = Date.now();
  const from = isoDay(now - (Number(period) - 1) * 86_400_000);
  const to = isoDay(now);
  const { data, isPending, error } = useEnergy(from, to);
  const days = useMemo(() => data ?? [], [data]);
  const categories = [...new Set(days.map((d) => d.category))].sort();

  const columns: Column[] = useMemo(() => {
    const byDay = new Map<string, EnergyDay[]>();
    for (const d of days) byDay.set(d.day, [...(byDay.get(d.day) ?? []), d]);
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, rows]) => ({
        key: day,
        label: day.slice(8, 10) + "/" + day.slice(5, 7),
        title: formatDay(day),
        segments: categories.map((c) => ({
          key: String(c),
          label: ENERGY_CATEGORY[c]?.label ?? `Catégorie ${c}`,
          color: ENERGY_CATEGORY[c]?.color ?? "--series-3",
          value: sum(rows.filter((r) => r.category === c), (r) => r.kwh),
        })),
        detail: (["peak", "off_peak"] as const)
          .map((t) => [t, sum(rows.filter((r) => r.tariff === t), (r) => r.kwh)] as const)
          .filter(([, v]) => v > 0)
          .map(([t, v]) => `${formatNumber(v, "kWh")} en ${TARIFF[t]}`),
      }));
  }, [days, categories]);

  const total = sum(days, (d) => d.kwh);
  const cost = days.some((d) => d.cost !== null) ? sum(days, (d) => d.cost) : null;
  const offPeak = sum(days.filter((d) => d.tariff === "off_peak"), (d) => d.kwh);
  const nDays = columns.length || 1;

  return (
    <>
      <PageHeader
        title="Énergie"
        subtitle="Consommation électrique déclarée par Atlantic, jour par jour"
        actions={<Segmented label="Période" options={PERIODS} value={period} onChange={setPeriod} />}
      />
      {error && <ErrorState error={error} />}
      <div className="stack">
        <div className="grid-tiles">
          <div className="card tile">
            <div className="tile-label">Consommation</div>
            <div className="tile-value">
              {formatNumber(total, null)}
              <span className="unit">kWh</span>
            </div>
            <div className="meta">{columns.length} jours</div>
          </div>
          <div className="card tile">
            <div className="tile-label">Moyenne quotidienne</div>
            <div className="tile-value">
              {formatNumber(total / nDays, null)}
              <span className="unit">kWh</span>
            </div>
          </div>
          <div className="card tile">
            <div className="tile-label">Coût estimé</div>
            <div className="tile-value">
              {cost === null ? "—" : formatNumber(cost, null)}
              <span className="unit">€</span>
            </div>
            <div className="meta">selon les tarifs saisis dans Cozytouch</div>
          </div>
          <div className="card tile">
            <div className="tile-label">Part en heures creuses</div>
            <div className="tile-value">
              {total > 0 ? formatNumber((offPeak / total) * 100, null) : "—"}
              <span className="unit">%</span>
            </div>
          </div>
        </div>

        <Card
          title="Consommation journalière"
          subtitle="Chauffage et eau chaude, empilés"
          aside={
            <button
              type="button"
              className="btn icon"
              onClick={() => setAsTable((v) => !v)}
              aria-label={asTable ? "Afficher le graphique" : "Afficher le tableau"}
            >
              {asTable ? <IconChart /> : <IconTable />}
            </button>
          }
        >
          {isPending ? (
            <div className="skeleton" style={{ height: 240 }} />
          ) : columns.length === 0 ? (
            <div className="chart-empty">Aucune consommation sur la période</div>
          ) : asTable ? (
            <div className="table-wrap" style={{ maxHeight: 340, overflowY: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Jour</th>
                    {categories.map((c) => (
                      <th key={c} className="num">
                        {ENERGY_CATEGORY[c]?.label ?? c} (kWh)
                      </th>
                    ))}
                    <th className="num">Total (kWh)</th>
                  </tr>
                </thead>
                <tbody>
                  {[...columns].reverse().map((col) => (
                    <tr key={col.key}>
                      <td>{col.title}</td>
                      {col.segments.map((s) => (
                        <td key={s.key} className="num">
                          {formatNumber(s.value, null)}
                        </td>
                      ))}
                      <td className="num">{formatNumber(col.segments.reduce((a, s) => a + s.value, 0), null)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ColumnChart columns={columns} unit="kWh" />
          )}
          <div className="legend" style={{ marginTop: 12 }}>
            {categories.map((c) => (
              <span className="legend-key" key={c}>
                <i className="swatch-sq" style={{ background: `var(${ENERGY_CATEGORY[c]?.color ?? "--series-3"})` }} />
                {ENERGY_CATEGORY[c]?.label ?? `Catégorie ${c}`}
              </span>
            ))}
          </div>
          <p className="note">
            Atlantic fournit environ 32 jours glissants ; le dashboard les conserve au-delà.
          </p>
        </Card>
      </div>
    </>
  );
}
