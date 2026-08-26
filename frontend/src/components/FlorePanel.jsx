import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkle, PaperPlaneRight, FileText, X, Plus, Eye, Lightning, FolderOpen } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import TrustBadges from "./TrustBadges";
import { couleurDomaine } from "@/lib/domaines";
import { useContexte } from "@/lib/contexte";
import { useMesh } from "@/lib/mesh";

function contexteDepuis(pathname) {
  if (pathname.startsWith("/travaux") || pathname.startsWith("/cases")) return "case";
  if (pathname.startsWith("/investigations")) return "investigation";
  if (pathname.startsWith("/atlas") || pathname.startsWith("/carte")) return "atlas";
  if (pathname.startsWith("/jumeaux") || pathname.startsWith("/registry") || pathname.startsWith("/administration")) return "jumeaux";
  return "actualites";
}

const COMPORTEMENTS = {
  explorer: { label: "Exploration", couleur: "#0E7490" },
  expliquer: { label: "Explication", couleur: "#6D28D9" },
  recommander: { label: "Recommandation", couleur: "#B45309" },
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
          <Sparkle size={15} weight="fill" className="shrink-0 text-[#3730A3]" />
          <span className="font-code text-[11px] font-medium text-[#111110]" data-testid="lot-count">
            {lot.ids.length} source{lot.ids.length > 1 ? "s" : ""} sélectionnée{lot.ids.length > 1 ? "s" : ""}
          </span>
          <select onChange={(e) => e.target.value && lot.onAction("profil", e.target.value)} value="" data-testid="lot-profil" className="rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-[11px] text-[#3F3F3C] focus:outline-none">
            <option value="">Appliquer un profil…</option>
            {lot.profils.map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("environnement", e.target.value)} value="" data-testid="lot-environnement" className="rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-[11px] text-[#3F3F3C] focus:outline-none">
            <option value="">Définir l'environnement…</option>
            {["production", "préproduction", "recette", "développement"].map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("frequence", e.target.value)} value="" data-testid="lot-frequence" className="rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-[11px] text-[#3F3F3C] focus:outline-none">
            <option value="">Modifier la fréquence…</option>
            {["horaire", "quotidienne", "hebdomadaire"].map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <button onClick={() => lot.onAction("tester")} data-testid="lot-tester-btn" className="flex items-center gap-1.5 rounded-md border border-[#3730A3]/40 px-2.5 py-1.5 text-[11px] text-[#3730A3] transition-colors hover:bg-[#3730A3]/10">
            <Lightning size={12} /> Tester les connexions
          </button>
          <button onClick={() => lot.onAction("supprimer")} data-testid="lot-supprimer-btn" className="rounded-md border border-[#B91C1C]/40 px-2.5 py-1.5 text-[11px] text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/10">
            Supprimer
          </button>
          <button onClick={lot.onAnnuler} data-testid="lot-annuler-btn" className="ml-auto text-[11px] text-[#71716D] transition-colors hover:text-[#111110]">✕</button>
        </div>
      </motion.div>
    </div>
  );
}

function CarteReponse({ data, index, propsEtat, setPropsEtat, justifOuverte, setJustifOuverte, ajouterJumeau, navigate }) {
  return (
    <div className="rounded-xl border border-[#E5E5E3] bg-white p-4" data-testid={`flore-reponse-${index}`}>
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-[#71716D]">
        <Sparkle size={12} className="text-[#3730A3]" /> Flore
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

      <p className="mt-2 text-sm leading-relaxed text-[#3F3F3C]" data-testid={`flore-texte-${index}`}>{data.reponse}</p>

      {data.propositions?.some((_, pi) => !propsEtat[`${index}-${pi}`]) && (
        <div className="mt-3" data-testid={`flore-propositions-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Proposition pour la carte</div>
          {data.propositions.map((p, pi) =>
            propsEtat[`${index}-${pi}`] ? null : (
              <div key={pi} className="mt-2 rounded-lg border border-[#0E7490]/20 bg-[#0E7490]/[0.04] px-3 py-2.5" data-testid={`flore-proposition-${index}-${pi}`}>
                <p className="text-xs text-[#3F3F3C]">
                  J'ai identifié <span className="font-semibold" style={{ color: couleurDomaine(p.domaine) }}>{p.nom}</span> comme voisin pertinent.
                </p>
                {justifOuverte === `${index}-${pi}` && (
                  <p className="mt-1.5 border-l-2 border-[#0E7490]/40 pl-2 text-[11px] leading-relaxed text-[#52524F]" data-testid={`flore-prop-justif-${index}-${pi}`}>
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
                    className="flex items-center gap-1 rounded-md bg-[#0E7490] px-2 py-1 text-[10px] font-semibold text-white transition-colors hover:bg-[#0891B2]"
                  >
                    <Plus size={11} /> Ajouter au contexte
                  </button>
                  <button
                    onClick={() => setJustifOuverte(justifOuverte === `${index}-${pi}` ? null : `${index}-${pi}`)}
                    data-testid={`flore-prop-examiner-${index}-${pi}`}
                    className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]"
                  >
                    <Eye size={11} /> {justifOuverte === `${index}-${pi}` ? "Masquer la justification" : "Examiner la justification"}
                  </button>
                  <button
                    onClick={() => setPropsEtat((s) => ({ ...s, [`${index}-${pi}`]: "ignore" }))}
                    data-testid={`flore-prop-ignorer-${index}-${pi}`}
                    className="rounded-md px-2 py-1 text-[10px] text-[#71716D] transition-colors hover:text-[#3F3F3C]"
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
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Contributions des jumeaux</div>
          <ul className="mt-2 space-y-1.5">
            {data.contributions.map((c, ci) => (
              <li key={ci} className="flex items-baseline gap-2 text-sm">
                <span
                  className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[10px]"
                  style={{ color: couleurDomaine(c.domaine), borderColor: `${couleurDomaine(c.domaine)}44`, backgroundColor: `${couleurDomaine(c.domaine)}12` }}
                >
                  {c.jumeau}
                </span>
                <span className="text-[#52524F]">{c.texte}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.preuves?.length > 0 && (
        <div className="mt-3" data-testid={`flore-preuves-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Preuves</div>
          <ul className="mt-2 space-y-1">
            {data.preuves.map((p, pi) => (
              <li key={pi} className="flex items-baseline gap-2 text-sm text-[#52524F]">
                <FileText size={13} className="shrink-0 translate-y-0.5 text-[#71716D]" />
                <span><span className="font-code text-[11px] text-[#111110]">{p.source}</span> — {p.detail}</span>
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
            className="rounded-md bg-[#3730A3] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA]"
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
    commanderCarte, focusVisuel, lot, floreOuverte, ouvrirFlore, fermerFlore,
  } = useContexte();
  const { jumeauPar, mesh } = useMesh();
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
  const inputRef = useRef(null);
  const conversationRef = useRef(null);

  // Contexte actif : le Case courant quand le panneau est ouvert depuis un case
  useEffect(() => {
    if (!caseId) {
      setCaseCtx(null);
      return;
    }
    api.get(`/cases/${caseId}`).then((r) => setCaseCtx(r.data)).catch(() => setCaseCtx(null));
  }, [caseId]);

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
      if (e.key === "Escape") fermerFlore();
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
  }, [ouvrirFlore, fermerFlore]);

  useEffect(() => {
    conversationRef.current?.scrollTo({ top: conversationRef.current.scrollHeight, behavior: "smooth" });
  }, [echanges, chargement]);

  const demander = async (q) => {
    const finale = (q ?? question).trim();
    if (!finale || chargement) return;
    setChargement(true);
    setQuestion("");
    try {
      const { data } = await api.post("/aurora/demander", { contexte, question: finale, selection, domaine: domaineSel });
      setEchanges((e) => [...e, { question: finale, data }]);
      setJustifOuverte(null);
      if (data.commande_carte) commanderCarte(data.commande_carte);
    } catch {
      setEchanges((e) => [...e, { question: finale, data: { reponse: "Flore est momentanément injoignable.", contributions: [], preuves: [], indicateurs: null } }]);
    } finally {
      setChargement(false);
    }
  };

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

  if (lot) return <LotBar lot={lot} />;
  if (!floreOuverte) return null;
  return (
    <motion.aside
      initial={{ x: 60, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="fixed bottom-0 right-0 top-14 z-40 flex w-[440px] max-w-[94vw] flex-col border-l border-[#E5E5E3] bg-white/95 backdrop-blur-xl"
      data-testid="flore-panel"
    >
      {/* En-tête */}
      <div className="shrink-0 border-b border-[#E5E5E3] px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkle size={16} weight="fill" className="text-[#3730A3]" />
            <span className="font-display text-sm font-bold text-[#111110]">Flore</span>
            {caseCtx && <span className="font-code text-[10px] text-[#71716D]" data-testid="flore-case-num">— CASE-{String(caseCtx.num ?? 0).padStart(3, "0")}</span>}
            {!caseCtx && <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">orchestre les jumeaux du Mesh</span>}
          </div>
          <div className="flex items-center gap-1.5">
            {echanges.length > 0 && (
              <button
                onClick={creerCase}
                disabled={creationCase}
                data-testid="flore-creer-travail-btn"
                title="Conserver cet échange comme travail"
                className="flex items-center gap-1.5 rounded-md border border-[#B45309]/40 bg-[#B45309]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#B45309] transition-colors hover:bg-[#B45309]/15 disabled:opacity-50"
              >
                <FolderOpen size={12} /> {creationCase ? "Création…" : "Conserver comme travail"}
              </button>
            )}
            <button onClick={fermerFlore} data-testid="flore-fermer-btn" title="Fermer Flore (Échap)" className="rounded-md p-1.5 text-[#71716D] transition-colors hover:bg-[#F0F0EE] hover:text-[#111110]">
              <X size={15} />
            </button>
          </div>
        </div>

        {caseCtx && (
          <div className="mt-2 rounded-lg border border-[#3730A3]/25 bg-[#3730A3]/[0.05] px-3 py-2" data-testid="flore-contexte-case">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#3730A3]/70">Contexte actif</div>
            <div className="mt-1 space-y-0.5 font-code text-[10px] text-[#52524F]">
              <div>• Travail : {caseCtx.titre}</div>
              <div>• {(caseCtx.jumeaux || []).length} jumeau{(caseCtx.jumeaux || []).length > 1 ? "x" : ""} mobilisé{(caseCtx.jumeaux || []).length > 1 ? "s" : ""}</div>
            </div>
            <div className="mt-1.5 text-[11px] italic text-[#71716D]">Que souhaitez-vous approfondir ?</div>
          </div>
        )}

        {(selection.length > 0 || domaineSel) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid="flore-contexte">
            <span className="font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">
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

        {focusVisuel && (
          <div className="mt-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]" data-testid="flore-focus-visuel">
            Focus visuel : {focusVisuel.type === "domaine" ? `Domaine ${focusVisuel.label}` : focusVisuel.label}
          </div>
        )}

        {promptFocus && (
          <div className="mt-2 rounded-lg border border-[#6D28D9]/25 bg-[#6D28D9]/[0.05] px-3 py-2" data-testid="flore-prompt-focus">
            <p className="text-[11px] leading-snug text-[#3F3F3C]">
              Vous êtes entré dans le domaine <span className="font-semibold text-[#111110]">{promptFocus.domaine}</span>. Voulez-vous conserver {promptFocus.noms.join(", ")} dans le contexte ?
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button onClick={() => setPromptFocus(null)} data-testid="flore-prompt-conserver" className="rounded-md bg-[#6D28D9] px-2 py-1 text-[10px] font-semibold text-white transition-colors hover:bg-[#7C3AED]">
                Conserver
              </button>
              <button
                onClick={() => { setSelection(selection.filter((id) => jumeauPar(id)?.domaine === promptFocus.domaine)); setPromptFocus(null); }}
                data-testid="flore-prompt-retirer"
                className="rounded-md border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]"
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
                className="rounded-md border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:border-[#0E7490]/50 hover:text-[#0E7490]"
              >
                Ajouter les jumeaux de {promptFocus.domaine}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Une exploration qui s'approfondit peut devenir un Travail — Flore propose sans imposer */}
      {echanges.length >= 2 && !caseId && !propTravailMasquee && (
        <div className="mx-4 mb-2 rounded-lg border border-[#B45309]/30 bg-[#FFFBEB] px-3 py-2.5" data-testid="flore-proposition-travail">
          <p className="text-[11px] leading-snug text-[#3F3F3C]">
            Cette exploration implique {selection.length > 0 ? `${selection.length} jumeau${selection.length > 1 ? "x" : ""}` : "plusieurs jumeaux"} et pourrait mériter une mémoire persistante.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <button onClick={() => { setPropTravailMasquee(true); creerCase(); }} disabled={creationCase} data-testid="flore-prop-conserver-btn" className="rounded-md bg-[#B45309] px-2.5 py-1.5 text-[10px] font-semibold text-white transition-colors hover:bg-[#92400E] disabled:opacity-50">
              Conserver comme travail
            </button>
            <button onClick={proposerAjout} data-testid="flore-prop-ajouter-btn" className="rounded-md border border-[#B45309]/40 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-[#B45309] transition-colors hover:bg-[#FFFBEB]">
              Ajouter à un travail existant
            </button>
            <button onClick={() => setPropTravailMasquee(true)} data-testid="flore-prop-ignorer-btn" className="rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]">
              Continuer sans conserver
            </button>
          </div>
          {choixTravail && (
            <div className="mt-2 border-t border-[#B45309]/20 pt-2" data-testid="flore-prop-choix-travail">
              {choixTravail === "chargement" ? (
                <p className="font-code text-[10px] text-[#71716D]">Chargement des travaux ouverts…</p>
              ) : choixTravail.length === 0 ? (
                <p className="font-code text-[10px] text-[#71716D]">Aucun travail ouvert — conservez celui-ci.</p>
              ) : (
                choixTravail.slice(0, 4).map((c) => (
                  <button
                    key={c.id}
                    onClick={() => ajouterATravail(c.id)}
                    disabled={ajoutEnCours}
                    data-testid={`flore-prop-travail-${c.id}`}
                    className="mt-1 block w-full truncate rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-left text-[11px] text-[#3F3F3C] transition-colors hover:border-[#B45309]/50 hover:text-[#111110] disabled:opacity-50"
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
        {echanges.length === 0 && !chargement && (
          <div className="mt-8 text-center">
            <Sparkle size={22} weight="fill" className="mx-auto text-[#3730A3]/60" />
            <p className="mt-3 text-sm text-[#52524F]">Posez une question — Flore mobilise les jumeaux concernés et montre leurs preuves.</p>
            <p className="mt-1 font-code text-[10px] text-[#71716D]">Une conversation importante peut devenir un travail.</p>
          </div>
        )}
        {echanges.map((e, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-8 rounded-xl rounded-br-sm bg-[#3730A3]/15 px-3.5 py-2.5" data-testid={`flore-question-${i}`}>
              <p className="text-sm text-[#111110]">{e.question}</p>
            </div>
            <CarteReponse
              data={e.data} index={i}
              propsEtat={propsEtat} setPropsEtat={setPropsEtat}
              justifOuverte={justifOuverte} setJustifOuverte={setJustifOuverte}
              ajouterJumeau={ajouterJumeau} navigate={navigate}
            />
          </div>
        ))}
        {chargement && (
          <div className="flex items-center gap-2 px-1 font-code text-[11px] text-[#71716D]" data-testid="flore-chargement">
            <Sparkle size={13} className="animate-pulse text-[#3730A3]" /> Flore croise les sources…
          </div>
        )}
      </div>

      {/* Suggestions + composer */}
      <div className="shrink-0 border-t border-[#E5E5E3] px-4 py-3">
        {selection.length > 0 && (
          <div className="mb-2.5 flex flex-wrap items-center gap-1.5" data-testid="flore-deleguer">
            <span className="font-code text-[9px] uppercase tracking-[0.18em] text-[#71716D]">Déléguer au Mesh :</span>
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
                className="rounded-full border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-2.5 py-1 text-[11px] text-[#0E7490] transition-colors hover:bg-[#0E7490]/15"
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
                className="rounded-full border border-[#E5E5E3] bg-[#F7F7F6] px-2.5 py-1 text-[11px] text-[#52524F] transition-colors duration-200 hover:border-[#3730A3]/50 hover:text-[#111110]"
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
            className="h-10 flex-1 rounded-lg border border-[#E5E5E3] bg-white px-3 text-sm text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={chargement || !question.trim()}
            data-testid="flore-send-btn"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#3730A3] text-white transition-colors hover:bg-[#4338CA] disabled:opacity-30"
          >
            <PaperPlaneRight size={16} weight="fill" />
          </button>
        </form>
      </div>
    </motion.aside>
  );
}
