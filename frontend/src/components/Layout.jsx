import { NavLink, Outlet } from "react-router-dom";
import {
  Sun,
  Compass,
  Briefcase,
  CirclesThree,
  Database,
  Play,
} from "@phosphor-icons/react";
import { useMesh } from "@/lib/mesh";
import { useDemo } from "@/lib/demo";
import FlorePanel from "./FlorePanel";
import DemoTour from "./DemoTour";
import Topbar from "./Topbar";

const NAV = [
  { to: "/", label: "Aujourd'hui", icon: Sun, end: true, testid: "nav-aujourdhui" },
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/cases", label: "Cases", icon: Briefcase, testid: "nav-cases" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
  { to: "/administration", label: "Administration", icon: Database, testid: "nav-administration" },
];

export default function Layout() {
  const { mesh } = useMesh();
  const { demarrer, courant } = useDemo();
  const actifs = mesh?.jumeaux.filter((j) => j.statut === "actif").length ?? 0;
  const total = mesh?.jumeaux.length ?? 0;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#050505] text-foreground">
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/[0.08] bg-[#0A0A0A]" data-testid="sidebar">
        <div className="px-5 pb-8 pt-6">
          <div className="flex items-center gap-2.5">
            <span className="pulse-soft h-2.5 w-2.5 rounded-full bg-[#3B82F6]" />
            <span className="font-display text-xl font-black tracking-[0.18em] text-white">MÉRIDIAN</span>
          </div>
          <div className="mt-1.5 font-code text-[10px] tracking-[0.2em]">
            <span className="text-[#22D3EE]">DÉCOUVRIR</span>
            <span className="text-white/30"> · </span>
            <span className="text-[#A78BFA]">COMPRENDRE</span>
            <span className="text-white/30"> · </span>
            <span className="text-[#FBBF24]">DÉCIDER</span>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3">
          {NAV.map(({ to, label, icon: Icon, end, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              data-testid={testid}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md border-l-2 px-3 py-2.5 text-sm transition-colors duration-200 ${
                  isActive
                    ? "border-[#3B82F6] bg-white/[0.06] font-semibold text-white"
                    : "border-transparent text-white/55 hover:bg-white/[0.04] hover:text-white"
                }`
              }
            >
              <Icon size={18} weight="regular" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto space-y-3 px-4 pb-5">
          <button
            onClick={demarrer}
            data-testid="demo-start-btn"
            className="flex w-full items-center gap-2.5 rounded-md border border-[#3B82F6]/40 bg-[#3B82F6]/10 px-3 py-2.5 text-sm font-semibold text-[#7FB3FA] transition-colors duration-200 hover:bg-[#3B82F6]/20"
          >
            <Play size={16} weight="fill" />
            {courant >= 0 ? "Parcours en cours…" : "Parcours Olympiade"}
          </button>
          <div className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-2.5" data-testid="mesh-status">
            <div className="flex items-center gap-2">
              <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#10B981]" />
              <span className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Mesh vivant</span>
            </div>
            <div className="mt-1 text-sm text-white/80">
              <span className="font-code font-medium text-white">{actifs}</span> jumeaux actifs
              <span className="text-white/40"> / {total}</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="relative flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <div className="relative flex-1 overflow-hidden">
          <Outlet />
        </div>
      </main>

      <FlorePanel />
      <DemoTour />
    </div>
  );
}
