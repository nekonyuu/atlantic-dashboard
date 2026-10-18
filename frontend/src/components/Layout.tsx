import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useEnergy, useHealth } from "../api/hooks";
import { formatAge } from "../lib/format";
import { isoDay } from "../lib/range";
import { IconAuto, IconBolt, IconChart, IconDrop, IconFlame, IconHome, IconMoon, IconSun } from "./icons";
import { StatusBanner } from "./StatusBanner";
import { Status } from "./ui";

type Theme = "auto" | "light" | "dark";
const THEME_KEY = "pac-theme";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "auto";
  } catch {
    return "auto";
  }
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* stockage indisponible : le choix vaut pour la session */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "auto" ? "light" : t === "light" ? "dark" : "auto"))];
}

const THEME = {
  auto: { icon: <IconAuto />, label: "Thème : système" },
  light: { icon: <IconSun />, label: "Thème : clair" },
  dark: { icon: <IconMoon />, label: "Thème : sombre" },
};

function useNavItems() {
  const now = Date.now();
  // la page Énergie n'apparaît que si le fournisseur déclare des consommations
  const energy = useEnergy(isoDay(now - 31 * 86_400_000), isoDay(now));
  const items = [
    { to: "/", label: "Vue d'ensemble", short: "Accueil", icon: <IconHome /> },
    { to: "/ecs", label: "Eau chaude", short: "ECS", icon: <IconDrop /> },
    { to: "/chauffage", label: "Chauffage", short: "Chauffage", icon: <IconFlame /> },
    { to: "/historique", label: "Historique", short: "Historique", icon: <IconChart /> },
  ];
  if ((energy.data?.length ?? 0) > 0) items.push({ to: "/energie", label: "Énergie", short: "Énergie", icon: <IconBolt /> });
  return items;
}

function CollectStatus() {
  const { data, isError } = useHealth();
  if (isError) return <Status tone="critical">Serveur injoignable</Status>;
  if (!data) return null;
  if (data.poller.stopped_reason) return <Status tone="critical">Collecte arrêtée</Status>;
  if (data.poller.stale) return <Status tone="warning">Collecte en retard</Status>;
  return <Status tone="good">Collecte active</Status>;
}

export function Layout() {
  const [theme, nextTheme] = useTheme();
  const items = useNavItems();
  const health = useHealth();
  const last = health.data?.poller.last_success;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <IconFlame size={17} />
          </span>
          <span>
            Alfea Excellia S<small>Pompe à chaleur · ECS</small>
          </span>
        </div>
        <nav aria-label="Pages">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} end={i.to === "/"} className="nav-link">
              {i.icon}
              {i.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <CollectStatus />
          {last ? <span>Dernière collecte {formatAge(Date.now() / 1000 - last)}</span> : null}
          <button type="button" className="btn" onClick={nextTheme} aria-label={THEME[theme].label}>
            {THEME[theme].icon}
            {THEME[theme].label}
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="mobile-brand">
          <span className="brand-mark">
            <IconFlame size={17} />
          </span>
          <span style={{ marginRight: "auto" }}>Alfea Excellia S</span>
          <CollectStatus />
          <button type="button" className="btn icon" onClick={nextTheme} aria-label={THEME[theme].label}>
            {THEME[theme].icon}
          </button>
        </div>
        <StatusBanner />
        <Outlet />
      </div>

      <nav className="tabbar" aria-label="Pages">
        {items.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.to === "/"}>
            {i.icon}
            {i.short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
