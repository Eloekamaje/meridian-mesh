import { X } from "@phosphor-icons/react";
import { couleurDomaine } from "@/lib/domaines";
import { TwinDetail } from "./details";

// Colonne gauche de l'Atlas : intelligence locale du jumeau sélectionné.
// La carte se redimensionne (colonne de layout) — le jumeau n'est jamais caché derrière.
export default function PanneauJumeau({
  jumeau, voisins, relationsRecentes,
  favori, onBasculerFavori, statsTwin, onInterroger,
  onExplorerRelations, onOuvrirInvestigation, onChoisirVoisin, onFermer,
}) {
  return (
    <aside className="flex h-full w-[400px] shrink-0 flex-col border-r border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/85 backdrop-blur-xl" data-testid="panneau-jumeau">
      <div className="flex items-center gap-2 border-b border-[rgba(148,163,184,0.16)] px-4 py-2.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(jumeau.domaine) }} />
        <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Jumeau · {jumeau.domaine}</span>
        <button
          onClick={onFermer}
          data-testid="panneau-jumeau-fermer"
          title="Fermer (Échap)"
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-[#7C93A8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
        >
          <X size={13} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <TwinDetail
          selected={jumeau}
          favori={favori}
          onBasculerFavori={onBasculerFavori}
          statsTwin={statsTwin}
          onInterroger={onInterroger}
          voisins={voisins}
          relationsRecentes={relationsRecentes}
          onChoisirVoisin={onChoisirVoisin}
          onExplorerRelations={onExplorerRelations}
          onOuvrirInvestigation={onOuvrirInvestigation}
        />
      </div>
    </aside>
  );
}
