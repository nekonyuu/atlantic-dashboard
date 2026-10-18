import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import type { Gap, Series } from "../api/types";
import { formatAxisTime, formatDateTime, formatNumber, formatTick } from "../lib/format";
import { cssVar, styleFor } from "../lib/palette";

/** Un graphique = une unité = un axe Y (jamais de double axe). */
export interface LineChartProps {
  series: Series[];
  height?: number;
}

/** Aligne les séries sur un axe X commun (débuts de bucket) ; ``null`` = pas de valeur. */
export function alignSeries(series: Series[]): uPlot.AlignedData {
  const xs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.start)))).sort((a, b) => a - b);
  const columns = series.map((s) => {
    const byStart = new Map(s.points.map((p) => [p.start, p.avg]));
    return xs.map((x) => byStart.get(x) ?? null);
  });
  return [xs, ...columns];
}

export function mergeGaps(series: Series[]): Gap[] {
  const seen = new Map<string, Gap>();
  for (const s of series) for (const g of s.gaps) seen.set(`${g.start}-${g.end}`, g);
  return [...seen.values()].sort((a, b) => a.start - b.start);
}

export function isEmpty(series: Series[]): boolean {
  return series.every((s) => s.points.every((p) => p.avg === null));
}

/** Zones de trou : aplat + hachures à 45°, dessinés sous les courbes. */
function gapsPlugin(gaps: Gap[]): uPlot.Plugin {
  return {
    hooks: {
      drawClear: (u) => {
        const { ctx, bbox } = u;
        ctx.save();
        ctx.beginPath();
        ctx.rect(bbox.left, bbox.top, bbox.width, bbox.height);
        ctx.clip();
        for (const g of gaps) {
          const left = Math.max(u.valToPos(g.start, "x", true), bbox.left);
          const right = Math.min(u.valToPos(g.end, "x", true), bbox.left + bbox.width);
          if (right - left < 1) continue;
          ctx.fillStyle = cssVar("--gap-fill");
          ctx.fillRect(left, bbox.top, right - left, bbox.height);
          ctx.save();
          ctx.beginPath();
          ctx.rect(left, bbox.top, right - left, bbox.height);
          ctx.clip();
          ctx.strokeStyle = cssVar("--gap-ink");
          ctx.lineWidth = devicePixelRatio;
          ctx.beginPath();
          const step = 7 * devicePixelRatio;
          for (let x = left - bbox.height; x < right; x += step) {
            ctx.moveTo(x, bbox.top + bbox.height);
            ctx.lineTo(x + bbox.height, bbox.top);
          }
          ctx.stroke();
          ctx.restore();
        }
        ctx.restore();
      },
    },
  };
}

/** Infobulle HTML : heure + valeur de chaque série au point survolé. */
function tooltipPlugin(series: Series[], gaps: Gap[]): uPlot.Plugin {
  let tip: HTMLDivElement;
  return {
    hooks: {
      init: (u) => {
        tip = document.createElement("div");
        tip.className = "tooltip";
        tip.style.display = "none";
        u.over.appendChild(tip);
        u.over.addEventListener("mouseleave", () => (tip.style.display = "none"));
      },
      setCursor: (u) => {
        const idx = u.cursor.idx;
        if (idx == null || u.cursor.left == null || u.cursor.left < 0) {
          tip.style.display = "none";
          return;
        }
        const x = u.data[0][idx];
        const inGap = gaps.find((g) => x >= g.start && x < g.end);
        const rows = series
          .map((s, i) => {
            const v = u.data[i + 1][idx];
            const st = styleFor(s.metric);
            const value = v == null ? "—" : formatNumber(v, s.unit);
            return `<div class="tooltip-row"><span><i class="key-line${st.dashed ? " dashed" : ""}" style="background:var(${st.color});--key:var(${st.color})"></i>${escapeHtml(s.label)}</span><b>${value}</b></div>`;
          })
          .join("");
        tip.innerHTML =
          `<div class="tooltip-time">${formatDateTime(x)}</div>${rows}` +
          (inGap ? `<div class="tooltip-time" style="margin:6px 0 0">Collecte interrompue</div>` : "");
        tip.style.display = "block";
        const flip = u.cursor.left > u.over.clientWidth * 0.6;
        tip.style.left = `${u.cursor.left}px`;
        tip.style.top = `${Math.max(u.cursor.top ?? 0, 40)}px`;
        tip.style.transform = flip ? "translate(calc(-100% - 12px), -50%)" : "translate(12px, -50%)";
      },
    },
  };
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

export function LineChart({ series, height = 260 }: LineChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const data = useMemo(() => alignSeries(series), [series]);
  const gaps = useMemo(() => mergeGaps(series), [series]);
  const unit = series[0]?.unit ?? null;
  const empty = isEmpty(series);

  useEffect(() => {
    const el = ref.current;
    if (!el || empty) return;
    const build = () => {
      const text3 = cssVar("--text-3");
      const grid = cssVar("--grid");
      const opts: uPlot.Options = {
        width: el.clientWidth,
        height,
        padding: [10, 10, 0, 0],
        legend: { show: false },
        cursor: {
          drag: { x: true, y: false, setScale: true },
          points: { size: 8, width: 2, fill: cssVar("--surface") },
          y: false,
        },
        scales: { x: { time: true } },
        axes: [
          {
            stroke: text3,
            grid: { show: false },
            ticks: { stroke: grid, width: 1, size: 4 },
            space: 80,
            font: "12px " + cssVar("--font"),
            values: (_u, vals, _a, _s, incr) => vals.map((v) => formatAxisTime(v, incr)),
          },
          {
            stroke: text3,
            grid: { stroke: grid, width: 1 },
            ticks: { show: false },
            size: 58,
            space: 36,
            font: "12px " + cssVar("--font"),
            values: (_u, vals, _a, _s, incr) => vals.map((v) => (v == null ? "" : formatTick(v, incr, unit))),
          },
        ],
        series: [
          {},
          ...series.map((s) => {
            const st = styleFor(s.metric);
            const color = cssVar(st.color);
            return {
              label: s.label,
              stroke: color,
              width: 2,
              dash: st.dashed ? [5, 4] : undefined,
              spanGaps: false,
              points: { show: false },
              fill: series.length === 1 && !st.dashed ? `${color}1a` : undefined,
            } satisfies uPlot.Series;
          }),
        ],
        plugins: [gapsPlugin(gaps), tooltipPlugin(series, gaps)],
      };
      return new uPlot(opts, data, el);
    };
    let plot = build();
    const resize = new ResizeObserver(() => plot.setSize({ width: el.clientWidth, height }));
    resize.observe(el);
    // changement de thème : les couleurs viennent des variables CSS, on reconstruit
    const rebuild = () => {
      plot.destroy();
      plot = build();
    };
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", rebuild);
    const observer = new MutationObserver(rebuild);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      resize.disconnect();
      observer.disconnect();
      media.removeEventListener("change", rebuild);
      plot.destroy();
    };
  }, [data, gaps, series, unit, height, empty]);

  if (empty) {
    return (
      <div className="chart-empty" style={{ minHeight: height }}>
        <span>Pas encore de données sur cette période</span>
        <span style={{ fontSize: 12.5 }}>Les courbes se remplissent au fil de la collecte.</span>
      </div>
    );
  }
  return (
    <div className="chart-box">
      <div ref={ref} role="img" aria-label={`Courbe : ${series.map((s) => s.label).join(", ")}`} />
    </div>
  );
}

export function Legend({ series, showGaps }: { series: { metric: string; label: string }[]; showGaps: boolean }) {
  return (
    <div className="legend">
      {series.map((s) => {
        const st = styleFor(s.metric);
        return (
          <span className="legend-key" key={s.metric + s.label}>
            <i
              className={`key-line${st.dashed ? " dashed" : ""}`}
              style={{ background: `var(${st.color})`, ["--key" as string]: `var(${st.color})` }}
            />
            {s.label}
          </span>
        );
      })}
      {showGaps && (
        <span className="legend-key">
          <i className="key-hatch" />
          Collecte interrompue
        </span>
      )}
    </div>
  );
}
