import { useState } from "react";
import { X, UploadSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const MODES = [
  ["cmdb", "CMDB", "Instances déclarées dans la CMDB d'entreprise"],
  ["manifeste", "Ancien manifeste", "Manifeste d'un jumeau existant"],
  ["fichier", "Fichier structuré", "CSV ou JSON d'instances"],
  ["inventaire", "Inventaire d'entreprise", "Export de l'inventaire applicatif"],
];

export default function ImportModal({ commandeId, modeInitial = "cmdb", onImporte, onFermer }) {
  const [mode, setMode] = useState(modeInitial);
  const [apercu, setApercu] = useState(null);
  const [chargement, setChargement] = useState(false);

  const analyser = async () => {
    setChargement(true);
    try {
      const { data } = await api.post(`/commandes/${commandeId}/import/apercu`, { mode });
      setApercu(data);
    } catch {
      toast.error("Analyse impossible");
    } finally {
      setChargement(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" data-testid="import-modal">
      <div className="absolute inset-0 bg-white" onClick={onFermer} />
      <div className="relative w-[min(560px,92vw)] rounded-xl border border-[#E5E5E3] bg-white p-6">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-base font-bold text-[#111110]">Importer des sources</h3>
          <button onClick={onFermer} data-testid="import-fermer" className="text-[#71716D] hover:text-[#111110]"><X size={16} /></button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {MODES.map(([m, titre, desc]) => (
            <button key={m} onClick={() => { setMode(m); setApercu(null); }} data-testid={`import-mode-${m}`} className={`rounded-lg border p-3 text-left transition-colors ${mode === m ? "border-[#0E7490]/50 bg-[#0E7490]/[0.05]" : "border-[#E5E5E3] hover:border-[#D4D4D0]"}`}>
              <div className="text-xs font-semibold text-[#111110]">{titre}</div>
              <div className="mt-0.5 text-[10px] text-[#71716D]">{desc}</div>
            </button>
          ))}
        </div>

        {!apercu ? (
          <button onClick={analyser} disabled={chargement} data-testid="import-analyser-btn" className="mt-4 flex items-center gap-1.5 rounded-md bg-[#3730A3] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-40">
            <UploadSimple size={13} /> {chargement ? "Analyse…" : "Analyser"}
          </button>
        ) : (
          <div data-testid="import-apercu">
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[
                [apercu.detectees, "détectées", "#E5E7EB"],
                [apercu.nouvelles.length, "nouvelles", "#0E7490"],
                [apercu.presentes.length, "déjà présentes", "#64748B"],
                [apercu.a_mapper.length, "à mapper", "#B45309"],
              ].map(([n, l, c]) => (
                <div key={l} className="rounded-lg border border-[#E5E5E3] px-2 py-2.5">
                  <div className="font-display text-lg font-bold" style={{ color: c }}>{n}</div>
                  <div className="font-code text-[9px] text-[#71716D]">{l}</div>
                </div>
              ))}
            </div>
            <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto">
              {apercu.nouvelles.map((s, i) => (
                <li key={i} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#3F3F3C]">
                  {s.nom} <span className="font-code text-[9px] text-[#71716D]">· {s.environnement} · {s.perimetre}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-[#71716D]">Confirmer pour ajouter les {apercu.nouvelles.length} nouvelles instances à la commande — rien d'autre ne sera modifié.</p>
            <div className="mt-4 flex gap-2">
              <button onClick={() => onImporte(apercu.nouvelles)} data-testid="import-confirmer-btn" className="rounded-md bg-[#047857] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#065F46]">
                Confirmer l'import
              </button>
              <button onClick={() => setApercu(null)} className="rounded-md border border-[#E5E5E3] px-4 py-2 text-xs text-[#52524F] hover:text-[#111110]">Retour</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
