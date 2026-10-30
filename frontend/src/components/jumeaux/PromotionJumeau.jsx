import { useState } from "react";
import { IdentificationBadge, SealCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import {
  estJumeauProvisoire,
  missionProposeePromotion,
  nomProposePromotion,
  raisonsProvisoire,
} from "@/lib/jumeaux";

const BORDURE = "border-[rgba(148,163,184,0.16)]";
const FOCUS = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]";
const CHAMP = `w-full rounded-md border ${BORDURE} bg-[#0F1D28] px-3 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] ${FOCUS}`;

function messageErreur(statut, detail) {
  if (statut === 400) return detail || "Promotion refusée : vérifiez le nom et la mission de l'application.";
  if (statut === 404) return "Jumeau introuvable : la promotion n'a pas été appliquée.";
  if (statut === 409) return detail || "Ce jumeau est déjà promu ou son identité a changé : rechargez la revue avant de réessayer.";
  return detail || "Promotion impossible pour l'instant.";
}

// Promotion d'un twin provisoire : une décision humaine qui fixe le nom et la mission de l'application.
// L'identifiant du jumeau ne change pas : preuves, interfaces et liens restent attachés.
export default function PromotionJumeau({ jumeau, jid, onPromu }) {
  const identifiant = jid || jumeau?.id;
  const [nom, setNom] = useState(() => nomProposePromotion(jumeau || {}));
  const [mission, setMission] = useState(() => missionProposeePromotion(jumeau || {}));
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [fait, setFait] = useState(false);

  if (!jumeau || !identifiant || jumeau.niveau !== "complet" || !estJumeauProvisoire(jumeau)) return null;

  const raisons = raisonsProvisoire(jumeau);

  const promouvoir = async (e) => {
    e.preventDefault();
    const nomPropre = nom.trim();
    const missionPropre = mission.trim();
    if (!nomPropre || !missionPropre) {
      toast.error("Nom et mission sont requis pour promouvoir l'application.");
      return;
    }
    setEnvoi(true);
    try {
      await api.post(`/jumeaux/${encodeURIComponent(identifiant)}/promouvoir`, {
        nom: nomPropre,
        mission: missionPropre,
        motif: motif.trim() || null,
      });
      setFait(true);
      toast.success(`${nomPropre} promue : son identifiant d'application est conservé.`);
      onPromu?.();
    } catch (erreur) {
      toast.error(messageErreur(erreur.response?.status, erreur.response?.data?.detail));
      setEnvoi(false);
    }
  };

  return (
    <section className="rounded-xl border border-[#F2B84B]/30 bg-[#F2B84B]/[0.04] p-5" data-testid="promotion-jumeau" aria-label="Promouvoir l'application">
      <div className="flex items-start gap-2">
        <IdentificationBadge size={16} className="mt-0.5 shrink-0 text-[#F2B84B]" aria-hidden />
        <div>
          <h2 className="text-sm font-semibold text-[#F2F6F8]">Identité provisoire — promouvoir l'application</h2>
          <p className="mt-1 text-xs leading-relaxed text-[#94A3B8]">
            Ce jumeau n'a pas encore de nom et de mission confirmés. La promotion fixe son identité d'application :
            <span className="text-[#D8E2EA]"> son identifiant ne change pas</span>, et ses preuves, interfaces et liens restent attachés.
          </p>
          {raisons.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" data-testid="promotion-raisons">
              {raisons.map((raison) => (
                <li key={raison} className="rounded-full border border-[#F2B84B]/30 px-2 py-0.5 font-code text-[9px] text-[#F2B84B]">
                  {raison}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {fait ? (
        <p className="mt-4 flex items-center gap-1.5 text-xs text-[#34D399]" data-testid="promotion-succes">
          <SealCheck size={14} aria-hidden /> Promotion enregistrée. La revue se recharge avec l'identité confirmée.
        </p>
      ) : (
        <form onSubmit={promouvoir} className="mt-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block" htmlFor="promotion-nom">
              <span className="mb-1 block font-code text-[10px] uppercase tracking-wider text-[#94A3B8]">Nom de l'application</span>
              <input id="promotion-nom" value={nom} onChange={(e) => setNom(e.target.value)} maxLength={200} required
                placeholder="Ex. Gestion des paiements" data-testid="promotion-nom" className={CHAMP} />
            </label>
            <label className="block" htmlFor="promotion-mission">
              <span className="mb-1 block font-code text-[10px] uppercase tracking-wider text-[#94A3B8]">Mission</span>
              <input id="promotion-mission" value={mission} onChange={(e) => setMission(e.target.value)} maxLength={2000} required
                placeholder="Ce que l'application fait, pour qui" data-testid="promotion-mission" className={CHAMP} />
            </label>
          </div>
          <label className="block" htmlFor="promotion-motif">
            <span className="mb-1 block font-code text-[10px] uppercase tracking-wider text-[#94A3B8]">Motif de la promotion (facultatif)</span>
            <input id="promotion-motif" value={motif} onChange={(e) => setMotif(e.target.value)} maxLength={2000}
              placeholder="Pourquoi cette identité est la bonne" data-testid="promotion-motif" className={CHAMP} />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={envoi} data-testid="promotion-btn"
              className={`flex h-9 items-center gap-1.5 rounded-md bg-[#F2B84B] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#F8CF7A] disabled:opacity-50 ${FOCUS}`}>
              <SealCheck size={14} aria-hidden /> {envoi ? "Promotion en cours…" : "Promouvoir l'application"}
            </button>
            <span className="text-[11px] text-[#7C93A8]">
              L'id <span className="font-code text-[10px] text-[#94A3B8]">{identifiant}</span> reste inchangé.
            </span>
          </div>
        </form>
      )}
    </section>
  );
}
