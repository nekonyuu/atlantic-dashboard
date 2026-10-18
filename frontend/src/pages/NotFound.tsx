import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="card empty-state">
      <strong style={{ color: "var(--text-2)" }}>Page introuvable</strong>
      <Link to="/">Retour à la vue d'ensemble</Link>
    </div>
  );
}
