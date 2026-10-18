import { useLayoutEffect, useRef, useState } from "react";

import { formatNumber } from "../lib/format";

export interface ColumnSegment {
  key: string;
  label: string;
  color: string; // variable CSS
  value: number;
}

export interface Column {
  key: string;
  label: string; // libellé court sous l'axe
  title: string; // libellé complet de l'infobulle
  segments: ColumnSegment[];
  detail?: string[];
}

const PAD = { top: 24, right: 8, bottom: 26, left: 48 };
const GAP = 2; // espace de surface entre segments empilés

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v)!;
}

/** Colonnes empilées : <= 24 px, sommet arrondi 4 px, base carrée, axe Y unique. */
export function ColumnChart({ columns, unit, height = 240 }: { columns: Column[]; unit: string; height?: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const totals = columns.map((c) => c.segments.reduce((a, s) => a + s.value, 0));
  const max = niceMax(Math.max(0, ...totals));
  const plotW = Math.max(width - PAD.left - PAD.right, 10);
  const plotH = height - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(columns.length, 1);
  const barW = Math.min(24, Math.max(slot * 0.62, 3));
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const labelEvery = Math.ceil(columns.length / Math.max(Math.floor(plotW / 46), 1));

  const tipCol = hover !== null ? columns[hover] : null;
  const tipX = hover !== null ? PAD.left + slot * hover + slot / 2 : 0;

  return (
    <div ref={wrap} className="chart-box">
      <svg className="columns" width={width} height={height} role="img" aria-label="Consommation journalière">
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end">
              {formatNumber(t, null)}
            </text>
          </g>
        ))}
        <text x={PAD.left - 8} y={10} textAnchor="end" style={{ fontSize: 11 }}>
          {unit}
        </text>
        {columns.map((c, i) => {
          const x = PAD.left + slot * i + (slot - barW) / 2;
          let acc = 0;
          const segs = c.segments.filter((s) => s.value > 0);
          return (
            <g key={c.key}>
              <rect
                className="hit"
                x={PAD.left + slot * i}
                y={PAD.top}
                width={slot}
                height={plotH}
                rx={4}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={`${c.title} : ${formatNumber(totals[i], unit)}`}
              />
              {segs.map((s, j) => {
                const top = y(acc + s.value);
                const bottom = y(acc);
                acc += s.value;
                const isTop = j === segs.length - 1;
                const h = Math.max(bottom - top - (j > 0 ? GAP : 0), 1);
                return (
                  <path
                    key={s.key}
                    d={roundedTop(x, top, barW, h, isTop ? Math.min(4, barW / 2, h) : 0)}
                    fill={`var(${s.color})`}
                    pointerEvents="none"
                  />
                );
              })}
              {i % labelEvery === 0 && (
                <text x={x + barW / 2} y={height - 8} textAnchor="middle">
                  {c.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {tipCol && (
        <div
          className="tooltip"
          style={{
            left: tipX,
            top: PAD.top + plotH / 3,
            transform: tipX > width * 0.6 ? "translate(calc(-100% - 12px), -50%)" : "translate(12px, -50%)",
          }}
        >
          <div className="tooltip-time">{tipCol.title}</div>
          {tipCol.segments.map((s) => (
            <div className="tooltip-row" key={s.key}>
              <span>
                <i className="swatch-sq" style={{ background: `var(${s.color})` }} />
                {s.label}
              </span>
              <b>{formatNumber(s.value, unit)}</b>
            </div>
          ))}
          {tipCol.detail?.map((d) => (
            <div className="tooltip-time" key={d} style={{ margin: "4px 0 0" }}>
              {d}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function roundedTop(x: number, y: number, w: number, h: number, r: number): string {
  if (r <= 0) return `M${x},${y}h${w}v${h}h${-w}Z`;
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
