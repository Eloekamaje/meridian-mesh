import { useState } from "react";
import { Sparkle, CheckCircle, Circle, Flag, Question, TrendUp, Compass, Scales, Footprints } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel } from "./utils";

function Bloc({ titre, question, icon: Icon, couleur, children, testid }) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.015] p-4" data-testid={testid}>
      <div className="flex items-center gap-2">
        <Icon size={14} style={{ color: couleur }} />
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.18em] text-white/50">{titre}</div>
          <div className="font-code text-[9px] italic text-white/30">{question}</div>
        </div>
      </div>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

export default function OngletApercu({ cas, maj, setCas }) {
  const [actualisation, setActualisation] = useState(false);
  const questions = cas.questions || [];
  const ouvertes = questions.filter((q) => !q.resolue);
  const optionsATrancher = (cas.options || []).filter((o) => o.statut === "a_evaluer");
  const evolutions = cas.evolutions_recentes || [];
  const premiereVisite = !cas.derniere_visite;
  const histoRecents = [...(cas.historique || [])].slice(-3).reverse();

  const actualiserResume = async () => {
    setActualisation(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/resume`);
      setCas((c) => ({ ...c, resume: data.resume }));
      toast.success("Résumé actualisé par Flore");
    } catch {
      toast.error("Actualisation impossible");
    } finally {
      setActualisation(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="onglet-apercu">
      <Bloc titre="Situation" question="Pourquoi ce Case existe-t-il ?" icon={Compass} couleur="#3B82F6" testid="apercu-situation">
        <textarea
          value={cas.objectif || ""}
          onChange={(e) => setCas({ ...cas, objectif: e.target.value })}
          onBlur={(e) => maj({ objectif: e.target.value })}
          rows={2}
          placeholder="Pourquoi ce case existe-t-il ?"
          data-testid="case-objectif"
          className="w-full resize-none rounded-md border border-transparent bg-transparent px-0 py-0 text-sm leading-relaxed text-white/80 focus:border-white/10 focus:bg-black/30 focus:px-2 focus:outline-none"
        />
      </Bloc>

      <Bloc titre="Compréhension actuelle" question="Que savons-nous maintenant ?" icon={Sparkle} couleur="#22D3EE" testid="apercu-comprehension">
        <textarea
          value={cas.resume || ""}
          onChange={(e) => setCas({ ...cas, resume: e.target.value })}
          onBlur={(e) => maj({ resume: e.target.value })}
          rows={3}
          placeholder="Aucune compréhension consolidée — laissez Flore synthétiser."
          data-testid="case-resume"
          className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-white/75 focus:border-white/10 focus:bg-black/30 focus:px-2 focus:outline-none"
        />
        <button onClick={actualiserResume} disabled={actualisation} data-testid="actualiser-resume-btn" className="mt-1.5 flex items-center gap-1.5 rounded-md border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] px-2.5 py-1.5 text-[11px] font-semibold text-[#22D3EE] transition-colors hover:bg-[#22D3EE]/15 disabled:opacity-50">
          <Sparkle size={12} /> {actualisation ? "Flore synthétise…" : "Actualiser par Flore"}
        </button>
      </Bloc>

      <Bloc titre="Évolution récente" question="Qu'est-ce qui a changé depuis ma dernière visite ?" icon={TrendUp} couleur="#10B981" testid="apercu-evolution">
        {premiereVisite ? (
          <ul className="space-y-1">
            {histoRecents.map((h, i) => (
              <li key={i} className="flex gap-2 text-xs">
                <span className="shrink-0 font-code text-[9px] leading-5 text-white/30">{rel(h.quand)}</span>
                <span className="text-white/60">{h.texte}</span>
              </li>
            ))}
          </ul>
        ) : evolutions.length > 0 ? (
          <ul className="space-y-1">
            {evolutions.map((h, i) => (
              <li key={i} className="flex gap-2 text-xs" data-testid={`evolution-${i}`}>
                <span className="shrink-0 font-code text-[9px] leading-5 text-[#10B981]">{rel(h.quand)}</span>
                <span className="text-white/70">{h.texte}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-white/35">Rien de nouveau depuis votre dernière visite.</p>
        )}
      </Bloc>

      <Bloc titre="Questions ouvertes" question="Qu'est-ce qui reste à comprendre ?" icon={Question} couleur="#FBBF24" testid="apercu-questions">
        <ul className="space-y-1.5">
          {ouvertes.slice(0, 4).map((q) => {
            const i = questions.indexOf(q);
            return (
              <li key={i} className="flex items-center gap-2 text-xs text-white/75">
                <button onClick={() => maj({ questions: questions.map((x, xi) => (xi === i ? { ...x, resolue: true } : x)) })} data-testid={`apercu-question-${i}`} className="text-white/30 transition-colors hover:text-[#10B981]">
                  <Circle size={14} />
                </button>
                {q.texte}
              </li>
            );
          })}
          {ouvertes.length === 0 && (
            <li className="flex items-center gap-2 text-xs text-[#10B981]"><CheckCircle size={14} weight="fill" /> Toutes les questions sont levées.</li>
          )}
        </ul>
      </Bloc>

      <Bloc titre="Décisions attendues" question="Sur quoi un humain doit-il se prononcer ?" icon={Scales} couleur="#A78BFA" testid="apercu-decisions">
        {optionsATrancher.length > 0 ? (
          <ul className="space-y-1">
            {optionsATrancher.map((o) => (
              <li key={o.id} className="text-xs text-white/75" data-testid={`apercu-option-${o.id}`}>
                <Flag size={11} className="mr-1 inline text-[#A78BFA]" /> Trancher : {o.titre}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-white/35">Aucune décision en attente{optionsATrancher.length === 0 && (cas.decisions || []).length > 0 ? ` — dernière : ${cas.decisions[cas.decisions.length - 1].texte.slice(0, 80)}` : ""}.</p>
        )}
      </Bloc>

      <Bloc titre="Prochaine étape" question="Que devons-nous faire maintenant ?" icon={Footprints} couleur="#F97316" testid="apercu-prochaine-etape">
        <textarea
          value={cas.prochaine_etape || ""}
          onChange={(e) => setCas({ ...cas, prochaine_etape: e.target.value })}
          onBlur={(e) => maj({ prochaine_etape: e.target.value })}
          rows={2}
          placeholder={optionsATrancher.length > 0 ? `Suggestion : trancher « ${optionsATrancher[0].titre} »` : "Définir la prochaine étape…"}
          data-testid="case-prochaine-etape"
          className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-white/80 placeholder:italic placeholder:text-white/30 focus:border-white/10 focus:bg-black/30 focus:px-2 focus:outline-none"
        />
      </Bloc>
    </div>
  );
}
