import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { ShieldCheck, LockSimple, Bell, Flag, Users, Sparkle, Compass, Newspaper, Briefcase, CirclesThree, GearSix, Plus, List, Play } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { useDemo } from "@/lib/demo";
import { parseQuand } from "@/lib/temps";

const TYPES_NOTIF = { mention: "#9B87F5", assignation: "#F2B84B", a_revoir: "#F87171" };

const NAV = [
  { to: "/atlas", label: "Atlas", icon: Compass, testid: "nav-atlas" },
  { to: "/actualites", label: "Actualités", icon: Newspaper, testid: "nav-actualites" },
  { to: "/travaux", label: "Travaux", icon: Briefcase, testid: "nav-travaux" },
  { to: "/jumeaux", label: "Jumeaux", icon: CirclesThree, testid: "nav-jumeaux" },
];

// En-tête contextuel permanent : espace actif · état du Mesh · sollicitations · Flore · identité
export default function Topbar() {
  const { personas, persona, espaces, vues, cible, info, changerPersona, changerCible, version } = usePerimetre();
  const { mesh } = useMesh();
  const { floreOuverte, basculerFlore } = useContexte();
  const { demarrer, courant } = useDemo();
  const navigate = useNavigate();
  const [notifs, setNotifs] = useState([]);
  const [nonLues, setNonLues] = useState(0);
  const [aTraiter, setATraiter] = useState(0);
  const [panneau, setPanneau] = useState(false);
  const [menuOuvert, setMenuOuvert] = useState(false);
  const [recents, setRecents] = useState([]);
  const refPanneau = useRef(null);
  const refMenu = useRef(null);

  const adminAutorise = espaces.some((e) => e.global);
  const espacesSecondaires = espaces.filter((e) => !e.global);

  const actifs = mesh?.jumeaux.filter((j) => j.statut === "actif").length ?? 0;

  // Fraîcheur du Mesh : la mise à jour la plus récente parmi les jumeaux
  const fraicheurMesh = (() => {
    let meilleur = null;
    for (const j of mesh?.jumeaux || []) {
      const d = parseQuand(j.fraicheur);
      if (d && (!meilleur || d > meilleur.d)) meilleur = { d, texte: j.fraicheur };
    }
    return meilleur?.texte || null;
  })();

  const chargerNotifs = () =>
    api.get("/notifications").then((r) => {
      setNotifs(r.data.notifications);
      setNonLues(r.data.non_lues);
    }).catch(() => {});

  useEffect(() => {
    chargerNotifs();
    api.get("/initiatives/compteurs").then((r) => setATraiter(r.data.a_traiter)).catch(() => {});
    const t = setInterval(() => {
      chargerNotifs();
      api.get("/initiatives/compteurs").then((r) => setATraiter(r.data.a_traiter)).catch(() => {});
    }, 20000);
    return () => clearInterval(t);
  }, [persona, cible]);

  useEffect(() => {
    const fermer = (e) => {
      if (refPanneau.current && !refPanneau.current.contains(e.target)) setPanneau(false);
      if (refMenu.current && !refMenu.current.contains(e.target)) setMenuOuvert(false);
    };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  useEffect(() => {
    api.get("/cases").then((r) => setRecents([...r.data].sort((a, b) => (b.maj_le || "").localeCompare(a.maj_le || "")).slice(0, 3))).catch(() => {});
  }, [version]);

  const ouvrirNotif = async (n) => {
    setPanneau(false);
    await api.post(`/notifications/${n.id}/lue`).catch(() => {});
    chargerNotifs();
    if (n.lien) navigate(n.lien);
  };

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-4" data-testid="topbar">
      {/* Marque + navigation primaire */}
      <div className="flex shrink-0 items-center gap-1.5">
        <div className="mr-1.5 flex items-center gap-2" data-testid="marque">
          <span className="pulse-soft h-2 w-2 shrink-0 rounded-full bg-[#9B87F5]" />
          <span className="hidden font-display text-sm font-black tracking-[0.18em] text-[#F2F6F8] md:inline">MÉRIDIAN</span>
        </div>
        <nav className="hidden items-center gap-1 md:flex" data-testid="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, testid }) => (
            <NavLink
              key={to}
              to={to}
              data-testid={testid}
              title={label}
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs transition-colors ${
                  isActive ? "bg-[rgba(155,135,245,0.14)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
                }`
              }
            >
              <Icon size={15} /> <span className="hidden xl:inline">{label}</span>
            </NavLink>
          ))}
        </nav>
        {/* Menu secondaire — hamburger */}
        <div className="relative" ref={refMenu}>
          <button
            onClick={() => setMenuOuvert(!menuOuvert)}
            data-testid="nav-menu-btn"
            title="Espaces, récents, parcours guidé, administration"
            className={`flex h-8 w-8 items-center justify-center rounded-md border transition-colors ${menuOuvert ? "border-[#9B87F5]/50 bg-[rgba(155,135,245,0.10)] text-[#C4B5FD]" : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:text-[#F2F6F8]"}`}
          >
            <List size={15} weight="bold" />
          </button>
          {menuOuvert && (
            <div className="glass absolute left-0 top-10 z-50 w-72 rounded-xl p-2" data-testid="nav-menu">
              {/* Mobile : la navigation primaire vit dans ce menu */}
              <div className="pb-1 md:hidden">
                {NAV.map(({ to, label, icon: Icon, testid }) => (
                  <NavLink
                    key={to}
                    to={to}
                    data-testid={`menu-${testid}`}
                    onClick={() => setMenuOuvert(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs transition-colors ${
                        isActive ? "bg-[rgba(155,135,245,0.14)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
                      }`
                    }
                  >
                    <Icon size={15} /> {label}
                  </NavLink>
                ))}
              </div>
              {espacesSecondaires.length > 0 && (
                <div className="pb-1">
                  <div className="px-2.5 pb-1 pt-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">Espaces</div>
                  {espacesSecondaires.map((e) => (
                    <button key={e.id} onClick={() => { changerCible(e.id); setMenuOuvert(false); }} data-testid={`sidebar-espace-${e.id}`} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                      <Users size={13} className="shrink-0 text-[#7C93A8]" /> <span className="truncate">{e.label}</span>
                    </button>
                  ))}
                </div>
              )}
              {recents.length > 0 && (
                <div className="pb-1" data-testid="sidebar-recents">
                  <div className="px-2.5 pb-1 pt-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">Récents</div>
                  {recents.map((c) => (
                    <button key={c.id} onClick={() => { navigate(`/travaux/${c.id}`); setMenuOuvert(false); }} data-testid={`sidebar-recent-${c.id}`} title={c.titre} className="block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                      {c.titre}
                    </button>
                  ))}
                </div>
              )}
              <div className="border-t border-[rgba(148,163,184,0.12)] pt-1">
                <div className="pb-1 lg:hidden">
                  <div className="px-2.5 pb-1 pt-1 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">Profil</div>
                  {personas.map((p) => (
                    <button key={p.id} onClick={() => { changerPersona(p.id); setMenuOuvert(false); }} data-testid={`menu-persona-${p.id}`} className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${persona === p.id ? "bg-[rgba(155,135,245,0.14)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"}`}>
                      <Users size={13} className="shrink-0 text-[#7C93A8]" /> <span className="truncate">{p.nom} — {p.role}</span>
                    </button>
                  ))}
                </div>
                <button onClick={() => { demarrer(); setMenuOuvert(false); }} data-testid="demo-start-btn" className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <Play size={14} weight={courant >= 0 ? "fill" : "regular"} /> Parcours guidé
                </button>
                {adminAutorise && (
                  <NavLink to="/administration" data-testid="nav-administration" onClick={() => setMenuOuvert(false)} className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${isActive ? "bg-[rgba(155,135,245,0.14)] font-semibold text-[#C4B5FD]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"}`}>
                    <GearSix size={14} /> Administration
                  </NavLink>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Espace actif — l'autorisation devient une simple icône (détail au survol) */}
      <div className="flex min-w-0 items-center gap-1.5">
        {info && (
          <span
            title={info.espace.global ? "Vue complète du périmètre autorisé" : `Filtré côté serveur · ${info.nb_autorises} jumeaux`}
            data-testid="perimetre-badge"
            className="hidden shrink-0 sm:inline-flex"
          >
            {info.espace.global ? <ShieldCheck size={14} className="text-[#34D399]" /> : <LockSimple size={14} className="text-[#F2B84B]" />}
          </span>
        )}
        <select
          value={cible}
          onChange={(e) => changerCible(e.target.value)}
          data-testid="selecteur-perimetre"
          title="Équipe / espace actif"
          className="h-8 w-24 min-w-0 truncate rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs font-semibold text-[#F2F6F8] focus:border-[#9B87F5]/60 focus:outline-none sm:w-40"
        >
          <optgroup label="Espaces">
            {espaces.map((e) => (
              <option key={e.id} value={e.id} label={e.global ? `${e.label} · autorisé` : e.label} />
            ))}
          </optgroup>
          {vues.length > 0 && (
            <optgroup label="Vues enregistrées">
              {vues.map((v) => (
                <option key={v.id} value={`vue:${v.id}`} label={`Vue — ${v.nom}`} />
              ))}
            </optgroup>
          )}
        </select>
      </div>

      <div className="flex-1" />

      {/* État du Mesh + sollicitations + identité */}
      <div className="flex shrink-0 items-center gap-2.5">
        <button
          onClick={() => navigate("/travaux/nouveau")}
          data-testid="sidebar-nouveau-travail"
          title="Nouveau travail"
          className="flex h-8 items-center gap-1.5 rounded-lg bg-[#9B87F5] px-2.5 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7]"
        >
          <Plus size={13} weight="bold" /> <span className="hidden 2xl:inline">Nouveau travail</span>
        </button>
        <span
          className="hidden items-center gap-1.5 whitespace-nowrap font-code text-[10px] uppercase tracking-[0.15em] text-[#94A3B8] xl:flex"
          data-testid="mesh-status"
          title={fraicheurMesh ? `Mesh vivant · à jour ${fraicheurMesh}` : "Mesh vivant"}
        >
          <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#34D399]" />
          Mesh vivant · {actifs} jumeaux{fraicheurMesh && <span className="normal-case tracking-normal text-[#7C93A8]" data-testid="mesh-fraicheur"> · {fraicheurMesh}</span>}
        </span>

        <button
          onClick={() => navigate("/actualites?vue=a_traiter")}
          data-testid="a-traiter-pill"
          title="Sollicitations du Mesh en attente"
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
            aTraiter > 0 ? "border-[#F2B84B]/40 bg-[rgba(242,184,75,0.10)] text-[#F2B84B] hover:bg-[#F2B84B]/10" : "border-[rgba(148,163,184,0.16)] text-[#7C93A8]"
          }`}
        >
          <Flag size={12} /> {aTraiter}<span className="hidden sm:inline">&nbsp;à traiter</span>
        </button>

        {/* Flore — présence conversationnelle globale de Méridian (⌘K) */}
        <button
          onClick={basculerFlore}
          data-testid="btn-parler-flore"
          title="Parler à Flore (⌘K) — disponible partout, comprend le contexte de ce que vous regardez"
          className={`flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-semibold transition-colors ${
            floreOuverte
              ? "border-[#9B87F5] bg-[#9B87F5] text-[#071019]"
              : "border-[#9B87F5]/40 bg-[#9B87F5]/[0.06] text-[#9B87F5] hover:bg-[#9B87F5]/12"
          }`}
        >
          <Sparkle size={13} weight="fill" />
          <span className="hidden sm:inline">Parler à Flore</span>
        </button>

        {/* Notifications */}
        <div className="relative" ref={refPanneau}>
          <button
            onClick={() => setPanneau(!panneau)}
            data-testid="notif-btn"
            title="Notifications"
            className={`relative flex h-8 w-8 items-center justify-center rounded-md border transition-colors ${panneau ? "border-[#F2B84B]/50 bg-[rgba(242,184,75,0.10)] text-[#F2B84B]" : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:text-[#F2F6F8]"}`}
          >
            <Bell size={14} />
            {nonLues > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#F87171] px-1 font-code text-[9px] font-bold text-[#071019]" data-testid="notif-badge">
                {nonLues}
              </span>
            )}
          </button>
          {panneau && (
            <div className="glass absolute right-0 top-10 z-50 w-96 max-w-[90vw] rounded-xl p-2" data-testid="notif-panel">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Notifications</span>
                {nonLues > 0 && (
                  <button
                    onClick={async () => { await api.post("/notifications/tout-lire").catch(() => {}); chargerNotifs(); }}
                    data-testid="notif-tout-lire"
                    className="font-code text-[10px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
                  >
                    Tout marquer lu
                  </button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifs.map((n) => (
                  <button key={n.id} onClick={() => ouvrirNotif(n)} data-testid={`notif-item-${n.id}`}
                    className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-[rgba(148,163,184,0.10)] ${n.lu ? "opacity-45" : ""}`}>
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: TYPES_NOTIF[n.type] || "#7C93A8" }} />
                    <span className="min-w-0">
                      <span className="block text-xs leading-snug text-[#D8E2EA]">{n.texte}</span>
                      <span className="mt-0.5 block font-code text-[9px] text-[#7C93A8]">{new Date(n.quand).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                    </span>
                  </button>
                ))}
                {notifs.length === 0 && <p className="px-2 py-4 text-center text-xs text-[#7C93A8]">Aucune notification.</p>}
              </div>
            </div>
          )}
        </div>

        {/* Identité */}
        <div className="hidden items-center gap-1.5 border-l border-[rgba(148,163,184,0.16)] pl-2.5 lg:flex">
          <Users size={14} className="text-[#7C93A8]" />
          <select
            value={persona}
            onChange={(e) => changerPersona(e.target.value)}
            data-testid="selecteur-persona"
            title="Profil actif"
            className="h-8 w-24 min-w-0 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none lg:w-40"
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
