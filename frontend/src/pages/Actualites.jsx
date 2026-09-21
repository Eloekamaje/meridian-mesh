import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CaretLeft, CaretRight, Sparkle, Compass, ArrowRight, CalendarBlank, DotsThree, ArrowSquareOut, ArrowsLeftRight } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";
import { fmtDateLongue, fmtDateInput, finDeJournee, fmtDate } from "@/lib/temps";
import CarteInitiative from "@/components/CarteInitiative";
import ComposerFlore from "@/components/ComposerFlore";

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
};

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

const heure = (iso) => new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function CarteHistoire({ h, vedette, dateCible, estAujourdhui, navigate, mesh }) {
  const [menu, setMenu] = useState(false);
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

  const actionPrincipale = () => {
    if (h.genre === "travail" || h.genre === "decision") {
      return (
        <button onClick={() => navigate(h.liens.travail)} data-testid={`histoire-reprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
          Reprendre <ArrowRight size={11} />
        </button>
      );
    }
    if (h.incertain) {
      return (
        <button onClick={() => navigate(`/actualites/comprendre/${h.id}`)} data-testid={`histoire-suivre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#60A5FA]">
          Suivre la vérification
        </button>
      );
    }
    return (
      <button onClick={() => navigate(`/actualites/comprendre/${h.id}`)} data-testid={`histoire-comprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]">
        <Sparkle size={11} weight="fill" /> Comprendre
      </button>
    );
  };

  return (
    <article
      className={`rise rounded-xl border bg-[#0F1D28] p-5 transition-colors ${vedette ? "border-[#60A5FA]/25 shadow-sm" : "border-[rgba(148,163,184,0.16)] hover:border-[#41576D]"}`}
      data-testid={`histoire-${h.id}`}
    >
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.2em]">
        <span className={`h-1.5 ${h.incertain ? "w-2.5 rounded-sm border border-dashed" : "w-1.5 rounded-full"}`} style={{ backgroundColor: h.incertain ? "transparent" : g[1], borderColor: g[1] }} />
        <span style={{ color: g[1] }}>{vedette ? `${g[0]} principale` : g[0]}</span>
        <span className="text-[#7C93A8]">· {heure(h.quand)}</span>
        {h.restreinte && <span className="rounded border border-[#F2B84B]/40 px-1 py-0.5 text-[#F2B84B]">périmètre partiel</span>}
      </div>
      <h3 className={`mt-2 font-semibold leading-snug text-[#F2F6F8] ${vedette ? "font-display text-lg" : "text-sm"}`}>{h.titre}</h3>
      {h.recit && <p className={`mt-1.5 leading-relaxed text-[#94A3B8] ${vedette ? "text-sm" : "text-xs"}`}>{h.recit}</p>}

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
          <button onClick={() => setMenu((m) => !m)} data-testid={`histoire-menu-${h.id}`} title="Autres actions" className="flex h-7 w-7 items-center justify-center rounded-md border border-[rgba(148,163,184,0.16)] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">
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
                <button onClick={() => navigate(h.liens.investigation)} data-testid={`histoire-investigation-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#94A3B8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                  <ArrowRight size={12} /> Approfondir
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
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
                    {label}
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
                  {titreCourt}
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
                      <span className="rounded-full border border-[#34D399]/30 bg-[rgba(52,211,153,0.12)] px-2 py-0.5 font-code text-[9px] text-[#34D399]">{d.statut === "active" ? "active" : d.statut}</span>
                    </div>
                    <div className="mt-2 grid gap-1.5 font-code text-[10px] text-[#94A3B8] sm:grid-cols-2">
                      <span>Périmètre : {(d.jumeaux || []).map((jid) => mesh?.jumeaux.find((x) => x.id === jid)?.nom || jid).join(", ")}</span>
                      <span>Durée : {d.duree} · jusqu'au {new Date(d.jusqu_a).toLocaleString("fr-FR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</span>
                      <span>Sources : {d.sources}</span>
                      <span>Produira : {d.livrable}</span>
                    </div>
                    <p className="mt-2 border-l-2 border-[#F2B84B]/40 pl-2.5 text-[11px] italic text-[#F2B84B]">{d.validation_requise}</p>
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
              <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">{s.titre}</h2>
              <div className="mt-3 space-y-4">
                {s.histoires.map((h) => (
                  <CarteHistoire key={h.id} h={h} vedette={h.id === vedetteId} dateCible={dateCible} estAujourdhui={estAujourdhui} navigate={navigate} mesh={mesh} />
                ))}
              </div>
            </section>
          ))}

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
