import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import type { Latest, Series } from "../api/types";
import { formatAge, formatValue } from "../lib/format";
import { Sparkline } from "./charts";
import { IconAlert, IconCheck, IconClock, IconOff } from "./icons";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="topbar-actions">{actions}</div>}
    </div>
  );
}

/** Valeur + unité séparées typographiquement. */
export function ValueText({ value }: { value: Latest | undefined }) {
  if (!value) return <>—</>;
  if (typeof value.value === "number" && !value.display && value.unit) {
    const text = formatValue(value.value, null, null);
    return (
      <>
        {text}
        <span className="unit">{value.unit}</span>
      </>
    );
  }
  return <>{formatValue(value.value, value.unit, value.display)}</>;
}

/** Date du dernier changement de la valeur. Une valeur stable reste valide tant que la collecte
 * fonctionne : son ancienneté n'est pas une alerte (le bandeau d'état signale une collecte en panne). */
export function Freshness({ value }: { value: Latest | undefined }) {
  if (!value) return <span className="meta">Aucune donnée</span>;
  return <span className="meta">Modifiée {formatAge(value.age_seconds)}</span>;
}

export function Tile({
  label,
  icon,
  value,
  trend,
  extra,
  loading,
}: {
  label: string;
  icon?: ReactNode;
  value: Latest | undefined;
  trend?: Series;
  extra?: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="card tile">
      <div className="tile-label">
        {icon}
        {label}
      </div>
      {loading ? (
        <div className="skeleton" style={{ height: 32, width: "60%", marginTop: 6 }} />
      ) : (
        <div className="tile-value">
          <ValueText value={value} />
        </div>
      )}
      {extra && <div className="meta">{extra}</div>}
      {trend && <Sparkline series={trend} />}
      <div className="tile-foot">
        <Freshness value={value} />
        {trend && <span className="meta">24 h</span>}
      </div>
    </div>
  );
}

export type Tone = "good" | "warning" | "critical" | "info" | "neutral";

const TONE_ICON: Record<Tone, ReactNode> = {
  good: <IconCheck size={14} />,
  warning: <IconAlert size={14} />,
  critical: <IconOff size={14} />,
  info: <IconClock size={14} />,
  neutral: null,
};

/** Statut : toujours icône + libellé, jamais la couleur seule. */
export function Status({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`status ${tone === "neutral" ? "" : tone}`}>
      {TONE_ICON[tone]}
      {children}
    </span>
  );
}

export function Alert({ tone, title, children }: { tone: "warning" | "critical"; title: string; children?: ReactNode }) {
  return (
    <div className={`alert ${tone}`} role={tone === "critical" ? "alert" : "status"}>
      <IconAlert />
      <div>
        <strong>{title}</strong> {children}
      </div>
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.status === 0
        ? "Le serveur du dashboard est injoignable."
        : error.message
      : "Erreur inattendue.";
  return <Alert tone="critical" title="Impossible de charger les données.">{message}</Alert>;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" aria-pressed={o.id === value} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Card({
  title,
  subtitle,
  aside,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">{title}</h2>
          {subtitle && <p className="card-sub">{subtitle}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}
