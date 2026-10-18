import { useMemo, useState } from "react";

import { useEquipment, useSeries } from "../api/hooks";
import type { Gap, MetricMeta, Series } from "../api/types";
import { ChartCard, mergeGapsOf } from "../components/charts";
import { Card, ErrorState, PageHeader, Segmented, Status } from "../components/ui";
import { formatDateTime, formatDuration, GAP_CAUSES } from "../lib/format";
import { styleFor } from "../lib/palette";
import { usePreset } from "../lib/usePreset";

const DEFAULT = ["room_1/room_temperature", "heat_pump/outdoor_temperature", "dhw/dhw_temperature"];
const MAX_PER_CHART = 4;

/** Une métrique est traçable si elle est numérique continue (pas un enum ni un compteur cumulé). */
function plottable(m: MetricMeta): boolean {
  return Object.keys(m.enum).length === 0 && !m.cumulative && m.unit !== null;
}

export function History() {
  const equipment = useEquipment();
  const period = usePreset("7j");
  const [selected, setSelected] = useState<string[]>(DEFAULT);

  const metrics = useMemo(
    () =>
      (equipment.data ?? []).flatMap((e) =>
        e.metrics.filter(plottable).map((m) => ({ id: `${e.id}/${m.key}`, equipment: e, meta: m })),
      ),
    [equipment.data],
  );
  const requests = selected
    .filter((id) => metrics.some((m) => m.id === id))
    .map((id) => {
      const [equipment, metric] = id.split("/");
      return { equipment, metric };
    });
  const { series, loading, error } = useSeries(requests, period.range);

  // petits multiples : un graphique par unité (jamais deux échelles sur un même axe)
  const byUnit = useMemo(() => {
    const groups = new Map<string, Series[]>();
    for (const s of series) groups.set(s.unit ?? "", [...(groups.get(s.unit ?? "") ?? []), s]);
    return [...groups.entries()];
  }, [series]);
  const gaps: Gap[] = useMemo(() => mergeGapsOf(series), [series]);

  const toggle = (id: string) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const unitCount = (unit: string | null) =>
    selected.filter((id) => metrics.find((m) => m.id === id)?.meta.unit === unit).length;

  return (
    <>
      <PageHeader
        title="Historique"
        subtitle="Superposez les mesures sur la période de votre choix"
        actions={<Segmented label="Période" options={period.options} value={period.id} onChange={period.setId} />}
      />
      {(equipment.isError || error) && <ErrorState error={equipment.error ?? error} />}
      <div className="stack">
        <Card title="Mesures" subtitle="Les mesures de même unité partagent un graphique">
          {equipment.isPending ? (
            <div className="skeleton" style={{ height: 80 }} />
          ) : (
            <div className="picker">
              {(equipment.data ?? [])
                .filter((e) => e.metrics.some(plottable))
                .map((e) => (
                  <div className="picker-group" key={e.id}>
                    <h3>{e.label}</h3>
                    <div className="chips">
                      {e.metrics.filter(plottable).map((m) => {
                        const id = `${e.id}/${m.key}`;
                        const on = selected.includes(id);
                        const full = !on && unitCount(m.unit) >= MAX_PER_CHART;
                        return (
                          <button
                            key={id}
                            type="button"
                            className="chip"
                            aria-pressed={on}
                            disabled={full}
                            title={full ? `${MAX_PER_CHART} mesures au plus par graphique` : undefined}
                            onClick={() => toggle(id)}
                          >
                            <span className="dot" style={on ? { background: `var(${styleFor(m.key).color})` } : undefined} />
                            {m.label}
                            {m.unit && <span className="muted">{m.unit}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </Card>

        {requests.length === 0 && !equipment.isPending && (
          <div className="card empty-state">Sélectionnez au moins une mesure.</div>
        )}
        {byUnit.map(([unit, group]) => (
          <ChartCard
            key={unit}
            title={unit ? `Mesures en ${unit}` : "Mesures"}
            subtitle={`${period.preset.label} · pas ${group[0].bucket === "5m" ? "5 min" : group[0].bucket === "1h" ? "1 h" : "1 jour"}`}
            series={group}
            loading={loading}
            height={280}
          />
        ))}

        <Card title="Interruptions de collecte" subtitle="Aucune valeur n'est inventée pendant ces périodes">
          {gaps.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              Aucune interruption sur la période.
            </p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Début</th>
                    <th>Fin</th>
                    <th className="num">Durée</th>
                    <th>Cause</th>
                    <th>Énergie</th>
                  </tr>
                </thead>
                <tbody>
                  {gaps.map((g) => (
                    <tr key={g.start}>
                      <td>{formatDateTime(g.start)}</td>
                      <td>{g.ongoing ? "en cours" : formatDateTime(g.end)}</td>
                      <td className="num">{formatDuration(g.duration_seconds)}</td>
                      <td>{GAP_CAUSES[g.cause] ?? g.cause}</td>
                      <td>{g.recovered ? <Status tone="good">Rattrapée</Status> : <Status tone="neutral">Non</Status>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
