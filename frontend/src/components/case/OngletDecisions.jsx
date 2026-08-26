import { useState } from "react";
import { Plus, CheckFat, Prohibit } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const TYPES_DECISION = { arbitrage: "Arbitrage", validation: "Validation", rejet: "Rejet", report: "Report" };
const RISQUES = { faible: ["faible", "#10B981"], moyen: ["moyen", "#FBBF24"], eleve: ["élevé", "#F87171"] };
const STATUTS_OPTION = { a_evaluer: ["À évaluer", "#FBBF24"], recommandee: ["Recommandée par Flore", "#22D3EE"], retenue: ["Retenue", "#10B981"], ecartee: ["Écartée", "#94A3B8"] };

export default function OngletDecisions({ cas, maj, setCas }) {
  const [formOption, setFormOption] = useState(null);
  const [formDecision, setFormDecision] = useState(null);

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

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="onglet-decisions">
      <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-options">
        <div className="flex items-center justify-between">
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Options considérées</div>
          <button onClick={() => setFormOption(formOption ? null : { risque: "moyen" })} data-testid="option-add-toggle" className="text-white/40 transition-colors hover:text-white"><Plus size={14} /></button>
        </div>
        <div className="mt-2.5 space-y-2">
          {(cas.options || []).map((o) => {
            const r = RISQUES[o.risque] || [o.risque, "#9CA3AF"];
            const so = STATUTS_OPTION[o.statut] || STATUTS_OPTION.a_evaluer;
            return (
              <div key={o.id} className={`rounded-lg border p-3 ${o.statut === "ecartee" ? "border-white/[0.04] opacity-50" : "border-white/[0.06] bg-white/[0.02]"}`} data-testid={`option-${o.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-white/85">{o.titre}</span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: r[1], borderColor: `${r[1]}44` }}>risque {r[0]}</span>
                    <span className="rounded border px-1.5 py-0.5 font-code text-[9px]" style={{ color: so[1], borderColor: `${so[1]}44`, backgroundColor: `${so[1]}12` }} data-testid={`option-statut-${o.id}`}>{so[0]}</span>
                  </div>
                </div>
                {o.description && <p className="mt-1 text-[11px] leading-snug text-white/55">{o.description}</p>}
                {(o.impacts || []).length > 0 && (
                  <ul className="mt-1.5 space-y-0.5">
                    {o.impacts.map((im, i) => <li key={i} className="font-code text-[10px] text-white/45">→ {im}</li>)}
                  </ul>
                )}
                {o.statut === "a_evaluer" || o.statut === "recommandee" ? (
                  <div className="mt-2 flex gap-1.5">
                    <button onClick={() => trancher(o, "retenue")} data-testid={`option-retenir-${o.id}`} className="flex items-center gap-1 rounded-md bg-[#10B981]/15 border border-[#10B981]/40 px-2 py-1 text-[10px] font-semibold text-[#10B981] transition-colors hover:bg-[#10B981]/25">
                      <CheckFat size={11} /> Retenir
                    </button>
                    <button onClick={() => trancher(o, "ecartee")} data-testid={`option-ecarter-${o.id}`} className="flex items-center gap-1 rounded-md border border-white/15 px-2 py-1 text-[10px] text-white/50 transition-colors hover:text-white">
                      <Prohibit size={11} /> Écarter
                    </button>
                  </div>
                ) : null}
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

      <section className="rounded-xl border border-white/[0.07] p-4" data-testid="case-decisions">
        <div className="flex items-center justify-between">
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Décisions humaines</div>
          <button onClick={() => setFormDecision(formDecision ? null : { type: "arbitrage" })} data-testid="decision-add-toggle" className="text-white/40 transition-colors hover:text-white"><Plus size={14} /></button>
        </div>
        <div className="mt-2.5 space-y-2">
          {(cas.decisions || []).map((d, i) => (
            <div key={i} className="rounded-lg border border-[#FBBF24]/20 bg-[#FBBF24]/[0.04] p-3" data-testid={`decision-${i}`}>
              <div className="flex items-center justify-between">
                <span className="font-code text-[9px] uppercase tracking-wider text-[#FBBF24]">{TYPES_DECISION[d.type] || d.type}</span>
                <span className="font-code text-[9px] text-white/30">{new Date(d.quand).toLocaleDateString("fr-FR")} · {d.par}</span>
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
    </div>
  );
}
