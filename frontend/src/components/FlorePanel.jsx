import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkle, PaperPlaneRight, FileText, X, Plus, Eye, Lightning, FolderOpen, CheckCircle, CircleNotch, Circle } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import TrustBadges from "./TrustBadges";
import FloreActivite, { delaiMin } from "./FloreActivite";
import { couleurDomaine } from "@/lib/domaines";
import { useContexte } from "@/lib/contexte";
import { useMesh } from "@/lib/mesh";
import { usePilotage } from "@/lib/pilotage";

function contexteDepuis(pathname) {
  // « case » = page DÉTAIL d'un travail uniquement (Flore y est l'onglet Conversation du dossier) ;
  // la liste /travaux reste un contexte normal où Flore s'ouvre en superposition.
  if (/^\/(travaux|cases)\/[^/]+/.test(pathname)) return "case";
  if (pathname.startsWith("/travaux") || pathname.startsWith("/cases")) return "travaux";
  if (pathname.startsWith("/investigations")) return "investigation";
  if (pathname.startsWith("/atlas") || pathname.startsWith("/carte")) return "atlas";
  if (pathname.startsWith("/jumeaux") || pathname.startsWith("/registry") || pathname.startsWith("/administration")) return "jumeaux";
  return "actualites";
}

const COMPORTEMENTS = {
  explorer: { label: "Exploration", couleur: "#25D0C8" },
  expliquer: { label: "Explication", couleur: "#9B87F5" },
  recommander: { label: "Recommandation", couleur: "#F2B84B" },
};

const SUGGESTIONS_SELECTION = [
  "Comprendre leurs relations",
  "Rechercher des dépendances inconnues",
  "Analyser un changement",
  "Trouver les points critiques",
  "Optimiser ce parcours",
  "Ouvrir une investigation",
];

const SUGGESTIONS_DOMAINE = [
  "Comprendre les relations internes",
  "Rechercher des dépendances inconnues",
  "Analyser un changement",
  "Trouver les points critiques",
  "Ouvrir une investigation",
];

const SUGGESTIONS_REGISTRE = [
  "Pourquoi leur connaissance est-elle faible ?",
  "Lequel peut être admis ?",
  "Comparer leurs sources",
  "Rechercher les blocages communs",
];

function LotBar({ lot }) {
  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-40 w-[min(780px,94vw)] -translate-x-1/2">
      <motion.div layout transition={{ type: "spring", stiffness: 380, damping: 32 }} className="glass pointer-events-auto rounded-xl p-2.5">
        <div className="flex flex-wrap items-center gap-2 px-1" data-testid="lot-bar">
          <Sparkle size={15} weight="fill" className="shrink-0 text-[#9B87F5]" />
          <span className="font-code text-[11px] font-medium text-[#F2F6F8]" data-testid="lot-count">
            {lot.ids.length} source{lot.ids.length > 1 ? "s" : ""} sélectionnée{lot.ids.length > 1 ? "s" : ""}
          </span>
          <select onChange={(e) => e.target.value && lot.onAction("profil", e.target.value)} value="" data-testid="lot-profil" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-[11px] text-[#D8E2EA] focus:outline-none">
            <option value="">Appliquer un profil…</option>
            {lot.profils.map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("environnement", e.target.value)} value="" data-testid="lot-environnement" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-[11px] text-[#D8E2EA] focus:outline-none">
            <option value="">Définir l'environnement…</option>
            {["production", "préproduction", "recette", "développement"].map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("frequence", e.target.value)} value="" data-testid="lot-frequence" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 py-1.5 text-[11px] text-[#D8E2EA] focus:outline-none">
            <option value="">Modifier la fréquence…</option>
            {["horaire", "quotidienne", "hebdomadaire"].map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <button onClick={() => lot.onAction("tester")} data-testid="lot-tester-btn" className="flex items-center gap-1.5 rounded-md border border-[#9B87F5]/40 px-2.5 py-1.5 text-[11px] text-[#9B87F5] transition-colors hover:bg-[#9B87F5]/10">
            <Lightning size={12} /> Tester les connexions
          </button>
          <button onClick={() => lot.onAction("supprimer")} data-testid="lot-supprimer-btn" className="rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] text-[#F87171] transition-colors hover:bg-[#F87171]/10">
            Supprimer
          </button>
          <button onClick={lot.onAnnuler} data-testid="lot-annuler-btn" className="ml-auto text-[11px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]">✕</button>
        </div>
      </motion.div>
    </div>
  );
}

// Réponse de Flore en télétype : les caractères s'écrivent progressivement avec curseur
// lumineux (désactivé si prefers-reduced-motion). Les réponses anciennes s'affichent d'un bloc.
function TexteTeletype({ texte, actif, testid }) {
  const reduit = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [n, setN] = useState(() => (actif && !reduit ? 0 : (texte || "").length));
  useEffect(() => {
    if (!actif || reduit) { setN((texte || "").length); return undefined; }
    setN(0);
    const t = setInterval(() => {
      setN((v) => {
        if (v >= texte.length) { clearInterval(t); return v; }
        return Math.min(texte.length, v + 3);
      });
    }, 18);
    return () => clearInterval(t);
  }, [texte, actif, reduit]);
  const fini = n >= (texte || "").length;
  return (
    <p className="mt-2 text-sm leading-relaxed text-[#D8E2EA]" data-testid={testid}>
      {(texte || "").slice(0, n)}
      {!fini && <span className="curseur-teletype">▍</span>}
    </p>
  );
}

function CarteReponse({ data, index, propsEtat, setPropsEtat, justifOuverte, setJustifOuverte, ajouterJumeau, navigate, derniere }) {
  const { commanderCarte, setPreuveSurvolee } = useContexte();
  const pilote = usePilotage();
  return (
    <div className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4" data-testid={`flore-reponse-${index}`}>
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">
        <Sparkle size={12} className="text-[#9B87F5]" /> Flore
        {data.comportement && COMPORTEMENTS[data.comportement] && (
          <span
            className="rounded border px-1.5 py-0.5"
            style={{
              color: COMPORTEMENTS[data.comportement].couleur,
              borderColor: `${COMPORTEMENTS[data.comportement].couleur}44`,
              backgroundColor: `${COMPORTEMENTS[data.comportement].couleur}12`,
            }}
            data-testid={`flore-comportement-${index}`}
          >
            {COMPORTEMENTS[data.comportement].label}
          </span>
        )}
      </div>

      <TexteTeletype texte={data.reponse} actif={derniere} testid={`flore-texte-${index}`} />

      {data.propositions?.some((_, pi) => !propsEtat[`${index}-${pi}`]) && (
        <div className="mt-3" data-testid={`flore-propositions-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Proposition pour la carte</div>
          {data.propositions.map((p, pi) =>
            propsEtat[`${index}-${pi}`] ? null : (
              <div key={pi} className="mt-2 rounded-lg border border-[#25D0C8]/20 bg-[#25D0C8]/[0.04] px-3 py-2.5" data-testid={`flore-proposition-${index}-${pi}`}>
                <p className="text-xs text-[#D8E2EA]">
                  J'ai identifié <span className="font-semibold" style={{ color: couleurDomaine(p.domaine) }}>{p.nom}</span> comme voisin pertinent.
                </p>
                {justifOuverte === `${index}-${pi}` && (
                  <p className="mt-1.5 border-l-2 border-[#25D0C8]/40 pl-2 text-[11px] leading-relaxed text-[#94A3B8]" data-testid={`flore-prop-justif-${index}-${pi}`}>
                    {p.justification}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <button
                    onClick={() => {
                      ajouterJumeau(p.jumeau_id);
                      setPropsEtat((s) => ({ ...s, [`${index}-${pi}`]: "ajoute" }));
                      toast.success(`${p.nom} ajouté au contexte`);
                    }}
                    data-testid={`flore-prop-ajouter-${index}-${pi}`}
                    className="flex items-center gap-1 rounded-md bg-[#25D0C8] px-2 py-1 text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#0891B2]"
                  >
                    <Plus size={11} /> Ajouter au contexte
                  </button>
                  <button
                    onClick={() => setJustifOuverte(justifOuverte === `${index}-${pi}` ? null : `${index}-${pi}`)}
                    data-testid={`flore-prop-examiner-${index}-${pi}`}
                    className="flex items-center gap-1 rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1 text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
                  >
                    <Eye size={11} /> {justifOuverte === `${index}-${pi}` ? "Masquer la justification" : "Examiner la justification"}
                  </button>
                  <button
                    onClick={() => setPropsEtat((s) => ({ ...s, [`${index}-${pi}`]: "ignore" }))}
                    data-testid={`flore-prop-ignorer-${index}-${pi}`}
                    className="rounded-md px-2 py-1 text-[10px] text-[#7C93A8] transition-colors hover:text-[#D8E2EA]"
                  >
                    Ignorer
                  </button>
                </div>
              </div>
            )
          )}
        </div>
      )}

      {data.contributions?.length > 0 && (
        <div className="mt-3" data-testid={`flore-contributions-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Contributions des jumeaux</div>
          <ul className="mt-2 space-y-1.5">
            {data.contributions.map((c, ci) => (
              <li key={ci} className="flex items-baseline gap-2 text-sm">
                <span
                  className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[10px]"
                  style={{ color: couleurDomaine(c.domaine), borderColor: `${couleurDomaine(c.domaine)}44`, backgroundColor: `${couleurDomaine(c.domaine)}12` }}
                >
                  {c.jumeau}
                </span>
                <span className="text-[#94A3B8]">{c.texte}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.preuves?.length > 0 && (
        <div className="mt-3" data-testid={`flore-preuves-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Preuves</div>
          <ul className="mt-2 space-y-1">
            {data.preuves.map((p, pi) => (
              <li key={pi}>
                {p.preuveId && pilote ? (
                  // Preuve de démonstration : ouvre le panneau de lecture (suspend la lecture)
                  <button
                    onClick={() => pilote.ouvrirPreuve(p.preuveId)}
                    data-testid={`flore-preuve-demo-${p.preuveId}`}
                    className="flex w-full items-baseline gap-2 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-2 text-left text-sm text-[#94A3B8] transition-colors hover:border-[#9B87F5]/50 hover:bg-[#9B87F5]/5"
                  >
                    <FileText size={13} className="shrink-0 translate-y-0.5 text-[#7C93A8]" />
                    <span>
                      <span className="font-code text-[11px] text-[#F2F6F8]">{p.source}</span> — {p.detail}
                    </span>
                  </button>
                ) : p.relation_id ? (
                  // Preuve relationnelle : survol = le trajet pulse sur la carte ; clic = centrer + sélectionner
                  <button
                    onMouseEnter={() => setPreuveSurvolee(p.relation_id)}
                    onMouseLeave={() => setPreuveSurvolee(null)}
                    onClick={() => commanderCarte({ type: "relation", relationId: p.relation_id })}
                    data-testid={`flore-preuve-rel-${p.relation_id}`}
                    className="flex w-full items-baseline gap-2 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-2 text-left text-sm text-[#94A3B8] transition-colors hover:border-[#25D0C8]/50 hover:bg-[#25D0C8]/5"
                  >
                    <FileText size={13} className="shrink-0 translate-y-0.5 text-[#7C93A8]" />
                    <span>
                      <span className="font-code text-[11px] text-[#F2F6F8]">{p.source}</span> — {p.detail}
                      {p.confiance != null && <span className="font-code text-[10px] text-[#25D0C8]"> · {p.confiance} %</span>}
                      {p.quand && <span className="font-code text-[10px] text-[#7C93A8]"> · {p.quand}</span>}
                    </span>
                  </button>
                ) : (
                  <span className="flex items-baseline gap-2 text-sm text-[#94A3B8]">
                    <FileText size={13} className="shrink-0 translate-y-0.5 text-[#7C93A8]" />
                    <span><span className="font-code text-[11px] text-[#F2F6F8]">{p.source}</span> — {p.detail}</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <TrustBadges indicateurs={data.indicateurs} />
        {data.action && (
          <button
            onClick={() => navigate(data.action.route)}
            className="rounded-md bg-[#9B87F5] px-3 py-1.5 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7]"
            data-testid={`flore-action-btn-${index}`}
          >
            {data.action.label}
          </button>
        )}
      </div>
    </div>
  );
}

export default function FlorePanel() {
  const location = useLocation();
  const navigate = useNavigate();
  const contexte = contexteDepuis(location.pathname);
  const caseMatch = location.pathname.match(/^\/(?:travaux|cases)\/([^/?]+)/);
  const caseId = caseMatch && caseMatch[1] !== "nouveau" ? caseMatch[1] : null;
  const {
    selection, setSelection, domaineSel, retirerJumeau, setDomaineSel, ajouterJumeau,
    commanderCarte, focusVisuel, lot, floreOuverte, ouvrirFlore, fermerFlore, atlasCtx, questionFlore, setQuestionFlore,
  } = useContexte();
  const { jumeauPar, mesh } = useMesh();
  const pilote = usePilotage();
  const [question, setQuestion] = useState("");
  const [echanges, setEchanges] = useState([]);
  const [chargement, setChargement] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [propsEtat, setPropsEtat] = useState({});
  const [justifOuverte, setJustifOuverte] = useState(null);
  const [promptFocus, setPromptFocus] = useState(null);
  const [creationCase, setCreationCase] = useState(false);
  const [propTravailMasquee, setPropTravailMasquee] = useState(false);
  const [choixTravail, setChoixTravail] = useState(null); // liste des travaux ouverts proposés à l'ajout
  const [ajoutEnCours, setAjoutEnCours] = useState(false);
  const [caseCtx, setCaseCtx] = useState(null);
  const prevFocusRef = useRef(null);
  const prevAtlasSig = useRef(null);
  const inputRef = useRef(null);
  const conversationRef = useRef(null);
  const panelRef = useRef(null);

  // Conversation persistante, contexte évolutif : si la sélection Atlas change en cours
  // de conversation, le fil n'est JAMAIS réinitialisé — un marqueur signale la transition
  useEffect(() => {
    if (!atlasCtx) return;
    const sig = `${atlasCtx.domaine || ""}|${atlasCtx.jumeau || ""}|${atlasCtx.relation || ""}`;
    if (prevAtlasSig.current && prevAtlasSig.current !== sig && floreOuverte && echanges.length > 0) {
      const cible = atlasCtx.jumeau ? `jumeau ${atlasCtx.jumeau}` : atlasCtx.relation ? `relation ${atlasCtx.relation}` : atlasCtx.domaine ? `domaine ${atlasCtx.domaine}` : "Mesh global";
      setEchanges((e) => [...e, { marqueur: true, texte: `Contexte actualisé : ${cible}` }]);
    }
    prevAtlasSig.current = sig;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atlasCtx?.domaine, atlasCtx?.jumeau, atlasCtx?.relation]);

  // Contexte actif : le Case courant quand le panneau est ouvert depuis un case
  useEffect(() => {
    if (!caseId) {
      setCaseCtx(null);
      return;
    }
    api.get(`/cases/${caseId}`).then((r) => setCaseCtx(r.data)).catch(() => setCaseCtx(null));
  }, [caseId]);

  // Pilotage externe (démonstration Polaris) : le fil et l'activité viennent du moteur
  const fil = pilote ? pilote.echanges : echanges;
  const idxDerniereReponse = fil.reduce((acc, e, i) => (e.data ? i : acc), -1);

  const selJumeaux = selection.map(jumeauPar).filter(Boolean);
  const nbDomaine = domaineSel && mesh ? mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === domaineSel).length : 0;
  const suggestionsActives = selection.length > 0 ? (contexte === "jumeaux" ? SUGGESTIONS_REGISTRE : SUGGESTIONS_SELECTION) : domaineSel ? SUGGESTIONS_DOMAINE : suggestions;

  useEffect(() => {
    api.get(`/aurora/suggestions?contexte=${contexte}`).then((r) => setSuggestions(r.data)).catch(() => {});
  }, [contexte]);

  // Changer de focus visuel ne supprime jamais la sélection — Flore propose de l'ajuster
  useEffect(() => {
    const f = focusVisuel;
    if (f?.type === "domaine" && prevFocusRef.current?.label !== f.label) {
      const hors = selection.map(jumeauPar).filter(Boolean).filter((j) => j.domaine !== f.label);
      setPromptFocus(hors.length > 0 ? { domaine: f.label, noms: hors.map((j) => j.nom) } : null);
      if (hors.length > 0) ouvrirFlore();
    }
    if (f) prevFocusRef.current = f;
  }, [focusVisuel]);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ouvrirFlore();
        setTimeout(() => inputRef.current?.focus(), 150);
      }
      if (e.key === "Escape" && !pilote) fermerFlore();
    };
    const ask = (e) => {
      if (e.detail) setQuestion(e.detail);
      ouvrirFlore();
      setTimeout(() => inputRef.current?.focus(), 150);
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("meridian:flore-ask", ask);
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("meridian:flore-ask", ask);
    };
  }, [ouvrirFlore, fermerFlore, pilote]);

  useEffect(() => {
    conversationRef.current?.scrollTo({ top: conversationRef.current.scrollHeight, behavior: "smooth" });
  }, [fil, chargement, pilote?.activite]);

  const demander = async (q) => {
    const finale = (q ?? question).trim();
    if (!finale || chargement) return;
    setChargement(true);
    setQuestion("");
    try {
      const { data } = await delaiMin(api.post("/aurora/demander", { contexte, question: finale, selection, domaine: domaineSel }));
      setEchanges((e) => [...e, { question: finale, data }]);
      setJustifOuverte(null);
      if (data.commande_carte) commanderCarte(data.commande_carte);
    } catch {
      setEchanges((e) => [...e, { question: finale, data: { reponse: "Flore est momentanément injoignable.", contributions: [], preuves: [], indicateurs: null } }]);
    } finally {
      setChargement(false);
    }
  };

  // Superposition : clic en dehors du panneau → fermeture (le bouton « Parler à Flore »
  // gère lui-même son basculement ; Échap ferme aussi — handler clavier ci-dessus)
  useEffect(() => {
    if (pilote || !floreOuverte) return undefined;
    const clicDehors = (e) => {
      if (panelRef.current?.contains(e.target)) return;
      if (e.target.closest?.('[data-testid="btn-parler-flore"]')) return;
      fermerFlore();
    };
    // Phase de capture : React Flow stoppe la propagation des clics sur la carte,
    // seul un listener en capture les voit passer.
    document.addEventListener("mousedown", clicDehors, true);
    return () => document.removeEventListener("mousedown", clicDehors, true);
  }, [floreOuverte, fermerFlore, pilote]);

  // Questions pré-remplies depuis les pages métier (« Analyser ce travail », …) :
  // envoyées dès que le panneau est ouvert. Garde par ref (StrictMode rejoue les effets)
  // et réarmement à la fermeture du panneau.
  const questionEnCours = useRef(null);
  useEffect(() => {
    if (!floreOuverte) { questionEnCours.current = null; return; }
    if (!questionFlore || questionEnCours.current === questionFlore) return;
    questionEnCours.current = questionFlore;
    setQuestionFlore(null);
    demander(questionFlore);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionFlore, floreOuverte]);

  const creerCase = async () => {
    if (!echanges.length || creationCase) return;
    setCreationCase(true);
    const premiere = echanges[0].question;
    const now = new Date().toISOString();
    try {
      const { data } = await api.post("/cases", {
        titre: premiere.length > 90 ? premiere.slice(0, 87) + "…" : premiere,
        type: "demande",
        objectif: premiere,
        jumeaux: selection,
        conversation: echanges.flatMap((e) => [
          { role: "utilisateur", texte: e.question, quand: now },
          { role: "flore", comportement: e.data.comportement, texte: e.data.reponse, quand: now },
        ]),
      });
      toast.success("Travail conservé depuis la conversation");
      fermerFlore();
      navigate(`/travaux/${data.id}`);
    } catch {
      toast.error("Conservation du travail impossible");
    } finally {
      setCreationCase(false);
    }
  };

  const ajouterATravail = async (cid) => {
    if (ajoutEnCours) return;
    setAjoutEnCours(true);
    const now = new Date().toISOString();
    try {
      const { data: c } = await api.get(`/cases/${cid}`);
      const fusion = [
        ...(c.conversation || []),
        ...echanges.flatMap((e) => [
          { role: "utilisateur", texte: e.question, quand: now },
          { role: "flore", comportement: e.data.comportement, texte: e.data.reponse, quand: now },
        ]),
      ];
      await api.patch(`/cases/${cid}`, { conversation: fusion });
      toast.success(`Exploration ajoutée à « ${c.titre} »`);
      fermerFlore();
      navigate(`/travaux/${cid}`);
    } catch {
      toast.error("Ajout impossible");
    } finally {
      setAjoutEnCours(false);
    }
  };

  const proposerAjout = () => {
    setChoixTravail("chargement");
    api.get("/cases").then((r) => setChoixTravail(r.data.filter((c) => c.statut !== "clos"))).catch(() => setChoixTravail([]));
  };

  // Sur une page Travail, la conversation avec Flore EST le dossier (onglet Conversation) :
  // le panneau global serait un doublon — il se ferme et ne s'ouvre pas sur ces pages.
  useEffect(() => {
    if (contexte === "case" && floreOuverte) fermerFlore();
  }, [contexte, floreOuverte, fermerFlore]);

  if (lot) return <LotBar lot={lot} />;

  if (pilote ? !pilote.ouvert : !floreOuverte || contexte === "case") return null;
  return (
    <motion.aside
      ref={panelRef}
      initial={{ x: 60, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className={`hud-gauche hud-violet fixed bottom-0 right-0 top-12 z-40 flex w-[440px] flex-col border-l border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 shadow-[-24px_0_48px_rgba(4,9,15,0.55)] backdrop-blur-xl max-sm:w-[94vw] max-sm:max-w-[94vw] ${chargement ? "hud-reflexion" : ""}`}
      data-testid="flore-panel"
    >
      {/* En-tête */}
      <div className="shrink-0 border-b border-[rgba(148,163,184,0.16)] px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkle size={16} weight="fill" className="text-[#9B87F5]" />
            <span className="font-display text-sm font-bold text-[#F2F6F8]">Flore</span>
            {caseCtx && <span className="font-code text-[10px] text-[#7C93A8]" data-testid="flore-case-num">— CASE-{String(caseCtx.num ?? 0).padStart(3, "0")}</span>}
            {!caseCtx && <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">orchestre les jumeaux du Mesh</span>}
          </div>
          <div className="flex items-center gap-1.5">
            {pilote && (
              <span className="rounded border border-[#25D0C8]/40 bg-[#25D0C8]/[0.07] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#25D0C8]" data-testid="flore-badge-demo">
                Démo guidée
              </span>
            )}
            {!pilote && echanges.length > 0 && (
              <button
                onClick={creerCase}
                disabled={creationCase}
                data-testid="flore-creer-travail-btn"
                title="Conserver cet échange comme travail"
                className="flex items-center gap-1.5 rounded-md border border-[#F2B84B]/40 bg-[#F2B84B]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#F2B84B] transition-colors hover:bg-[#F2B84B]/15 disabled:opacity-50"
              >
                <FolderOpen size={12} /> {creationCase ? "Création…" : "Conserver comme travail"}
              </button>
            )}
            {!pilote && (
              <button onClick={fermerFlore} data-testid="flore-fermer-btn" title="Fermer Flore (Échap)" className="rounded-md p-1.5 text-[#7C93A8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]">
                <X size={15} />
              </button>
            )}
          </div>
        </div>

        {caseCtx && (
          <div className="mt-2 rounded-lg border border-[#9B87F5]/25 bg-[#9B87F5]/[0.05] px-3 py-2" data-testid="flore-contexte-case">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#9B87F5]/70">Contexte actif</div>
            <div className="mt-1 space-y-0.5 font-code text-[10px] text-[#94A3B8]">
              <div>• Travail : {caseCtx.titre}</div>
              <div>• {(caseCtx.jumeaux || []).length} jumeau{(caseCtx.jumeaux || []).length > 1 ? "x" : ""} mobilisé{(caseCtx.jumeaux || []).length > 1 ? "s" : ""}</div>
            </div>
            <div className="mt-1.5 text-[11px] italic text-[#7C93A8]">Que souhaitez-vous approfondir ?</div>
          </div>
        )}

        {(selection.length > 0 || domaineSel) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid="flore-contexte">
            <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">
              Contexte{selection.length > 0 ? ` — ${selection.length} jumeau${selection.length > 1 ? "x" : ""}` : ""}
            </span>
            {domaineSel && (
              <span className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(domaineSel), borderColor: `${couleurDomaine(domaineSel)}55`, backgroundColor: `${couleurDomaine(domaineSel)}12` }} data-testid="flore-domaine-chip">
                Domaine {domaineSel} · {nbDomaine} jumeaux
                <button onClick={() => setDomaineSel(null)} className="opacity-60 transition-opacity hover:opacity-100" data-testid="flore-domaine-chip-retirer">
                  <X size={10} />
                </button>
              </span>
            )}
            {selJumeaux.map((j) => (
              <span key={j.id} className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(j.domaine), borderColor: `${couleurDomaine(j.domaine)}55`, backgroundColor: `${couleurDomaine(j.domaine)}12` }} data-testid={`flore-chip-${j.id}`}>
                {j.nom}
                <button onClick={() => retirerJumeau(j.id)} className="opacity-60 transition-opacity hover:opacity-100" data-testid={`flore-chip-retirer-${j.id}`}>
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Instantané Atlas — Flore sait où se trouve l'utilisateur et ce qu'il regarde */}
        {atlasCtx && contexte === "atlas" && (
          <div className="mt-2 rounded-lg border border-[#25D0C8]/25 bg-[#25D0C8]/[0.04] px-3 py-2" data-testid="flore-contexte-atlas">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#25D0C8]">
              Atlas · {atlasCtx.zoomLabel || "Domaines"}
            </div>
            <div className="mt-0.5 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="flore-contexte-atlas-detail">
              {atlasCtx.domaine ? `Domaine ${atlasCtx.domaine}` : "Mesh global"}
              {atlasCtx.jumeau ? ` · Sélection : ${atlasCtx.jumeau}` : ""}
              {atlasCtx.relation ? ` · Relation : ${atlasCtx.relation}` : ""}
              {atlasCtx.couches?.length ? ` · Couches : ${atlasCtx.couches.join(", ")}` : ""}
            </div>
          </div>
        )}

        {focusVisuel && (          <div className="mt-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]" data-testid="flore-focus-visuel">
            Focus visuel : {focusVisuel.type === "domaine" ? `Domaine ${focusVisuel.label}` : focusVisuel.label}
          </div>
        )}

        {promptFocus && (
          <div className="mt-2 rounded-lg border border-[#9B87F5]/25 bg-[#9B87F5]/[0.05] px-3 py-2" data-testid="flore-prompt-focus">
            <p className="text-[11px] leading-snug text-[#D8E2EA]">
              Vous êtes entré dans le domaine <span className="font-semibold text-[#F2F6F8]">{promptFocus.domaine}</span>. Voulez-vous conserver {promptFocus.noms.join(", ")} dans le contexte ?
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button onClick={() => setPromptFocus(null)} data-testid="flore-prompt-conserver" className="rounded-md bg-[#9B87F5] px-2 py-1 text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#9B87F5]">
                Conserver
              </button>
              <button
                onClick={() => { setSelection(selection.filter((id) => jumeauPar(id)?.domaine === promptFocus.domaine)); setPromptFocus(null); }}
                data-testid="flore-prompt-retirer"
                className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1 text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
              >
                Retirer
              </button>
              <button
                onClick={() => {
                  const voisins = (mesh?.jumeaux || []).filter((j) => !j.anonyme && j.domaine === promptFocus.domaine).map((j) => j.id);
                  setSelection([...new Set([...selection, ...voisins])]);
                  setPromptFocus(null);
                }}
                data-testid="flore-prompt-voisins"
                className="rounded-md border border-[rgba(148,163,184,0.16)] px-2 py-1 text-[10px] text-[#94A3B8] transition-colors hover:border-[#25D0C8]/50 hover:text-[#25D0C8]"
              >
                Ajouter les jumeaux de {promptFocus.domaine}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Une exploration qui s'approfondit peut devenir un Travail — Flore propose sans imposer */}
      {!pilote && echanges.length >= 2 && !caseId && !propTravailMasquee && (
        <div className="mx-4 mb-2 rounded-lg border border-[#F2B84B]/30 bg-[rgba(242,184,75,0.10)] px-3 py-2.5" data-testid="flore-proposition-travail">
          <p className="text-[11px] leading-snug text-[#D8E2EA]">
            Cette exploration implique {selection.length > 0 ? `${selection.length} jumeau${selection.length > 1 ? "x" : ""}` : "plusieurs jumeaux"} et pourrait mériter une mémoire persistante.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <button onClick={() => { setPropTravailMasquee(true); creerCase(); }} disabled={creationCase} data-testid="flore-prop-conserver-btn" className="rounded-md bg-[#F2B84B] px-2.5 py-1.5 text-[10px] font-semibold text-[#071019] transition-colors hover:bg-[#F8CF7A] disabled:opacity-50">
              Conserver comme travail
            </button>
            <button onClick={proposerAjout} data-testid="flore-prop-ajouter-btn" className="rounded-md border border-[#F2B84B]/40 bg-[#0F1D28] px-2.5 py-1.5 text-[10px] font-semibold text-[#F2B84B] transition-colors hover:bg-[rgba(242,184,75,0.10)]">
              Ajouter à un travail existant
            </button>
            <button onClick={() => setPropTravailMasquee(true)} data-testid="flore-prop-ignorer-btn" className="rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-1.5 text-[10px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]">
              Continuer sans conserver
            </button>
          </div>
          {choixTravail && (
            <div className="mt-2 border-t border-[#F2B84B]/20 pt-2" data-testid="flore-prop-choix-travail">
              {choixTravail === "chargement" ? (
                <p className="font-code text-[10px] text-[#7C93A8]">Chargement des travaux ouverts…</p>
              ) : choixTravail.length === 0 ? (
                <p className="font-code text-[10px] text-[#7C93A8]">Aucun travail ouvert — conservez celui-ci.</p>
              ) : (
                choixTravail.slice(0, 4).map((c) => (
                  <button
                    key={c.id}
                    onClick={() => ajouterATravail(c.id)}
                    disabled={ajoutEnCours}
                    data-testid={`flore-prop-travail-${c.id}`}
                    className="mt-1 block w-full truncate rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-1.5 text-left text-[11px] text-[#D8E2EA] transition-colors hover:border-[#F2B84B]/50 hover:text-[#F2F6F8] disabled:opacity-50"
                  >
                    {c.titre}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Conversation */}
      <div ref={conversationRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" data-testid="flore-echanges">
        {fil.length === 0 && !chargement && !pilote?.activite && (
          <div className="mt-8 text-center">
            <Sparkle size={22} weight="fill" className="mx-auto text-[#9B87F5]/60" />
            <p className="mt-3 text-sm text-[#94A3B8]">Posez une question — Flore mobilise les jumeaux concernés et montre leurs preuves.</p>
            <p className="mt-1 font-code text-[10px] text-[#7C93A8]">Une conversation importante peut devenir un travail.</p>
          </div>
        )}
        {fil.map((e, i) =>
          e.marqueur ? (
            <div key={i} className="flex items-center gap-2 px-1 py-0.5" data-testid={`flore-marqueur-${i}`}>
              <span className="h-px flex-1 bg-[rgba(148,163,184,0.16)]" />
              <span className="font-code text-[9px] uppercase tracking-[0.15em] text-[#25D0C8]">{e.texte}</span>
              <span className="h-px flex-1 bg-[rgba(148,163,184,0.16)]" />
            </div>
          ) : (
          <div key={e.id || i} className="space-y-2">
            {e.question && (
              <div className="ml-8 rounded-xl rounded-br-sm bg-[#9B87F5]/15 px-3.5 py-2.5" data-testid={`flore-question-${i}`}>
                <p className="text-sm text-[#F2F6F8]">{e.question}</p>
              </div>
            )}
            {e.data && (
              <CarteReponse
                data={e.data} index={i} derniere={i === idxDerniereReponse}
                propsEtat={propsEtat} setPropsEtat={setPropsEtat}
                justifOuverte={justifOuverte} setJustifOuverte={setJustifOuverte}
                ajouterJumeau={ajouterJumeau} navigate={navigate}
              />
            )}
          </div>
          )
        )}
        {chargement && (
          <div className="px-1" data-testid="flore-chargement">
            <FloreActivite testid="flore-chargement-activite" />
          </div>
        )}
        {pilote?.activite && (
          <div className="rounded-xl border border-[#9B87F5]/25 bg-[#9B87F5]/[0.05] px-3.5 py-3" data-testid="flore-activite-demo">
            <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#9B87F5]">
              <Sparkle size={12} weight="fill" /> {pilote.activite.label}
            </div>
            <ul className="mt-2 space-y-1.5">
              {pilote.activite.ops.map((op, oi) => (
                <li
                  key={oi}
                  className="flex items-center gap-2 text-xs"
                  style={{ color: op.status === "done" ? "#7C93A8" : op.status === "running" ? "#F2F6F8" : "#4B6072" }}
                  data-testid={`flore-activite-demo-op-${oi}`}
                >
                  {op.status === "done" ? (
                    <CheckCircle size={13} weight="fill" className="shrink-0 text-[#25D0C8]" />
                  ) : op.status === "running" ? (
                    <CircleNotch size={13} className="shrink-0 animate-spin text-[#9B87F5]" />
                  ) : (
                    <Circle size={13} className="shrink-0" />
                  )}
                  {op.label}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Suggestions + composer (masqués en démonstration pilotée) */}
      {!pilote && (
      <div className="shrink-0 border-t border-[rgba(148,163,184,0.16)] px-4 py-3">
        {selection.length > 0 && (
          <div className="mb-2.5 flex flex-wrap items-center gap-1.5" data-testid="flore-deleguer">
            <span className="font-code text-[9px] uppercase tracking-[0.18em] text-[#7C93A8]">Déléguer au Mesh :</span>
            {[
              ["surveillance", "Surveiller 24 h"],
              ["comparaison", "Comparer les scénarios"],
              ["confirmation", "Demander confirmation"],
            ].map(([type, label]) => (
              <button
                key={type}
                onClick={async () => {
                  try {
                    const { data } = await api.post("/delegations", { type, jumeaux: selection, duree_h: 24 });
                    toast.success(`Délégation enregistrée — « ${data.tache} » visible dans Suivis`);
                  } catch (e) {
                    toast.error(e.response?.data?.detail || "Délégation impossible");
                  }
                }}
                data-testid={`flore-deleguer-${type}`}
                title="Tâche bornée : périmètre, durée, livrable et limites connus — visible dans Actualités → Suivis"
                className="rounded-full border border-[#25D0C8]/30 bg-[#25D0C8]/[0.06] px-2.5 py-1 text-[11px] text-[#25D0C8] transition-colors hover:bg-[#25D0C8]/15"
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {suggestionsActives.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {suggestionsActives.slice(0, 4).map((s, i) => (
              <button
                key={i}
                onClick={() => demander(s)}
                data-testid={`flore-suggestion-${i}`}
                className="rounded-full border border-[rgba(148,163,184,0.16)] bg-[rgba(148,163,184,0.07)] px-2.5 py-1 text-[11px] text-[#94A3B8] transition-colors duration-200 hover:border-[#9B87F5]/50 hover:text-[#F2F6F8]"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); demander(); }} className="flex items-center gap-2">
          <input
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={
              chargement
                ? "Flore croise les sources…"
                : selection.length > 0
                  ? "Que voulez-vous comprendre sur cette sélection ?"
                  : domaineSel
                    ? `Interroger le domaine ${domaineSel}…`
                    : "Demander à Flore…  (⌘K)"
            }
            disabled={chargement}
            data-testid="flore-input"
            className="h-10 flex-1 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 text-sm text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#9B87F5]/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={chargement || !question.trim()}
            data-testid="flore-send-btn"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#9B87F5] text-[#071019] transition-colors hover:bg-[#B4A5F7] disabled:opacity-30"
          >
            <PaperPlaneRight size={16} weight="fill" />
          </button>
        </form>
      </div>
      )}
    </motion.aside>
  );
}
