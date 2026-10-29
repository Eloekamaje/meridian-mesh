// Les messages écrits pendant que Flore répond (useFileMessages) : en attente au-dessus de la zone de saisie, ils
// partiront ensemble à la fin du tour. « Réorienter maintenant » arrête le tour : ils partent aussitôt.
export default function FileMessages({ file, occupe, onRetirer, onModifier, onReorienter, testid = "file-messages" }) {
  if (!file?.length) return null;
  const btn = "rounded px-1 font-code text-[10px] text-[#93C5FD] hover:bg-[#60A5FA]/15 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#60A5FA]";
  return (
    <div className="mb-2 space-y-1.5" data-testid={testid} aria-live="polite">
      <div className="flex items-center justify-between font-code text-[10px] uppercase tracking-[0.15em] text-[#7C93A8]">
        <span>{`En attente · ${file.length} message${file.length > 1 ? "s" : ""}, envoyé${file.length > 1 ? "s" : ""} à la fin de la réponse`}</span>
        {occupe && onReorienter && (
          <button type="button" onClick={onReorienter} data-testid={`${testid}-reorienter`}
            className="rounded border border-[#F2B84B]/50 px-2 py-0.5 normal-case tracking-normal text-[#F2B84B] hover:bg-[#F2B84B]/10 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#F2B84B]">
            Réorienter maintenant
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {file.map((m, i) => (
          <span key={`${i}-${m}`} className="inline-flex max-w-full items-center gap-2 rounded-full border border-[rgba(148,163,184,0.25)] bg-[#0F1D28] py-0.5 pl-3 pr-1.5 text-xs text-[#D8E2EA]">
            <span className="truncate">{m}</span>
            <button type="button" className={btn} onClick={() => onModifier?.(i)} aria-label={`Modifier le message en attente : ${m}`}>Modifier</button>
            <button type="button" className={btn} onClick={() => onRetirer?.(i)} aria-label={`Retirer le message en attente : ${m}`}>Retirer</button>
          </span>
        ))}
      </div>
    </div>
  );
}
