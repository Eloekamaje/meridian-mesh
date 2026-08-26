import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, SealCheck, Compass } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import RevueContenu from "@/components/jumeaux/RevueContenu";
import { STATUTS } from "@/lib/jumeaux";

export default function RevueJumeau() {
  const { jid } = useParams();
  const navigate = useNavigate();
  const { recharger } = useMesh();
  const { version } = usePerimetre();
  const [jumeau, setJumeau] = useState(null);
  const [examen, setExamen] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [admission, setAdmission] = useState(false);

  useEffect(() => {
    let actif = true;
    setJumeau(null);
    setExamen(null);
    setErreur(null);
    (async () => {
      try {
        const { data: liste } = await api.get("/jumeaux");
        const j = liste.find((x) => x.id === jid);
        if (!j) {
          if (actif) setErreur("Jumeau introuvable dans votre périmètre.");
          return;
        }
        if (actif) setJumeau(j);
        const { data } = await api.post(`/jumeaux/${jid}/examiner`);
        if (actif) setExamen(data);
      } catch (e) {
        if (actif) setErreur(e.response?.data?.detail || "Examen indisponible à ce niveau d'autorisation.");
      }
    })();
    return () => {
      actif = false;
    };
  }, [jid, version]);

  const admettre = async () => {
    setAdmission(true);
    try {
      await api.post(`/jumeaux/${jid}/admettre`);
      toast.success(`${jumeau.nom} admis dans le Mesh`);
      recharger();
      navigate("/jumeaux");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Admission impossible");
      setAdmission(false);
    }
  };

  const st = jumeau ? STATUTS[jumeau.statut] || [jumeau.statut, "#71716D"] : null;
  const estAdmission = jumeau?.statut === "observation";

  return (
    <div className="flex h-full flex-col" data-testid="revue-page">
      <div className="border-b border-[#E5E5E3] px-8 py-3.5" data-testid="revue-entete">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/jumeaux")} data-testid="revue-retour-btn" className="flex items-center gap-1.5 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]">
              <ArrowLeft size={13} /> Jumeaux
            </button>
            <div>
              <h1 className="font-display text-xl font-bold tracking-tight text-[#111110]" data-testid="revue-titre">
                {estAdmission ? "Revue d'admission" : "Revue"} — {jumeau?.nom || "…"}
              </h1>
              <p className="font-code text-[10px] text-[#71716D]">{jid} · Domaine {jumeau?.domaine || "…"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {st && (
              <span className="rounded border px-2 py-1 font-code text-[10px]" style={{ color: st[1], borderColor: `${st[1]}44`, backgroundColor: `${st[1]}12` }} data-testid="revue-statut">
                {st[0]}
              </span>
            )}
            <button onClick={() => navigate(`/atlas?focus=${jid}`)} data-testid="revue-atlas-btn" className="flex items-center gap-1.5 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-xs text-[#52524F] transition-colors hover:border-[#0E7490]/50 hover:text-[#111110]">
              <Compass size={13} /> Centrer dans l'Atlas
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-4xl">
          {erreur && (
            <div className="rounded-xl border border-[#B91C1C]/25 bg-[#B91C1C]/[0.05] px-5 py-6" data-testid="revue-erreur">
              <p className="text-sm text-[#B91C1C]">{erreur}</p>
              <button onClick={() => navigate("/jumeaux")} className="mt-3 rounded-md border border-[#E5E5E3] px-3 py-1.5 text-xs text-[#52524F] transition-colors hover:text-[#111110]" data-testid="revue-erreur-retour-btn">
                ← Retour aux jumeaux
              </button>
            </div>
          )}
          {!erreur && !examen && (
            <p className="font-code text-[11px] text-[#71716D]" data-testid="revue-chargement">Examen du jumeau en cours…</p>
          )}
          {examen && jumeau && (
            <>
              <RevueContenu examen={examen} jumeau={jumeau} />
              {(jumeau.gouvernance || []).length > 0 && (
                <section className="mt-6 rounded-xl border border-[#E5E5E3] bg-white p-5" data-testid="revue-gouvernance">
                  <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#52524F]">Gouvernance de l'autonomie</h2>
                  <p className="mt-1 text-[11px] text-[#71716D]">L'autonomie dépend du type d'action — jamais globale.</p>
                  <div className="mt-3 space-y-1">
                    {jumeau.gouvernance.map((g) => {
                      const c = { delegue: "#047857", supervise: "#B45309", interdit: "#B91C1C", observe: "#71716D" }[g.niveau] || "#71716D";
                      const l = { delegue: "Délégué", supervise: "Supervisé", interdit: "Interdit", observe: "Observé" }[g.niveau] || g.niveau;
                      return (
                        <div key={g.action} className="flex items-center justify-between border-b border-[#F0F0EE] py-1.5 last:border-b-0" data-testid={`gouv-${g.action.slice(0, 20)}`}>
                          <span className="text-xs text-[#3F3F3C]">{g.action}</span>
                          <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>{l}</span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
              {jumeau.statut !== "actif" && jumeau.niveau === "complet" && (
                <button onClick={admettre} disabled={admission} data-testid="confirmer-admission-btn" className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-[#B45309] px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#92400E] disabled:opacity-50">
                  <SealCheck size={16} /> {admission ? "Admission en cours…" : "Confirmer l'admission dans le Mesh"}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
