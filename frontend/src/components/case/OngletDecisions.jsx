import { useState } from "react";
import { Plus, CheckFat, Prohibit } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const TYPES_DECISION = { arbitrage: "Arbitrage", validation: "Validation", rejet: "Rejet", report: "Report" };
const RISQUES = { faible: ["faible", "#047857"], moyen: ["moyen", "#B45309"], eleve: ["élevé", "#B91C1C"] };
const STATUTS_OPTION = { a_evaluer: ["À évaluer", "#B45309"], recommandee: ["Recommandée par Flore", "#0E7490"], retenue: ["Retenue", "#047857"], ecartee: ["Écartée", "#64748B"] };

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
      <section className="rounded-xl border border-[#E5E5E3] p-4" data-testid="case-options">
        <div className="flex items-center justify-between">
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Options considérées</div>
          <button onClick={() => setFormOption(formOption ? null : { risque: "moyen" })} data-testid="option-add-toggle" className="text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={14} /></button>
        </div>
        <div className="mt-2.5 space-y-2">
          {(cas.options || []).map((o) => {
            const r = RISQUES[o.risque] || [o.risque, "#71716D"];
            const so = STATUTS_OPTION[o.statut] || STATUTS_OPTION.a_evaluer;
            return (
              <div key={o.id} className={`rounded-lg border p-3 ${o.statut === "ecartee" ? "border-[#E5E5E3] opacity-50" : "border-[#E5E5E3] bg-white"}`} data-testid={`option-${o.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-[#111110]">{o.titre}</span>
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
                    <button onClick={() => trancher(o, "retenue")} data-testid={`option-retenir-${o.id}`} className="flex items-center gap-1 rounded-md bg-[#047857]/15 border border-[#047857]/40 px-2 py-1 text-[10px] font-semibold text-[#047857] transition-colors hover:bg-[#047857]/25">
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
          {(cas.options || []).length === 0 && !formOption && <p className="text-xs text-[#71716D]">Aucune option pour l'instant.</p>}
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
      </section>

      <section className="rounded-xl border border-[#E5E5E3] p-4" data-testid="case-decisions">
        <div className="flex items-center justify-between">
          <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Décisions humaines</div>
          <button onClick={() => setFormDecision(formDecision ? null : { type: "arbitrage" })} data-testid="decision-add-toggle" className="text-[#71716D] transition-colors hover:text-[#111110]"><Plus size={14} /></button>
        </div>
        <div className="mt-2.5 space-y-2">
          {(cas.decisions || []).map((d, i) => (
            <div key={i} className="rounded-lg border border-[#B45309]/20 bg-[#B45309]/[0.04] p-3" data-testid={`decision-${i}`}>
              <div className="flex items-center justify-between">
                <span className="font-code text-[9px] uppercase tracking-wider text-[#B45309]">{TYPES_DECISION[d.type] || d.type}</span>
                <span className="font-code text-[9px] text-[#71716D]">{new Date(d.quand).toLocaleDateString("fr-FR")} · {d.par}</span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-[#3F3F3C]">{d.texte}</p>
            </div>
          ))}
          {(cas.decisions || []).length === 0 && !formDecision && <p className="text-xs text-[#71716D]">Aucune décision enregistrée.</p>}
        </div>
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
      </section>
    </div>
  );
}
