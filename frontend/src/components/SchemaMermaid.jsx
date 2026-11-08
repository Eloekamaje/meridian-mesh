import { useEffect, useId, useState } from "react";

// Un schéma Mermaid dans une réponse de Flore. Le harness a déjà gardé les seules flèches fondées et posé leurs
// couleurs ; ici, on dessine avec Pele, le même moteur que le chat OpenCode (mode strict, SVG thémé).
// La bibliothèque n'est chargée qu'au premier schéma.
let pret = null;
function charger() {
  pret = pret || import("pele/lazy");
  return pret;
}

export default function SchemaMermaid({ code, complet = true }) {
  const id = `schema-pele-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [etat, setEtat] = useState({ svg: null, erreur: false });
  useEffect(() => {
    if (!complet) return undefined;
    let actif = true;
    charger()
      .then(async (pele) => {
        if (!pele.detectType(code)) throw new Error("diagramme non reconnu");
        const fontSans = '"Inter", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        return pele.renderAsync(code, {
          idPrefix: `${id}-`,
          fontFamily: fontSans,
          fontSize: 14,
          images: false,
          linkRel: "noopener noreferrer",
        });
      })
      .then(({ svg }) => actif && setEtat({ svg, erreur: false }))
      .catch(() => actif && setEtat({ svg: null, erreur: true }));
    return () => { actif = false; };
  }, [code, complet, id]);

  const cadre = "mt-3 mb-6 min-h-24 overflow-x-auto rounded-[6px] border-[0.5px] border-[#ffffff1a] bg-[#2e2e2e] p-4";
  if (!complet) return <div className={`${cadre} text-xs text-[#7C93A8]`}>Schéma en préparation…</div>;
  if (etat.erreur) {
    return (
      <div className={cadre} data-testid="schema-illisible">
        <div className="mb-1 text-xs text-[#F2B84B]">Schéma illisible, voici sa description :</div>
        <pre className="whitespace-pre-wrap font-code text-[11px] text-[#94A3B8]">{code}</pre>
      </div>
    );
  }
  if (!etat.svg) return <div className={`${cadre} text-xs text-[#7C93A8]`}>Dessin du schéma…</div>;
  // svg produit par Pele en mode strict (libellés échappés, aucun gestionnaire d'événement).
  return <div className={cadre} data-testid="schema-mermaid" role="img" aria-label="Schéma"
    dangerouslySetInnerHTML={{ __html: etat.svg }} />;
}
