import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { House, Newspaper, Compass, Briefcase, CirclesThree, GearSix, Plus, SidebarSimple, Play, Users } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useDemo } from "@/lib/demo";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

const NAV = [
  { to: "/", label: "Accueil", icon: House, end: true, testid: "nav-accueil" },
  { to: "/actualites", label: "Actualités", icon: Newspaper, testid: "nav-actualites" },
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/travaux", label: "Travaux", icon: Briefcase, testid: "nav-travaux" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
];

export default function Layout() {
  const { espaces, personas, persona, changerCible, version } = usePerimetre();
  const { demarrer, courant } = useDemo();
  const navigate = useNavigate();
  const [repliee, setRepliee] = useState(() => typeof window !== "undefined" && window.matchMedia("(max-width: 1024px)").matches); // repliée par défaut sur tablette/mobile
  const [recents, setRecents] = useState([]);

  useEffect(() => {
    api.get("/cases").then((r) => setRecents([...r.data].sort((a, b) => (b.maj_le || "").localeCompare(a.maj_le || "")).slice(0, 3))).catch(() => {});
  }, [version]);

  const adminAutorise = espaces.some((e) => e.global);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#F7F7F6] text-foreground" data-testid="layout">
      {/* Barre latérale — mémoire et grands espaces */}
      <aside className={`flex shrink-0 flex-col border-r border-[#E5E5E3] bg-white transition-all duration-200 ${repliee ? "w-14" : "w-60"}`} data-testid="sidebar">
        <div className="flex h-12 items-center gap-2.5 border-b border-[#E5E5E3] px-3.5">
          <span className="pulse-soft h-2 w-2 shrink-0 rounded-full bg-[#3730A3]" />
          {!repliee && <span className="font-display text-sm font-black tracking-[0.18em] text-[#111110]">MÉRIDIAN</span>}
          <button onClick={() => setRepliee(!repliee)} data-testid="sidebar-toggle" title={repliee ? "Déplier" : "Replier"} className="ml-auto rounded-md p-1 text-[#71716D] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]">
            <SidebarSimple size={16} />
          </button>
        </div>

        <div className="p-2.5">
          <button
            onClick={() => navigate("/travaux/nouveau")}
            data-testid="sidebar-nouveau-travail"
            title="Nouveau travail"
            className={`flex w-full items-center gap-2 rounded-lg bg-[#3730A3] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA] ${repliee ? "justify-center px-0" : ""}`}
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
                  isActive ? "bg-[#EEECFA] font-semibold text-[#312E81]" : "text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]"
                } ${repliee ? "justify-center px-0" : ""}`
              }
            >
              <Icon size={17} /> {!repliee && label}
            </NavLink>
          ))}

          {!repliee && espaces.filter((e) => !e.global).length > 0 && (
            <div className="pt-4">
              <div className="px-2.5 pb-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#71716D]">Espaces</div>
              {espaces.filter((e) => !e.global).map((e) => (
                <button key={e.id} onClick={() => changerCible(e.id)} data-testid={`sidebar-espace-${e.id}`} title={`Basculer vers ${e.label}`} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-xs text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]">
                  <Users size={13} className="shrink-0 text-[#71716D]" /> <span className="truncate">{e.label}</span>
                </button>
              ))}
            </div>
          )}

          {!repliee && recents.length > 0 && (
            <div className="pt-4" data-testid="sidebar-recents">
              <div className="px-2.5 pb-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#71716D]">Récents</div>
              {recents.map((c) => (
                <button key={c.id} onClick={() => navigate(`/travaux/${c.id}`)} data-testid={`sidebar-recent-${c.id}`} title={c.titre} className="block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]">
                  {c.titre}
                </button>
              ))}
            </div>
          )}
        </nav>

        <div className="space-y-0.5 border-t border-[#E5E5E3] p-2.5">
          <button onClick={demarrer} data-testid="demo-start-btn" title="Parcours guidé Olympiade" className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110] ${repliee ? "justify-center px-0" : ""}`}>
            <Play size={14} weight={courant >= 0 ? "fill" : "regular"} /> {!repliee && "Parcours guidé"}
          </button>
          {adminAutorise && (
            <NavLink to="/administration" data-testid="nav-administration" title="Administration" className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors ${isActive ? "bg-[#EEECFA] font-semibold text-[#312E81]" : "text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]"} ${repliee ? "justify-center px-0" : ""}`}>
              <GearSix size={17} /> {!repliee && "Administration"}
            </NavLink>
          )}
        </div>
      </aside>

      {/* Colonne principale */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="relative flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>

      <FlorePanel />
      <DemoTour />
    </div>
  );
}
