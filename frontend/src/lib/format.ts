import type { Latest, Value } from "../api/types";

const TZ = "Europe/Paris";

const dateTime = new Intl.DateTimeFormat("fr-FR", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});
const dayFmt = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, weekday: "short", day: "2-digit", month: "2-digit" });
const num = (digits: number) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits });

export function formatDateTime(epoch: number): string {
  return dateTime.format(new Date(epoch * 1000));
}

const hourFmt = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const shortDay = new Intl.DateTimeFormat("fr-FR", { timeZone: TZ, day: "2-digit", month: "2-digit" });

/** Graduation de l'axe des temps : heures sous la journée (date à minuit), jours au-delà. */
export function formatAxisTime(epoch: number, increment: number): string {
  const d = new Date(epoch * 1000);
  if (increment >= 86_400) return shortDay.format(d);
  const hm = hourFmt.format(d);
  return hm === "00:00" ? shortDay.format(d) : hm;
}

/** Graduation de l'axe des valeurs : autant de décimales que le pas l'exige, pas plus. */
export function formatTick(value: number, increment: number, unit: string | null): string {
  const digits = Math.min(Math.max(0, -Math.floor(Math.log10(increment || 1))), 3);
  const text = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(
    value,
  );
  return unit ? `${text} ${unit}` : text;
}

export function formatDay(day: string): string {
  return dayFmt.format(new Date(`${day}T12:00:00Z`));
}

/** « il y a 3 min », « il y a 2 h 05 », « il y a 3 j ». */
export function formatAge(seconds: number): string {
  if (seconds < 60) return "à l'instant";
  const min = Math.floor(seconds / 60);
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `il y a ${h} h ${String(min % 60).padStart(2, "0")}`;
  return `il y a ${Math.floor(h / 24)} j`;
}

export function formatDuration(seconds: number): string {
  const min = Math.round(seconds / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} h ${String(min % 60).padStart(2, "0")}`;
  return `${Math.round(h / 24)} j`;
}

export function formatNumber(value: number, unit?: string | null): string {
  const digits = unit === "°C" || unit === "bar" ? 1 : Math.abs(value) >= 100 ? 0 : 2;
  const text = num(digits).format(value);
  return unit ? `${text} ${unit}` : text;
}

/** Libellés d'enum du catalogue Atlantic (anglais/abréviations) -> français. */
const ENUM_FR: Record<string, string> = {
  Heat: "Chauffage",
  Cool: "Rafraîchissement",
  Auto: "Automatique",
  Off: "Arrêt",
  On: "Marche",
  No: "Non",
  Yes: "Oui",
  PROG: "Programmé",
  BASIC: "Manuel",
  Inactive: "Inactif",
  Active: "Actif",
  Disabled: "Désactivé",
  Enabled: "Activé",
  ECS: "Eau chaude",
  DHW: "Eau chaude",
  Stop: "Arrêt",
  Standby: "Veille",
  Undefined: "Non défini",
};

export function translateEnum(label: string): string {
  return ENUM_FR[label] ?? label;
}

export function formatValue(value: Value, unit: string | null, display: string | null): string {
  if (display) return translateEnum(display);
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if (typeof value === "number") return formatNumber(value, unit);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function formatLatest(l: Latest | undefined): string {
  return l ? formatValue(l.value, l.unit, l.display) : "—";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${num(0).format(bytes / 1024)} Ko`;
  return `${num(1).format(bytes / 1024 / 1024)} Mo`;
}

export const GAP_CAUSES: Record<string, string> = {
  downtime: "Service arrêté",
  provider_error: "Erreur du cloud Atlantic",
  credentials: "Identifiants refusés",
  unknown: "Erreur inattendue",
};
