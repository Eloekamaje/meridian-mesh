import { useState } from "react";
import { CaretDown } from "@phosphor-icons/react";

export default function Depliable({
  id,
  titre,
  resume,
  children,
  ouvertParDefaut = false,
  ouvert: ouvertControle,
  onOuvertChange,
  testid,
  className = "",
}) {
  const [ouvertInterne, setOuvertInterne] = useState(ouvertParDefaut);
  const controle = ouvertControle !== undefined;
  const ouvert = controle ? ouvertControle : ouvertInterne;
  const contenuId = `${id}-contenu`;

  const basculer = () => {
    const suivant = !ouvert;
    if (!controle) setOuvertInterne(suivant);
    onOuvertChange?.(suivant);
  };

  return (
    <div className={className} data-testid={testid}>
      <button
        type="button"
        onClick={basculer}
        aria-expanded={ouvert}
        aria-controls={contenuId}
        data-testid={testid ? `${testid}-bouton` : undefined}
        className="flex w-full items-center justify-between gap-3 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-3 py-2.5 text-left transition-colors hover:border-[#41576D] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]"
      >
        <span className="min-w-0">
          <span className="block font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">{titre}</span>
          {resume && <span className="mt-0.5 block text-[11px] leading-relaxed text-[#7C93A8]">{resume}</span>}
        </span>
        <CaretDown
          size={14}
          aria-hidden="true"
          className={`shrink-0 text-[#7C93A8] transition-transform ${ouvert ? "rotate-180" : ""}`}
        />
      </button>
      {ouvert && (
        <div id={contenuId} data-testid={testid ? `${testid}-contenu` : undefined} className="mt-2">
          {children}
        </div>
      )}
    </div>
  );
}
