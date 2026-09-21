// Panneau de lecture d'une preuve : consultable sans casser la lecture (pause auto),
// mention « pièce de démonstration » (§7.6, EXP-13).
import { X } from "@phosphor-icons/react";

export default function PreuvePanneau({ preuve, onFermer }) {
  if (!preuve) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#04090F]/80 p-6" onClick={onFermer} data-testid="preuve-panneau">
      <div
        className="w-full max-w-[560px] rounded-xl border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-start justify-between gap-4">
          <div>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#58A6FF]">{preuve.sourceType}</div>
            <h3 className="mt-1 font-display text-lg font-bold text-[#F2F6F8]" data-testid="preuve-titre">{preuve.title}</h3>
          </div>
          <button onClick={onFermer} className="rounded-lg p-1.5 text-[#7C93A8] transition-colors hover:bg-[#071019] hover:text-[#F2F6F8]" data-testid="preuve-fermer-btn" aria-label="Fermer">
            <X size={16} />
          </button>
        </div>
        <div className="font-code text-[10px] text-[#7C93A8]">{preuve.periodLabel}</div>
        <blockquote className="mt-4 rounded-lg border-l-2 border-[#60A5FA] bg-[#071019] p-4 text-sm leading-relaxed text-[#D8E2EA]" data-testid="preuve-extrait">
          {preuve.excerpt}
        </blockquote>
        <div className="mt-4 space-y-2 text-sm">
          <p className="text-[#D8E2EA]"><span className="font-semibold text-[#34D399]">Ce que ça supporte — </span>{preuve.supports}</p>
          <p className="text-[#D8E2EA]"><span className="font-semibold text-[#F2B84B]">Ses limites — </span>{preuve.limits}</p>
        </div>
        <p className="mt-4 border-t border-[rgba(148,163,184,0.1)] pt-3 text-center font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">
          Pièce de démonstration — données fictives
        </p>
      </div>
    </div>
  );
}
