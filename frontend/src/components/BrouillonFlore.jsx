import LigneActiviteFlore from "./LigneActiviteFlore";
import MarkdownFlore from "./MarkdownFlore";
import { brouillonLisible } from "@/lib/fluxFlore";

// La réponse en cours (jumeau/flux.py) : les vraies étapes de Flore, puis son brouillon marqué « en relecture ».
// `onArreter` : bouton « Arrêter » ; une fois arrêté, le brouillon reste affiché, marqué « interrompu ».
export default function BrouillonFlore({ flux, onArreter, testid = "flore-brouillon" }) {
  const etapes = flux.etapes.length ? flux.etapes : ["Flore se met au travail…"];
  return (
    <div className="space-y-2" data-testid={testid}>
      <LigneActiviteFlore testid={`${testid}-activite`} activite={{ id: "en-cours", status: flux.interrompu ? "done" : "running",
        ops: etapes.map((label, i) => ({ label, status: flux.interrompu || i < etapes.length - 1 ? "done" : "running" })) }} />
      {flux.brouillon && (
        <div className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4">
          <MarkdownFlore texte={brouillonLisible(flux.brouillon)} />
          {!flux.relecture && !flux.interrompu && <span className="curseur-teletype">▍</span>}
          {flux.interrompu
            ? <span className="mt-2 inline-block rounded-full border border-[#F2B84B]/50 px-2 py-0.5 font-code text-[10px] text-[#F2B84B]" data-testid="flore-brouillon-interrompu">interrompu</span>
            : <span className="mt-2 inline-block rounded-full border border-[#F2B84B]/50 px-2 py-0.5 font-code text-[10px] text-[#F2B84B]">en relecture</span>}
        </div>
      )}
      {onArreter && !flux.interrompu && (
        <button type="button" onClick={onArreter} aria-label="Arrêter la réponse" data-testid={`${testid}-arreter`}
          className="rounded-md border border-white/[0.15] px-2.5 py-1 text-xs text-[#D8E2EA] transition-colors hover:border-[#F87171]/60 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">
          Arrêter
        </button>
      )}
    </div>
  );
}
