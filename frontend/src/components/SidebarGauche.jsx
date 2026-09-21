import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { 
  Compass, 
  Newspaper, 
  Briefcase, 
  CirclesThree, 
  GearSix, 
  Plus, 
  MagnifyingGlass, 
  SidebarSimple, 
  X,
  Sparkle, 
  Bell, 
  Users, 
  Check, 
  CaretDown,
  PlayCircle,
  Detective
} from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { usePilotage } from "@/lib/pilotage";
import IndicateurClic from "@/components/IndicateurClic";
import logoComplet from "@/assets/logo/meridian-logo-clair.png";
import logoSymbole from "@/assets/logo/meridian-symbole.png";

const NAV_ITEMS = [
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/actualites", label: "Actualités", icon: Newspaper, testid: "nav-actualites" },
  { to: "/investigations", label: "Investigations", icon: Detective, testid: "nav-investigations" },
  { to: "/travaux", label: "Travaux", icon: Briefcase, testid: "nav-travaux" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
  { to: "/administration", label: "Administration", icon: GearSix, testid: "nav-administration" },
];

export default function SidebarGauche({ mode = "bureau", onOuvrir, onFermer }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { personas, persona, changerPersona, espaces, cible, changerCible } = usePerimetre();
  const { basculerFlore, repliAuto } = useContexte();
  // Non nul uniquement dans la démonstration Polaris : la coquille est alors verrouillée
  const pilote = usePilotage();

  // État replié : mémorisé dans le localStorage pour confort utilisateur.
  // En démonstration la barre reste dépliée : le bouton « Nouveau travail » doit être visible.
  const [replieMemo, setReplieMemo] = useState(() => {
    return localStorage.getItem("meridian_sidebar_replie") === "true";
  });
  // Replié d'office quand un panneau de détail s'ouvre ; l'utilisateur peut la redéplier tant que ce panneau reste ouvert
  const [depliageForce, setDepliageForce] = useState(false);
  useEffect(() => { if (!repliAuto) setDepliageForce(false); }, [repliAuto]);
  // bureau : replié à la demande (ou par un panneau de détail) ; rail (tablette) : toujours en icônes ; tiroir : toujours complet
  const replie = mode === "rail" ? true : mode === "tiroir" ? false : !pilote && (repliAuto ? !depliageForce : replieMemo);
  const tiroir = mode === "tiroir";

  const [menuProfil, setMenuProfil] = useState(false);
  const [recents, setRecents] = useState([]);
  const refProfil = useRef(null);

  const basculerRepli = () => {
    if (mode === "rail") { onOuvrir?.(); return; }
    if (mode === "tiroir") { onFermer?.(); return; }
    if (repliAuto) { setDepliageForce((d) => !d); return; }
    setReplieMemo((prev) => {
      const suivant = !prev;
      localStorage.setItem("meridian_sidebar_replie", suivant ? "true" : "false");
      return suivant;
    });
  };

  useEffect(() => {
    api.get("/cases")
      .then((r) => {
        const sorted = [...r.data].sort((a, b) => (b.maj_le || "").localeCompare(a.maj_le || ""));
        setRecents(sorted.slice(0, 8));
      })
      .catch(() => {});
    // En démonstration, la liste se recharge quand le travail naît, s'enrichit ou se fige
  }, [pilote?.versionTravaux, location.pathname]);

  // « Nouveau travail » : en démonstration le clic lance la séquence scénarisée
  // (le moteur ouvre la page) ; hors démonstration il ouvre la vraie page de création.
  const ouvrirNouveauTravail = () => {
    if (tiroir) onFermer?.();
    if (pilote) {
      if (pilote.ouvertureEnAttente) pilote.demarrerOuverture();
      return;
    }
    navigate("/travaux/nouveau");
  };

  // Navigation verrouillée en démonstration : « Atlas » reste dans la démo, le reste est neutralisé
  const lienActif = (to) => !pilote || to === "/atlas";

  useEffect(() => {
    const fermer = (e) => {
      if (refProfil.current && !refProfil.current.contains(e.target)) {
        setMenuProfil(false);
      }
    };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  const personaActuel = personas.find((p) => p.id === persona) || { nom: "Majella Elobo", role: "Directeur SI" };
  // Démonstration : l'identité est celle du rôle joué, pas celle de la personne connectée
  const identite = pilote
    ? { nom: personaActuel.nom, sous: personaActuel.role, initiales: (personaActuel.nom || "?").slice(0, 2).toUpperCase() }
    : { nom: "Majella Elobo", sous: `${personaActuel.role || "Directeur SI"} · Mesh 38`, initiales: "ME" };

  return (
    <aside 
      className={`relative flex h-full shrink-0 flex-col border-r border-white/[0.08] bg-[#091420] text-[#DCE6EE] transition-all duration-200 ease-in-out select-none ${
        replie ? "w-14 items-center px-2 py-3" : tiroir ? "w-full px-3 py-3" : "w-64 px-3 py-3"
      }`}
      data-testid="sidebar-gauche"
    >
      {/* ===================================================================== */}
      {/* EN-TÊTE DE LA BARRE LATÉRALE                                          */}
      {/* ===================================================================== */}
      {!replie ? (
        <div className="mb-3 flex items-center justify-between px-1">
          {/* Logo Méridian (version pour fond sombre) */}
          <img src={logoComplet} alt="Méridian" className="h-6 w-auto select-none" draggable={false} data-testid="sidebar-logo" />

          <div className="flex items-center gap-1">
            {/* Recherche globale */}
            <button 
              onClick={() => { navigate("/atlas"); if (tiroir) onFermer?.(); }} 
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[#7C93A8] transition-colors hover:bg-white/[0.06] hover:text-white"
              title="Rechercher dans le SI"
            >
              <MagnifyingGlass size={15} />
            </button>

            {/* Bouton pour replier la barre latérale vers les icônes seules */}
            <button 
              onClick={basculerRepli}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[#7C93A8] transition-colors hover:bg-white/[0.06] hover:text-white"
              title="Masquer le panneau latéral (afficher uniquement les icônes)"
              data-testid="btn-toggle-sidebar"
            >
              {tiroir ? <X size={16} /> : <SidebarSimple size={16} />}
            </button>
          </div>
        </div>
      ) : (
        <div className="mb-3 flex flex-col items-center gap-3">
          {/* Symbole Méridian ; au survol (ou au focus clavier), l'icône de dépliage prend sa place */}
          <button
            onClick={basculerRepli}
            className="group relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-white/[0.08] focus-visible:bg-white/[0.08]"
            title="Déplier la barre latérale"
            aria-label="Déplier la barre latérale"
            data-testid="btn-toggle-sidebar"
          >
            <img src={logoSymbole} alt="Méridian" className="h-6 w-auto select-none transition-opacity duration-150 group-hover:opacity-0 group-focus-visible:opacity-0" draggable={false} data-testid="sidebar-symbole" />
            <SidebarSimple size={18} className="absolute text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100" />
          </button>
        </div>
      )}

      {/* ===================================================================== */}
      {/* BOUTON D'ACTION : NOUVEAU TRAVAIL (Style ChatGPT)                     */}
      {/* ===================================================================== */}
      {/* Démonstration : le clic est le geste que le visiteur doit faire — halo, main et bulle l'y invitent */}
      {!replie ? (
        <div className="relative mb-4">
          <button
            onClick={ouvrirNouveauTravail}
            className={`flex min-h-[44px] w-full items-center gap-2.5 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs font-medium text-white transition-all hover:border-white/20 hover:bg-white/[0.08] shadow-sm ${
              pilote?.ouvertureEnAttente ? "animate-pulse ring-2 ring-[#BFDBFE] ring-offset-2 ring-offset-[#091420]" : ""
            }`}
            data-testid="btn-nouveau-travail-sidebar"
          >
            <Plus size={15} className="text-[#38BDF8]" />
            <span>Nouveau travail</span>
          </button>
          {pilote?.ouvertureEnAttente && <IndicateurClic />}
        </div>
      ) : (
        <button
          onClick={ouvrirNouveauTravail}
          className="mb-4 flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-[#38BDF8] transition-all hover:bg-white/[0.08] hover:scale-105"
          title="Nouveau travail"
          data-testid="btn-nouveau-travail-sidebar"
        >
          <Plus size={16} weight="bold" />
        </button>
      )}

      {/* ===================================================================== */}
      {/* LIENS DE NAVIGATION PRIMAIRES                                         */}
      {/* ===================================================================== */}
      <nav className={`space-y-1 ${replie ? "w-full flex flex-col items-center" : ""}`} data-testid="sidebar-nav-items">
        {NAV_ITEMS.map(({ to, label, icon: Icon, testid }) => (
          <NavLink
            key={to}
            to={to}
            onClick={(e) => { if (!lienActif(to)) e.preventDefault(); else if (tiroir) onFermer?.(); }}
            data-testid={testid}
            aria-disabled={!lienActif(to) || undefined}
            title={!lienActif(to) ? "Indisponible pendant la démonstration" : replie ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl transition-colors ${
                replie 
                  ? `h-9 w-9 justify-center ${isActive ? "bg-sky-500/20 text-sky-300 font-semibold" : "text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"}`
                  : `px-3 py-2 text-xs font-medium ${isActive ? "bg-sky-500/15 text-sky-200 font-semibold" : "text-[#8E9FA5] hover:bg-white/[0.05] hover:text-white"}`
              }`
            }
          >
            <Icon size={17} className="shrink-0" />
            {!replie && <span>{label}</span>}
          </NavLink>
        ))}
        {/* Entrée de la démonstration : même menu partout ; pendant la démo elle est active et inerte */}
        <NavLink
          to="/demo"
          onClick={(e) => { if (pilote) e.preventDefault(); else if (tiroir) onFermer?.(); }}
          data-testid="nav-demo"
          title={replie ? "Démonstration" : undefined}
          className={({ isActive }) => {
            const actif = isActive || !!pilote;
            return `flex items-center gap-3 rounded-xl transition-colors ${
              replie
                ? `h-9 w-9 justify-center hover:bg-white/[0.06] ${actif ? "bg-[#60A5FA]/20 text-[#BFDBFE]" : "text-[#60A5FA]"}`
                : `px-3 py-2 text-xs font-medium ${actif ? "bg-[#60A5FA]/15 font-semibold text-white" : "text-[#93C5FD] hover:bg-[#60A5FA]/10 hover:text-white"}`
            }`;
          }}
        >
          <PlayCircle size={17} className="shrink-0" />
          {!replie && <span>Démonstration</span>}
        </NavLink>
      </nav>

      {/* Séparateur */}
      <div className="my-3 border-t border-white/[0.06] w-full" />

      {/* ===================================================================== */}
      {/* SECTION RÉCENTES (Visible uniquement en mode déplié)                 */}
      {/* ===================================================================== */}
      {!replie ? (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1" data-testid="sidebar-recents-zone">
          <div className="px-2 py-1 text-[11px] font-semibold text-[#64748B]">
            Récentes
          </div>

          {recents.length === 0 && (
            <div className="px-2.5 py-1.5 text-[11px] text-[#64748B]" data-testid="sidebar-recents-vide">
              Aucun travail pour l'instant.
            </div>
          )}
          {recents.slice(0, 8).map((c) => (
            <NavLink
              key={c.id}
              to={`/travaux/${c.id}`}
              onClick={(e) => { if (pilote && !pilote.travailOuvrable) e.preventDefault(); else if (tiroir) onFermer?.(); }}
              data-testid={`sidebar-recent-${c.id}`}
              className={({ isActive }) =>
                `flex items-center gap-2 truncate rounded-xl px-2.5 py-1.5 text-xs transition-colors ${
                  isActive
                    ? "bg-white/[0.08] font-semibold text-white"
                    : "text-[#8E9FA5] hover:bg-white/[0.04] hover:text-white"
                }`
              }
              title={c.titre}
            >
              <span className="truncate">{c.titre}</span>
              {c.demo_phase === "en_construction" && (
                <span className="shrink-0 rounded-full bg-[#60A5FA]/20 px-1.5 py-px font-code text-[8px] uppercase tracking-wider text-[#BFDBFE]">en cours</span>
              )}
            </NavLink>
          ))}
        </div>
      ) : (
        <div className="flex-1" />
      )}

      {/* ===================================================================== */}
      {/* PIED DE BARRE LATÉRALE : PROFIL UTILISATEUR & STATUT MESH              */}
      {/* ===================================================================== */}
      <div className="mt-auto shrink-0 pt-2 w-full" ref={refProfil}>
        {!replie ? (
          <div className="relative">
            <button
              onClick={() => { if (!pilote) setMenuProfil(!menuProfil); }}
              className="flex w-full items-center justify-between rounded-xl px-2 py-2 transition-colors hover:bg-white/[0.06]"
              data-testid="sidebar-profil-btn"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-[#38BDF8] to-[#60A5FA] font-display text-xs font-bold text-[#071019] shadow-sm">
                  {identite.initiales}
                </div>
                <div className="min-w-0 text-left">
                  <div className="truncate text-xs font-semibold text-white">
                    {identite.nom}
                  </div>
                  <div className="truncate text-[10px] text-[#7C93A8]">
                    {identite.sous}
                  </div>
                </div>
              </div>
              <CaretDown size={13} className="text-[#64748B]" />
            </button>

            {/* Menu profil / Persona switcher */}
            {menuProfil && (
              <div className="absolute bottom-12 left-0 z-50 w-56 rounded-2xl border border-white/10 bg-[#0C1724] p-2 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
                <div className="px-2 py-1 text-[10px] font-code uppercase tracking-wider text-[#7C93A8]">
                  Changer de rôle / persona
                </div>
                {personas.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      changerPersona(p.id);
                      setMenuProfil(false);
                    }}
                    className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                      persona === p.id 
                        ? "bg-sky-500/20 text-sky-200 font-semibold" 
                        : "text-[#CBD5E1] hover:bg-white/[0.06] hover:text-white"
                    }`}
                  >
                    <span>{p.nom}</span>
                    {persona === p.id && <Check size={12} className="text-sky-400" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <button
              onClick={() => setReplieMemo(false)}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-tr from-[#38BDF8] to-[#60A5FA] font-display text-xs font-bold text-[#071019] shadow-sm hover:scale-105 transition-transform"
              title={`${identite.nom} (${personaActuel.role || "Directeur SI"})`}
            >
              {identite.initiales}
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
