import { useState } from "react";
import { Sparkle, CheckCircle, Circle, Flag, Question, TrendUp, Compass, Scales, Footprints } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel } from "./utils";
import ObjetsTravail from "./ObjetsTravail";

function Bloc({ titre, question, icon: Icon, couleur, children, testid }) {
  return (
    <div className="rounded-xl border border-[#E5E5E3] bg-white p-4" data-testid={testid}>
      <div className="flex items-center gap-2">
        <Icon size={14} style={{ color: couleur }} />
        <div>
          <div className="font-code text-[10px] uppercase tracking-[0.18em] text-[#52524F]">{titre}</div>
          <div className="font-code text-[9px] italic text-[#71716D]">{question}</div>
        </div>
      </div>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

export default function OngletApercu({ cas, maj, setCas, situations }) {
  const [actualisation, setActualisation] = useState(false);
  const questions = cas.questions || [];
  const ouvertes = questions.filter((q) => !q.resolue);
  const optionsATrancher = (cas.options || []).filter((o) => o.statut === "a_evaluer");
  const evolutions = cas.evolutions_recentes || [];
  const premiereVisite = !cas.derniere_visite;
  const histoRecents = [...(cas.historique || [])].slice(-3).reverse();
  const hypAValider = (cas.hypotheses || []).filter((h) => h.statut === "a_valider");
  const dernierMessage = [...(cas.conversation || [])].reverse().find((m) => m.role === "flore") || [...(cas.conversation || [])].slice(-1)[0];

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
    <div data-testid="onglet-apercu">
      <div className="grid gap-4 lg:grid-cols-2">
        <Bloc titre="Situation" question="Pourquoi ce travail existe-t-il ?" icon={Compass} couleur="#3730A3" testid="apercu-situation">
          <textarea
            value={cas.objectif || ""}
            onChange={(e) => setCas({ ...cas, objectif: e.target.value })}
            onBlur={(e) => maj({ objectif: e.target.value })}
            rows={2}
            placeholder="Pourquoi ce travail existe-t-il ?"
            data-testid="case-objectif"
            className="w-full resize-none rounded-md border border-transparent bg-transparent px-0 py-0 text-sm leading-relaxed text-[#3F3F3C] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
        </Bloc>

        <Bloc titre="Compréhension actuelle" question="Que savons-nous maintenant ?" icon={Sparkle} couleur="#0E7490" testid="apercu-comprehension">
          <textarea
            value={cas.resume || ""}
            onChange={(e) => setCas({ ...cas, resume: e.target.value })}
            onBlur={(e) => maj({ resume: e.target.value })}
            rows={3}
            placeholder="Aucune compréhension consolidée — laissez Flore synthétiser."
            data-testid="case-resume"
            className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-[#3F3F3C] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
          <button onClick={actualiserResume} disabled={actualisation} data-testid="actualiser-resume-btn" className="mt-1.5 flex items-center gap-1.5 rounded-md border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-2.5 py-1.5 text-[11px] font-semibold text-[#0E7490] transition-colors hover:bg-[#0E7490]/15 disabled:opacity-50">
            <Sparkle size={12} /> {actualisation ? "Flore synthétise…" : "Actualiser par Flore"}
          </button>
        </Bloc>

        <Bloc titre="Évolution récente" question="Qu'est-ce qui a changé depuis ma dernière visite ?" icon={TrendUp} couleur="#047857" testid="apercu-evolution">
          {premiereVisite ? (
            <ul className="space-y-1">
              {histoRecents.map((h, i) => (
                <li key={i} className="flex gap-2 text-xs">
                  <span className="shrink-0 font-code text-[9px] leading-5 text-[#71716D]">{rel(h.quand)}</span>
                  <span className="text-[#52524F]">{h.texte}</span>
                </li>
              ))}
            </ul>
          ) : evolutions.length > 0 ? (
            <ul className="space-y-1">
              {evolutions.map((h, i) => (
                <li key={i} className="flex gap-2 text-xs" data-testid={`evolution-${i}`}>
                  <span className="shrink-0 font-code text-[9px] leading-5 text-[#047857]">{rel(h.quand)}</span>
                  <span className="text-[#3F3F3C]">{h.texte}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[#71716D]">Rien de nouveau depuis votre dernière visite.</p>
          )}
        </Bloc>

        <Bloc titre="Décisions attendues" question="Sur quoi un humain doit-il se prononcer ?" icon={Scales} couleur="#6D28D9" testid="apercu-decisions">
          {optionsATrancher.length > 0 ? (
            <ul className="space-y-1">
              {optionsATrancher.map((o) => (
                <li key={o.id} className="text-xs text-[#3F3F3C]" data-testid={`apercu-option-${o.id}`}>
                  <Flag size={11} className="mr-1 inline text-[#6D28D9]" /> Trancher : {o.titre}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[#71716D]">Aucune décision en attente{optionsATrancher.length === 0 && (cas.decisions || []).length > 0 ? ` — dernière : ${cas.decisions[cas.decisions.length - 1].texte.slice(0, 80)}` : ""}.</p>
          )}
        </Bloc>

        <Bloc titre="Prochaine étape" question="Que devons-nous faire maintenant ?" icon={Footprints} couleur="#C2410C" testid="apercu-prochaine-etape">
          <textarea
            value={cas.prochaine_etape || ""}
            onChange={(e) => setCas({ ...cas, prochaine_etape: e.target.value })}
            onBlur={(e) => maj({ prochaine_etape: e.target.value })}
            rows={2}
            placeholder={optionsATrancher.length > 0 ? `Suggestion : trancher « ${optionsATrancher[0].titre} »` : "Définir la prochaine étape…"}
            data-testid="case-prochaine-etape"
            className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-[#3F3F3C] placeholder:italic placeholder:text-[#71716D] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
        </Bloc>
      </div>

      {/* Objets structurés du travail (déplacés de l'onglet Conversation) */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2" data-testid="apercu-objets">
        <ObjetsTravail cas={cas} maj={maj} setCas={setCas} situations={situations} />
      </div>
    </div>
  );
}
