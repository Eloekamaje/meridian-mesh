import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { List, X, House, Newspaper, Briefcase, CirclesThree, GearSix, Play, Plus } from "@phosphor-icons/react";
import { usePerimetre } from "@/lib/perimetre";
import { useDemo } from "@/lib/demo";

// Hub de navigation flottant — remplace la sidebar globale sur l'Atlas (carte plein écran,
// façon Google Maps : les outils flottent sans casser la carte)
export default function AtlasHub() {
  const [ouvert, setOuvert] = useState(false);
  const { espaces } = usePerimetre();
  const { demarrer } = useDemo();
  const navigate = useNavigate();
  const adminAutorise = espaces.some((e) => e.global);

  const LIENS = [
    ["/", "Accueil", House, "accueil"],
    ["/actualites", "Actualités", Newspaper, "actualites"],
    ["/travaux", "Travaux", Briefcase, "travaux"],
    ["/jumeaux", "Jumeaux", CirclesThree, "jumeaux"],
  ];

  return (
    <div className="fixed left-3 top-3 z-40" data-testid="atlas-hub">
      <div className="glass rounded-xl p-1.5">
        <button
          onClick={() => setOuvert((o) => !o)}
          data-testid="hub-menu-btn"
          title="Menu Méridian"
          className="flex h-8 items-center gap-2 rounded-lg px-2.5 transition-colors hover:bg-[#F0F0EE]"
        >
          <span className="pulse-soft h-2 w-2 rounded-full bg-[#3730A3]" />
          <span className="font-display text-xs font-black tracking-[0.18em] text-[#111110]">MÉRIDIAN</span>
          {ouvert ? <X size={13} className="text-[#71716D]" /> : <List size={13} className="text-[#71716D]" />}
        </button>
      </div>
      {ouvert && (
        <div className="glass absolute left-0 top-14 z-50 w-56 rounded-xl p-1.5" data-testid="hub-menu">
          {LIENS.map(([to, label, Icon, tid]) => (
            <Link
              key={to}
              to={to}
              onClick={() => setOuvert(false)}
              data-testid={`hub-nav-${tid}`}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]"
            >
              <Icon size={15} /> {label}
            </Link>
          ))}
          <div className="my-1 border-t border-[#E5E5E3]" />
          <button
            onClick={() => { setOuvert(false); navigate("/travaux/nouveau"); }}
            data-testid="hub-nouveau-travail"
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-semibold text-[#3730A3] transition-colors hover:bg-[#EEECFA]"
          >
            <Plus size={15} weight="bold" /> Nouveau travail
          </button>
          <button
            onClick={() => { setOuvert(false); demarrer(); }}
            data-testid="hub-demo"
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]"
          >
            <Play size={15} /> Parcours guidé
          </button>
          {adminAutorise && (
            <Link
              to="/administration"
              onClick={() => setOuvert(false)}
              data-testid="hub-nav-administration"
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-[#52524F] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]"
            >
              <GearSix size={15} /> Administration
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
