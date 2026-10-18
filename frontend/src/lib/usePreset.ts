import { useMemo, useState } from "react";

import { PRESETS, rangeFor } from "./range";

/** Période choisie (préréglage), mémorisée pour la page. */
export function usePreset(initial = "24h") {
  const [id, setId] = useState(initial);
  const preset = PRESETS.find((p) => p.id === id) ?? PRESETS[0];
  // recalculée à chaque changement de préréglage ; le rafraîchissement 60 s relit la même clé
  const range = useMemo(() => rangeFor(preset), [preset]);
  return { id, setId, preset, range, options: PRESETS.map((p) => ({ id: p.id, label: p.label })) };
}
