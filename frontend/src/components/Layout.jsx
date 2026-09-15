import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { House, Newspaper, Compass, Briefcase, CirclesThree, GearSix, Plus, SidebarSimple, Play, Users } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useDemo } from "@/lib/demo";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

const NAV = [
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/actualites", label: "Actualités", icon: Newspaper, testid: "nav-actualites" },
  { to: "/travaux", label: "Travaux", icon: Briefcase, testid: "nav-travaux" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
];

export default function Layout() {
  const { espaces, personas, persona, changerCible, version } = usePerimetre();
  const { demarrer, courant } = useDemo();
  const navigate = useNavigate();
  const [repliee, setRepliee] = useState(true); // menu réduit par défaut (icônes seules) ; déplié à la demande
  const [recents, setRecents] = useState([]);

  useEffect(() => {
    api.get("/cases").then((r) => setRecents([...r.data].sort((a, b) => (b.maj_le || "").localeCompare(a.maj_le || "")).slice(0, 3))).catch(() => {});
  }, [version]);

  const adminAutorise = espaces.some((e) => e.global);
  const location = useLocation();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[rgba(148,163,184,0.07)] text-foreground" data-testid="layout">
      {/* Barre latérale — mémoire et grands espaces (réduite par défaut, dépliée à la demande) */}
      <aside className={`flex shrink-0 flex-col border-r border-[rgba(148,163,184,0.16)] bg-[#0F1D28] transition-all duration-200 ${repliee ? "w-14" : "w-60"}`} data-testid="sidebar">
        <div className="flex h-12 items-center gap-2.5 border-b border-[rgba(148,163,184,0.16)] px-3.5">
          <span className="pulse-soft h-2 w-2 shrink-0 rounded-full bg-[#9B87F5]" />
          {!repliee && <span className="font-display text-sm font-black tracking-[0.18em] text-[#F2F6F8]">MÉRIDIAN</span>}
          <button onClick={() => setRepliee(!repliee)} data-testid="sidebar-toggle" title={repliee ? "Déplier" : "Replier"} className="ml-auto rounded-md p-1 text-[#7C93A8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
            <SidebarSimple size={16} />
          </button>
        </div>

        <div className="p-2.5">
          <button
            onClick={() => navigate("/travaux/nouveau")}
            data-testid="sidebar-nouveau-travail"
            title="Nouveau travail"
            className={`flex w-full items-center gap-2 rounded-lg bg-[#9B87F5] px-3 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7] ${repliee ? "justify-center px-0" : ""}`}
          >
            <Plus size={14} weight="bold" /> {!repliee && "Nouveau travail"}
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2.5" data-testid="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, end, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              data-testid={testid}
              title={label}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors ${
                  isActive ? "bg-[rgba(155,135,245,0.12)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
                } ${repliee ? "justify-center px-0" : ""}`
              }
            >
              <Icon size={17} /> {!repliee && label}
            </NavLink>
          ))}

          {!repliee && espaces.filter((e) => !e.global).length > 0 && (
            <div className="pt-4">
              <div className="px-2.5 pb-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">Espaces</div>
              {espaces.filter((e) => !e.global).map((e) => (
                <button key={e.id} onClick={() => changerCible(e.id)} data-testid={`sidebar-espace-${e.id}`} title={`Basculer vers ${e.label}`} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <Users size={13} className="shrink-0 text-[#7C93A8]" /> <span className="truncate">{e.label}</span>
                </button>
              ))}
            </div>
          )}

          {!repliee && recents.length > 0 && (
            <div className="pt-4" data-testid="sidebar-recents">
              <div className="px-2.5 pb-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">Récents</div>
              {recents.map((c) => (
                <button key={c.id} onClick={() => navigate(`/travaux/${c.id}`)} data-testid={`sidebar-recent-${c.id}`} title={c.titre} className="block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  {c.titre}
                </button>
              ))}
            </div>
          )}
        </nav>

        <div className="space-y-0.5 border-t border-[rgba(148,163,184,0.16)] p-2.5">
          <button onClick={demarrer} data-testid="demo-start-btn" title="Parcours guidé Olympiade" className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8] ${repliee ? "justify-center px-0" : ""}`}>
            <Play size={14} weight={courant >= 0 ? "fill" : "regular"} /> {!repliee && "Parcours guidé"}
          </button>
          {adminAutorise && (
            <NavLink to="/administration" data-testid="nav-administration" title="Administration" className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors ${isActive ? "bg-[rgba(155,135,245,0.12)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"} ${repliee ? "justify-center px-0" : ""}`}>
              <GearSix size={17} /> {!repliee && "Administration"}
            </NavLink>
          )}
        </div>
      </aside>

      {/* Colonne principale */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="relative flex-1 overflow-hidden">
          <div key={location.pathname} className="page-transition h-full">
            <Outlet />
          </div>
        </main>
      </div>

      <FlorePanel />
      <DemoTour />
    </div>
  );
}
