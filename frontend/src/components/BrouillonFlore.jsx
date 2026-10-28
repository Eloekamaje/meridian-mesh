import LigneActiviteFlore from "./LigneActiviteFlore";
import { brouillonLisible } from "@/lib/fluxFlore";

// La réponse en cours (jumeau/flux.py) : les vraies étapes de Flore, puis son brouillon marqué « en relecture ».
export default function BrouillonFlore({ flux, testid = "flore-brouillon" }) {
  const etapes = flux.etapes.length ? flux.etapes : ["Flore se met au travail…"];
  return (
    <div className="space-y-2" data-testid={testid}>
      <LigneActiviteFlore testid={`${testid}-activite`} activite={{ id: "en-cours", status: "running",
        ops: etapes.map((label, i) => ({ label, status: i < etapes.length - 1 ? "done" : "running" })) }} />
      {flux.brouillon && (
        <div className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4">
          <p className="whitespace-pre-line text-sm leading-relaxed text-[#D8E2EA]">
            {brouillonLisible(flux.brouillon)}{!flux.relecture && <span className="curseur-teletype">▍</span>}
          </p>
          <span className="mt-2 inline-block rounded-full border border-[#F2B84B]/50 px-2 py-0.5 font-code text-[10px] text-[#F2B84B]">en relecture</span>
        </div>
      )}
    </div>
  );
}
