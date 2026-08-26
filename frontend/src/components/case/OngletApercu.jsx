import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkle, CheckCircle, Circle, Plus, Flask, FileText, Flag, CheckFat, Prohibit, Eye, Question, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel, catHistorique, FILTRES_ACTIVITE } from "./utils";

const TYPES_DECISION = { arbitrage: "Arbitrage", validation: "Validation", rejet: "Rejet", report: "Report" };
const RISQUES = { faible: ["faible", "#047857"], moyen: ["moyen", "#B45309"], eleve: ["élevé", "#B91C1C"] };
const STATUTS_OPTION = { a_evaluer: ["À évaluer", "#B45309"], recommandee: ["Recommandée par Flore", "#0E7490"], retenue: ["Retenue", "#047857"], ecartee: ["Écartée", "#64748B"] };

const STATUTS_HYP = {
  a_valider: ["À valider", "#B45309"],
  confirmee: ["Confirmée", "#047857"],
  rejetee: ["Rejetée", "#B91C1C"],
};
const CYCLE = ["a_valider", "confirmee", "rejetee"];

const COULEURS_CAT = { discussions: "#3730A3", flore: "#0E7490", decouvertes: "#6D28D9", decisions: "#B45309", mesh: "#64748B" };

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

// Aperçu = le rapport structuré du travail (pas des cartes) — décisions, actions et activité y sont consolidées
export default function OngletApercu({ cas, maj, setCas, situations }) {
  const navigate = useNavigate();
  const [actualisation, setActualisation] = useState(false);
  const [nouvelleQuestion, setNouvelleQuestion] = useState("");
  const [nouvelleHyp, setNouvelleHyp] = useState("");
  const [nouvelleInv, setNouvelleInv] = useState(null);
  const [producSynthese, setProducSynthese] = useState(false);
  const [formOption, setFormOption] = useState(null);
  const [formDecision, setFormDecision] = useState(null);
  const [filtre, setFiltre] = useState("tout");
  const [preuvesOuvertes, setPreuvesOuvertes] = useState(null);
  const [ignores, setIgnores] = useState({});

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

  const ajouterOption = async () => {
    if (!formOption?.titre?.trim()) return;
    try {
      const { data } = await api.post(`/cases/${cas.id}/options`, {
        titre: formOption.titre,
        description: formOption.description || "",
        impacts: (formOption.impacts || "").split(",").map((s) => s.trim()).filter(Boolean),
        risque: formOption.risque || "moyen",
      });
      setCas((c) => ({ ...c, options: [...(c.options || []), data] }));
      setFormOption(null);
      toast.success("Option ajoutée");
    } catch {
      toast.error("Ajout impossible");
    }
  };

  const trancher = async (o, verdict) => {
    try {
      if (verdict === "retenue") {
        const { data } = await api.post(`/cases/${cas.id}/decisions`, { texte: `Retenue : ${o.titre} — ${o.description || "option choisie parmi les scénarios du case."}`, type: "arbitrage" });
        setCas((c) => ({ ...c, decisions: [...(c.decisions || []), data] }));
        toast.success("Décision enregistrée — elle enrichit la mémoire du Mesh");
      } else {
        toast.info("Option écartée");
      }
      maj({ options: (cas.options || []).map((x) => (x.id === o.id ? { ...x, statut: verdict } : x)) });
    } catch {
      toast.error("Action impossible");
    }
  };

  const enregistrerDecision = async () => {
    if (!formDecision?.texte?.trim()) return;
    try {
      const { data } = await api.post(`/cases/${cas.id}/decisions`, formDecision);
      setCas((c) => ({ ...c, decisions: [...(c.decisions || []), data] }));
      setFormDecision(null);
      toast.success("Décision enregistrée — elle enrichit la mémoire du Mesh");
    } catch {
      toast.error("Enregistrement impossible");
    }
  };

  const promouvoirQuestion = (m) => {
    maj({ questions: [...(cas.questions || []), { texte: m.texte.slice(0, 140), resolue: false }] });
    toast.success("Ajouté comme question du travail");
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
          {/* Options considérées */}
          <div data-testid="case-options">
            <div className="flex items-center justify-between">
              <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Options considérées</span>
              <button onClick={() => setFormOption(formOption ? null : { risque: "moyen" })} data-testid="option-add-toggle" className="text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={14} /></button>
            </div>
            <div className="mt-2 space-y-2">
              {options.map((o) => {
                const r = RISQUES[o.risque] || [o.risque, "#71716D"];
                const so = STATUTS_OPTION[o.statut] || STATUTS_OPTION.a_evaluer;
                return (
                  <div key={o.id} className={`rounded-lg border p-3 ${o.statut === "ecartee" ? "border-[#E5E5E3] opacity-50" : "border-[#E5E5E3] bg-white"}`} data-testid={`option-${o.id}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2 text-xs font-semibold text-[#111110]">
                        {o.statut === "a_evaluer" && <Flag size={12} className="shrink-0 text-[#6D28D9]" data-testid={`apercu-option-${o.id}`} />}
                        {o.titre}
                      </span>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: r[1], borderColor: `${r[1]}44` }}>risque {r[0]}</span>
                        <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: so[1], borderColor: `${so[1]}44`, backgroundColor: `${so[1]}12` }} data-testid={`option-statut-${o.id}`}>{so[0]}</span>
                      </div>
                    </div>
                    {o.description && <p className="mt-1 text-[11px] leading-snug text-[#52524F]">{o.description}</p>}
                    {(o.impacts || []).length > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {o.impacts.map((im, i) => <li key={i} className="font-code text-[10px] text-[#71716D]">→ {im}</li>)}
                      </ul>
                    )}
                    {o.statut === "a_evaluer" || o.statut === "recommandee" ? (
                      <div className="mt-2 flex gap-1.5">
                        <button onClick={() => trancher(o, "retenue")} data-testid={`option-retenir-${o.id}`} className="flex items-center gap-1 rounded-md border border-[#047857]/40 bg-[#047857]/15 px-2 py-1 text-[10px] font-semibold text-[#047857] transition-colors hover:bg-[#047857]/25">
                          <CheckFat size={11} /> Retenir
                        </button>
                        <button onClick={() => trancher(o, "ecartee")} data-testid={`option-ecarter-${o.id}`} className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]">
                          <Prohibit size={11} /> Écarter
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {options.length === 0 && !formOption && <p className="text-sm text-[#71716D]">Aucune option pour l'instant.</p>}
            </div>
            {formOption && (
              <div className="mt-2.5 space-y-2 rounded-lg border border-[#3730A3]/25 bg-[#3730A3]/[0.03] p-3" data-testid="option-form">
                <input value={formOption.titre || ""} onChange={(e) => setFormOption({ ...formOption, titre: e.target.value })} placeholder="Titre de l'option…" data-testid="option-titre-input" className="w-full rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
                <input value={formOption.description || ""} onChange={(e) => setFormOption({ ...formOption, description: e.target.value })} placeholder="Description…" data-testid="option-description-input" className="w-full rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
                <input value={formOption.impacts || ""} onChange={(e) => setFormOption({ ...formOption, impacts: e.target.value })} placeholder="Impacts (séparés par des virgules)…" data-testid="option-impacts-input" className="w-full rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
                <div className="flex items-center gap-2">
                  <select value={formOption.risque} onChange={(e) => setFormOption({ ...formOption, risque: e.target.value })} data-testid="option-risque-select" className="rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-xs text-[#3F3F3C] focus:outline-none">
                    {Object.entries(RISQUES).map(([k, [l]]) => <option key={k} value={k} label={`Risque ${l}`} />)}
                  </select>
                  <button onClick={ajouterOption} data-testid="option-add-submit" className="rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#4338CA]">Ajouter</button>
                </div>
              </div>
            )}
          </div>

          {/* Décisions humaines */}
          <div className="mt-4" data-testid="case-decisions">
            <div className="flex items-center justify-between">
              <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Décisions humaines</span>
              <button onClick={() => setFormDecision(formDecision ? null : { type: "arbitrage" })} data-testid="decision-add-toggle" className="text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={14} /></button>
            </div>
            <ul className="mt-2 space-y-1.5 border-l-2 border-[#047857]/25 pl-3">
              {decisions.map((d, i) => (
                <li key={i} className="text-xs text-[#3F3F3C]" data-testid={`decision-${i}`}>
                  <span className="font-code text-[9px] uppercase tracking-wider text-[#B45309]">{TYPES_DECISION[d.type] || d.type}</span>
                  <span className="mx-1.5 font-code text-[9px] text-[#71716D]">{new Date(d.quand).toLocaleDateString("fr-FR")} · {d.par}</span>
                  <p className="mt-0.5 leading-relaxed"><span className="font-semibold text-[#047857]">Décidé</span> — {d.texte}</p>
                </li>
              ))}
              {decisions.length === 0 && !formDecision && <li className="text-sm text-[#71716D]">Aucune décision enregistrée.</li>}
            </ul>
            {formDecision && (
              <div className="mt-2.5 space-y-2 rounded-lg border border-[#B45309]/25 bg-[#B45309]/[0.03] p-3" data-testid="decision-form">
                <textarea value={formDecision.texte || ""} onChange={(e) => setFormDecision({ ...formDecision, texte: e.target.value })} rows={2} placeholder="Texte de la décision…" data-testid="decision-texte-input" className="w-full resize-none rounded-md border border-[#E5E5E3] bg-white px-2.5 py-1.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
                <div className="flex items-center gap-2">
                  <select value={formDecision.type} onChange={(e) => setFormDecision({ ...formDecision, type: e.target.value })} data-testid="decision-type-select" className="rounded-md border border-[#E5E5E3] bg-white px-2 py-1.5 text-xs text-[#3F3F3C] focus:outline-none">
                    {Object.entries(TYPES_DECISION).map(([k, l]) => <option key={k} value={k} label={l} />)}
                  </select>
                  <button onClick={enregistrerDecision} data-testid="decision-add-submit" className="rounded-md bg-[#B45309] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#92400E]">Enregistrer</button>
                </div>
              </div>
            )}
          </div>
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

        <Section numero="09" titre="Activité" testid="apercu-activite">
          <div className="flex flex-wrap gap-1.5" data-testid="activite-filtres">
            {FILTRES_ACTIVITE.map(([id, label]) => (
              <button
                key={id}
                onClick={() => setFiltre(id)}
                data-testid={`filtre-activite-${id}`}
                className={`rounded-full border px-3 py-1 font-code text-[10px] transition-colors ${
                  filtre === id ? "border-[#3730A3]/60 bg-[#3730A3]/10 text-[#312E81]" : "border-[#E5E5E3] text-[#71716D] hover:text-[#111110]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-3 space-y-3" data-testid="activite-flux">
            {visibles.map((e) => {
              if (e.historique) {
                return (
                  <div key={e.cle} className="flex items-start gap-2.5 px-1" data-testid={`activite-${e.cle}`}>
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: COULEURS_CAT[e.cat] }} />
                    <div>
                      <p className="text-xs text-[#52524F]">{e.historique.texte}</p>
                      <p className="mt-0.5 font-code text-[9px] text-[#71716D]">{new Date(e.quand).toLocaleString("fr-FR")}</p>
                    </div>
                  </div>
                );
              }
              const m = e.message;
              if (m.role === "utilisateur") {
                return (
                  <div key={e.cle} className="ml-10 rounded-xl rounded-br-sm bg-[#3730A3]/15 px-3.5 py-2.5" data-testid={`activite-${e.cle}`}>
                    <p className="text-sm text-[#111110]">{m.texte}</p>
                    <p className="mt-1 text-right font-code text-[9px] text-[#71716D]">{m.quand ? new Date(m.quand).toLocaleString("fr-FR") : ""}</p>
                  </div>
                );
              }
              if (ignores[e.cle]) return null;
              return (
                <div key={e.cle} className="mr-4 rounded-xl rounded-bl-sm border border-[#E5E5E3] bg-white px-3.5 py-3" data-testid={`activite-${e.cle}`}>
                  <div className="mb-1 flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#0E7490]/70">
                    <Sparkle size={10} weight="fill" /> Flore
                    {m.comportement && <span className="text-[#71716D]">· {m.comportement}</span>}
                  </div>
                  <p className="text-sm leading-relaxed text-[#3F3F3C]">{m.texte}</p>
                  {preuvesOuvertes === e.cle && (m.preuves || []).length > 0 && (
                    <ul className="mt-2 space-y-1 border-l-2 border-[#0E7490]/30 pl-2.5" data-testid={`preuves-${e.cle}`}>
                      {m.preuves.map((p, pi) => (
                        <li key={pi} className="flex items-baseline gap-2 text-xs text-[#52524F]">
                          <FileText size={11} className="shrink-0 translate-y-0.5 text-[#71716D]" />
                          <span><span className="font-code text-[10px] text-[#3F3F3C]">{p.source}</span> — {p.detail}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {/* Promotions : une réponse de Flore ne devient pas automatiquement une vérité du Travail */}
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    <button onClick={() => promouvoirQuestion(m)} data-testid={`promouvoir-question-${e.cle}`} className="flex items-center gap-1 rounded-md border border-[#B45309]/35 px-2 py-1 text-[10px] text-[#B45309] transition-colors hover:bg-[#B45309]/10">
                      <Question size={11} /> Ajouter comme question
                    </button>
                    <button onClick={() => promouvoirInvestigation(m)} data-testid={`promouvoir-investigation-${e.cle}`} className="flex items-center gap-1 rounded-md border border-[#6D28D9]/35 px-2 py-1 text-[10px] text-[#6D28D9] transition-colors hover:bg-[#6D28D9]/10">
                      <Flask size={11} /> Ouvrir une investigation
                    </button>
                    {(m.preuves || []).length > 0 && (
                      <button onClick={() => setPreuvesOuvertes(preuvesOuvertes === e.cle ? null : e.cle)} data-testid={`voir-preuves-${e.cle}`} className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2 py-1 text-[10px] text-[#52524F] transition-colors hover:text-[#111110]">
                        <Eye size={11} /> {preuvesOuvertes === e.cle ? "Masquer les preuves" : `Voir les preuves (${m.preuves.length})`}
                      </button>
                    )}
                    <button onClick={() => setIgnores((s) => ({ ...s, [e.cle]: true }))} data-testid={`ignorer-${e.cle}`} className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-[#71716D] transition-colors hover:text-[#52524F]">
                      <X size={11} /> Ignorer
                    </button>
                  </div>
                </div>
              );
            })}
            {visibles.length === 0 && <p className="py-4 text-xs text-[#71716D]">Aucune entrée dans cette catégorie.</p>}
          </div>
        </Section>

        <Section numero="10" titre="Prochaine étape" testid="apercu-prochaine-etape">
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
