import { ArrowLeft } from "@phosphor-icons/react";

// Un seul bouton retour pour toute l'application : même style, même place (à gauche du titre), libellé « Parent » sur écran
// large, icône seule (avec libellé accessible) sur petit écran pour laisser la place au titre.
export function BoutonRetour({ label, onClick, testid, accent = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      aria-label={`Retour : ${label}`}
      title={`Retour : ${label}`}
      className={`flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors sm:h-8 ${accent ? "border-[#60A5FA]/60 bg-[#60A5FA]/10 font-semibold text-[#BFDBFE] hover:bg-[#60A5FA]/20" : "border-[rgba(148,163,184,0.16)] bg-[#0F1D28] text-[#94A3B8] hover:text-[#F2F6F8]"}`}
    >
      <ArrowLeft size={13} />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

// En-tête des pages de détail (revue, commande, rapport…) : retour + titre + repères à gauche, statuts et actions à droite ;
// sur petit écran, le titre passe en pleine largeur et les actions descendent dessous.
export default function EntetePage({ retour, surtitre, titre, sousTitre, droite, testid, titreTestid, children }) {
  return (
    <div className="shrink-0 border-b border-[rgba(148,163,184,0.16)] px-4 py-3 sm:px-8 sm:py-3.5" data-testid={testid}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex w-full min-w-0 items-center gap-3 sm:w-auto sm:flex-1 sm:gap-4">
          {retour && <BoutonRetour {...retour} />}
          <div className="min-w-0 flex-1">
            {surtitre && <div className="mb-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">{surtitre}</div>}
            <h1 className="font-display text-base font-bold leading-snug tracking-tight text-[#F2F6F8] sm:text-xl" data-testid={titreTestid}>{titre}</h1>
            {sousTitre && <div className="font-code text-[11px] text-[#7C93A8]">{sousTitre}</div>}
          </div>
        </div>
        {droite && <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{droite}</div>}
      </div>
      {children}
    </div>
  );
}
