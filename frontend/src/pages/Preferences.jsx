import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";

const TONS = [["direct", "Direct"], ["pedagogique", "Pédagogique"], ["chaleureux", "Chaleureux"]];
const LONGUEURS = [["concis", "Concis"], ["moyenne", "Moyenne"], ["detaillee", "Détaillée"]];

export default function Preferences() {
  const [valeurs, setValeurs] = useState({ ton: "direct", langue: "fr", longueur: "moyenne", suggestions: true });
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    api.get("/preferences").then(({ data }) => setValeurs((v) => ({ ...v, ...data }))).catch(() => {});
  }, []);

  const changer = (cle, valeur) => setValeurs((v) => ({ ...v, [cle]: valeur }));

  const enregistrer = async (evenement) => {
    evenement.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await api.put("/preferences", valeurs);
      setValeurs((v) => ({ ...v, ...data }));
      toast.success("Préférences enregistrées");
    } catch {
      toast.error("Impossible d’enregistrer les préférences");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 text-[#F2F6F8]">
      <p className="font-code text-[10px] uppercase tracking-[0.18em] text-[#7C93A8]">Compte</p>
      <h1 className="mt-2 font-display text-3xl font-semibold">Préférences de conversation</h1>
      <p className="mt-2 text-sm text-[#94A3B8]">
        Ces réglages changent la forme des réponses. Ils ne changent ni les preuves, ni l’autorité.
      </p>
      <form onSubmit={enregistrer} className="mt-6 space-y-4 rounded-2xl border border-white/[0.10] bg-[#0C1724] p-6">
        <label className="block text-xs text-[#94A3B8]">
          Ton
          <select value={valeurs.ton} onChange={(e) => changer("ton", e.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8]">
            {TONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label className="block text-xs text-[#94A3B8]">
          Longueur
          <select value={valeurs.longueur} onChange={(e) => changer("longueur", e.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8]">
            {LONGUEURS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label className="block text-xs text-[#94A3B8]">
          Langue
          <input value={valeurs.langue} onChange={(e) => changer("langue", e.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8]" />
        </label>
        <label className="flex items-center gap-2 text-sm text-[#CBD5E1]">
          <input type="checkbox" checked={!!valeurs.suggestions}
            onChange={(e) => changer("suggestions", e.target.checked)} />
          Proposer une suite après les réponses
        </label>
        <button type="submit" disabled={envoi}
          className="h-10 rounded-lg bg-[#60A5FA] px-5 text-sm font-semibold text-[#071019] disabled:opacity-50">
          {envoi ? "Enregistrement…" : "Enregistrer"}
        </button>
      </form>
    </div>
  );
}
