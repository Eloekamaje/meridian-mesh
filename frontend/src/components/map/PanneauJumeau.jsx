import { useState } from "react";
import { X } from "@phosphor-icons/react";
import { couleurDomaine } from "@/lib/domaines";
import { TwinDetail } from "./details";

// Colonne droite de l'Atlas : intelligence locale du jumeau sélectionné.
// La carte se redimensionne (colonne de layout) — le jumeau n'est jamais caché derrière.
// Le MÊME panneau à toutes les tailles : colonne de 400 px dans la mise en page (bureau), superposée à droite de la carte (tablette),
// feuille en bas d'écran (téléphone). Même contenu, mêmes rubriques ; seule la façon de se poser sur la carte change.
export default function PanneauJumeau({
  jumeau, voisins, relationsRecentes,
  favori, onBasculerFavori, statsTwin, onInterroger,
  onExplorerRelations, onOuvrirInvestigation, onChoisirVoisin, onFermer,
  presentation = "colonne", // "colonne" | "superposee" | "feuillet"
}) {
  const [replie, setReplie] = useState(false);
  const feuillet = presentation === "feuillet";
  const classes = {
    colonne: "flex h-full w-[400px] shrink-0 flex-col border-l border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/85 backdrop-blur-xl",
    superposee: "absolute inset-y-0 right-0 z-20 flex w-[min(400px,92vw)] flex-col border-l border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/95 shadow-2xl backdrop-blur-xl",
    feuillet: "glass absolute inset-x-0 bottom-0 z-20 flex max-h-[70vh] flex-col overflow-hidden rounded-t-2xl border-t border-[rgba(148,163,184,0.16)] shadow-2xl",
  }[presentation];
  return (
    <aside className={classes} data-testid="panneau-jumeau" data-presentation={presentation} data-state={feuillet && replie ? "reduit" : "complet"}>
      {feuillet && (
        <button onClick={() => setReplie((r) => !r)} data-testid="feuillet-poignee" title={replie ? "Déplier le détail" : "Replier (état réduit)"} className="flex h-9 w-full shrink-0 items-center justify-center">
          <span className="h-1 w-10 rounded-full bg-[#5B7089]" />
        </button>
      )}
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
      {!(feuillet && replie) && (
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
      )}
    </aside>
  );
}
