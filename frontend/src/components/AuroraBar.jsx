import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Sparkle, PaperPlaneRight, FileText, X } from "@phosphor-icons/react";
import api from "@/lib/api";
import TrustBadges from "./TrustBadges";
import { couleurDomaine } from "@/lib/domaines";

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

export default function AuroraBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const contexte = contexteDepuis(location.pathname);
  const [question, setQuestion] = useState("");
  const [reponse, setReponse] = useState(null);
  const [questionPosee, setQuestionPosee] = useState("");
  const [chargement, setChargement] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const inputRef = useRef(null);

  useEffect(() => {
    setReponse(null);
    api.get(`/aurora/suggestions?contexte=${contexte}`).then((r) => setSuggestions(r.data)).catch(() => {});
  }, [contexte]);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const demander = async (q) => {
    const finale = (q ?? question).trim();
    if (!finale || chargement) return;
    setChargement(true);
    setQuestionPosee(finale);
    setQuestion("");
    try {
      const { data } = await api.post("/aurora/demander", { contexte, question: finale });
      setReponse(data);
    } catch {
      setReponse({ reponse: "Aurora est momentanément injoignable.", contributions: [], preuves: [], indicateurs: null });
    } finally {
      setChargement(false);
    }
  };

  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-40 w-[min(700px,92vw)] -translate-x-1/2" data-testid="aurora-bar">
      {reponse && (
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

      <div className="glass pointer-events-auto rounded-xl p-2.5">
        {!reponse && suggestions.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5 px-1">
            {suggestions.map((s, i) => (
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
        <form
          onSubmit={(e) => { e.preventDefault(); demander(); }}
          className="flex items-center gap-2"
        >
          <Sparkle size={18} weight="fill" className="ml-2 shrink-0 text-[#3B82F6]" />
          <input
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={chargement ? "Aurora croise les sources…" : "Demander à Aurora…  (⌘K)"}
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
        </form>
      </div>
    </div>
  );
}
