// Couleur fixe par mesure : une série garde sa couleur quels que soient les filtres
// (règle « la couleur suit l'entité, jamais son rang »). Les consignes reprennent la
// teinte de la mesure qu'elles pilotent, en pointillé.

export interface SeriesStyle {
  color: string; // variable CSS
  dashed?: boolean;
}

const STYLES: Record<string, SeriesStyle> = {
  outdoor_temperature: { color: "--series-1" },
  dhw_temperature: { color: "--series-2" },
  dhw_setpoint: { color: "--series-2", dashed: true },
  room_temperature: { color: "--series-3" },
  room_setpoint: { color: "--series-3", dashed: true },
  flow_temperature: { color: "--series-4" },
  flow_setpoint: { color: "--series-4", dashed: true },
  return_temperature: { color: "--series-5" },
  water_pressure: { color: "--series-1" },
  modulation: { color: "--series-7" },
  circulator_flow: { color: "--series-6" },
  dhw_charge_setpoint: { color: "--series-2", dashed: true },
  energy_heating_cumulative: { color: "--series-1" },
  energy_dhw_cumulative: { color: "--series-2" },
  wifi_rssi: { color: "--series-7" },
};

export function styleFor(metric: string): SeriesStyle {
  return STYLES[metric] ?? { color: "--series-1" };
}

export function cssVar(name: string): string {
  if (typeof document === "undefined") return "#888";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

/** Catégories de consommation du fournisseur (correspondance chauffage/ECS non confirmée). */
export const ENERGY_CATEGORY: Record<number, { label: string; color: string }> = {
  1: { label: "Catégorie 1", color: "--series-1" },
  2: { label: "Catégorie 2", color: "--series-2" },
};
