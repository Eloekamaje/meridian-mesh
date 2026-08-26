import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkle, PaperPlaneRight, FileText, Question, Flask, Eye, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { catHistorique, FILTRES_ACTIVITE } from "./utils";

const COULEURS_CAT = { discussions: "#3B82F6", flore: "#22D3EE", decouvertes: "#A78BFA", decisions: "#FBBF24", mesh: "#94A3B8" };

export default function OngletActivite({ cas, maj, setCas }) {
  const navigate = useNavigate();
  const [filtre, setFiltre] = useState("tout");
  const [message, setMessage] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [preuvesOuvertes, setPreuvesOuvertes] = useState(null);
  const [ignores, setIgnores] = useState({});

  const entrees = useMemo(() => {
    const conv = (cas.conversation || []).map((m, i) => ({
      cle: `msg-${i}`,
      quand: m.quand,
      cat: m.role === "flore" ? "flore" : "discussions",
      message: m,
    }));
    const histo = (cas.historique || []).map((h, i) => ({ cle: `histo-${i}`, quand: h.quand, cat: catHistorique(h.texte), historique: h }));
    return [...conv, ...histo].sort((a, b) => (b.quand || "").localeCompare(a.quand || ""));
  }, [cas.conversation, cas.historique]);

  const visibles = filtre === "tout" ? entrees : entrees.filter((e) => e.cat === filtre);

  const envoyer = async () => {
    const texte = message.trim();
    if (!texte || envoi) return;
    setEnvoi(true);
    setMessage("");
    try {
      const { data } = await api.post(`/cases/${cas.id}/messages`, { texte });
      setCas((c) => ({ ...c, conversation: [...(c.conversation || []), data.utilisateur, data.flore] }));
    } catch {
      toast.error("Flore est momentanément injoignable");
      setMessage(texte);
    } finally {
      setEnvoi(false);
    }
  };

  const promouvoirQuestion = (m) => {
    maj({ questions: [...(cas.questions || []), { texte: m.texte.slice(0, 140), resolue: false }] });
    toast.success("Ajouté comme question du case");
  };

  const promouvoirInvestigation = async (m) => {
    try {
      const { data } = await api.post(`/cases/${cas.id}/investigations`, { texte: m.texte.slice(0, 120) });
      toast.success("Investigation ouverte et liée au case");
      navigate(`/investigations/${data.id}`);
    } catch {
      toast.error("Ouverture impossible");
    }
  };

  return (
    <div data-testid="onglet-activite">
      {/* Filtres */}
      <div className="flex flex-wrap gap-1.5" data-testid="activite-filtres">
        {FILTRES_ACTIVITE.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setFiltre(id)}
            data-testid={`filtre-activite-${id}`}
            className={`rounded-full border px-3 py-1.5 font-code text-[10px] transition-colors ${
              filtre === id ? "border-[#3B82F6]/60 bg-[#3B82F6]/15 text-white" : "border-white/10 text-white/45 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Flux unifié */}
      <div className="mt-4 space-y-3" data-testid="activite-flux">
        {visibles.map((e) => {
          if (e.historique) {
            return (
              <div key={e.cle} className="flex items-start gap-2.5 px-1" data-testid={`activite-${e.cle}`}>
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: COULEURS_CAT[e.cat] }} />
                <div>
                  <p className="text-xs text-white/60">{e.historique.texte}</p>
                  <p className="mt-0.5 font-code text-[9px] text-white/25">{new Date(e.quand).toLocaleString("fr-FR")}</p>
                </div>
              </div>
            );
          }
          const m = e.message;
          if (m.role === "utilisateur") {
            return (
              <div key={e.cle} className="ml-10 rounded-xl rounded-br-sm bg-[#3B82F6]/15 px-3.5 py-2.5" data-testid={`activite-${e.cle}`}>
                <p className="text-sm text-white/90">{m.texte}</p>
                <p className="mt-1 text-right font-code text-[9px] text-white/25">{m.quand ? new Date(m.quand).toLocaleString("fr-FR") : ""}</p>
              </div>
            );
          }
          if (ignores[e.cle]) return null;
          return (
            <div key={e.cle} className="mr-4 rounded-xl rounded-bl-sm border border-white/[0.07] bg-white/[0.02] px-3.5 py-3" data-testid={`activite-${e.cle}`}>
              <div className="mb-1 flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#22D3EE]/70">
                <Sparkle size={10} weight="fill" /> Flore
                {m.comportement && <span className="text-white/30">· {m.comportement}</span>}
              </div>
              <p className="text-sm leading-relaxed text-white/75">{m.texte}</p>

              {preuvesOuvertes === e.cle && (m.preuves || []).length > 0 && (
                <ul className="mt-2 space-y-1 border-l-2 border-[#22D3EE]/30 pl-2.5" data-testid={`preuves-${e.cle}`}>
                  {m.preuves.map((p, pi) => (
                    <li key={pi} className="flex items-baseline gap-2 text-xs text-white/60">
                      <FileText size={11} className="shrink-0 translate-y-0.5 text-white/30" />
                      <span><span className="font-code text-[10px] text-white/80">{p.source}</span> — {p.detail}</span>
                    </li>
                  ))}
                </ul>
              )}

              {/* Promotions : une réponse de Flore ne devient pas automatiquement une vérité du Case */}
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                <button onClick={() => promouvoirQuestion(m)} data-testid={`promouvoir-question-${e.cle}`} className="flex items-center gap-1 rounded-md border border-[#FBBF24]/35 px-2 py-1 text-[10px] text-[#FBBF24] transition-colors hover:bg-[#FBBF24]/10">
                  <Question size={11} /> Ajouter comme question
                </button>
                <button onClick={() => promouvoirInvestigation(m)} data-testid={`promouvoir-investigation-${e.cle}`} className="flex items-center gap-1 rounded-md border border-[#A78BFA]/35 px-2 py-1 text-[10px] text-[#A78BFA] transition-colors hover:bg-[#A78BFA]/10">
                  <Flask size={11} /> Ouvrir une investigation
                </button>
                {(m.preuves || []).length > 0 && (
                  <button onClick={() => setPreuvesOuvertes(preuvesOuvertes === e.cle ? null : e.cle)} data-testid={`voir-preuves-${e.cle}`} className="flex items-center gap-1 rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/60 transition-colors hover:text-white">
                    <Eye size={11} /> {preuvesOuvertes === e.cle ? "Masquer les preuves" : `Voir les preuves (${m.preuves.length})`}
                  </button>
                )}
                <button onClick={() => setIgnores((s) => ({ ...s, [e.cle]: true }))} data-testid={`ignorer-${e.cle}`} className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-white/35 transition-colors hover:text-white/60">
                  <X size={11} /> Ignorer
                </button>
              </div>
            </div>
          );
        })}
        {visibles.length === 0 && <p className="py-6 text-center text-xs text-white/30">Aucune entrée dans cette catégorie.</p>}
      </div>

      {/* Composer */}
      <form onSubmit={(e) => { e.preventDefault(); envoyer(); }} className="mt-4 flex items-center gap-2 border-t border-white/[0.07] pt-3">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Message humain ou question à Flore — dans le cadre de ce case…"
          disabled={envoi}
          data-testid="case-msg-input"
          className="h-10 flex-1 rounded-lg border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-white/35 focus:border-[#3B82F6]/60 focus:outline-none"
        />
        <button type="submit" disabled={envoi || !message.trim()} data-testid="case-msg-send" className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#3B82F6] text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-30">
          <PaperPlaneRight size={15} weight="fill" />
        </button>
      </form>
      {envoi && <p className="mt-1.5 font-code text-[10px] text-white/40" data-testid="case-flore-chargement">Flore croise les sources…</p>}
    </div>
  );
}
