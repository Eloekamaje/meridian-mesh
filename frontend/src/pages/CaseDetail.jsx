import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { ArrowLeft, Compass, Sparkle, PaperPlaneRight, Plus, CheckCircle, Circle, FileText, Users } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";
import { TYPES_CASE, STATUTS_CASE } from "./Cases";

const TYPES_DECISION = { arbitrage: "Arbitrage", validation: "Validation", rejet: "Rejet", report: "Report" };
const RISQUES = { faible: ["faible", "#10B981"], moyen: ["moyen", "#FBBF24"], eleve: ["élevé", "#F87171"] };

export default function CaseDetail() {
  const { cid } = useParams();
  const navigate = useNavigate();
  const { mesh, jumeauPar } = useMesh();
  const { version } = usePerimetre();
  const { setSelection, ouvrirFlore } = useContexte();
  const [cas, setCas] = useState(null);
  const [situations, setSituations] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [message, setMessage] = useState("");
  const [envoiMsg, setEnvoiMsg] = useState(false);
  const [nouvelleQuestion, setNouvelleQuestion] = useState("");
  const [formOption, setFormOption] = useState(null);
  const [formDecision, setFormDecision] = useState(null);

  const charger = () => api.get(`/cases/${cid}`).then((r) => setCas(r.data)).catch((e) => setErreur(e.response?.data?.detail || "Case introuvable"));

  useEffect(() => {
    setCas(null);
    setErreur(null);
    charger();
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
  }, [cid, version]);

  const maj = async (champs) => {
    try {
      const { data } = await api.patch(`/cases/${cid}`, champs);
      setCas(data);
    } catch {
      toast.error("Mise à jour impossible");
    }
  };

  const envoyerMessage = async () => {
    const texte = message.trim();
    if (!texte || envoiMsg) return;
    setEnvoiMsg(true);
    setMessage("");
    try {
      const { data } = await api.post(`/cases/${cid}/messages`, { texte });
      setCas((c) => ({ ...c, conversation: [...(c.conversation || []), data.utilisateur, data.flore] }));
      if (data.reponse_complete?.commande_carte) {
        // Les commandes carte de Flore restent actives depuis un Case
      }
    } catch {
      toast.error("Flore est momentanément injoignable");
      setMessage(texte);
    } finally {
      setEnvoiMsg(false);
    }
  };

  const ajouterOption = async () => {
    if (!formOption?.titre?.trim()) return;
    try {
      const { data } = await api.post(`/cases/${cid}/options`, {
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

  const enregistrerDecision = async () => {
    if (!formDecision?.texte?.trim()) return;
    try {
      const { data } = await api.post(`/cases/${cid}/decisions`, formDecision);
      setCas((c) => ({ ...c, decisions: [...(c.decisions || []), data] }));
      setFormDecision(null);
      toast.success("Décision enregistrée — elle enrichit la mémoire du Mesh");
    } catch {
      toast.error("Enregistrement impossible");
    }
  };

  const produireSynthese = async () => {
    try {
      const { data } = await api.post(`/cases/${cid}/livrables`);
      setCas((c) => ({ ...c, livrables: [...(c.livrables || []), data] }));
      toast.success("Synthèse produite");
    } catch {
      toast.error("Production impossible");
    }
  };

  const voirAtlas = () => {
    setSelection(cas.jumeaux || []);
    navigate("/atlas");
  };

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="case-erreur">
        <p className="text-sm text-[#F87171]">{erreur}</p>
        <button onClick={() => navigate("/cases")} className="rounded-md border border-white/10 px-3 py-1.5 text-xs text-white/60 hover:text-white" data-testid="case-erreur-retour">← Retour aux cases</button>
      </div>
    );
  }
  if (!cas) return <div className="p-8 font-code text-[11px] text-white/40" data-testid="case-chargement">Chargement du case…</div>;

  const t = TYPES_CASE[cas.type] || [cas.type, "#9CA3AF"];
  const questions = cas.questions || [];

  return (
    <div className="flex h-full flex-col" data-testid="case-detail">
      {/* En-tête */}
      <div className="border-b border-white/[0.07] px-8 py-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/cases")} data-testid="case-retour-btn" className="flex items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1.5 text-xs text-white/55 transition-colors hover:text-white">
              <ArrowLeft size={13} /> Cases
            </button>
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: t[1], borderColor: `${t[1]}44`, backgroundColor: `${t[1]}12` }} data-testid="case-type">{t[0]}</span>
                <h1 className="font-display text-xl font-bold tracking-tight text-white" data-testid="case-titre">{cas.titre}</h1>
              </div>
              <p className="mt-0.5 flex items-center gap-1.5 font-code text-[10px] text-white/40">
                <Users size={11} /> {(cas.participants || []).join(" · ") || "—"} · créé le {new Date(cas.cree_le).toLocaleDateString("fr-FR")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select value={cas.statut} onChange={(e) => maj({ statut: e.target.value })} data-testid="case-statut-select" className="rounded-md border border-white/10 bg-black/50 px-2.5 py-1.5 text-xs text-white focus:outline-none">
              {Object.entries(STATUTS_CASE).map(([k, [l]]) => <option key={k} value={k} label={l} />)}
            </select>
            <button onClick={voirAtlas} data-testid="case-atlas-btn" className="flex items-center gap-1.5 rounded-md border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] px-3 py-1.5 text-xs text-[#22D3EE] transition-colors hover:bg-[#22D3EE]/15">
              <Compass size={13} /> Voir le contexte dans l'Atlas
            </button>
            <button onClick={() => ouvrirFlore()} data-testid="case-flore-btn" className="flex items-center gap-1.5 rounded-md border border-[#3B82F6]/40 bg-[#3B82F6]/[0.08] px-3 py-1.5 text-xs font-semibold text-[#7FB3FA] transition-colors hover:bg-[#3B82F6]/15">
              <Sparkle size={13} weight="fill" /> Flore
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[minmax(0,1fr)_330px]">
          {/* Colonne principale */}
          <div className="space-y-5">
            {/* Objectif */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-objectif-section">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Objectif</div>
              <textarea
                value={cas.objectif || ""}
                onChange={(e) => setCas({ ...cas, objectif: e.target.value })}
                onBlur={(e) => maj({ objectif: e.target.value })}
                rows={2}
                placeholder="Pourquoi ce case existe-t-il ?"
                data-testid="case-objectif"
                className="mt-2 w-full resize-none rounded-md border border-white/[0.08] bg-black/30 px-3 py-2 text-sm leading-relaxed text-white/80 focus:border-[#3B82F6]/50 focus:outline-none"
              />
            </section>

            {/* Questions */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-questions">
              <div className="flex items-center justify-between">
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Questions à lever</div>
                <span className="font-code text-[10px] text-white/30">{questions.filter((q) => q.resolue).length}/{questions.length} résolues</span>
              </div>
              <ul className="mt-2.5 space-y-1.5">
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
            </section>

            {/* Conversation Flore persistée */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-conversation">
              <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-white/40">
                <Sparkle size={12} className="text-[#3B82F6]" /> Conversation avec Flore
              </div>
              <div className="mt-3 space-y-3">
                {(cas.conversation || []).map((m, i) =>
                  m.role === "utilisateur" ? (
                    <div key={i} className="ml-10 rounded-xl rounded-br-sm bg-[#3B82F6]/15 px-3.5 py-2.5" data-testid={`case-msg-${i}`}>
                      <p className="text-sm text-white/90">{m.texte}</p>
                    </div>
                  ) : (
                    <div key={i} className="mr-10 rounded-xl rounded-bl-sm border border-white/[0.07] bg-white/[0.02] px-3.5 py-2.5" data-testid={`case-msg-${i}`}>
                      <div className="mb-1 flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#3B82F6]/70"><Sparkle size={10} weight="fill" /> Flore</div>
                      <p className="text-sm leading-relaxed text-white/75">{m.texte}</p>
                    </div>
                  )
                )}
                {(cas.conversation || []).length === 0 && <p className="text-xs text-white/30">Aucun échange pour l'instant — interrogez Flore dans le cadre de ce case.</p>}
                {envoiMsg && <p className="font-code text-[11px] text-white/40" data-testid="case-flore-chargement">Flore croise les sources…</p>}
              </div>
              <form onSubmit={(e) => { e.preventDefault(); envoyerMessage(); }} className="mt-3 flex items-center gap-2">
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Interroger Flore sur ce case…"
                  disabled={envoiMsg}
                  data-testid="case-msg-input"
                  className="h-10 flex-1 rounded-lg border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-white/35 focus:border-[#3B82F6]/60 focus:outline-none"
                />
                <button type="submit" disabled={envoiMsg || !message.trim()} data-testid="case-msg-send" className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#3B82F6] text-white transition-colors hover:bg-[#2F6FDB] disabled:opacity-30">
                  <PaperPlaneRight size={15} weight="fill" />
                </button>
              </form>
            </section>

            {/* Livrables */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-livrables">
              <div className="flex items-center justify-between">
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Livrables</div>
                <button onClick={produireSynthese} data-testid="produire-synthese-btn" className="flex items-center gap-1.5 rounded-md border border-[#A78BFA]/40 bg-[#A78BFA]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#A78BFA] transition-colors hover:bg-[#A78BFA]/15">
                  <FileText size={12} /> Produire une synthèse
                </button>
              </div>
              <div className="mt-2.5 space-y-2">
                {(cas.livrables || []).map((l) => (
                  <div key={l.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3" data-testid={`livrable-${l.id}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-white/85">{l.titre}</span>
                      <span className="font-code text-[9px] text-white/30">{new Date(l.cree_le).toLocaleString("fr-FR")}</span>
                    </div>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-xs leading-relaxed text-white/60">{l.contenu}</pre>
                  </div>
                ))}
                {(cas.livrables || []).length === 0 && <p className="text-xs text-white/30">Aucun livrable — Flore peut produire une synthèse à partir du contenu du case.</p>}
              </div>
            </section>
          </div>

          {/* Colonne latérale */}
          <div className="space-y-5">
            {/* Contexte SI */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-contexte-si">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Contexte SI — jumeaux mobilisés</div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {(cas.jumeaux || []).map((id) => {
                  const j = jumeauPar(id);
                  if (!j) return null;
                  return (
                    <Link key={id} to={`/jumeaux/${id}/revue`} data-testid={`case-jumeau-${id}`} className="rounded-full border px-2.5 py-1 font-code text-[10px] transition-opacity hover:opacity-80" style={{ color: couleurDomaine(j.domaine), borderColor: `${couleurDomaine(j.domaine)}55`, backgroundColor: `${couleurDomaine(j.domaine)}12` }}>
                      {j.nom}
                    </Link>
                  );
                })}
                {(cas.jumeaux || []).length === 0 && <span className="text-xs text-white/30">Aucun jumeau mobilisé.</span>}
              </div>
            </section>

            {/* Investigations liées */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-investigations">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Investigations liées</div>
              <ul className="mt-2.5 space-y-1.5">
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
            </section>

            {/* Options & scénarios */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-options">
              <div className="flex items-center justify-between">
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Options & scénarios</div>
                <button onClick={() => setFormOption(formOption ? null : { risque: "moyen" })} data-testid="option-add-toggle" className="text-white/40 transition-colors hover:text-white"><Plus size={14} /></button>
              </div>
              <div className="mt-2.5 space-y-2">
                {(cas.options || []).map((o) => {
                  const r = RISQUES[o.risque] || [o.risque, "#9CA3AF"];
                  return (
                    <div key={o.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3" data-testid={`option-${o.id}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-white/85">{o.titre}</span>
                        <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: r[1], borderColor: `${r[1]}44` }}>risque {r[0]}</span>
                      </div>
                      {o.description && <p className="mt-1 text-[11px] leading-snug text-white/55">{o.description}</p>}
                      {(o.impacts || []).length > 0 && (
                        <ul className="mt-1.5 space-y-0.5">
                          {o.impacts.map((im, i) => <li key={i} className="font-code text-[10px] text-white/45">→ {im}</li>)}
                        </ul>
                      )}
                      {o.statut === "recommandee" && <div className="mt-1.5 font-code text-[9px] uppercase tracking-wider text-[#FBBF24]">recommandée par Flore</div>}
                    </div>
                  );
                })}
                {(cas.options || []).length === 0 && !formOption && <p className="text-xs text-white/30">Aucune option pour l'instant.</p>}
              </div>
              {formOption && (
                <div className="mt-2.5 space-y-2 rounded-lg border border-[#3B82F6]/25 bg-[#3B82F6]/[0.03] p-3" data-testid="option-form">
                  <input value={formOption.titre || ""} onChange={(e) => setFormOption({ ...formOption, titre: e.target.value })} placeholder="Titre de l'option…" data-testid="option-titre-input" className="w-full rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
                  <input value={formOption.description || ""} onChange={(e) => setFormOption({ ...formOption, description: e.target.value })} placeholder="Description…" data-testid="option-description-input" className="w-full rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
                  <input value={formOption.impacts || ""} onChange={(e) => setFormOption({ ...formOption, impacts: e.target.value })} placeholder="Impacts (séparés par des virgules)…" data-testid="option-impacts-input" className="w-full rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
                  <div className="flex items-center gap-2">
                    <select value={formOption.risque} onChange={(e) => setFormOption({ ...formOption, risque: e.target.value })} data-testid="option-risque-select" className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white/70 focus:outline-none">
                      {Object.entries(RISQUES).map(([k, [l]]) => <option key={k} value={k} label={`Risque ${l}`} />)}
                    </select>
                    <button onClick={ajouterOption} data-testid="option-add-submit" className="rounded-md bg-[#3B82F6] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#2F6FDB]">Ajouter</button>
                  </div>
                </div>
              )}
            </section>

            {/* Décisions */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-decisions">
              <div className="flex items-center justify-between">
                <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Décisions</div>
                <button onClick={() => setFormDecision(formDecision ? null : { type: "arbitrage" })} data-testid="decision-add-toggle" className="text-white/40 transition-colors hover:text-white"><Plus size={14} /></button>
              </div>
              <div className="mt-2.5 space-y-2">
                {(cas.decisions || []).map((d, i) => (
                  <div key={i} className="rounded-lg border border-[#FBBF24]/20 bg-[#FBBF24]/[0.04] p-3" data-testid={`decision-${i}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-code text-[9px] uppercase tracking-wider text-[#FBBF24]">{TYPES_DECISION[d.type] || d.type}</span>
                      <span className="font-code text-[9px] text-white/30">{new Date(d.quand).toLocaleDateString("fr-FR")}</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-white/80">{d.texte}</p>
                  </div>
                ))}
                {(cas.decisions || []).length === 0 && !formDecision && <p className="text-xs text-white/30">Aucune décision enregistrée.</p>}
              </div>
              {formDecision && (
                <div className="mt-2.5 space-y-2 rounded-lg border border-[#FBBF24]/25 bg-[#FBBF24]/[0.03] p-3" data-testid="decision-form">
                  <textarea value={formDecision.texte || ""} onChange={(e) => setFormDecision({ ...formDecision, texte: e.target.value })} rows={2} placeholder="Texte de la décision…" data-testid="decision-texte-input" className="w-full resize-none rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-white/30 focus:outline-none" />
                  <div className="flex items-center gap-2">
                    <select value={formDecision.type} onChange={(e) => setFormDecision({ ...formDecision, type: e.target.value })} data-testid="decision-type-select" className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white/70 focus:outline-none">
                      {Object.entries(TYPES_DECISION).map(([k, l]) => <option key={k} value={k} label={l} />)}
                    </select>
                    <button onClick={enregistrerDecision} data-testid="decision-add-submit" className="rounded-md bg-[#FBBF24] px-3 py-1.5 text-[11px] font-semibold text-black hover:bg-[#E5A910]">Enregistrer</button>
                  </div>
                </div>
              )}
            </section>

            {/* Historique */}
            <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-historique">
              <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Historique</div>
              <ul className="mt-2.5 space-y-2">
                {[...(cas.historique || [])].reverse().map((h, i) => (
                  <li key={i} className="flex gap-2 text-[11px]">
                    <span className="shrink-0 font-code text-[9px] leading-5 text-white/30">{new Date(h.quand).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })}</span>
                    <span className="text-white/60">{h.texte}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
