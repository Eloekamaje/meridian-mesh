import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkle, PaperPlaneRight, FileText, X, CaretDown, Plus, Eye, Lightning } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import TrustBadges from "./TrustBadges";
import { couleurDomaine } from "@/lib/domaines";
import { useContexte } from "@/lib/contexte";
import { useMesh } from "@/lib/mesh";

function contexteDepuis(pathname) {
  if (pathname.startsWith("/investigations")) return "investigation";
  if (pathname.startsWith("/decisions") || pathname.startsWith("/change-lab")) return "decisions";
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

export default function AuroraBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const contexte = contexteDepuis(location.pathname);
  const { selection, setSelection, domaineSel, retirerJumeau, setDomaineSel, ajouterJumeau, commanderCarte, focusVisuel, lot } = useContexte();
  const { jumeauPar, mesh } = useMesh();
  const [question, setQuestion] = useState("");
  const [reponse, setReponse] = useState(null);
  const [questionPosee, setQuestionPosee] = useState("");
  const [chargement, setChargement] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [replie, setReplie] = useState(false);
  const [propsEtat, setPropsEtat] = useState({});
  const [justifOuverte, setJustifOuverte] = useState(null);
  const [promptFocus, setPromptFocus] = useState(null);
  const prevFocusRef = useRef(null);
  const inputRef = useRef(null);

  const selJumeaux = selection.map(jumeauPar).filter(Boolean);
  const nbDomaine = domaineSel && mesh ? mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === domaineSel).length : 0;
  const suggestionsActives = selection.length > 0 ? SUGGESTIONS_SELECTION : domaineSel ? SUGGESTIONS_DOMAINE : suggestions;

  useEffect(() => {
    setReponse(null);
    api.get(`/aurora/suggestions?contexte=${contexte}`).then((r) => setSuggestions(r.data)).catch(() => {});
  }, [contexte]);

  // Changer de focus visuel ne supprime jamais la sélection — Aurora propose de l'ajuster
  useEffect(() => {
    const f = focusVisuel;
    if (f?.type === "domaine" && prevFocusRef.current?.label !== f.label) {
      const hors = selection.map(jumeauPar).filter(Boolean).filter((j) => j.domaine !== f.label);
      setPromptFocus(hors.length > 0 ? { domaine: f.label, noms: hors.map((j) => j.nom) } : null);
    }
    if (f) prevFocusRef.current = f;
  }, [focusVisuel]);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setReplie(false);
        inputRef.current?.focus();
      }
    };
    const ask = (e) => {
      if (e.detail) setQuestion(e.detail);
      setReplie(false);
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("meridian:aurora-ask", ask);
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("meridian:aurora-ask", ask);
    };
  }, []);

  const demander = async (q) => {
    const finale = (q ?? question).trim();
    if (!finale || chargement) return;
    setChargement(true);
    setQuestionPosee(finale);
    setQuestion("");
    try {
      const { data } = await api.post("/aurora/demander", { contexte, question: finale, selection, domaine: domaineSel });
      setReponse(data);
      setPropsEtat({});
      setJustifOuverte(null);
      if (data.commande_carte) commanderCarte(data.commande_carte);
    } catch {
      setReponse({ reponse: "Aurora est momentanément injoignable.", contributions: [], preuves: [], indicateurs: null });
    } finally {
      setChargement(false);
    }
  };

  if (replie && !lot) {
    return (
      <button
        onClick={() => setReplie(false)}
        data-testid="aurora-pill"
        className="glass rise fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full px-4 py-2.5 text-xs font-semibold text-white/80 transition-colors hover:text-white"
      >
        <Sparkle size={15} weight="fill" className="text-[#3B82F6]" />
        Aurora
        {selection.length > 0 && <span className="font-code text-[10px] text-white/45">· {selection.length} jumeau{selection.length > 1 ? "x" : ""}</span>}
        {reponse && <span className="h-1.5 w-1.5 rounded-full bg-[#22D3EE]" />}
      </button>
    );
  }

  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-40 w-[min(700px,92vw)] -translate-x-1/2" data-testid="aurora-bar">
      {reponse && !lot && (
        <div className="glass rise pointer-events-auto mb-3 max-h-[52vh] overflow-y-auto rounded-xl p-5" data-testid="aurora-panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-white/45">
                <Sparkle size={13} className="text-[#3B82F6]" /> Réponse Aurora
                {reponse.comportement && COMPORTEMENTS[reponse.comportement] && (
                  <span
                    className="rounded border px-1.5 py-0.5"
                    style={{
                      color: COMPORTEMENTS[reponse.comportement].couleur,
                      borderColor: `${COMPORTEMENTS[reponse.comportement].couleur}44`,
                      backgroundColor: `${COMPORTEMENTS[reponse.comportement].couleur}12`,
                    }}
                    data-testid="aurora-comportement"
                  >
                    {COMPORTEMENTS[reponse.comportement].label}
                  </span>
                )}
              </div>
              <div className="mt-1 text-sm font-semibold text-white/85">{questionPosee}</div>
            </div>
            <button onClick={() => setReponse(null)} className="text-white/40 transition-colors hover:text-white" data-testid="aurora-close-btn">
              <X size={16} />
            </button>
          </div>

          <p className="mt-3 text-sm leading-relaxed text-white/80" data-testid="aurora-reponse">{reponse.reponse}</p>

          {reponse.propositions?.some((_, i) => !propsEtat[i]) && (
            <div className="mt-4" data-testid="aurora-propositions">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Proposition pour la carte</div>
              {reponse.propositions.map((p, i) =>
                propsEtat[i] ? null : (
                  <div key={i} className="mt-2 rounded-lg border border-[#22D3EE]/20 bg-[#22D3EE]/[0.04] px-3 py-2.5" data-testid={`aurora-proposition-${i}`}>
                    <p className="text-xs text-white/75">
                      J'ai identifié <span className="font-semibold" style={{ color: couleurDomaine(p.domaine) }}>{p.nom}</span> comme voisin pertinent.
                    </p>
                    {justifOuverte === i && (
                      <p className="mt-1.5 border-l-2 border-[#22D3EE]/40 pl-2 text-[11px] leading-relaxed text-white/55" data-testid={`aurora-prop-justif-${i}`}>
                        {p.justification}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <button
                        onClick={() => {
                          ajouterJumeau(p.jumeau_id);
                          setPropsEtat((s) => ({ ...s, [i]: "ajoute" }));
                          toast.success(`${p.nom} ajouté au contexte`);
                        }}
                        data-testid={`aurora-prop-ajouter-${i}`}
                        className="flex items-center gap-1 rounded-md bg-[#22D3EE] px-2 py-1 text-[10px] font-semibold text-black transition-colors hover:bg-[#17B8D4]"
                      >
                        <Plus size={11} /> Ajouter au contexte
                      </button>
                      <button
                        onClick={() => setJustifOuverte(justifOuverte === i ? null : i)}
                        data-testid={`aurora-prop-examiner-${i}`}
                        className="flex items-center gap-1 rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/65 transition-colors hover:text-white"
                      >
                        <Eye size={11} /> {justifOuverte === i ? "Masquer la justification" : "Examiner la justification"}
                      </button>
                      <button
                        onClick={() => setPropsEtat((s) => ({ ...s, [i]: "ignore" }))}
                        data-testid={`aurora-prop-ignorer-${i}`}
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

          {reponse.contributions?.length > 0 && (
            <div className="mt-4" data-testid="aurora-contributions">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Contributions des jumeaux</div>
              <ul className="mt-2 space-y-1.5">
                {reponse.contributions.map((c, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-sm">
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

          {reponse.preuves?.length > 0 && (
            <div className="mt-4" data-testid="aurora-preuves">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Preuves</div>
              <ul className="mt-2 space-y-1">
                {reponse.preuves.map((p, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-sm text-white/65">
                    <FileText size={13} className="shrink-0 translate-y-0.5 text-white/35" />
                    <span><span className="font-code text-[11px] text-white/85">{p.source}</span> — {p.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <TrustBadges indicateurs={reponse.indicateurs} />
            {reponse.action && (
              <button
                onClick={() => { navigate(reponse.action.route); setReponse(null); }}
                className="rounded-md bg-[#3B82F6] px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-[#2F6FDB]"
                data-testid="aurora-action-btn"
              >
                {reponse.action.label}
              </button>
            )}
          </div>
        </div>
      )}

      <motion.div
        layout
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
        className={`glass pointer-events-auto rounded-xl p-2.5 ${lot ? "w-[min(780px,94vw)]" : "w-[min(700px,92vw)]"}`}
      >
        {lot ? (
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
        ) : (
          <>
        {focusVisuel && (
          <div className="mb-1.5 px-1 font-code text-[9px] uppercase tracking-[0.2em] text-white/30" data-testid="aurora-focus-visuel">
            Focus visuel : {focusVisuel.type === "domaine" ? `Domaine ${focusVisuel.label}` : focusVisuel.label}
          </div>
        )}
        {promptFocus && (
          <div className="mb-2 rounded-lg border border-[#A78BFA]/25 bg-[#A78BFA]/[0.05] px-3 py-2" data-testid="aurora-prompt-focus">
            <p className="text-[11px] leading-snug text-white/70">
              Vous êtes entré dans le domaine <span className="font-semibold text-white">{promptFocus.domaine}</span>. Voulez-vous conserver {promptFocus.noms.join(", ")} dans le contexte ?
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button onClick={() => setPromptFocus(null)} data-testid="aurora-prompt-conserver" className="rounded-md bg-[#A78BFA] px-2 py-1 text-[10px] font-semibold text-black transition-colors hover:bg-[#8B5CF6]">
                Conserver
              </button>
              <button
                onClick={() => { setSelection(selection.filter((id) => jumeauPar(id)?.domaine === promptFocus.domaine)); setPromptFocus(null); }}
                data-testid="aurora-prompt-retirer"
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
                data-testid="aurora-prompt-voisins"
                className="rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/65 transition-colors hover:border-[#22D3EE]/50 hover:text-[#22D3EE]"
              >
                Ajouter les jumeaux de {promptFocus.domaine}
              </button>
            </div>
          </div>
        )}
        {(selection.length > 0 || domaineSel) && (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 border-b border-white/[0.06] px-1 pb-2" data-testid="aurora-contexte">
            <span className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">
              Contexte actif{selection.length > 0 ? ` — ${selection.length} jumeau${selection.length > 1 ? "x" : ""}` : ""}
            </span>
            {domaineSel && (
              <span className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(domaineSel), borderColor: `${couleurDomaine(domaineSel)}55`, backgroundColor: `${couleurDomaine(domaineSel)}12` }} data-testid="aurora-domaine-chip">
                Domaine {domaineSel} · {nbDomaine} jumeaux accessibles
                <button onClick={() => setDomaineSel(null)} className="opacity-60 transition-opacity hover:opacity-100" data-testid="aurora-domaine-chip-retirer">
                  <X size={10} />
                </button>
              </span>
            )}
            {selJumeaux.map((j) => (
              <span key={j.id} className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(j.domaine), borderColor: `${couleurDomaine(j.domaine)}55`, backgroundColor: `${couleurDomaine(j.domaine)}12` }} data-testid={`aurora-chip-${j.id}`}>
                {j.nom}
                <button onClick={() => retirerJumeau(j.id)} className="opacity-60 transition-opacity hover:opacity-100" data-testid={`aurora-chip-retirer-${j.id}`}>
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}

        {!reponse && suggestionsActives.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5 px-1">
            {suggestionsActives.map((s, i) => (
              <button
                key={i}
                onClick={() => demander(s)}
                data-testid={`aurora-suggestion-${i}`}
                className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/55 transition-colors duration-200 hover:border-[#3B82F6]/50 hover:text-white"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={(e) => { e.preventDefault(); demander(); }} className="flex items-center gap-2">
          <Sparkle size={18} weight="fill" className="ml-2 shrink-0 text-[#3B82F6]" />
          <input
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={
              chargement
                ? "Aurora croise les sources…"
                : selection.length > 0
                  ? "Que voulez-vous comprendre sur cette sélection ?"
                  : domaineSel
                    ? `Interroger le domaine ${domaineSel}…`
                    : "Demander à Aurora…  (⌘K)"
            }
            disabled={chargement}
            data-testid="aurora-input"
            className="h-9 flex-1 bg-transparent text-sm text-white placeholder:text-white/35 focus:outline-none"
          />
          <button
            type="submit"
            disabled={chargement || !question.trim()}
            data-testid="aurora-send-btn"
            className="flex h-9 w-9 items-center justify-center rounded-md bg-[#3B82F6] text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-30"
          >
            <PaperPlaneRight size={16} weight="fill" />
          </button>
          <button
            type="button"
            onClick={() => setReplie(true)}
            title="Réduire Aurora (le contexte est conservé)"
            data-testid="aurora-reduire-btn"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-white/40 transition-colors hover:bg-white/[0.06] hover:text-white"
          >
            <CaretDown size={16} />
          </button>
        </form>
          </>
        )}
      </motion.div>
    </div>
  );
}
