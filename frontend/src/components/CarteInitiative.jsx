import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, CheckCircle, FolderOpen } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { couleurDomaine } from "@/lib/domaines";
import { rel } from "@/components/case/utils";

export const GENRES_INIT = {
  a_confirmer: ["Confirmation demandée", "#B45309"],
  investigation_recommandee: ["Investigation recommandée", "#6D28D9"],
  decision_a_examiner: ["Décision à examiner", "#3730A3"],
  action_proposee: ["Action proposée", "#B45309"],
  a_surveiller: ["À surveiller", "#0369A1"],
  information: ["Information", "#71716D"],
};

function Bloc({ titre, children, testid }) {
  return (
    <div data-testid={testid}>
      <div className="font-code text-[9px] uppercase tracking-[0.18em] text-[#71716D]">{titre}</div>
      <div className="mt-1 text-xs leading-relaxed text-[#3F3F3C]">{children}</div>
    </div>
  );
}

// Une initiative répond toujours aux 7 questions : quoi, pourquoi moi, pourquoi maintenant, périmètre, preuves, confiance, attente
export default function CarteInitiative({ init, mesh, onChange }) {
  const navigate = useNavigate();
  const [preuves, setPreuves] = useState(false);
  const [rejet, setRejet] = useState(false);
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const g = GENRES_INIT[init.genre] || [init.genre, "#71716D"];
  const traitee = init.statut !== "en_attente";

  const repondre = async (choix, extra = {}) => {
    if (envoi) return;
    setEnvoi(true);
    try {
      const { data } = await api.post(`/initiatives/${init.id}/repondre`, { choix, motif: extra.motif || undefined, travail_id: extra.travail_id });
      toast.success("Réponse enregistrée — elle enrichit la mémoire collective");
      onChange?.(data.initiative);
      const low = choix.toLowerCase();
      if ((low.startsWith("créer") || low.startsWith("creer") || low.startsWith("ajouter")) && data.travail_id) navigate(`/travaux/${data.travail_id}`);
      if (low.startsWith("comparer") && data.travail_id) navigate(`/travaux/${data.travail_id}?vue=decisions`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Réponse impossible");
    } finally {
      setEnvoi(false);
    }
  };

  const actions = () => {
    if (init.genre === "investigation_recommandee") {
      return (
        <>
          {init.travail_id && (
            <button onClick={() => repondre("Ajouter à ce travail", { travail_id: init.travail_id })} disabled={envoi} data-testid={`init-ajouter-${init.id}`} className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-50">
              <FolderOpen size={12} /> Ajouter à ce travail
            </button>
          )}
          <button onClick={() => repondre("Créer un nouveau travail")} disabled={envoi} data-testid={`init-creer-${init.id}`} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-50">
            Créer un nouveau travail
          </button>
          <button onClick={() => repondre("Surveiller seulement")} disabled={envoi} data-testid={`init-surveiller-${init.id}`} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-50">
            Surveiller seulement
          </button>
        </>
      );
    }
    if (init.genre === "decision_a_examiner") {
      return (
        <>
          <button onClick={() => repondre("Comparer les options")} disabled={envoi} data-testid={`init-comparer-${init.id}`} className="rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA] disabled:opacity-50">
            Comparer les options
          </button>
          <button onClick={() => repondre("Demander une validation")} disabled={envoi} data-testid={`init-valider-${init.id}`} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-50">
            Demander une validation
          </button>
          <button onClick={() => setRejet(true)} data-testid={`init-rejeter-${init.id}`} className="rounded-md border border-[#B91C1C]/30 px-3 py-1.5 text-[11px] text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/5">
            Rejeter la proposition
          </button>
        </>
      );
    }
    if (init.genre === "action_proposee") {
      return (
        <>
          <button onClick={() => navigate(`/jumeaux/${init.jumeau_cible}/revue`)} data-testid={`init-examiner-${init.id}`} className="rounded-md bg-[#B45309] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#92400E]">
            Examiner l'admission
          </button>
          <button onClick={() => setRejet(true)} data-testid={`init-rejeter-${init.id}`} className="rounded-md border border-[#B91C1C]/30 px-3 py-1.5 text-[11px] text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/5">
            Rejeter la proposition
          </button>
        </>
      );
    }
    if (init.genre === "a_surveiller" || init.genre === "information") {
      return (
        <>
          <button onClick={() => window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: `Explique-moi : ${init.titre} — ${init.raison}` }))} data-testid={`init-comprendre-${init.id}`} className="rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
            Comprendre
          </button>
          <button onClick={() => repondre("Suivre")} disabled={envoi} data-testid={`init-suivre-${init.id}`} className="rounded-md border border-[#0369A1]/40 px-3 py-1.5 text-[11px] font-semibold text-[#0369A1] transition-colors hover:bg-[#0369A1]/10 disabled:opacity-50">
            Suivre
          </button>
          <button onClick={() => repondre("Ignorer")} disabled={envoi} data-testid={`init-ignorer-${init.id}`} className="rounded-md border border-[#E5E5E3] px-3 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-50">
            Ignorer
          </button>
        </>
      );
    }
    return (init.options || []).map((o) => (
      <button key={o} onClick={() => repondre(o)} disabled={envoi} data-testid={`init-option-${init.id}-${o.slice(0, 12)}`} className="rounded-md border border-[#B45309]/40 bg-[#FFFBEB] px-3 py-1.5 text-[11px] font-semibold text-[#B45309] transition-colors hover:bg-[#B45309]/10 disabled:opacity-50">
        {o}
      </button>
    ));
  };

  return (
    <article className={`rounded-xl border bg-white p-5 ${traitee ? "border-[#E5E5E3] opacity-75" : "border-[#E5E5E3] hover:border-[#D4D4D0]"} transition-colors`} data-testid={`initiative-${init.id}`}>
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.2em]">
        <span className="rounded border px-1.5 py-0.5" style={{ color: g[1], borderColor: `${g[1]}44`, backgroundColor: `${g[1]}0D` }} data-testid={`init-genre-${init.id}`}>{g[0]}</span>
        <span className="text-[#71716D]">{rel(init.quand)}</span>
        <span className="ml-auto text-[#71716D]">Urgence : {init.urgence}</span>
      </div>

      <h3 className="mt-2 text-base font-semibold leading-snug text-[#111110]" data-testid={`init-titre-${init.id}`}>{init.titre}</h3>

      <div className="mt-3 space-y-3">
        <Bloc titre="Pourquoi vous ?" testid={`init-pourquoi-${init.id}`}>{init.pourquoi_vous}</Bloc>
        <Bloc titre="Ce que Méridian a découvert" testid={`init-decouverte-${init.id}`}>
          {init.raison}
          {(init.preuves || []).length > 0 && (
            <>
              <button onClick={() => setPreuves((p) => !p)} data-testid={`init-preuves-${init.id}`} className="mt-1.5 flex items-center gap-1 font-code text-[10px] text-[#3730A3] hover:underline">
                <Eye size={11} /> {init.preuves.length} preuve{init.preuves.length > 1 ? "s" : ""} · {preuves ? "masquer" : "afficher"}
              </button>
              {preuves && (
                <ul className="mt-1.5 space-y-1 border-l-2 border-[#3730A3]/25 pl-2.5">
                  {init.preuves.map((p, k) => <li key={k} className="font-code text-[10px] leading-snug text-[#52524F]">{p}</li>)}
                </ul>
              )}
            </>
          )}
        </Bloc>
        <div className="grid gap-3 sm:grid-cols-2">
          <Bloc titre="Confiance" testid={`init-confiance-${init.id}`}>{init.confiance}</Bloc>
          <Bloc titre="Impact potentiel" testid={`init-impact-${init.id}`}>{init.impact}</Bloc>
        </div>
        <Bloc titre="Ce qui est attendu de vous" testid={`init-attendu-${init.id}`}>{init.attendu}</Bloc>
      </div>

      {(init.jumeaux || []).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {init.jumeaux.map((jid) => {
            const j = mesh?.jumeaux.find((x) => x.id === jid);
            const c = couleurDomaine(j?.domaine);
            return <span key={jid} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>{j?.nom || jid}</span>;
          })}
        </div>
      )}

      {init.travail_titre && !traitee && (
        <p className="mt-3 flex items-center gap-1.5 font-code text-[10px] text-[#52524F]" data-testid={`init-travail-${init.id}`}>
          <FolderOpen size={11} /> Travail existant correspondant : « {init.travail_titre} »
        </p>
      )}

      <div className="mt-3.5 border-t border-[#F0F0EE] pt-3" data-testid={`init-actions-${init.id}`}>
        {traitee ? (
          <p className="flex items-center gap-1.5 text-xs text-[#047857]" data-testid={`init-reponse-${init.id}`}>
            <CheckCircle size={13} weight="fill" />
            {init.statut === "suivi" ? "Sous surveillance — visible dans Suivis" : `Réponse : ${init.reponse?.choix}`}
            {init.reponse?.motif && <span className="text-[#71716D]">— motif conservé : {init.reponse.motif}</span>}
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">{actions()}</div>
        )}
        {rejet && !traitee && (
          <div className="mt-2 flex gap-1.5">
            <input value={motif} onChange={(e) => setMotif(e.target.value)} placeholder="Motif du rejet (conservé pour l'apprentissage)…" data-testid={`init-motif-${init.id}`} className="h-8 w-full rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:border-[#B91C1C]/50 focus:outline-none" />
            <button onClick={() => repondre("Rejeter la proposition", { motif })} disabled={envoi || !motif.trim()} data-testid={`init-rejeter-confirm-${init.id}`} className="shrink-0 rounded-md bg-[#B91C1C] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-40">
              Rejeter
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
