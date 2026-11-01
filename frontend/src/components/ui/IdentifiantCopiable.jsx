import { useRef, useState } from "react";
import { Check, Copy } from "@phosphor-icons/react";

export default function IdentifiantCopiable({
  identifiant,
  libelle = "Identifiant",
  testid,
  className = "",
}) {
  const [etat, setEtat] = useState(null);
  const codeRef = useRef(null);
  const valeur = identifiant == null ? "" : String(identifiant);

  const selectionner = () => {
    if (!codeRef.current || typeof window === "undefined") return;
    const selection = window.getSelection?.();
    if (!selection) return;
    const plage = document.createRange?.();
    if (!plage) return;
    plage.selectNodeContents(codeRef.current);
    selection.removeAllRanges();
    selection.addRange(plage);
  };

  const copier = async () => {
    if (!valeur) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("presse-papier indisponible");
      await navigator.clipboard.writeText(valeur);
      setEtat("copie");
    } catch {
      selectionner();
      setEtat("selection");
    }
  };

  if (!valeur) return null;

  return (
    <span className={`inline-flex max-w-full items-center gap-1.5 rounded border border-[rgba(148,163,184,0.18)] bg-[#0B1620] px-1.5 py-0.5 ${className}`} data-testid={testid}>
      <span className="shrink-0 font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">{libelle}</span>
      <code ref={codeRef} className="min-w-0 select-all truncate font-code text-[10px] text-[#D8E2EA]" data-testid={testid ? `${testid}-valeur` : undefined}>
        {valeur}
      </code>
      <button
        type="button"
        onClick={copier}
        title={etat === "copie" ? "Identifiant copié" : etat === "selection" ? "Identifiant sélectionné — Ctrl+C pour copier" : `Copier ${libelle.toLowerCase()}`}
        aria-label={etat === "copie" ? `${libelle} copié` : etat === "selection" ? `${libelle} sélectionné, utiliser Ctrl+C pour copier` : `Copier ${libelle.toLowerCase()} ${valeur}`}
        data-testid={testid ? `${testid}-copier` : undefined}
        className="shrink-0 text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
      >
        {etat === "copie" ? <Check size={10} weight="bold" /> : <Copy size={10} />}
      </button>
    </span>
  );
}
