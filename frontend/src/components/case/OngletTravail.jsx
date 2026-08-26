import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, CheckCircle, Circle, FileText, Flask } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const STATUTS_HYP = {
  a_valider: ["À valider", "#FBBF24"],
  confirmee: ["Confirmée", "#10B981"],
  rejetee: ["Rejetée", "#F87171"],
};
const CYCLE = ["a_valider", "confirmee", "rejetee"];

function Carte({ titre, children, testid, action }) {
  return (
    <section className="rounded-xl border border-white/[0.07] p-4" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">{titre}</div>
        {action}
      </div>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

export default function OngletTravail({ cas, maj, setCas, situations }) {
  const [nouvelleQuestion, setNouvelleQuestion] = useState("");
  const [nouvelleHyp, setNouvelleHyp] = useState("");
  const [nouvelleInv, setNouvelleInv] = useState(null);
  const questions = cas.questions || [];
  const hypotheses = cas.hypotheses || [];

  const ajouterHypothese = async () => {
    if (!nouvelleHyp.trim()) return;
    try {
      const { data } = await api.post(`/cases/${cas.id}/hypotheses`, { texte: nouvelleHyp.trim() });
      setCas((c) => ({ ...c, hypotheses: [...(c.hypotheses || []), data] }));
      setNouvelleHyp("");
      toast.success("Hypothèse ajoutée");
    } catch {
      toast.error("Ajout impossible");
    }
  };

  const ouvrirInvestigation = async () => {
    if (!nouvelleInv?.trim()) return;
    try {
      await api.post(`/cases/${cas.id}/investigations`, { texte: nouvelleInv.trim() });
      toast.success("Investigation ouverte et liée au case");
      setNouvelleInv(null);
      const { data } = await api.get(`/cases/${cas.id}`);
      setCas(data);
    } catch {
      toast.error("Ouverture impossible");
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="onglet-travail">
      <Carte titre={`Questions — ${questions.filter((q) => q.resolue).length}/${questions.length} levées`} testid="case-questions">
        <ul className="space-y-1.5">
          {questions.map((q, i) => (
            <li key={i} className="flex items-center gap-2.5 text-sm">
              <button
                onClick={() => maj({ questions: questions.map((x, xi) => (xi === i ? { ...x, resolue: !x.resolue } : x)) })}
                data-testid={`question-toggle-${i}`}
                className={q.resolue ? "text-[#10B981]" : "text-white/30 hover:text-white/60"}
              >
                {q.resolue ? <CheckCircle size={16} weight="fill" /> : <Circle size={16} />}
              </button>
              <span className={q.resolue ? "text-white/40 line-through" : "text-white/80"}>{q.texte}</span>
            </li>
          ))}
        </ul>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!nouvelleQuestion.trim()) return;
            maj({ questions: [...questions, { texte: nouvelleQuestion.trim(), resolue: false }] });
            setNouvelleQuestion("");
          }}
          className="mt-2.5 flex gap-2"
        >
          <input value={nouvelleQuestion} onChange={(e) => setNouvelleQuestion(e.target.value)} placeholder="Ajouter une question…" data-testid="question-add-input" className="h-8 flex-1 rounded-md border border-white/10 bg-black/40 px-2.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
          <button type="submit" data-testid="question-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-white/15 px-2.5 text-[11px] text-white/60 hover:text-white"><Plus size={12} /> Ajouter</button>
        </form>
      </Carte>

      <Carte titre="Hypothèses" testid="case-hypotheses">
        <ul className="space-y-1.5">
          {hypotheses.map((h, i) => {
            const s = STATUTS_HYP[h.statut] || STATUTS_HYP.a_valider;
            return (
              <li key={h.id} className="flex items-center gap-2.5 rounded-lg border border-white/[0.06] px-2.5 py-2" data-testid={`hypothese-${h.id}`}>
                <button
                  onClick={() => maj({ hypotheses: hypotheses.map((x) => (x.id === h.id ? { ...x, statut: CYCLE[(CYCLE.indexOf(h.statut) + 1) % 3] } : x)) })}
                  data-testid={`hypothese-statut-${h.id}`}
                  title="Changer le statut"
                  className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider transition-colors"
                  style={{ color: s[1], borderColor: `${s[1]}44`, backgroundColor: `${s[1]}12` }}
                >
                  {s[0]}
                </button>
                <span className={`text-xs ${h.statut === "rejetee" ? "text-white/35 line-through" : "text-white/75"}`}>{h.texte}</span>
              </li>
            );
          })}
          {hypotheses.length === 0 && <li className="text-xs text-white/30">Aucune hypothèse formulée.</li>}
        </ul>
        <form onSubmit={(e) => { e.preventDefault(); ajouterHypothese(); }} className="mt-2.5 flex gap-2">
          <input value={nouvelleHyp} onChange={(e) => setNouvelleHyp(e.target.value)} placeholder="Formuler une hypothèse…" data-testid="hypothese-add-input" className="h-8 flex-1 rounded-md border border-white/10 bg-black/40 px-2.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
          <button type="submit" data-testid="hypothese-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-white/15 px-2.5 text-[11px] text-white/60 hover:text-white"><Plus size={12} /> Ajouter</button>
        </form>
      </Carte>

      <Carte
        titre="Investigations"
        testid="case-investigations"
        action={<button onClick={() => setNouvelleInv(nouvelleInv === null ? "" : null)} data-testid="investigation-add-toggle" className="flex items-center gap-1 font-code text-[10px] text-white/40 transition-colors hover:text-white"><Plus size={12} /> Ouvrir une investigation</button>}
      >
        <ul className="space-y-1.5">
          {(cas.situations || []).map((sid) => {
            const s = situations.find((x) => x.id === sid);
            return (
              <li key={sid}>
                <Link to={`/investigations/${sid}`} data-testid={`case-situation-${sid}`} className="text-xs text-[#3B82F6] hover:underline">
                  → {s?.titre || sid}
                </Link>
              </li>
            );
          })}
          {(cas.situations || []).length === 0 && <li className="text-xs text-white/30">Aucune investigation — une incertitude qui demande une recherche structurée peut en ouvrir une.</li>}
        </ul>
        {nouvelleInv !== null && (
          <form onSubmit={(e) => { e.preventDefault(); ouvrirInvestigation(); }} className="mt-2.5 flex gap-2" data-testid="investigation-form">
            <input value={nouvelleInv} onChange={(e) => setNouvelleInv(e.target.value)} placeholder="Objet de l'investigation…" data-testid="investigation-add-input" className="h-8 flex-1 rounded-md border border-white/10 bg-black/40 px-2.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
            <button type="submit" data-testid="investigation-add-submit" className="flex h-8 items-center gap-1 rounded-md border border-[#A78BFA]/40 px-2.5 text-[11px] text-[#A78BFA] hover:bg-[#A78BFA]/10"><Flask size={12} /> Ouvrir</button>
          </form>
        )}
      </Carte>

      <Carte titre="Analyses & livrables" testid="case-livrables" action={<ProduireSynthese cas={cas} setCas={setCas} />}>
        <div className="space-y-2">
          {(cas.livrables || []).map((l) => (
            <div key={l.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3" data-testid={`livrable-${l.id}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white/85">{l.titre}</span>
                <span className="font-code text-[9px] text-white/30">{new Date(l.cree_le).toLocaleString("fr-FR")}</span>
              </div>
              <pre className="mt-2 whitespace-pre-wrap font-sans text-xs leading-relaxed text-white/60">{l.contenu}</pre>
            </div>
          ))}
          {(cas.livrables || []).length === 0 && <p className="text-xs text-white/30">Aucune analyse — Flore peut produire une synthèse du case.</p>}
        </div>
      </Carte>
    </div>
  );
}

function ProduireSynthese({ cas, setCas }) {
  const [envoi, setEnvoi] = useState(false);
  return (
    <button
      onClick={async () => {
        setEnvoi(true);
        try {
          const { data } = await api.post(`/cases/${cas.id}/livrables`);
          setCas((c) => ({ ...c, livrables: [...(c.livrables || []), data] }));
          toast.success("Synthèse produite");
        } catch {
          toast.error("Production impossible");
        } finally {
          setEnvoi(false);
        }
      }}
      data-testid="produire-synthese-btn"
      className="flex items-center gap-1.5 rounded-md border border-[#A78BFA]/40 bg-[#A78BFA]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#A78BFA] transition-colors hover:bg-[#A78BFA]/15"
    >
      <FileText size={12} /> {envoi ? "Production…" : "Produire une synthèse"}
    </button>
  );
}
