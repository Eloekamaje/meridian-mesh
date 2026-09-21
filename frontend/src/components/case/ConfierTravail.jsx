import { useEffect, useState } from "react";
import { X, UserPlus, ArrowsLeftRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

// Confier un travail à une personne nommée : l'associer (elle y participe) ou lui en transférer la responsabilité.
// Elle est prévenue ; elle doit avoir les droits sur les jumeaux du travail — le serveur le refuse sinon.
export default function ConfierTravail({ cas, personas, moi, onFermer, onConfie }) {
  const candidats = personas.filter((p) => p.id !== moi && !(cas.participants || []).includes(p.id));
  const [cible, setCible] = useState(candidats[0]?.id || "");
  const [mode, setMode] = useState("associer");
  const [note, setNote] = useState("");
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    const echap = (e) => e.key === "Escape" && onFermer();
    document.addEventListener("keydown", echap);
    return () => document.removeEventListener("keydown", echap);
  }, [onFermer]);

  const envoyer = async () => {
    setEnvoi(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/confier`, { persona: cible, mode, note });
      toast.success(mode === "transferer" ? "Responsabilité transférée" : "Personne associée au travail");
      onConfie(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Impossible de confier ce travail");
      setEnvoi(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onFermer()} data-testid="confier-travail">
      <div className="w-full max-w-md rounded-2xl border border-[rgba(148,163,184,0.16)] bg-[#0C1724] p-5 shadow-2xl" role="dialog" aria-label="Confier ce travail">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-base font-semibold text-[#F2F6F8]">Confier ce travail</h2>
            <p className="mt-1 text-xs leading-relaxed text-[#94A3B8]">La personne est prévenue. Elle doit avoir les droits sur les jumeaux du travail.</p>
          </div>
          <button onClick={onFermer} title="Fermer" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"><X size={15} /></button>
        </div>

        {candidats.length === 0 ? (
          <p className="mt-4 text-sm text-[#94A3B8]" data-testid="confier-personne-aucune">Tout le monde participe déjà à ce travail.</p>
        ) : (
          <div className="mt-4 space-y-4">
            <fieldset>
              <legend className="mb-1.5 block font-code text-[11px] uppercase tracking-[0.16em] text-[#94A3B8]">À qui ?</legend>
              <div className="space-y-1">
                {candidats.map((p) => (
                  <label key={p.id} className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm ${cible === p.id ? "border-[#60A5FA]/50 bg-[#60A5FA]/10 text-[#F2F6F8]" : "border-[rgba(148,163,184,0.16)] text-[#D8E2EA] hover:border-[#41576D]"}`}>
                    <input type="radio" name="confier-personne" value={p.id} checked={cible === p.id} onChange={() => setCible(p.id)} className="accent-[#60A5FA]" data-testid={`confier-personne-${p.id}`} />
                    <span className="min-w-0 flex-1"><span className="font-medium">{p.nom}</span> <span className="text-xs text-[#7C93A8]">· {p.role}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-1.5 block font-code text-[11px] uppercase tracking-[0.16em] text-[#94A3B8]">Comment ?</legend>
              <div className="grid grid-cols-2 gap-2">
                {[["associer", "L'associer", "Elle participe, vous restez responsable.", UserPlus], ["transferer", "Lui transférer", "Elle devient responsable, vous participez.", ArrowsLeftRight]].map(([id, titre, aide, Icone]) => (
                  <button key={id} type="button" onClick={() => setMode(id)} aria-pressed={mode === id} data-testid={`confier-mode-${id}`}
                    className={`rounded-lg border px-3 py-2 text-left ${mode === id ? "border-[#60A5FA]/50 bg-[#60A5FA]/10" : "border-[rgba(148,163,184,0.16)] hover:border-[#41576D]"}`}>
                    <span className="flex items-center gap-1.5 text-[13px] font-medium text-[#F2F6F8]"><Icone size={14} className="text-[#60A5FA]" /> {titre}</span>
                    <span className="mt-0.5 block text-xs leading-snug text-[#7C93A8]">{aide}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <div>
              <label htmlFor="confier-note" className="mb-1.5 block font-code text-[11px] uppercase tracking-[0.16em] text-[#94A3B8]">Un mot pour elle (facultatif)</label>
              <textarea id="confier-note" value={note} onChange={(e) => setNote(e.target.value)} rows={2} data-testid="confier-note" placeholder="Ce que vous attendez, ce qui presse…"
                className="w-full resize-none rounded-md border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] px-2.5 py-2 text-[13px] text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
            </div>
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onFermer} className="rounded-md border border-[rgba(148,163,184,0.2)] px-3.5 py-2 text-xs text-[#D8E2EA] hover:border-white/30">Annuler</button>
          <button onClick={envoyer} disabled={!cible || envoi || candidats.length === 0} data-testid="confier-valider" className="rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-40">
            {envoi ? "Envoi…" : mode === "transferer" ? "Transférer" : "Associer"}
          </button>
        </div>
      </div>
    </div>
  );
}
