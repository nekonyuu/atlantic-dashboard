import { useMemo, useState } from "react";

import type { Series } from "../api/types";
import { formatDateTime, formatNumber } from "../lib/format";
import { styleFor } from "../lib/palette";
import { IconChart, IconTable } from "./icons";
import { Legend, LineChart, mergeGaps } from "./Chart";

export { mergeGaps as mergeGapsOf };

/** Courbe ~24 h en tête de tuile : forme seule, sans axe (le chiffre est la tuile). */
export function Sparkline({ series, width = 240, height = 34 }: { series?: Series; width?: number; height?: number }) {
  const path = useMemo(() => {
    const pts = (series?.points ?? []).filter((p) => p.avg !== null);
    if (pts.length < 2) return null;
    const xs = pts.map((p) => p.start);
    const ys = pts.map((p) => p.avg as number);
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    const sx = (x: number) => ((x - x0) / Math.max(x1 - x0, 1)) * (width - 4) + 2;
    const sy = (y: number) => height - 3 - ((y - y0) / Math.max(y1 - y0, 1e-9)) * (height - 6);
    // coupure de la ligne sur les buckets vides (un trou n'est pas relié)
    let d = "";
    let pen = false;
    for (const p of series!.points) {
      if (p.avg === null) {
        pen = false;
        continue;
      }
      d += `${pen ? "L" : "M"}${sx(p.start).toFixed(1)},${sy(p.avg).toFixed(1)}`;
      pen = true;
    }
    const last = pts[pts.length - 1];
    return { d, cx: sx(last.start), cy: sy(last.avg as number) };
  }, [series, width, height]);

  const box = { className: "sparkline", viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none" } as const;
  if (!series || !path) return <svg {...box} aria-hidden />;
  const color = `var(${styleFor(series.metric).color})`;
  return (
    <svg {...box} aria-hidden>
      <path
        d={path.d}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Carte de graphique : titre, légende, bascule courbe/tableau (accessibilité, lecture exacte). */
export function ChartCard({
  title,
  subtitle,
  series,
  loading,
  height = 260,
  actions,
}: {
  title: string;
  subtitle?: string;
  series: Series[];
  loading?: boolean;
  height?: number;
  actions?: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const gaps = useMemo(() => mergeGaps(series), [series]);
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">{title}</h2>
          {subtitle && <p className="card-sub">{subtitle}</p>}
        </div>
        <div className="topbar-actions">
          {actions}
          <button
            type="button"
            className="btn icon"
            onClick={() => setAsTable((v) => !v)}
            aria-label={asTable ? "Afficher la courbe" : "Afficher le tableau"}
            title={asTable ? "Afficher la courbe" : "Afficher le tableau"}
          >
            {asTable ? <IconChart /> : <IconTable />}
          </button>
        </div>
      </div>
      {loading && !series.length ? (
        <div className="skeleton" style={{ height }} />
      ) : asTable ? (
        <SeriesTable series={series} height={height} />
      ) : (
        <LineChart series={series} height={height} />
      )}
      {series.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Legend series={series} showGaps={gaps.length > 0} />
        </div>
      )}
    </section>
  );
}

function SeriesTable({ series, height }: { series: Series[]; height: number }) {
  const rows = useMemo(() => {
    const starts = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.start)))).sort((a, b) => b - a);
    const maps = series.map((s) => new Map(s.points.map((p) => [p.start, p])));
    return starts
      .map((t) => ({ t, cells: maps.map((m) => m.get(t)) }))
      .filter((r) => r.cells.some((c) => c && c.avg !== null));
  }, [series]);
  return (
    <div className="table-wrap" style={{ maxHeight: height + 40, overflowY: "auto" }}>
      <table className="table">
        <thead>
          <tr>
            <th>Période</th>
            {series.map((s) => (
              <th key={s.metric + s.equipment} className="num">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.t}>
              <td>{formatDateTime(r.t)}</td>
              {r.cells.map((c, i) => (
                <td key={i} className="num">
                  {c?.avg == null ? "—" : formatNumber(c.avg, series[i].unit)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
