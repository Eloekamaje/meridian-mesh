import { couleurDomaine } from "@/lib/domaines";
import { TwinDetail } from "./details";
import PanneauLateral from "./PanneauLateral";

// Intelligence locale du jumeau sélectionné : le contenu du panneau de l'Atlas (voir PanneauLateral pour la coque, commune à tous les détails).
export default function PanneauJumeau({
  jumeau, voisins, relationsRecentes,
  favori, onBasculerFavori, statsTwin, onInterroger,
  onExplorerRelations, onOuvrirInvestigation, onChoisirVoisin, onFermer,
  presentation = "colonne",
}) {
  return (
    <PanneauLateral kicker={`Jumeau · ${jumeau.domaine}`} couleur={couleurDomaine(jumeau.domaine)} onFermer={onFermer} presentation={presentation} testid="panneau-jumeau">
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
    </PanneauLateral>
  );
}
