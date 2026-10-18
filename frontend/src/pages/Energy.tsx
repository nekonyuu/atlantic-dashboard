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
const SPLITS = [
  { id: "usage", label: "Par usage" },
  { id: "tariff", label: "Par tarif" },
];
type Split = "usage" | "tariff";
const SPLIT_KEY = "pac-energy-split";

interface Group {
  key: string;
  label: string;
  color: string; // variable CSS
  match: (d: EnergyDay) => boolean;
}

// Couleurs distinctes de celles des usages (bleu/orange), paire adjacente validée de la palette.
const TARIFF_GROUPS: Group[] = [
  { key: "off_peak", label: "Heures creuses", color: "--series-3", match: (d) => d.tariff === "off_peak" },
  { key: "peak", label: "Heures pleines", color: "--series-4", match: (d) => d.tariff === "peak" },
  { key: "unknown", label: "Tarif inconnu", color: "--series-7", match: (d) => d.tariff === "unknown" },
];

function usageGroups(days: EnergyDay[]): Group[] {
  return [...new Set(days.map((d) => d.category))].sort().map((c) => ({
    key: `c${c}`,
    label: ENERGY_CATEGORY[c]?.label ?? `Catégorie ${c}`,
    color: ENERGY_CATEGORY[c]?.color ?? "--series-5",
    match: (d: EnergyDay) => d.category === c,
  }));
}

function readSplit(): Split {
  try {
    return localStorage.getItem(SPLIT_KEY) === "tariff" ? "tariff" : "usage";
  } catch {
    return "usage";
  }
}

function sum(days: EnergyDay[], pick: (d: EnergyDay) => number | null): number {
  return days.reduce((a, d) => a + (pick(d) ?? 0), 0);
}

export function Energy() {
  const [period, setPeriod] = useState("31");
  const [asTable, setAsTable] = useState(false);
  const [split, setSplitState] = useState<Split>(readSplit);
  const setSplit = (v: Split) => {
    setSplitState(v);
    try {
      localStorage.setItem(SPLIT_KEY, v);
    } catch {
      /* préférence non mémorisée : sans conséquence */
    }
  };
  const now = Date.now();
  const from = isoDay(now - (Number(period) - 1) * 86_400_000);
  const to = isoDay(now);
  const { data, isPending, error } = useEnergy(from, to);
  const days = useMemo(() => data ?? [], [data]);
  const { groups, others } = useMemo(() => {
    const usage = usageGroups(days);
    const tariff = TARIFF_GROUPS.filter((g) => days.some(g.match));
    return split === "usage" ? { groups: usage, others: tariff } : { groups: tariff, others: usage };
  }, [days, split]);

  const columns: Column[] = useMemo(() => {
    const byDay = new Map<string, EnergyDay[]>();
    for (const d of days) byDay.set(d.day, [...(byDay.get(d.day) ?? []), d]);
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, rows]) => ({
        key: day,
        label: day.slice(8, 10) + "/" + day.slice(5, 7),
        title: formatDay(day),
        segments: groups.map((g) => ({
          key: g.key,
          label: g.label,
          color: g.color,
          value: sum(rows.filter(g.match), (r) => r.kwh),
        })),
        // l'autre ventilation, en complément dans l'infobulle
        detail: others
          .map((g) => [g.label, sum(rows.filter(g.match), (r) => r.kwh)] as const)
          .filter(([, v]) => v > 0)
          .map(([label, v]) => `${label} : ${formatNumber(v, "kWh")}`),
      }));
  }, [days, groups, others]);

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
          subtitle={split === "usage" ? "Chauffage et eau chaude, empilés" : "Heures creuses et heures pleines, empilées"}
          aside={
            <div className="topbar-actions">
              <Segmented label="Ventilation" options={SPLITS} value={split} onChange={(v) => setSplit(v as Split)} />
              <button
              type="button"
              className="btn icon"
              onClick={() => setAsTable((v) => !v)}
              aria-label={asTable ? "Afficher le graphique" : "Afficher le tableau"}
            >
                {asTable ? <IconChart /> : <IconTable />}
              </button>
            </div>
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
                    {groups.map((g) => (
                      <th key={g.key} className="num">
                        {g.label} (kWh)
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
            {groups.map((g) => (
              <span className="legend-key" key={g.key}>
                <i className="swatch-sq" style={{ background: `var(${g.color})` }} />
                {g.label}
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
