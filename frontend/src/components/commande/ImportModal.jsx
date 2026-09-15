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
      <div className="absolute inset-0 bg-[#0F1D28]" onClick={onFermer} />
      <div className="relative w-[min(560px,92vw)] rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-6">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-base font-bold text-[#F2F6F8]">Importer des sources</h3>
          <button onClick={onFermer} data-testid="import-fermer" className="text-[#7C93A8] hover:text-[#F2F6F8]"><X size={16} /></button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {MODES.map(([m, titre, desc]) => (
            <button key={m} onClick={() => { setMode(m); setApercu(null); }} data-testid={`import-mode-${m}`} className={`rounded-lg border p-3 text-left transition-colors ${mode === m ? "border-[#25D0C8]/50 bg-[#25D0C8]/[0.05]" : "border-[rgba(148,163,184,0.16)] hover:border-[#41576D]"}`}>
              <div className="text-xs font-semibold text-[#F2F6F8]">{titre}</div>
              <div className="mt-0.5 text-[10px] text-[#7C93A8]">{desc}</div>
            </button>
          ))}
        </div>

        {!apercu ? (
          <button onClick={analyser} disabled={chargement} data-testid="import-analyser-btn" className="mt-4 flex items-center gap-1.5 rounded-md bg-[#9B87F5] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#B4A5F7] disabled:opacity-40">
            <UploadSimple size={13} /> {chargement ? "Analyse…" : "Analyser"}
          </button>
        ) : (
          <div data-testid="import-apercu">
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              {[
                [apercu.detectees, "détectées", "rgba(148,163,184,0.16)"],
                [apercu.nouvelles.length, "nouvelles", "#25D0C8"],
                [apercu.presentes.length, "déjà présentes", "#7C93A8"],
                [apercu.a_mapper.length, "à mapper", "#F2B84B"],
              ].map(([n, l, c]) => (
                <div key={l} className="rounded-lg border border-[rgba(148,163,184,0.16)] px-2 py-2.5">
                  <div className="font-display text-lg font-bold" style={{ color: c }}>{n}</div>
                  <div className="font-code text-[9px] text-[#7C93A8]">{l}</div>
                </div>
              ))}
            </div>
            <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto">
              {apercu.nouvelles.map((s, i) => (
                <li key={i} className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-[11px] text-[#D8E2EA]">
                  {s.nom} <span className="font-code text-[9px] text-[#7C93A8]">· {s.environnement} · {s.perimetre}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-[#7C93A8]">Confirmer pour ajouter les {apercu.nouvelles.length} nouvelles instances à la commande — rien d'autre ne sera modifié.</p>
            <div className="mt-4 flex gap-2">
              <button onClick={() => onImporte(apercu.nouvelles)} data-testid="import-confirmer-btn" className="rounded-md bg-[#34D399] px-4 py-2 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#065F46]">
                Confirmer l'import
              </button>
              <button onClick={() => setApercu(null)} className="rounded-md border border-[rgba(148,163,184,0.16)] px-4 py-2 text-xs text-[#94A3B8] hover:text-[#F2F6F8]">Retour</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
