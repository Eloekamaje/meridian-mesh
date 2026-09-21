import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CaretLeft, CaretRight, Sparkle, Compass, ArrowRight, CalendarBlank, DotsThree, ArrowSquareOut, ArrowsLeftRight, EyeSlash } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";
import { fmtDateLongue, fmtDateInput, finDeJournee, fmtDate } from "@/lib/temps";
import CarteInitiative from "@/components/CarteInitiative";
import ComposerFlore from "@/components/ComposerFlore";
import { delaiMin } from "@/components/FloreActivite";
import { toast } from "sonner";

const VUES_ACTUS = [
  ["brief", "Brief"],
  ["radar", "Radar"],
  ["a_traiter", "À traiter"],
  ["suivis", "Suivis"],
];

export const GENRES = {
  relation: ["Découverte", "#60A5FA"],
  contradiction: ["Contradiction", "#F87171"],
  connaissance: ["Connaissance", "#58A6FF"],
  changement: ["Transformation", "#F2B84B"],
  incident: ["Incident", "#F87171"],
  comportement: ["Comportement", "#60A5FA"],
  phenomene: ["Phénomène possible", "#60A5FA"],
  travail: ["Travail", "#60A5FA"],
  decision: ["Décision", "#60A5FA"],
  gouvernance: ["Gouvernance", "#7C93A8"],
  veille: ["Décision en veille", "#F2B84B"],
  verification: ["Vérification en cours", "#60A5FA"],
  opportunite: ["Opportunité", "#34D399"],
};

const RAISONS_ECART = [
  ["connu", "Déjà connu"],
  ["pas_pour_moi", "Ne me concerne pas"],
  ["trop_tot", "Trop tôt"],
  ["traite", "Traité ailleurs"],
];

const PORTEES = [
  ["personnel", "Personnel"],
  ["espace", "Mon espace"],
  ["global", "Mesh global"],
];

const PRESETS = [
  ["aujourdhui", "Aujourd'hui"],
  ["hier", "Hier"],
  ["avant-hier", "Il y a 2 jours"],
  ["7j", "7 derniers jours"],
  ["30j", "30 derniers jours"],
];

// L'heure quand le fait date d'aujourd'hui, sinon le jour : une heure sans jour trompe (un fait d'hier soir n'est pas « à 20:00 » aujourd'hui)
const heure = (iso) => {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
};

function CarteHistoire({ h, vedette, dateCible, estAujourdhui, navigate, mesh, onEcarter }) {
  const [menu, setMenu] = useState(false);
  const [ecart, setEcart] = useState(false);
  const [ouverture, setOuverture] = useState(false);
  const g = GENRES[h.genre] || [h.genre, "#7C93A8"];
  // Les histoires de relation/transformation s'ouvrent en Avant/Après à la date du phénomène
  const jourPhenomene = fmtDateInput(finDeJournee(h.quand));
  const sep = h.liens?.atlas?.includes("?") ? "&" : "?";
  const lienAtlas = h.liens?.atlas
    ? ["relation", "phenomene", "changement"].includes(h.genre)
      ? `${h.liens.atlas}${sep}avant-apres=${jourPhenomene}`
      : estAujourdhui
        ? h.liens.atlas
        : `${h.liens.atlas}${sep}date=${fmtDateInput(finDeJournee(dateCible))}`
    : null;

  // Une actualité qu'on ouvre devient un TRAVAIL : Flore y présente la situation, la garde sous vérification ou pose la question d'une
  // investigation selon l'intention. On y arrive avec le retour vers Actualités mis en évidence.
  const ouvrirTravail = async (intention) => {
    if (ouverture) return;
    setOuverture(true);
    try {
      const { data } = await delaiMin(api.post(`/actualites/histoire/${h.id}/travail`, { intention }), 1300);
      navigate(`/travaux/${data.id}`, { state: { retour: { label: "Actualités", to: "/actualites" } } });
    } catch {
      toast.error("Impossible d'ouvrir cette actualité");
      setOuverture(false);
    }
  };

  const [pourEquipe, setPourEquipe] = useState(false);
  const ecarter = async (raison) => {
    setMenu(false);
    setEcart(false);
    try {
      await api.post(`/actualites/histoire/${h.id}/ecarter`, { raison, portee: pourEquipe ? "equipe" : "moi" });
      onEcarter?.(h, raison);
    } catch {
      toast.error("Impossible d'écarter cette actualité");
    }
  };

  const actionPrincipale = () => {
    if (h.genre === "travail" || h.genre === "decision" || h.genre === "veille" || h.genre === "verification") {
      return (
        <button onClick={() => navigate(h.liens.travail)} data-testid={`histoire-reprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
          {h.action_label || "Reprendre"} <ArrowRight size={11} />
        </button>
      );
    }
    if (h.incertain) {
      return (
        <button onClick={() => ouvrirTravail("suivre")} disabled={ouverture} data-testid={`histoire-suivre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#60A5FA]">
          {ouverture ? "Flore prépare sa lecture…" : "Suivre la vérification"}
        </button>
      );
    }
    return (
      <button onClick={() => ouvrirTravail("comprendre")} disabled={ouverture} data-testid={`histoire-comprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
        <Sparkle size={11} weight="fill" /> {ouverture ? "Flore prépare sa lecture…" : h.action_label || "Comprendre"}
      </button>
    );
  };

  return (
    <article
      className={`rise rounded-xl border bg-[#0F1D28] p-5 transition-colors ${vedette ? "border-[#60A5FA]/25 shadow-sm" : h.attention === "critique" ? "border-[#F2B84B]/30" : "border-[rgba(148,163,184,0.16)] hover:border-[#41576D]"}`}
      data-testid={`histoire-${h.id}`}
    >
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.2em]">
        <span className={`h-1.5 ${h.incertain ? "w-2.5 rounded-sm border border-dashed" : "w-1.5 rounded-full"}`} style={{ backgroundColor: h.incertain ? "transparent" : g[1], borderColor: g[1] }} />
        <span style={{ color: g[1] }}>{vedette ? `${g[0]} principale` : g[0]}</span>
        <span className="text-[#7C93A8]">· {heure(h.quand)}</span>
        {h.attention === "critique" && <span className="rounded border border-[#F2B84B]/40 px-1 py-0.5 text-[#F2B84B]" data-testid={`histoire-critique-${h.id}`}>à traiter d'abord</span>}
        {h.restreinte && <span className="rounded border border-[#F2B84B]/40 px-1 py-0.5 text-[#F2B84B]">périmètre partiel</span>}
      </div>
      <h3 className={`mt-2 font-semibold leading-snug text-[#F2F6F8] ${vedette ? "font-display text-lg" : "text-sm"}`}>{h.titre}</h3>
      {h.recit && <p className={`mt-1.5 leading-relaxed text-[#94A3B8] ${vedette ? "text-sm" : "text-xs"}`}>{h.recit}</p>}
      {h.pourquoi_maintenant && (
        <p className="mt-2 text-xs text-[#DCE6EE]" data-testid={`histoire-pourquoi-${h.id}`}>
          <span className="mr-1.5 font-code text-[10px] uppercase tracking-[0.16em] text-[#F2B84B]">Pourquoi maintenant</span>{h.pourquoi_maintenant}
        </p>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {(h.jumeaux || []).slice(0, 5).map((jid) => {
          const j = mesh?.jumeaux.find((x) => x.id === jid);
          const c = couleurDomaine(j?.domaine);
          return (
            <span key={jid} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>
              {j?.nom || jid}
            </span>
          );
        })}
        {h.confiance && <span className="ml-auto font-code text-[9px] text-[#7C93A8]">Confiance : {h.confiance}</span>}
      </div>

      <div className="mt-3 flex items-center gap-2 border-t border-[rgba(148,163,184,0.10)] pt-3">
        {actionPrincipale()}
        <div className="relative">
          <button onClick={() => { setMenu((m) => !m); setEcart(false); }} data-testid={`histoire-menu-${h.id}`} title="Autres actions" className="flex h-7 w-7 items-center justify-center rounded-md border border-[rgba(148,163,184,0.16)] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
            <DotsThree size={15} weight="bold" />
          </button>
          {menu && (
            <div className="glass absolute left-0 top-8 z-30 w-52 rounded-xl p-1.5" data-testid={`histoire-menu-panel-${h.id}`}>
              {lienAtlas && (
                <button onClick={() => navigate(lienAtlas)} data-testid={`histoire-atlas-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <Compass size={12} /> Voir dans l'Atlas
                </button>
              )}
              {h.liens?.travail && (
                <button onClick={() => navigate(h.liens.travail)} data-testid={`histoire-travail-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <ArrowSquareOut size={12} /> Ouvrir le travail
                </button>
              )}
              {h.liens?.investigation && (
                <button onClick={() => { setMenu(false); ouvrirTravail("investiguer"); }} data-testid={`histoire-investigation-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <ArrowRight size={12} /> Approfondir
                </button>
              )}
              {!ecart ? (
                <button onClick={() => setEcart(true)} data-testid={`histoire-ecarter-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <EyeSlash size={12} /> Écarter…
                </button>
              ) : (
                <div className="mt-1 border-t border-[rgba(148,163,184,0.12)] pt-1" data-testid={`histoire-raisons-${h.id}`}>
                  <div className="flex gap-1 px-1.5 pb-1.5" role="group" aria-label="Pour qui">
                    {[[false, "Pour moi"], [true, "Pour l'équipe"]].map(([v, l]) => (
                      <button key={l} onClick={() => setPourEquipe(v)} aria-pressed={pourEquipe === v} data-testid={`ecarter-portee-${v ? "equipe" : "moi"}-${h.id}`}
                        className={`flex-1 rounded-md px-2 py-1 text-[11px] ${pourEquipe === v ? "bg-[#60A5FA] font-semibold text-[#071019]" : "border border-[rgba(148,163,184,0.2)] text-[#94A3B8]"}`}>{l}</button>
                    ))}
                  </div>
                  <div className="px-2.5 py-1 font-code text-[10px] uppercase tracking-[0.14em] text-[#7C93A8]">Pourquoi l'écarter ?</div>
                  {RAISONS_ECART.map(([id, label]) => (
                    <button key={id} onClick={() => ecarter(id)} data-testid={`ecarter-${id}-${h.id}`} className="flex w-full items-center rounded px-2.5 py-1.5 text-left text-[11px] text-[#D8E2EA] hover:bg-[rgba(148,163,184,0.10)]">
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

// Une section du « reste » : au plus six cartes d'abord, le journal peut compter des dizaines de lignes
function SectionReste({ s, ...carte }) {
  const [tout, setTout] = useState(false);
  const visibles = tout ? s.histoires : s.histoires.slice(0, 6);
  return (
    <section data-testid={`reste-${s.id}`}>
      <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">{s.titre}</h2>
      <div className="mt-3 space-y-4">
        {visibles.map((h) => <CarteHistoire key={h.id} h={h} {...carte} />)}
      </div>
      {s.histoires.length > 6 && !tout && (
        <button onClick={() => setTout(true)} className="mt-3 text-xs font-medium text-[#60A5FA] hover:text-[#93C5FD]">Afficher {s.histoires.length - 6} de plus</button>
      )}
    </section>
  );
}

export default function Actualites() {
  const navigate = useNavigate();
  const { version, persona } = usePerimetre();
  const { mesh } = useMesh();
  const { ouvrirFlore } = useContexte();
  const [decalage, setDecalage] = useState(0);
  const [jours, setJours] = useState(1);
  const [portee, setPortee] = useState("personnel");
  const [data, setData] = useState(null);
  const [nouvelles, setNouvelles] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  // La vue est pilotée par l'URL (source unique de vérité — la pillule « À traiter » doit toujours basculer)
  const vueParam = searchParams.get("vue");
  const vue = ["brief", "radar", "a_traiter", "suivis"].includes(vueParam) ? vueParam : "brief";
  const setVue = (v) => setSearchParams(v === "brief" ? {} : { vue: v }, { replace: true });
  const [initiatives, setInitiatives] = useState(null);
  const [compteurs, setCompteurs] = useState(null);
  const [delegations, setDelegations] = useState([]);
  const [calendrier, setCalendrier] = useState(false);
  const [resteOuvert, setResteOuvert] = useState(false);
  const [ecarteesOuvert, setEcarteesOuvert] = useState(false);
  const refCalendrier = useRef(null);

  useEffect(() => {
    const fermer = (e) => {
      if (refCalendrier.current && !refCalendrier.current.contains(e.target)) setCalendrier(false);
    };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  const dateCible = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - decalage);
    return d;
  }, [decalage]);
  const estAujourdhui = decalage === 0 && jours === 1;

  const charger = useCallback(() => {
    const p = new URLSearchParams({ date: fmtDateInput(dateCible), jours: String(jours), portee });
    return api.get(`/actualites?${p}`).then((r) => setData(r.data)).catch(() => {});
  }, [dateCible, jours, portee]);

  useEffect(() => {
    setNouvelles(0);
    charger();
  }, [charger, version, persona]);

  const chargerCompteurs = useCallback(
    () => api.get("/initiatives/compteurs").then((r) => setCompteurs(r.data)).catch(() => {}),
    []
  );
  useEffect(() => {
    chargerCompteurs();
    const t = setInterval(chargerCompteurs, 20000);
    return () => clearInterval(t);
  }, [chargerCompteurs, version, persona]);

  useEffect(() => {
    if (vue === "brief") return;
    const v = vue === "a_traiter" ? "a_traiter" : vue;
    api.get(`/initiatives?vue=${v}`).then((r) => setInitiatives(r.data)).catch(() => {});
    if (vue === "suivis") api.get("/delegations").then((r) => setDelegations(r.data)).catch(() => {});
  }, [vue, version, persona]);

  const initiativeRepondue = (maj) => {
    setInitiatives((liste) => (liste || []).map((i) => (i.id === maj.id ? maj : i)).filter((i) => vue === "suivis" || i.vue === vue || i.statut === "en_attente" ? true : i.vue === vue));
    chargerCompteurs();
    if (vue !== "brief") {
      const v = vue === "a_traiter" ? "a_traiter" : vue;
      api.get(`/initiatives?vue=${v}`).then((r) => setInitiatives(r.data)).catch(() => {});
    }
  };

  // Temps réel calme : les nouvelles actualités attendent un geste de l'utilisateur
  useEffect(() => {
    if (!estAujourdhui) return undefined;
    const t = setInterval(() => {
      const p = new URLSearchParams({ date: fmtDateInput(dateCible), jours: "1", portee });
      api.get(`/actualites?${p}`).then((r) => {
        setData((cur) => {
          if (!cur) return cur;
          const connus = new Set(cur.histoires.map((h) => h.id));
          setNouvelles((n) => n + r.data.histoires.filter((h) => !connus.has(h.id)).length);
          return cur;
        });
      }).catch(() => {});
    }, 15000);
    return () => clearInterval(t);
  }, [estAujourdhui, dateCible, portee]);

  const retablir = async (id) => {
    try {
      await api.delete(`/actualites/histoire/${id}/ecarter`);
      charger();
    } catch {
      toast.error("Impossible de rétablir cette actualité");
    }
  };
  const apresEcart = (h, raison) => {
    charger();
    toast(`« ${h.titre.length > 48 ? `${h.titre.slice(0, 48)}…` : h.titre} » écartée`, { description: RAISONS_ECART.find(([id]) => id === raison)?.[1], action: { label: "Annuler", onClick: () => retablir(h.id) } });
  };

  const appliquerPreset = (v) => {
    if (v === "aujourdhui") { setDecalage(0); setJours(1); }
    else if (v === "hier") { setDecalage(1); setJours(1); }
    else if (v === "avant-hier") { setDecalage(2); setJours(1); }
    else if (v === "7j") { setDecalage(0); setJours(7); }
    else if (v === "30j") { setDecalage(0); setJours(30); }
  };

  const presetActif =
    decalage === 0 && jours === 1 ? "aujourdhui"
    : decalage === 1 && jours === 1 ? "hier"
    : decalage === 2 && jours === 1 ? "avant-hier"
    : decalage === 0 && jours === 7 ? "7j"
    : decalage === 0 && jours === 30 ? "30j" : "";

  const titreCourt = useMemo(() => {
    const court = dateCible.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
    if (jours > 1) {
      const debut = new Date(dateCible);
      debut.setDate(debut.getDate() - jours + 1);
      return `Du ${debut.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} au ${court}`;
    }
    if (decalage === 0) return `Aujourd'hui · ${court}`;
    if (decalage === 1) return `Hier · ${court}`;
    return court;
  }, [decalage, jours, dateCible]);

  const histoires = data?.histoires || [];
  const sections = data?.sections || [];
  const vedetteId = sections.find((s) => s.id === "essentiel")?.histoires[0]?.id || histoires[0]?.id;
  const lienAtlasJournee = `/atlas?date=${fmtDateInput(finDeJournee(dateCible))}`;

  return (
    <div className="h-full overflow-y-auto px-4 py-5 pb-20 sm:px-8 sm:py-8" data-testid="actualites-page">
      <div className="mx-auto max-w-4xl">
        {/* Barre de lecture unique : vues · portées · temps */}
        <header className="rise relative z-30" ref={refCalendrier}>
          <h1 className="sr-only">Actualités</h1>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-0.5 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-0.5" data-testid="vues-actualites">
              {VUES_ACTUS.map(([id, label]) => {
                const n = id === "brief" ? null : compteurs?.[id === "a_traiter" ? "a_traiter" : id];
                return (
                  <button
                    key={id}
                    onClick={() => setVue(id)}
                    data-testid={`vue-${id}`}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      vue === id ? "bg-[#60A5FA] font-semibold text-[#071019]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
                    }`}
                  >
                    {id === "brief" ? (estAujourdhui ? "Aujourd'hui" : "Période") : label}
                    {n > 0 && (
                      <span className={`rounded-full px-1.5 font-code text-[9px] ${vue === id ? "bg-[#071019]/30 text-[#F2F6F8]" : id === "a_traiter" ? "bg-[#F2B84B] text-[#071019]" : "bg-[rgba(148,163,184,0.10)] text-[#94A3B8]"}`} data-testid={`vue-${id}-badge`}>
                        {n}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex gap-0.5 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-0.5" data-testid="portees" title="Portée — vue limitée à vos autorisations">
                {PORTEES.map(([id, label]) => (
                  <button key={id} onClick={() => setPortee(id)} data-testid={`portee-${id}`}
                    className={`rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors ${portee === id ? "bg-[#F2F6F8] text-[#071019]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"}`}>
                    {label === "Mon espace" ? "Espace" : label === "Mesh global" ? "Global" : label}
                  </button>
                ))}
              </div>
              <div className="relative flex items-center gap-0.5 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-0.5" data-testid="nav-temps">
                <button onClick={() => setDecalage((d) => d + 1)} data-testid="date-prec-btn" title="Période précédente" className="flex h-7 w-7 items-center justify-center rounded-md text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <CaretLeft size={13} />
                </button>
                <button onClick={() => setCalendrier((c) => !c)} data-testid="actualites-titre" title="Choisir la période" className="rounded-md px-2 py-1 text-xs font-semibold text-[#F2F6F8] transition-colors hover:bg-[rgba(148,163,184,0.10)]">
                  <span className="sm:hidden">{String(titreCourt).split(" · ")[0]}</span>
                  <span className="hidden sm:inline">{titreCourt}</span>
                </button>
                <button onClick={() => setDecalage((d) => Math.max(0, d - 1))} disabled={decalage === 0} data-testid="date-suiv-btn" title="Période suivante" className="flex h-7 w-7 items-center justify-center rounded-md text-[#94A3B8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8] disabled:opacity-30">
                  <CaretRight size={13} />
                </button>
                {calendrier && (
                  <div className="glass absolute right-0 top-10 z-40 w-56 rounded-xl p-2" data-testid="calendrier-popover">
                    <div className="space-y-0.5">
                      {PRESETS.map(([v, l]) => (
                        <button key={v} onClick={() => { appliquerPreset(v); setCalendrier(false); }} data-testid={`preset-${v}`}
                          className={`w-full rounded-md px-2.5 py-1.5 text-left text-xs transition-colors ${presetActif === v ? "bg-[rgba(96,165,250,0.12)] font-semibold text-[#BFDBFE]" : "text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"}`}>
                          {l}
                        </button>
                      ))}
                    </div>
                    <select value={presetActif} onChange={(e) => { if (e.target.value) { appliquerPreset(e.target.value); setCalendrier(false); } }} data-testid="date-preset-select" className="mt-2 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none">
                      <option value="" label="Période…" />
                      {PRESETS.map(([v, l]) => <option key={v} value={v} label={l} />)}
                    </select>
                    <label className="mt-2 flex items-center gap-1.5 text-[11px] text-[#7C93A8]">
                      <CalendarBlank size={13} />
                      <input type="date" value={fmtDateInput(dateCible)} max={fmtDateInput(new Date())}
                        onChange={(e) => {
                          if (!e.target.value) return;
                          const d = new Date(`${e.target.value}T12:00:00`);
                          setDecalage(Math.max(0, Math.round((new Date().setHours(12, 0, 0, 0) - d.getTime()) / 86400000)));
                          setJours(1);
                          setCalendrier(false);
                        }}
                        data-testid="date-input" className="h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none" />
                    </label>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="font-code text-[10px] text-[#7C93A8]" data-testid="portee-note">
              Vue limitée à vos autorisations{data?.espace_label ? ` · ${data.espace_label}` : ""}
            </span>
            {data?.note_portee && <span className="font-code text-[10px] text-[#F2B84B]" data-testid="portee-avertissement">{data.note_portee}</span>}
          </div>
        </header>

        {vue !== "brief" && (
          <div className="mt-6 space-y-4" data-testid={`panneau-${vue}`}>
            {initiatives === null && <p className="py-10 text-center font-code text-[11px] text-[#7C93A8]">Le Mesh prépare ses propositions…</p>}
            {(initiatives || []).map((init) => (
              <CarteInitiative key={init.id} init={init} mesh={mesh} onChange={initiativeRepondue} />
            ))}
            {initiatives && initiatives.length === 0 && (
              <div className="rounded-xl border border-dashed border-[#41576D] bg-[#0F1D28] p-8 text-center" data-testid={`${vue}-vide`}>
                <p className="text-sm text-[#94A3B8]">
                  {vue === "a_traiter" ? "Rien n'attend votre décision — le Mesh vous sollicite seulement quand c'est nécessaire."
                    : vue === "radar" ? "Aucune situation candidate — le Mesh ne détecte rien d'inhabituel dans votre périmètre."
                    : "Aucun phénomène suivi pour le moment."}
                </p>
              </div>
            )}
            {vue === "suivis" && delegations.length > 0 && (
              <div className="space-y-3" data-testid="delegations-liste">
                <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">Délégations actives</h2>
                {delegations.map((d) => (
                  <div key={d.id} className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4" data-testid={`delegation-${d.id}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-[#F2F6F8]">{d.tache}</span>
                      <span className={`rounded-full border px-2 py-0.5 font-code text-[9px] ${d.statut === "active" ? "border-[#34D399]/30 bg-[rgba(52,211,153,0.12)] text-[#34D399]" : "border-[rgba(148,163,184,0.25)] text-[#94A3B8]"}`}>{d.statut === "active" ? "active" : d.statut === "terminee" ? "terminée" : d.statut}</span>
                    </div>
                    <div className="mt-2 grid gap-1.5 font-code text-[10px] text-[#94A3B8] sm:grid-cols-2">
                      <span>Périmètre : {(d.jumeaux || []).map((jid) => mesh?.jumeaux.find((x) => x.id === jid)?.nom || jid).join(", ")}</span>
                      <span>Durée : {d.duree} · jusqu'au {new Date(d.jusqu_a).toLocaleString("fr-FR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</span>
                      <span>Sources : {d.sources}</span>
                      <span>Produira : {d.livrable}</span>
                    </div>
                    <p className="mt-2 border-l-2 border-[#F2B84B]/40 pl-2.5 text-[11px] italic text-[#F2B84B]">{d.validation_requise}</p>
                    {d.travail_id && (
                      <button onClick={() => navigate(`/travaux/${d.travail_id}`, { state: { retour: { label: "Actualités", to: "/actualites?vue=suivis" } } })} data-testid={`delegation-travail-${d.id}`}
                        className="mt-3 flex items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.2)] px-3 py-1.5 text-[11px] font-medium text-[#D8E2EA] transition-colors hover:border-[#60A5FA]/50 hover:text-white">
                        <ArrowSquareOut size={12} /> Ouvrir le travail
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {vue === "brief" && (<>

        {/* Consultation historique : le direct est suspendu visuellement */}
        {!estAujourdhui && (
          <div className="mt-5 flex items-center justify-between rounded-xl border border-[#F2B84B]/30 bg-[rgba(242,184,75,0.10)] px-4 py-2.5" data-testid="banniere-historique">
            <span className="text-xs text-[#F2B84B]">
              Vous consultez {jours > 1 ? "une période passée" : `le ${dateCible.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`} — le direct est suspendu.
            </span>
            <button onClick={() => appliquerPreset("aujourdhui")} data-testid="retour-aujourdhui-btn" className="rounded-md border border-[#F2B84B]/40 px-2.5 py-1 text-[11px] font-semibold text-[#F2B84B] transition-colors hover:bg-[#F2B84B]/10">
              Revenir à aujourd'hui
            </button>
          </div>
        )}
        {estAujourdhui && nouvelles > 0 && (
          <button onClick={() => { charger(); setNouvelles(0); }} data-testid="nouvelles-actus-btn" className="rise mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-[#34D399]/30 bg-[rgba(52,211,153,0.12)] px-4 py-2.5 text-xs font-semibold text-[#34D399] transition-colors hover:bg-[rgba(52,211,153,0.22)]">
            <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#34D399]" />
            Mesh vivant — {nouvelles} nouvelle{nouvelles > 1 ? "s" : ""} actualité{nouvelles > 1 ? "s" : ""}
          </button>
        )}

        {/* Le briefing de Flore — rédigé, adapté au rôle */}
        {data?.briefing && (
          <section className="rise mt-7" data-testid="briefing-flore">
            <h2 className="font-display text-xl font-bold text-[#F2F6F8]">{data.briefing.salutation}</h2>
            <div className="mt-1 flex items-center gap-2">
              <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#60A5FA]">{data.briefing.titre}</span>
              <span className="rounded-full border border-[rgba(148,163,184,0.16)] px-2 py-0.5 font-code text-[9px] text-[#7C93A8]">{data.briefing.lecture}</span>
            </div>
            <p className="mt-2.5 text-sm font-medium leading-relaxed text-[#F2F6F8]">{data.briefing.accroche || data.briefing.texte}</p>
            {data.briefing.detail && <p className="mt-1 text-xs italic text-[#7C93A8]">{data.briefing.detail}</p>}
            {data.briefing.points.length > 0 && (
              <ul className="mt-2 space-y-1">
                {data.briefing.points.map((p, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#94A3B8]" data-testid={`briefing-point-${i}`}>
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#60A5FA]" />{p}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-3.5 flex flex-wrap gap-2">
              <button
                onClick={() => { window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: `Résume-moi ${jours > 1 ? "cette période" : "cette journée"} dans le Mesh.` })); ouvrirFlore(); }}
                data-testid="briefing-explorer-btn"
                className="flex items-center gap-1.5 rounded-full bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]"
              >
                <Sparkle size={12} weight="fill" /> Explorer {jours > 1 ? "la période" : "la journée"} avec Flore
              </button>
              <button onClick={() => navigate(lienAtlasJournee)} data-testid="voir-journee-atlas-btn" className="flex items-center gap-1.5 rounded-full border border-[#60A5FA]/30 bg-[#60A5FA]/[0.06] px-4 py-2 text-xs font-semibold text-[#60A5FA] transition-colors hover:bg-[#60A5FA]/15">
                <Compass size={12} /> Voir {jours > 1 ? "la période" : "la journée"} dans l'Atlas
              </button>
            </div>
          </section>
        )}

        {/* Synthèse de période : pas sept feeds collés */}
        {data?.synthese && (
          <section className="rise mt-7 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5" data-testid="synthese-periode">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Synthèse de la période</div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[["relations", "nouvelles relations"], ["transformations", "transformations"], ["decisions", "décisions prises"], ["surveillance", "points à surveiller"]].map(([k, l]) => (
                <div key={k}>
                  <div className="font-display text-2xl font-black text-[#F2F6F8]" data-testid={`synthese-${k}`}>{data.synthese[k]}</div>
                  <div className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">{l}</div>
                </div>
              ))}
            </div>
            {data.synthese.tendance && (
              <p className="mt-3 border-l-2 border-[#60A5FA]/30 pl-3 text-xs italic text-[#D8E2EA]" data-testid="synthese-tendance">
                <span className="font-code text-[9px] not-italic uppercase tracking-wider text-[#60A5FA]">Tendance principale — </span>{data.synthese.tendance}
              </p>
            )}
            <div className="mt-4 flex gap-2">
              <button onClick={() => navigate(`/atlas?avant-apres=${data.synthese.debut}`)} data-testid="comparer-atlas-btn" className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
                <ArrowsLeftRight size={12} /> Comparer le {fmtDate(data.synthese.debut)} et le {fmtDate(data.synthese.fin)}
              </button>
            </div>
          </section>
        )}

        {/* Feed organisé par signification */}
        <div className="mt-8 space-y-8" data-testid="feed-actualites">
          {sections.map((s) => (
            <section key={s.id} data-testid={`section-${s.id}`}>
              {!(s.id === "essentiel" && data?.briefing) && <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">{s.titre}</h2>}
              <div className={`${s.id === "essentiel" && data?.briefing ? "mt-0" : "mt-3"} space-y-4`}>
                {s.histoires.map((h) => (
                  <CarteHistoire key={h.id} h={h} vedette={h.id === vedetteId} dateCible={dateCible} estAujourdhui={estAujourdhui} navigate={navigate} mesh={mesh} onEcarter={apresEcart} />
                ))}
              </div>
            </section>
          ))}

          {/* Budget d'attention : le reste existe, mais n'est pas sur le chemin de la personne */}
          {data?.budget && data.budget.reste > 0 && (
            <section data-testid="actualites-reste">
              <button onClick={() => setResteOuvert((o) => !o)} aria-expanded={resteOuvert} data-testid="reste-toggle"
                className="flex w-full items-center justify-between gap-3 rounded-xl border border-dashed border-[rgba(148,163,184,0.25)] px-4 py-3 text-left text-xs text-[#94A3B8] transition-colors hover:border-[#41576D] hover:text-[#F2F6F8]">
                <span>
                  <span className="font-semibold text-[#D8E2EA]">Le reste — {data.budget.reste} autre{data.budget.reste > 1 ? "s" : ""}</span>
                  <span className="ml-2 text-[#7C93A8]">rien d'urgent : découvertes, surveillance, journal de l'espace</span>
                </span>
                <CaretRight size={13} className={`shrink-0 transition-transform ${resteOuvert ? "rotate-90" : ""}`} />
              </button>
              {resteOuvert && (
                <div className="mt-6 space-y-8" data-testid="reste-contenu">
                  {(data.reste || []).map((s) => <SectionReste key={s.id} s={s} dateCible={dateCible} estAujourdhui={estAujourdhui} navigate={navigate} mesh={mesh} onEcarter={apresEcart} />)}
                </div>
              )}
            </section>
          )}

          {data?.ecartees?.length > 0 && (
            <section data-testid="actualites-ecartees">
              <button onClick={() => setEcarteesOuvert((o) => !o)} aria-expanded={ecarteesOuvert} data-testid="ecartees-toggle" className="flex items-center gap-1.5 font-code text-[11px] text-[#7C93A8] hover:text-[#D8E2EA]">
                <EyeSlash size={12} /> {data.ecartees.length} actualité{data.ecartees.length > 1 ? "s" : ""} écartée{data.ecartees.length > 1 ? "s" : ""}
              </button>
              {ecarteesOuvert && (
                <ul className="mt-2 space-y-1.5">
                  {data.ecartees.map((e) => (
                    <li key={e.id} className="flex items-center justify-between gap-3 rounded-lg border border-[rgba(148,163,184,0.12)] px-3 py-2 text-xs text-[#94A3B8]">
                      <span className="min-w-0 truncate">{e.titre} <span className="text-[#7C93A8]">· {e.raison}{e.portee === "equipe" ? " · pour l'équipe" : ""}</span></span>
                      <button onClick={() => retablir(e.id)} data-testid={`retablir-${e.id}`} className="shrink-0 font-medium text-[#60A5FA] hover:text-[#93C5FD]">Rétablir</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {data && histoires.length === 0 && (
            <div className="rounded-xl border border-dashed border-[#41576D] bg-[#0F1D28] p-10 text-center" data-testid="feed-vide">
              <p className="font-display text-base font-bold text-[#F2F6F8]">Rien d'important ne nécessite votre attention.</p>
              <p className="mt-2 text-xs leading-relaxed text-[#94A3B8]">
                Le Mesh reste actif : {data.mesh?.jumeaux_actifs ?? "—"} jumeaux actualisés dans votre périmètre, aucune transformation significative sur la période.
              </p>
              <button onClick={() => navigate("/atlas")} data-testid="explorer-mesh-btn" className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
                <Compass size={12} /> Explorer le Mesh
              </button>
            </div>
          )}
          {!data && <p className="py-10 text-center font-code text-[11px] text-[#7C93A8]" data-testid="feed-chargement">Flore prépare votre briefing…</p>}
        </div>

        {/* Composer compact — contextualisé au fil d'actualités */}
        <div className="mt-8" data-testid="actualites-composer-zone">
          <ComposerFlore compact placeholder="Interrogez ce fil d'actualités…" testidPrefix="actualites-composer" />
        </div>
        </>)}
      </div>
    </div>
  );
}
