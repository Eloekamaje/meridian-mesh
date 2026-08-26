import { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkle, CheckCircle, Circle, Plus, Flask, FileText, Flag } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel } from "./utils";

const STATUTS_HYP = {
  a_valider: ["À valider", "#B45309"],
  confirmee: ["Confirmée", "#047857"],
  rejetee: ["Rejetée", "#B91C1C"],
};
const CYCLE = ["a_valider", "confirmee", "rejetee"];

function Section({ numero, titre, children, testid }) {
  return (
    <section className="border-t border-[#E5E5E3] pt-5 first:border-t-0 first:pt-0" data-testid={testid}>
      <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#71716D]">
        <span className="mr-2 text-[#3730A3]">{numero}</span>{titre}
      </h2>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

// Aperçu = le rapport structuré du travail (pas des cartes)
export default function OngletApercu({ cas, maj, setCas, situations }) {
  const [actualisation, setActualisation] = useState(false);
  const [nouvelleQuestion, setNouvelleQuestion] = useState("");
  const [nouvelleHyp, setNouvelleHyp] = useState("");
  const [nouvelleInv, setNouvelleInv] = useState(null);
  const [producSynthese, setProducSynthese] = useState(false);

  const questions = cas.questions || [];
  const ouvertes = questions.filter((q) => !q.resolue);
  const hypotheses = cas.hypotheses || [];
  const options = cas.options || [];
  const aTrancher = options.filter((o) => o.statut === "a_evaluer");
  const decisions = cas.decisions || [];
  const evolutions = cas.evolutions_recentes || [];
  const histoRecents = [...(cas.historique || [])].slice(-4).reverse();
  const premiereVisite = !cas.derniere_visite;
  const dernierMessage = [...(cas.conversation || [])].reverse().find((m) => m.role === "flore") || [...(cas.conversation || [])].slice(-1)[0];
  const hypAValider = hypotheses.filter((h) => h.statut === "a_valider");

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
      toast.success("Investigation ouverte et liée au travail");
      setNouvelleInv(null);
      const { data } = await api.get(`/cases/${cas.id}`);
      setCas(data);
    } catch {
      toast.error("Ouverture impossible");
    }
  };

  const produireSynthese = async () => {
    setProducSynthese(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/livrables`);
      setCas((c) => ({ ...c, livrables: [...(c.livrables || []), data] }));
      toast.success("Synthèse produite");
    } catch {
      toast.error("Production impossible");
    } finally {
      setProducSynthese(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl" data-testid="onglet-apercu">
      <div className="space-y-7">
        {/* En-tête du rapport */}
        <header>
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#3730A3]">Rapport du travail</div>
          <p className="mt-1 font-code text-[10px] text-[#71716D]">
            Dernière activité {rel(cas.maj_le)} · {(cas.participants || []).length} participant{(cas.participants || []).length > 1 ? "s" : ""} · {(cas.conversation || []).length} échanges
          </p>
        </header>

        {/* Reprise — la session précédente en quatre lignes */}
        {!premiereVisite && (
          <Section numero="§" titre="Session précédente" testid="reprise-flore">
            <dl className="space-y-1.5 text-sm leading-relaxed text-[#3F3F3C]">
              <div className="flex gap-2"><dt className="w-32 shrink-0 font-code text-[10px] uppercase tracking-wider text-[#71716D]">Vous étiez ici</dt><dd data-testid="reprise-arret">{dernierMessage ? `« ${(dernierMessage.texte || "").slice(0, 140)}${(dernierMessage.texte || "").length > 140 ? "…" : ""} »` : "—"}</dd></div>
              <div className="flex gap-2"><dt className="w-32 shrink-0 font-code text-[10px] uppercase tracking-wider text-[#71716D]">Depuis</dt><dd data-testid="reprise-changements">{evolutions.length > 0 ? `${evolutions.length} évolution${evolutions.length > 1 ? "s" : ""} : ${evolutions[0].texte}` : "Rien de nouveau depuis votre dernière visite."}</dd></div>
              <div className="flex gap-2"><dt className="w-32 shrink-0 font-code text-[10px] uppercase tracking-wider text-[#71716D]">Reste incertain</dt><dd data-testid="reprise-incertain">{ouvertes.length > 0 || hypAValider.length > 0 ? `${ouvertes.length} question${ouvertes.length > 1 ? "s" : ""} · ${hypAValider.length} hypothèse${hypAValider.length > 1 ? "s" : ""} à valider` : "Aucune incertitude ouverte."}</dd></div>
              <div className="flex gap-2"><dt className="w-32 shrink-0 font-code text-[10px] uppercase tracking-wider text-[#71716D]">Prochaine étape</dt><dd className="font-semibold text-[#312E81]" data-testid="reprise-action">{cas.prochaine_etape || (aTrancher.length > 0 ? `Trancher « ${aTrancher[0].titre} »` : "Continuer la discussion avec Flore.")}</dd></div>
            </dl>
          </Section>
        )}

        <Section numero="01" titre="Situation" testid="apercu-situation">
          <textarea
            value={cas.objectif || ""}
            onChange={(e) => setCas({ ...cas, objectif: e.target.value })}
            onBlur={(e) => maj({ objectif: e.target.value })}
            rows={2}
            placeholder="Pourquoi ce travail existe-t-il ?"
            data-testid="case-objectif"
            className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-[#1d1d1b] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
        </Section>

        <Section numero="02" titre="Compréhension actuelle" testid="apercu-comprehension">
          <textarea
            value={cas.resume || ""}
            onChange={(e) => setCas({ ...cas, resume: e.target.value })}
            onBlur={(e) => maj({ resume: e.target.value })}
            rows={3}
            placeholder="Aucune compréhension consolidée — laissez Flore synthétiser."
            data-testid="case-resume"
            className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-[#1d1d1b] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
          <button onClick={actualiserResume} disabled={actualisation} data-testid="actualiser-resume-btn" className="mt-1 flex items-center gap-1.5 rounded-md border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-2.5 py-1.5 text-[11px] font-semibold text-[#0E7490] transition-colors hover:bg-[#0E7490]/15 disabled:opacity-50">
            <Sparkle size={12} /> {actualisation ? "Flore synthétise…" : "Actualiser par Flore"}
          </button>
        </Section>

        <Section numero="03" titre="Évolution récente" testid="apercu-evolution">
          <ul className="space-y-1.5">
            {(premiereVisite ? histoRecents : evolutions).map((h, i) => (
              <li key={i} className="flex gap-3 text-sm" data-testid={premiereVisite ? undefined : `evolution-${i}`}>
                <span className="w-20 shrink-0 pt-0.5 font-code text-[9px] uppercase tracking-wider text-[#71716D]">{rel(h.quand)}</span>
                <span className="text-[#3F3F3C]">{h.texte}</span>
              </li>
            ))}
            {(premiereVisite ? histoRecents : evolutions).length === 0 && <li className="text-sm text-[#71716D]">Rien de nouveau depuis votre dernière visite.</li>}
          </ul>
        </Section>

        <Section numero="04" titre="Décisions & options" testid="apercu-decisions">
          {aTrancher.length > 0 ? (
            <ul className="space-y-1.5">
              {aTrancher.map((o) => (
                <li key={o.id} className="flex items-center gap-2 text-sm text-[#3F3F3C]" data-testid={`apercu-option-${o.id}`}>
                  <Flag size={12} className="shrink-0 text-[#6D28D9]" /> À trancher : {o.titre}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-[#71716D]">Aucune option en attente d'évaluation.</p>
          )}
          {decisions.length > 0 && (
            <ul className="mt-2 space-y-1 border-l-2 border-[#047857]/25 pl-3">
              {decisions.slice(-3).map((d, i) => (
                <li key={i} className="text-xs text-[#52524F]"><span className="font-semibold text-[#047857]">Décidé</span> — {d.texte}</li>
              ))}
            </ul>
          )}
        </Section>

        <Section numero="05" titre={`Questions — ${questions.filter((q) => q.resolue).length}/${questions.length} levées`} testid="case-questions">
          <ul className="space-y-1.5">
            {questions.map((q, i) => (
              <li key={i} className="flex items-center gap-2.5 text-sm">
                <button
                  onClick={() => maj({ questions: questions.map((x, xi) => (xi === i ? { ...x, resolue: !x.resolue } : x)) })}
                  data-testid={`question-toggle-${i}`}
                  className={q.resolue ? "text-[#047857]" : "text-[#71716D] hover:text-[#52524F]"}
                >
                  {q.resolue ? <CheckCircle size={16} weight="fill" /> : <Circle size={16} />}
                </button>
                <span className={q.resolue ? "text-[#71716D] line-through" : "text-[#3F3F3C]"}>{q.texte}</span>
              </li>
            ))}
            {questions.length === 0 && <li className="text-sm text-[#71716D]">Aucune question consignée.</li>}
          </ul>
          <form onSubmit={(e) => { e.preventDefault(); if (!nouvelleQuestion.trim()) return; maj({ questions: [...questions, { texte: nouvelleQuestion.trim(), resolue: false }] }); setNouvelleQuestion(""); }} className="mt-2.5 flex gap-2">
            <input value={nouvelleQuestion} onChange={(e) => setNouvelleQuestion(e.target.value)} placeholder="Ajouter une question…" data-testid="question-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
            <button type="submit" data-testid="question-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 text-[11px] text-[#52524F] hover:text-[#111110]"><Plus size={12} /> Ajouter</button>
          </form>
        </Section>

        <Section numero="06" titre="Hypothèses" testid="case-hypotheses">
          <ul className="space-y-1.5">
            {hypotheses.map((h) => {
              const s = STATUTS_HYP[h.statut] || STATUTS_HYP.a_valider;
              return (
                <li key={h.id} className="flex items-center gap-2.5" data-testid={`hypothese-${h.id}`}>
                  <button
                    onClick={() => maj({ hypotheses: hypotheses.map((x) => (x.id === h.id ? { ...x, statut: CYCLE[(CYCLE.indexOf(h.statut) + 1) % 3] } : x)) })}
                    data-testid={`hypothese-statut-${h.id}`}
                    title="Changer le statut"
                    className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider transition-colors"
                    style={{ color: s[1], borderColor: `${s[1]}44`, backgroundColor: `${s[1]}12` }}
                  >
                    {s[0]}
                  </button>
                  <span className={`text-sm ${h.statut === "rejetee" ? "text-[#71716D] line-through" : "text-[#3F3F3C]"}`}>{h.texte}</span>
                </li>
              );
            })}
            {hypotheses.length === 0 && <li className="text-sm text-[#71716D]">Aucune hypothèse formulée.</li>}
          </ul>
          <form onSubmit={(e) => { e.preventDefault(); ajouterHypothese(); }} className="mt-2.5 flex gap-2">
            <input value={nouvelleHyp} onChange={(e) => setNouvelleHyp(e.target.value)} placeholder="Formuler une hypothèse…" data-testid="hypothese-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
            <button type="submit" data-testid="hypothese-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 text-[11px] text-[#52524F] hover:text-[#111110]"><Plus size={12} /> Ajouter</button>
          </form>
        </Section>

        <Section numero="07" titre="Investigations" testid="case-investigations">
          <ul className="space-y-1.5">
            {(cas.situations || []).map((sid) => {
              const s = (situations || []).find((x) => x.id === sid);
              return (
                <li key={sid}>
                  <Link to={`/investigations/${sid}`} data-testid={`case-situation-${sid}`} className="text-sm text-[#3730A3] hover:underline">
                    → {s?.titre || sid}
                  </Link>
                </li>
              );
            })}
            {(cas.situations || []).length === 0 && <li className="text-sm text-[#71716D]">Aucune investigation — une incertitude qui demande une recherche structurée peut en ouvrir une.</li>}
          </ul>
          {nouvelleInv === null ? (
            <button onClick={() => setNouvelleInv("")} data-testid="investigation-add-toggle" className="mt-2 flex items-center gap-1 font-code text-[10px] text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={12} /> Ouvrir une investigation</button>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); ouvrirInvestigation(); }} className="mt-2.5 flex gap-2" data-testid="investigation-form">
              <input value={nouvelleInv} onChange={(e) => setNouvelleInv(e.target.value)} placeholder="Objet de l'investigation…" data-testid="investigation-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
              <button type="submit" data-testid="investigation-add-submit" className="flex h-8 items-center gap-1 rounded-md border border-[#6D28D9]/40 px-2.5 text-[11px] text-[#6D28D9] hover:bg-[#6D28D9]/10"><Flask size={12} /> Ouvrir</button>
            </form>
          )}
        </Section>

        <Section numero="08" titre="Analyses & livrables" testid="case-livrables">
          <div className="space-y-3">
            {(cas.livrables || []).map((l) => (
              <article key={l.id} className="border-l-2 border-[#6D28D9]/30 pl-4" data-testid={`livrable-${l.id}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-[#111110]">{l.titre}</span>
                  <span className="font-code text-[9px] text-[#71716D]">{new Date(l.cree_le).toLocaleString("fr-FR")}</span>
                </div>
                <pre className="mt-1.5 whitespace-pre-wrap font-sans text-sm leading-relaxed text-[#52524F]">{l.contenu}</pre>
              </article>
            ))}
            {(cas.livrables || []).length === 0 && <p className="text-sm text-[#71716D]">Aucune analyse consignée.</p>}
          </div>
          <button onClick={produireSynthese} disabled={producSynthese} data-testid="produire-synthese-btn" className="mt-2.5 flex items-center gap-1.5 rounded-md border border-[#6D28D9]/40 bg-[#6D28D9]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#6D28D9] transition-colors hover:bg-[#6D28D9]/15 disabled:opacity-50">
            <FileText size={12} /> {producSynthese ? "Production…" : "Produire une synthèse"}
          </button>
        </Section>

        <Section numero="09" titre="Prochaine étape" testid="apercu-prochaine-etape">
          <textarea
            value={cas.prochaine_etape || ""}
            onChange={(e) => setCas({ ...cas, prochaine_etape: e.target.value })}
            onBlur={(e) => maj({ prochaine_etape: e.target.value })}
            rows={2}
            placeholder={aTrancher.length > 0 ? `Suggestion : trancher « ${aTrancher[0].titre} »` : "Définir la prochaine étape…"}
            data-testid="case-prochaine-etape"
            className="w-full resize-none rounded-md border border-transparent bg-transparent text-sm leading-relaxed text-[#1d1d1b] placeholder:italic placeholder:text-[#71716D] focus:border-[#E5E5E3] focus:bg-[#F7F7F6] focus:px-2 focus:outline-none"
          />
        </Section>
      </div>
    </div>
  );
}
