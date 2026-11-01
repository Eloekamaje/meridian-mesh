import { useState } from "react";
import { UploadSimple, FileText } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const TEXTES = {
  cmdb: "Collez ou déposez un export CMDB JSON/CSV : application_id, nom, proprietaire.",
  manifeste: "Collez ou déposez un manifeste JSON : { jumeau: { application_id, nom, proprietaire }, sources: [...] }.",
};

export default function ImportIdentite({ commandeId, mode, onImporte }) {
  const [contenu, setContenu] = useState("");
  const [apercu, setApercu] = useState(null);
  const [chargement, setChargement] = useState(false);

  const analyser = async () => {
    if (!contenu.trim()) {
      toast.error("Ajoutez un contenu JSON ou CSV.");
      return;
    }
    setChargement(true);
    try {
      const { data } = await api.post(`/commandes/${commandeId}/import/apercu`, { mode, contenu });
      setApercu(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Analyse impossible");
    } finally {
      setChargement(false);
    }
  };

  const lireFichier = (evenement) => {
    const fichier = evenement.target.files?.[0];
    if (!fichier) return;
    const lecteur = new FileReader();
    lecteur.onload = () => { setContenu(String(lecteur.result || "")); setApercu(null); };
    lecteur.readAsText(fichier);
  };

  return (
    <div className="rounded-lg border border-[rgba(96,165,250,0.22)] bg-[rgba(96,165,250,0.04)] p-3" data-testid={`identite-import-${mode}`}>
      <p className="flex items-center gap-2 text-[11px] leading-relaxed text-[#94A3B8]">
        <FileText size={14} className="shrink-0 text-[#93C5FD]" /> {TEXTES[mode]}
      </p>
      <input type="file" accept=".json,.csv,text/csv,application/json" onChange={lireFichier} data-testid="import-fichier" className="mt-2 block w-full text-[11px] text-[#94A3B8] file:mr-3 file:rounded-md file:border-0 file:bg-[#17324A] file:px-3 file:py-2 file:text-[11px] file:text-[#BFDBFE]" />
      <textarea value={contenu} onChange={(e) => { setContenu(e.target.value); setApercu(null); }} rows={8} data-testid="import-contenu" placeholder="JSON ou CSV…" className="mt-2 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-3 py-2 font-code text-[11px] text-[#D8E2EA] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
      {!apercu ? (
        <button type="button" onClick={analyser} disabled={chargement} data-testid="import-analyser-btn" className="mt-2 flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-4 py-2 text-xs font-semibold text-[#071019] hover:bg-[#93C5FD] disabled:opacity-40">
          <UploadSimple size={13} /> {chargement ? "Analyse…" : "Analyser"}
        </button>
      ) : (
        <div className="mt-3" data-testid="import-apercu">
          <p className="text-[11px] text-[#D8E2EA]">
            <strong>{apercu.identite?.nom || apercu.identite?.application_id}</strong>
            <span className="font-code text-[#7C93A8]"> · {apercu.identite?.application_id} · {apercu.nouvelles.length} nouvelle(s) · {(apercu.ignorees || []).length} déjà présente(s)</span>
          </p>
          {apercu.nouvelles.length > 0 && (
            <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto" data-testid="import-nouvelles">
              {apercu.nouvelles.map((s, i) => (
                <li key={`${s.connecteur}-${s.nom}-${i}`} className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-[11px] text-[#D8E2EA]">
                  {s.nom} <span className="font-code text-[9px] text-[#7C93A8]">· {s.connecteur} · {s.environnement}</span>
                </li>
              ))}
            </ul>
          )}
          {(apercu.ignorees || []).length > 0 && (
            <p className="mt-2 text-[10px] text-[#F2B84B]" data-testid="import-ignorees">
              {(apercu.ignorees || []).length} source(s) déjà dans la commande seront ignorées.
            </p>
          )}
          {apercu.nouvelles.length === 0 && (
            <p className="mt-2 text-[10px] text-[#7C93A8]">Aucune nouvelle source : seule l'identité sera mise à jour.</p>
          )}
          <button type="button" onClick={() => onImporte(apercu)} data-testid="import-confirmer-btn" className="mt-2 rounded-md bg-[#34D399] px-4 py-2 text-xs font-semibold text-[#071019] hover:bg-[#065F46]">
            Utiliser cette identité
          </button>
        </div>
      )}
    </div>
  );
}
