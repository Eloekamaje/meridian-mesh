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
  ArrowsClockwise,
  Brain
} from "@phosphor-icons/react";
import api from "@/lib/api";
import { resultatsRecherche, estConversation, PARAM_CONVERSATIONS } from "@/lib/conversationFlore";
import { useContexte } from "@/lib/contexte";
import { useIdentite } from "@/lib/identite";
import { useEvenements } from "@/lib/evenements";
import Notifications from "@/components/Notifications";
import logoComplet from "@/assets/logo/meridian-logo-clair.png";
import logoSymbole from "@/assets/logo/meridian-symbole.png";

const NAV_ITEMS = [
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/actualites", label: "Actualités", icon: Newspaper, testid: "nav-actualites" },
  { to: "/boucle", label: "Boucle", icon: ArrowsClockwise, testid: "nav-boucle" },
  { to: "/cognition", label: "Cognition", icon: Brain, testid: "nav-cognition" },
  { to: "/travaux", label: "Travaux", icon: Briefcase, testid: "nav-travaux" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
  { to: "/administration", label: "Administration", icon: GearSix, testid: "nav-administration" },
];

export default function SidebarGauche({ mode = "bureau", onOuvrir, onFermer }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { basculerFlore, repliAuto } = useContexte();

  // État replié : mémorisé dans le localStorage pour confort utilisateur.
  const [replieMemo, setReplieMemo] = useState(() => {
    return localStorage.getItem("meridian_sidebar_replie") === "true";
  });
  // Replié d'office quand un panneau de détail s'ouvre ; l'utilisateur peut la redéplier tant que ce panneau reste ouvert
  const [depliageForce, setDepliageForce] = useState(false);
  useEffect(() => { if (!repliAuto) setDepliageForce(false); }, [repliAuto]);
  // bureau : replié à la demande (ou par un panneau de détail) ; rail (tablette) : toujours en icônes ; tiroir : toujours complet
  const replie = mode === "rail" ? true : mode === "tiroir" ? false : (repliAuto ? !depliageForce : replieMemo);
  const tiroir = mode === "tiroir";

  const [recents, setRecents] = useState([]);
  const [tousTravaux, setTousTravaux] = useState([]);
  const [enCours, setEnCours] = useState(() => new Set()); // fils où Flore travaille encore
  const pretSse = useRef(false);
  const [recherche, setRecherche] = useState("");
  const [trouves, setTrouves] = useState(null); // réponse du serveur à GET /cases?q=
  const [aExaminer, setAExaminer] = useState(0); // travaux dont une décision est remise en question

  useEffect(() => {
    const q = recherche.trim();
    if (!q) { setTrouves(null); return undefined; }
    const t = setTimeout(() => {
      api.get("/cases", { params: { q, ...PARAM_CONVERSATIONS } }).then((r) => setTrouves(r.data)).catch(() => setTrouves(null));
    }, 250);
    return () => clearTimeout(t);
  }, [recherche]);
  const affiches = recherche.trim() ? resultatsRecherche(recherche, tousTravaux, trouves) : recents;

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

  // Un travail né ailleurs (le panneau Flore) : les Récents se rechargent
  const [majTravaux, setMajTravaux] = useState(0);
  useEffect(() => {
    const maj = () => setMajTravaux((v) => v + 1);
    window.addEventListener("meridian:travaux-maj", maj);
    return () => window.removeEventListener("meridian:travaux-maj", maj);
  }, []);

  useEffect(() => {
    api.get("/cases", { params: PARAM_CONVERSATIONS })
      .then((r) => {
        const sorted = [...r.data].sort((a, b) => (b.maj_le || "").localeCompare(a.maj_le || ""));
        // Ce qui bouge passe en premier (décision remise en question, puis fait nouveau), puis le plus récent
        const poids = (c) => (c.mouvement ? c.mouvement.niveau : 9);
        sorted.sort((a, b) => poids(a) - poids(b));
        setRecents(sorted.slice(0, 8));
        setTousTravaux(sorted);
        setAExaminer(sorted.filter((c) => c.mouvement?.niveau === 1).length);
      })
      .catch(() => {});
  }, [location.pathname, majTravaux]);

  // Les tours de Flore encore en cours : un instantané au montage, puis le canal SSE (démarrage/fin).
  // Le badge survit à la sortie de la page sans polling ; une fin recharge les Récents.
  useEffect(() => {
    api.get("/tours/en-cours")
      .then((r) => { if (!pretSse.current) setEnCours(new Set(r.data?.fils || [])); })
      .catch(() => {});
  }, []);

  useEvenements((e) => {
    if (e.type === "pret") {
      pretSse.current = true;
      setEnCours(new Set(e.fils || []));
    } else if (e.type === "tour.demarre" && e.fil) {
      setEnCours((avant) => new Set(avant).add(e.fil));
    } else if (e.type === "tour.fini" && e.fil) {
      setEnCours((avant) => { const suite = new Set(avant); suite.delete(e.fil); return suite; });
      setMajTravaux((v) => v + 1);
      // Plusieurs tours peuvent partager un même fil : on relit la vérité plutôt que de retirer le fil.
      api.get("/tours/en-cours")
        .then((r) => setEnCours(new Set(r.data?.fils || [])))
        .catch(() => {});
    }
  });

  // « Nouveau travail » ouvre la page de création.
  const ouvrirNouveauTravail = () => {
    if (tiroir) onFermer?.();
    navigate("/travaux/nouveau");
  };

  const identite = useIdentite();

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

            <Notifications />

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
          <Notifications />
        </div>
      )}

      {/* ===================================================================== */}
      {/* BOUTON D'ACTION : NOUVEAU TRAVAIL (Style ChatGPT)                     */}
      {/* ===================================================================== */}
      {!replie ? (
        <div className="relative mb-4">
          <button
            onClick={ouvrirNouveauTravail}
            className="flex min-h-[44px] w-full items-center gap-2.5 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs font-medium text-white transition-all hover:border-white/20 hover:bg-white/[0.08] shadow-sm"
            data-testid="btn-nouveau-travail-sidebar"
          >
            <Plus size={15} className="text-[#60A5FA]" />
            <span>Nouveau travail</span>
          </button>
        </div>
      ) : (
        <button
          onClick={ouvrirNouveauTravail}
          className="mb-4 flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-[#60A5FA] transition-all hover:bg-white/[0.08] hover:scale-105"
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
            onClick={() => { if (tiroir) onFermer?.(); }}
            data-testid={testid}
            title={replie ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl transition-colors ${
                replie 
                  ? `h-9 w-9 justify-center ${isActive ? "bg-blue-500/20 text-blue-300 font-semibold" : "text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"}`
                  : `px-3 py-2 text-xs font-medium ${isActive ? "bg-blue-500/15 text-blue-200 font-semibold" : "text-[#8E9FA5] hover:bg-white/[0.05] hover:text-white"}`
              }`
            }
          >
            <span className="relative flex shrink-0">
              <Icon size={17} />
              {to === "/travaux" && aExaminer > 0 && replie && <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-[#F87171]" />}
            </span>
            {!replie && <span>{label}</span>}
            {!replie && to === "/travaux" && aExaminer > 0 && <span className="ml-auto rounded-full bg-[#F87171]/15 px-1.5 font-code text-[11px] text-[#F87171]" data-testid="nav-travaux-compteur" title="Décisions à examiner">{aExaminer}</span>}
          </NavLink>
        ))}
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

          <input
            type="search" value={recherche} onChange={(e) => setRecherche(e.target.value)}
            placeholder="Rechercher un travail…" aria-label="Rechercher dans les travaux" data-testid="sidebar-recherche"
            className="mb-1 h-7 w-full rounded-lg border border-white/[0.08] bg-transparent px-2 text-[11px] text-[#D8E2EA] placeholder:text-[#526578] focus:border-[#60A5FA]/60 focus:outline-none"
          />
          {affiches.length === 0 && (
            <div className="px-2.5 py-1.5 text-[11px] text-[#64748B]" data-testid="sidebar-recents-vide">
              {recherche.trim() ? "Aucun travail trouvé." : "Aucun travail pour l'instant."}
            </div>
          )}
          {affiches.slice(0, 8).map((c) => (
            <NavLink
              key={c.id}
              to={`/travaux/${c.id}`}
              onClick={() => { if (tiroir) onFermer?.(); }}
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
              <span className="ml-auto flex shrink-0 items-center gap-1.5">
                {estConversation(c) && <span className="font-code text-[9px] text-[#64748B]" data-testid={`recent-conversation-${c.id}`}>conversation</span>}
                {c.mouvement && <span className={`h-2 w-2 shrink-0 rounded-full ${c.mouvement.niveau === 1 ? "bg-[#F87171]" : "bg-[#60A5FA]"}`} title={c.mouvement.texte} data-testid={`recent-mouvement-${c.id}`} />}
                {enCours.has(c.id) && (
                  <span className="flex shrink-0 items-center gap-1 rounded-full bg-[#60A5FA]/20 px-1.5 py-px font-code text-[8px] uppercase tracking-wider text-[#BFDBFE]"
                        title="Flore travaille sur ce travail"
                        data-testid={`recent-en-cours-${c.id}`}>
                    <span className="h-1 w-1 animate-pulse rounded-full bg-current" />
                    en cours
                  </span>
                )}
              </span>
            </NavLink>
          ))}
        </div>
      ) : (
        <div className="flex-1" />
      )}

      {/* ===================================================================== */}
      {/* PIED DE BARRE LATÉRALE : PROFIL UTILISATEUR & STATUT MESH              */}
      {/* ===================================================================== */}
      <div className="mt-auto shrink-0 pt-2 w-full">
        {!replie ? (
          <div className="flex w-full items-center justify-between rounded-xl px-2 py-2" data-testid="sidebar-profil">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-[#60A5FA] to-[#60A5FA] font-display text-xs font-bold text-[#071019] shadow-sm">
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
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <button
              onClick={() => setReplieMemo(false)}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-tr from-[#60A5FA] to-[#60A5FA] font-display text-xs font-bold text-[#071019] shadow-sm hover:scale-105 transition-transform"
              title={`${identite.nom} (${identite.profil?.role || "Directeur SI"})`}
            >
              {identite.initiales}
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
