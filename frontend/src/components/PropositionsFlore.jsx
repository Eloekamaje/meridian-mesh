import { useState } from "react";
import { CheckCircle, XCircle } from "@phosphor-icons/react";

// Approbation en ligne (P2) : les connaissances que Flore a proposées pendant ce tour, à trancher ici comme sur la
// page Revue. La décision est exécutée une seule fois côté serveur ; une fois tranchée, la carte dit qui a décidé.
// `actif` : le message appartient à un Travail (sinon la proposition se lit sans se trancher).
const LIBELLES = { ACCEPTED: "Validée", CONTESTED: "Contestée" };

export default function PropositionsFlore({ propositions, index, actif, bloque = false, onDecider }) {
  const [enCours, setEnCours] = useState(null);
  if (!propositions?.length) return null;
  const decider = async (claim, decision) => {
    setEnCours(claim);
    try { await onDecider(claim, decision); } finally { setEnCours(null); }
  };
  return (
    <div className="space-y-2" data-testid={`propositions-${index}`}>
      {propositions.map((p) => (
        <div key={p.claim} className="rounded-lg border border-[#F2B84B]/40 bg-[#F2B84B]/[0.05] px-3 py-2 text-xs">
          <div className="font-semibold text-[#F2B84B]">Flore propose une connaissance sur {p.nom || p.jumeau}</div>
          <div className="mt-0.5 text-[#CBD5E1]"><span className="font-code text-[11px] text-[#93C5FD]">{p.predicat}</span> — {p.objet}</div>
          {p.decision ? (
            <div className="mt-1.5 flex items-center gap-1.5 text-[#7C93A8]" data-testid={`decision-${index}-${p.claim}`}>
              {p.decision.valeur === "ACCEPTED" ? <CheckCircle size={13} className="text-[#34D399]" aria-hidden="true" /> : <XCircle size={13} className="text-[#F87171]" aria-hidden="true" />}
              {`${LIBELLES[p.decision.valeur] || p.decision.valeur} par ${p.decision.par}`}
            </div>
          ) : actif ? (
            <>
              <div className="mt-1 text-[#7C93A8]">Effet : la connaissance quitte « proposée » ; validée, elle compte dans ce que le jumeau sait. Il faut la permission « Valider » sur ce jumeau.</div>
              <div className="mt-1.5 flex gap-2">
                <button type="button" disabled={bloque || enCours === p.claim} onClick={() => decider(p.claim, "ACCEPTED")}
                  data-testid={`approuver-${index}-${p.claim}`}
                  className="rounded-md border border-[#34D399]/50 px-2.5 py-0.5 text-[#34D399] hover:bg-[#34D399]/10 disabled:opacity-50 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#34D399]">
                  Valider
                </button>
                <button type="button" disabled={bloque || enCours === p.claim} onClick={() => decider(p.claim, "CONTESTED")}
                  data-testid={`contester-${index}-${p.claim}`}
                  className="rounded-md border border-white/20 px-2.5 py-0.5 text-[#D8E2EA] hover:border-[#F87171]/60 disabled:opacity-50 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]">
                  Contester
                </button>
              </div>
            </>
          ) : (
            <div className="mt-1 text-[#7C93A8]">À trancher dans la revue du jumeau.</div>
          )}
        </div>
      ))}
    </div>
  );
}
