import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, CheckCircle, Circle, FileText, Flask, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { rel } from "./utils";

const STATUTS_HYP = {
  a_valider: ["À valider", "#B45309"],
  confirmee: ["Confirmée", "#047857"],
  rejetee: ["Rejetée", "#B91C1C"],
};
const CYCLE = ["a_valider", "confirmee", "rejetee"];

function Carte({ titre, children, testid, action }) {
  return (
    <section className="rounded-xl border border-[#E5E5E3] p-4" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">{titre}</div>
        {action}
      </div>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

export default function OngletTravail({ cas, maj, setCas, situations }) {
  const [nouvelleQuestion, setNouvelleQuestion] = useState("");
  const [nouveauMsg, setNouveauMsg] = useState("");
  const [envoiMsg, setEnvoiMsg] = useState(false);
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

  const dernierMessage = [...(cas.conversation || [])].reverse().find((m) => m.role === "flore") || [...(cas.conversation || [])].slice(-1)[0];
  const evolutions = cas.evolutions_recentes || [];
  const hypAValider = hypotheses.filter((h) => h.statut === "a_valider");
  const optionsATrancher = (cas.options || []).filter((o) => o.statut === "a_evaluer");
  const premiereVisite = !cas.derniere_visite;

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="onglet-travail">
      {/* Où en sommes-nous ? — la reprise précède le travail */}
      {!premiereVisite && (
        <div className="rounded-xl border border-[#3730A3]/25 bg-[#EEECFA] p-4 lg:col-span-2" data-testid="reprise-flore">
          <div className="flex items-center gap-2">
            <Sparkle size={14} weight="fill" className="text-[#3730A3]" />
            <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#312E81]">Où en sommes-nous ? — Flore vous replace</span>
            {cas.derniere_visite && <span className="font-code text-[9px] text-[#71716D]">dernière visite {rel(cas.derniere_visite)}</span>}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <div className="font-code text-[9px] uppercase tracking-wider text-[#71716D]">Vous étiez ici</div>
              <p className="mt-1 text-xs leading-snug text-[#3F3F3C]" data-testid="reprise-arret">
                {dernierMessage ? `Dernier échange : « ${(dernierMessage.texte || "").slice(0, 110)}${(dernierMessage.texte || "").length > 110 ? "…" : ""} »` : "Le travail n'a pas encore de conversation."}
              </p>
            </div>
            <div>
              <div className="font-code text-[9px] uppercase tracking-wider text-[#71716D]">Depuis</div>
              <p className="mt-1 text-xs leading-snug text-[#3F3F3C]" data-testid="reprise-changements">
                {evolutions.length > 0 ? `${evolutions.length} évolution${evolutions.length > 1 ? "s" : ""} : ${evolutions[0].texte}` : "Rien de nouveau depuis votre dernière visite."}
              </p>
            </div>
            <div>
              <div className="font-code text-[9px] uppercase tracking-wider text-[#71716D]">Reste incertain</div>
              <p className="mt-1 text-xs leading-snug text-[#3F3F3C]" data-testid="reprise-incertain">
                {hypAValider.length > 0 || questions.some((q) => !q.resolue)
                  ? `${questions.filter((q) => !q.resolue).length} question${questions.filter((q) => !q.resolue).length > 1 ? "s" : ""} ouverte${questions.filter((q) => !q.resolue).length > 1 ? "s" : ""} · ${hypAValider.length} hypothèse${hypAValider.length > 1 ? "s" : ""} à valider`
                  : "Aucune incertitude ouverte."}
              </p>
            </div>
            <div>
              <div className="font-code text-[9px] uppercase tracking-wider text-[#71716D]">Prochaine étape</div>
              <p className="mt-1 text-xs font-semibold leading-snug text-[#312E81]" data-testid="reprise-action">
                {cas.prochaine_etape || (optionsATrancher.length > 0 ? `Trancher « ${optionsATrancher[0].titre} »` : "Continuer la discussion avec Flore.")}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* La conversation durable — le fil EST le contenu du travail */}
      <div className="rounded-xl border border-[#E5E5E3] bg-white p-4 lg:col-span-2" data-testid="case-conversation">
        <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.18em] text-[#52524F]">
          <Sparkle size={11} weight="fill" className="text-[#3730A3]" /> Conversation avec Flore
        </div>
        <div className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
          {(cas.conversation || []).map((m, i) =>
            m.role === "utilisateur" ? (
              <p key={i} className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-[#EEECFA] px-3.5 py-2 text-xs text-[#1d1d1b]" data-testid={`case-msg-${i}`}>
                {m.texte}
              </p>
            ) : (
              <div key={i} data-testid={`case-msg-${i}`}>
                <p className="whitespace-pre-line text-xs leading-relaxed text-[#3F3F3C]">{m.texte}</p>
                {(m.contributions || []).length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.contributions.map((c, k) => (
                      <span key={k} className="rounded-full border border-[#E5E5E3] bg-[#F7F7F6] px-2 py-0.5 font-code text-[9px] text-[#52524F]">
                        {c.jumeau} — {c.texte}
                      </span>
                    ))}
                  </div>
                )}
                {(m.propositions || []).length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.propositions.map((p, k) => (
                      <button key={k} onClick={() => { setNouveauMsg(p.question || p.label); }} data-testid={`case-prop-${i}-${k}`}
                        className="rounded-full border border-[#E5E5E3] bg-white px-2.5 py-1 text-[10px] text-[#52524F] transition-colors hover:border-[#3730A3]/40 hover:text-[#3730A3]">
                        {p.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          )}
          {(cas.conversation || []).length === 0 && (
            <p className="text-xs text-[#71716D]">La conversation est la mémoire du travail — commencez ci-dessous.</p>
          )}
          {envoiMsg && <p className="font-code text-[10px] text-[#71716D]">Flore consulte le Mesh…</p>}
        </div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const q = nouveauMsg.trim();
            if (!q || envoiMsg) return;
            setEnvoiMsg(true);
            setNouveauMsg("");
            try {
              const { data } = await api.post(`/cases/${cas.id}/messages`, { texte: q });
              setCas((c) => ({ ...c, conversation: [...(c.conversation || []), data.utilisateur, data.flore] }));
            } catch {
              toast.error("Message impossible");
            } finally {
              setEnvoiMsg(false);
            }
          }}
          className="mt-3 flex gap-2 border-t border-[#F0F0EE] pt-3"
        >
          <input
            value={nouveauMsg}
            onChange={(e) => setNouveauMsg(e.target.value)}
            placeholder="Continuez avec Flore — chaque échange enrichit la mémoire du travail…"
            data-testid="case-msg-input"
            className="h-9 flex-1 rounded-md border border-[#E5E5E3] bg-white px-3 text-xs text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/50 focus:outline-none"
          />
          <button type="submit" disabled={envoiMsg || !nouveauMsg.trim()} data-testid="case-msg-send-btn" className="h-9 rounded-md bg-[#3730A3] px-4 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-40">
            Envoyer
          </button>
        </form>
      </div>

      <Carte titre={`Questions — ${questions.filter((q) => q.resolue).length}/${questions.length} levées`} testid="case-questions">
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
          <input value={nouvelleQuestion} onChange={(e) => setNouvelleQuestion(e.target.value)} placeholder="Ajouter une question…" data-testid="question-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
          <button type="submit" data-testid="question-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 text-[11px] text-[#52524F] hover:text-[#111110]"><Plus size={12} /> Ajouter</button>
        </form>
      </Carte>

      <Carte titre="Hypothèses" testid="case-hypotheses">
        <ul className="space-y-1.5">
          {hypotheses.map((h, i) => {
            const s = STATUTS_HYP[h.statut] || STATUTS_HYP.a_valider;
            return (
              <li key={h.id} className="flex items-center gap-2.5 rounded-lg border border-[#E5E5E3] px-2.5 py-2" data-testid={`hypothese-${h.id}`}>
                <button
                  onClick={() => maj({ hypotheses: hypotheses.map((x) => (x.id === h.id ? { ...x, statut: CYCLE[(CYCLE.indexOf(h.statut) + 1) % 3] } : x)) })}
                  data-testid={`hypothese-statut-${h.id}`}
                  title="Changer le statut"
                  className="shrink-0 rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider transition-colors"
                  style={{ color: s[1], borderColor: `${s[1]}44`, backgroundColor: `${s[1]}12` }}
                >
                  {s[0]}
                </button>
                <span className={`text-xs ${h.statut === "rejetee" ? "text-[#71716D] line-through" : "text-[#3F3F3C]"}`}>{h.texte}</span>
              </li>
            );
          })}
          {hypotheses.length === 0 && <li className="text-xs text-[#71716D]">Aucune hypothèse formulée.</li>}
        </ul>
        <form onSubmit={(e) => { e.preventDefault(); ajouterHypothese(); }} className="mt-2.5 flex gap-2">
          <input value={nouvelleHyp} onChange={(e) => setNouvelleHyp(e.target.value)} placeholder="Formuler une hypothèse…" data-testid="hypothese-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
          <button type="submit" data-testid="hypothese-add-btn" className="flex h-8 items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 text-[11px] text-[#52524F] hover:text-[#111110]"><Plus size={12} /> Ajouter</button>
        </form>
      </Carte>

      <Carte
        titre="Investigations"
        testid="case-investigations"
        action={<button onClick={() => setNouvelleInv(nouvelleInv === null ? "" : null)} data-testid="investigation-add-toggle" className="flex items-center gap-1 font-code text-[10px] text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={12} /> Ouvrir une investigation</button>}
      >
        <ul className="space-y-1.5">
          {(cas.situations || []).map((sid) => {
            const s = situations.find((x) => x.id === sid);
            return (
              <li key={sid}>
                <Link to={`/investigations/${sid}`} data-testid={`case-situation-${sid}`} className="text-xs text-[#3730A3] hover:underline">
                  → {s?.titre || sid}
                </Link>
              </li>
            );
          })}
          {(cas.situations || []).length === 0 && <li className="text-xs text-[#71716D]">Aucune investigation — une incertitude qui demande une recherche structurée peut en ouvrir une.</li>}
        </ul>
        {nouvelleInv !== null && (
          <form onSubmit={(e) => { e.preventDefault(); ouvrirInvestigation(); }} className="mt-2.5 flex gap-2" data-testid="investigation-form">
            <input value={nouvelleInv} onChange={(e) => setNouvelleInv(e.target.value)} placeholder="Objet de l'investigation…" data-testid="investigation-add-input" className="h-8 flex-1 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none" />
            <button type="submit" data-testid="investigation-add-submit" className="flex h-8 items-center gap-1 rounded-md border border-[#6D28D9]/40 px-2.5 text-[11px] text-[#6D28D9] hover:bg-[#6D28D9]/10"><Flask size={12} /> Ouvrir</button>
          </form>
        )}
      </Carte>

      <Carte titre="Analyses & livrables" testid="case-livrables" action={<ProduireSynthese cas={cas} setCas={setCas} />}>
        <div className="space-y-2">
          {(cas.livrables || []).map((l) => (
            <div key={l.id} className="rounded-lg border border-[#E5E5E3] bg-white p-3" data-testid={`livrable-${l.id}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[#111110]">{l.titre}</span>
                <span className="font-code text-[9px] text-[#71716D]">{new Date(l.cree_le).toLocaleString("fr-FR")}</span>
              </div>
              <pre className="mt-2 whitespace-pre-wrap font-sans text-xs leading-relaxed text-[#52524F]">{l.contenu}</pre>
            </div>
          ))}
          {(cas.livrables || []).length === 0 && <p className="text-xs text-[#71716D]">Aucune analyse — Flore peut produire une synthèse du travail.</p>}
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
      className="flex items-center gap-1.5 rounded-md border border-[#6D28D9]/40 bg-[#6D28D9]/[0.07] px-2.5 py-1.5 text-[11px] font-semibold text-[#6D28D9] transition-colors hover:bg-[#6D28D9]/15"
    >
      <FileText size={12} /> {envoi ? "Production…" : "Produire une synthèse"}
    </button>
  );
}
