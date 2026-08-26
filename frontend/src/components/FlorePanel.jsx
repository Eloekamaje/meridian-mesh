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
  if (pathname.startsWith("/cases")) return "case";
  if (pathname.startsWith("/investigations")) return "investigation";
  if (pathname.startsWith("/atlas") || pathname.startsWith("/carte")) return "atlas";
  if (pathname.startsWith("/jumeaux") || pathname.startsWith("/registry") || pathname.startsWith("/administration")) return "jumeaux";
  return "aujourdhui";
}

const COMPORTEMENTS = {
  explorer: { label: "Exploration", couleur: "#22D3EE" },
  expliquer: { label: "Explication", couleur: "#A78BFA" },
  recommander: { label: "Recommandation", couleur: "#FBBF24" },
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
          <Sparkle size={15} weight="fill" className="shrink-0 text-[#3B82F6]" />
          <span className="font-code text-[11px] font-medium text-white" data-testid="lot-count">
            {lot.ids.length} source{lot.ids.length > 1 ? "s" : ""} sélectionnée{lot.ids.length > 1 ? "s" : ""}
          </span>
          <select onChange={(e) => e.target.value && lot.onAction("profil", e.target.value)} value="" data-testid="lot-profil" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Appliquer un profil…</option>
            {lot.profils.map((p) => <option key={p.id} value={p.id}>{p.nom}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("environnement", e.target.value)} value="" data-testid="lot-environnement" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Définir l'environnement…</option>
            {["production", "préproduction", "recette", "développement"].map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select onChange={(e) => e.target.value && lot.onAction("frequence", e.target.value)} value="" data-testid="lot-frequence" className="rounded-md border border-white/15 bg-black/40 px-2 py-1.5 text-[11px] text-white/70 focus:outline-none">
            <option value="">Modifier la fréquence…</option>
            {["horaire", "quotidienne", "hebdomadaire"].map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <button onClick={() => lot.onAction("tester")} data-testid="lot-tester-btn" className="flex items-center gap-1.5 rounded-md border border-[#3B82F6]/40 px-2.5 py-1.5 text-[11px] text-[#3B82F6] transition-colors hover:bg-[#3B82F6]/10">
            <Lightning size={12} /> Tester les connexions
          </button>
          <button onClick={() => lot.onAction("supprimer")} data-testid="lot-supprimer-btn" className="rounded-md border border-[#F87171]/40 px-2.5 py-1.5 text-[11px] text-[#F87171] transition-colors hover:bg-[#F87171]/10">
            Supprimer
          </button>
          <button onClick={lot.onAnnuler} data-testid="lot-annuler-btn" className="ml-auto text-[11px] text-white/40 transition-colors hover:text-white">✕</button>
        </div>
      </motion.div>
    </div>
  );
}

function CarteReponse({ data, index, propsEtat, setPropsEtat, justifOuverte, setJustifOuverte, ajouterJumeau, navigate }) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid={`flore-reponse-${index}`}>
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.25em] text-white/45">
        <Sparkle size={12} className="text-[#3B82F6]" /> Flore
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

      <p className="mt-2 text-sm leading-relaxed text-white/80" data-testid={`flore-texte-${index}`}>{data.reponse}</p>

      {data.propositions?.some((_, pi) => !propsEtat[`${index}-${pi}`]) && (
        <div className="mt-3" data-testid={`flore-propositions-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/40">Proposition pour la carte</div>
          {data.propositions.map((p, pi) =>
            propsEtat[`${index}-${pi}`] ? null : (
              <div key={pi} className="mt-2 rounded-lg border border-[#22D3EE]/20 bg-[#22D3EE]/[0.04] px-3 py-2.5" data-testid={`flore-proposition-${index}-${pi}`}>
                <p className="text-xs text-white/75">
                  J'ai identifié <span className="font-semibold" style={{ color: couleurDomaine(p.domaine) }}>{p.nom}</span> comme voisin pertinent.
                </p>
                {justifOuverte === `${index}-${pi}` && (
                  <p className="mt-1.5 border-l-2 border-[#22D3EE]/40 pl-2 text-[11px] leading-relaxed text-white/55" data-testid={`flore-prop-justif-${index}-${pi}`}>
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
                    className="flex items-center gap-1 rounded-md bg-[#22D3EE] px-2 py-1 text-[10px] font-semibold text-black transition-colors hover:bg-[#17B8D4]"
                  >
                    <Plus size={11} /> Ajouter au contexte
                  </button>
                  <button
                    onClick={() => setJustifOuverte(justifOuverte === `${index}-${pi}` ? null : `${index}-${pi}`)}
                    data-testid={`flore-prop-examiner-${index}-${pi}`}
                    className="flex items-center gap-1 rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/65 transition-colors hover:text-white"
                  >
                    <Eye size={11} /> {justifOuverte === `${index}-${pi}` ? "Masquer la justification" : "Examiner la justification"}
                  </button>
                  <button
                    onClick={() => setPropsEtat((s) => ({ ...s, [`${index}-${pi}`]: "ignore" }))}
                    data-testid={`flore-prop-ignorer-${index}-${pi}`}
                    className="rounded-md px-2 py-1 text-[10px] text-white/40 transition-colors hover:text-white/70"
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
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/40">Contributions des jumeaux</div>
          <ul className="mt-2 space-y-1.5">
            {data.contributions.map((c, ci) => (
              <li key={ci} className="flex items-baseline gap-2 text-sm">
                <span
                  className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[10px]"
                  style={{ color: couleurDomaine(c.domaine), borderColor: `${couleurDomaine(c.domaine)}44`, backgroundColor: `${couleurDomaine(c.domaine)}12` }}
                >
                  {c.jumeau}
                </span>
                <span className="text-white/65">{c.texte}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.preuves?.length > 0 && (
        <div className="mt-3" data-testid={`flore-preuves-${index}`}>
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/40">Preuves</div>
          <ul className="mt-2 space-y-1">
            {data.preuves.map((p, pi) => (
              <li key={pi} className="flex items-baseline gap-2 text-sm text-white/65">
                <FileText size={13} className="shrink-0 translate-y-0.5 text-white/35" />
                <span><span className="font-code text-[11px] text-white/85">{p.source}</span> — {p.detail}</span>
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
            className="rounded-md bg-[#3B82F6] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
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
  const prevFocusRef = useRef(null);
  const inputRef = useRef(null);
  const conversationRef = useRef(null);

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
      toast.success("Case créé depuis la conversation");
      fermerFlore();
      navigate(`/cases/${data.id}`);
    } catch {
      toast.error("Création du case impossible");
    } finally {
      setCreationCase(false);
    }
  };

  if (lot) return <LotBar lot={lot} />;
  if (!floreOuverte) return null;

  return (
    <motion.aside
      initial={{ x: 60, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="fixed bottom-0 right-0 top-12 z-40 flex w-[440px] max-w-[94vw] flex-col border-l border-white/[0.08] bg-[#0A0A0A]/95 backdrop-blur-xl"
      data-testid="flore-panel"
    >
      {/* En-tête */}
      <div className="shrink-0 border-b border-white/[0.08] px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkle size={16} weight="fill" className="text-[#3B82F6]" />
            <span className="font-display text-sm font-bold text-white">Flore</span>
            <span className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">orchestre les jumeaux du Mesh</span>
          </div>
          <div className="flex items-center gap-1.5">
            {echanges.length > 0 && (
              <button
                onClick={creerCase}
                disabled={creationCase}
                data-testid="flore-creer-case-btn"
                title="Transformer cet échange en Case de travail"
                className="flex items-center gap-1.5 rounded-md border border-[#FBBF24]/40 bg-[#FBBF24]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#FBBF24] transition-colors hover:bg-[#FBBF24]/15 disabled:opacity-50"
              >
                <FolderOpen size={12} /> {creationCase ? "Création…" : "Créer un Case"}
              </button>
            )}
            <button onClick={fermerFlore} data-testid="flore-fermer-btn" title="Fermer Flore (Échap)" className="rounded-md p-1.5 text-white/40 transition-colors hover:bg-white/[0.06] hover:text-white">
              <X size={15} />
            </button>
          </div>
        </div>

        {(selection.length > 0 || domaineSel) && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid="flore-contexte">
            <span className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">
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
          <div className="mt-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-white/30" data-testid="flore-focus-visuel">
            Focus visuel : {focusVisuel.type === "domaine" ? `Domaine ${focusVisuel.label}` : focusVisuel.label}
          </div>
        )}

        {promptFocus && (
          <div className="mt-2 rounded-lg border border-[#A78BFA]/25 bg-[#A78BFA]/[0.05] px-3 py-2" data-testid="flore-prompt-focus">
            <p className="text-[11px] leading-snug text-white/70">
              Vous êtes entré dans le domaine <span className="font-semibold text-white">{promptFocus.domaine}</span>. Voulez-vous conserver {promptFocus.noms.join(", ")} dans le contexte ?
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button onClick={() => setPromptFocus(null)} data-testid="flore-prompt-conserver" className="rounded-md bg-[#A78BFA] px-2 py-1 text-[10px] font-semibold text-black transition-colors hover:bg-[#8B5CF6]">
                Conserver
              </button>
              <button
                onClick={() => { setSelection(selection.filter((id) => jumeauPar(id)?.domaine === promptFocus.domaine)); setPromptFocus(null); }}
                data-testid="flore-prompt-retirer"
                className="rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/65 transition-colors hover:text-white"
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
                className="rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/65 transition-colors hover:border-[#22D3EE]/50 hover:text-[#22D3EE]"
              >
                Ajouter les jumeaux de {promptFocus.domaine}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Conversation */}
      <div ref={conversationRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" data-testid="flore-echanges">
        {echanges.length === 0 && !chargement && (
          <div className="mt-8 text-center">
            <Sparkle size={22} weight="fill" className="mx-auto text-[#3B82F6]/60" />
            <p className="mt-3 text-sm text-white/55">Posez une question — Flore mobilise les jumeaux concernés et montre leurs preuves.</p>
            <p className="mt-1 font-code text-[10px] text-white/30">Une conversation importante peut devenir un Case.</p>
          </div>
        )}
        {echanges.map((e, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-8 rounded-xl rounded-br-sm bg-[#3B82F6]/15 px-3.5 py-2.5" data-testid={`flore-question-${i}`}>
              <p className="text-sm text-white/90">{e.question}</p>
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
          <div className="flex items-center gap-2 px-1 font-code text-[11px] text-white/40" data-testid="flore-chargement">
            <Sparkle size={13} className="animate-pulse text-[#3B82F6]" /> Flore croise les sources…
          </div>
        )}
      </div>

      {/* Suggestions + composer */}
      <div className="shrink-0 border-t border-white/[0.08] px-4 py-3">
        {suggestionsActives.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {suggestionsActives.slice(0, 4).map((s, i) => (
              <button
                key={i}
                onClick={() => demander(s)}
                data-testid={`flore-suggestion-${i}`}
                className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/55 transition-colors duration-200 hover:border-[#3B82F6]/50 hover:text-white"
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
            className="h-10 flex-1 rounded-lg border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-white/35 focus:border-[#3B82F6]/60 focus:outline-none"
          />
          <button
            type="submit"
            disabled={chargement || !question.trim()}
            data-testid="flore-send-btn"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#3B82F6] text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-30"
          >
            <PaperPlaneRight size={16} weight="fill" />
          </button>
        </form>
      </div>
    </motion.aside>
  );
}
