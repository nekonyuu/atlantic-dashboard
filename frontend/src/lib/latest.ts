import type { Latest } from "../api/types";

/** Index des dernières valeurs par « équipement/métrique ». */
export function indexLatest(rows: Latest[] | undefined): Map<string, Latest> {
  return new Map((rows ?? []).map((r) => [`${r.equipment}/${r.metric}`, r]));
}

/** Première valeur trouvée pour une métrique, quel que soit l'équipement (ex. room_1, room_2). */
export function findMetric(index: Map<string, Latest>, metric: string, equipment?: string): Latest | undefined {
  if (equipment) return index.get(`${equipment}/${metric}`);
  for (const v of index.values()) if (v.metric === metric) return v;
  return undefined;
}

/** Âge de la donnée la plus récente parmi des valeurs (secondes). */
export function freshest(rows: Latest[] | undefined): number | null {
  if (!rows?.length) return null;
  return Math.min(...rows.map((r) => r.age_seconds));
}
