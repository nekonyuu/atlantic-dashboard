import { useHealth, useLatest } from "../api/hooks";
import { formatAge, formatDuration, GAP_CAUSES } from "../lib/format";
import { freshest } from "../lib/latest";
import { Alert } from "./ui";

/** Bandeau d'état global : collecte arrêtée ou en retard, équipement indisponible, données anciennes. */
export function StatusBanner() {
  const health = useHealth();
  const latest = useLatest();

  if (health.isError) {
    return (
      <Alert tone="critical" title="Serveur du dashboard injoignable.">
        Les valeurs affichées peuvent être anciennes.
      </Alert>
    );
  }
  const h = health.data;
  if (!h) return null;

  if (h.poller.stopped_reason === "credentials") {
    return (
      <Alert tone="critical" title="Collecte arrêtée : identifiants Cozytouch refusés.">
        Corrigez le fichier .env puis redémarrez le conteneur.
      </Alert>
    );
  }
  const ongoing = h.recent_gaps.find((g) => g.ongoing);
  if (h.poller.stale || ongoing) {
    const since = h.poller.last_success;
    return (
      <Alert tone="warning" title="Cloud Atlantic indisponible.">
        {since ? `Dernière collecte réussie ${formatAge(Date.now() / 1000 - since)}` : "Aucune collecte réussie"}
        {ongoing ? ` · ${(GAP_CAUSES[ongoing.cause] ?? ongoing.cause).toLowerCase()} depuis ${formatDuration(ongoing.duration_seconds)}` : ""}
        . La collecte reprendra automatiquement.
      </Alert>
    );
  }
  const off = h.equipment.filter((e) => e.available === false);
  if (off.length) {
    return (
      <Alert tone="warning" title="Équipement injoignable :">
        {off.map((e) => e.id).join(", ")}.
      </Alert>
    );
  }
  const age = freshest(latest.data);
  if (age !== null && age > 6 * 3600) {
    return (
      <Alert tone="warning" title="Données anciennes :">
        aucune valeur nouvelle depuis {formatDuration(age)}.
      </Alert>
    );
  }
  return null;
}
