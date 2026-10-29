import { useEffect, useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import api from "@/lib/api";
import { typeSource } from "@/lib/preuvesFlore";

// La carte d'une preuve citée par Flore (Design System §67, §70), sur le modèle du panneau de la démonstration
// (PreuvePanneau) : type, source, lu au commit, extrait (lignes citées surlignées), ce que ça supporte, emplacement.
// L'extrait vient du serveur (/preuves/extrait), qui vérifie que l'interlocuteur voit les preuves de ce jumeau.
export default function PanneauPreuve({ preuve, n, phrase, onFermer }) {
  const [extrait, setExtrait] = useState(null); // null : en cours ; { lignes } ; { erreur }
  const fermer = useRef(null);
  const type = typeSource(preuve?.detail);
  const commit = /@([0-9a-f]{7,40})/.exec(preuve?.detail || "")?.[1];

  useEffect(() => {
    if (!preuve) return undefined;
    let actif = true;
    setExtrait(null);
    if (type !== "Code") { setExtrait({ lignes: null }); return undefined; }
    api.get("/preuves/extrait", { params: { locator: preuve.detail } })
      .then(({ data }) => actif && setExtrait(data))
      .catch(() => actif && setExtrait({ erreur: true }));
    return () => { actif = false; };
  }, [preuve, type]);

  useEffect(() => {
    if (!preuve) return undefined;
    fermer.current?.focus();
    const touche = (e) => { if (e.key === "Escape") onFermer(); };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [preuve, onFermer]);

  if (!preuve) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#04090F]/80 p-6" onClick={onFermer} data-testid="panneau-preuve">
      <div role="dialog" aria-modal="true" aria-labelledby="panneau-preuve-titre"
        className="max-h-[85vh] w-full max-w-[640px] overflow-y-auto rounded-xl border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-start justify-between gap-4">
          <div>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#58A6FF]">Preuve {n} · {type}</div>
            <h3 id="panneau-preuve-titre" className="mt-1 font-display text-lg font-bold text-[#F2F6F8]">{preuve.source}</h3>
          </div>
          <button ref={fermer} onClick={onFermer} aria-label="Fermer la preuve"
            className="rounded-lg p-1.5 text-[#7C93A8] transition-colors hover:bg-[#071019] hover:text-[#F2F6F8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]">
            <X size={16} />
          </button>
        </div>
        {commit && <div className="font-code text-[10px] text-[#7C93A8]">Lu au commit {commit}</div>}

        <div className="mt-4 overflow-x-auto rounded-lg border-l-2 border-[#60A5FA] bg-[#071019] p-3 font-code text-[12px] leading-relaxed" data-testid="panneau-preuve-extrait">
          {extrait === null && <span className="text-[#7C93A8]">Lecture de l'extrait…</span>}
          {extrait?.erreur && <span className="text-[#7C93A8]">Extrait indisponible pour vous (droits ou dépôt introuvable).</span>}
          {extrait && !extrait.erreur && !extrait.lignes && <span className="text-[#7C93A8]">Ouvrir la source pour lire ce passage.</span>}
          {extrait?.lignes?.map((l) => (
            <div key={l.n} className={`flex gap-3 whitespace-pre ${l.citee ? "bg-[#60A5FA]/10 text-[#F2F6F8]" : "text-[#7C93A8]"}`}>
              <span className="w-8 shrink-0 select-none text-right text-[#526578]">{l.n}</span><span>{l.texte}</span>
            </div>
          ))}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          {phrase && <p className="text-[#D8E2EA]"><span className="font-semibold text-[#34D399]">Ce que ça supporte — </span>{phrase}</p>}
          <p className="break-all font-code text-[11px] text-[#7C93A8]"><span className="font-sans font-semibold text-[#94A3B8]">Emplacement — </span>{preuve.detail}</p>
        </div>
      </div>
    </div>
  );
}
