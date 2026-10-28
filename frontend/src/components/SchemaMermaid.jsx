import { useEffect, useId, useState } from "react";

// Un schéma Mermaid dans une réponse de Flore. Le harness a déjà gardé les seules flèches fondées et posé leurs
// couleurs ; ici, on dessine en mode strict (pas de script ni de lien dans le schéma, libellés nettoyés).
// La bibliothèque n'est chargée qu'au premier schéma.
let pret = null;
function charger() {
  pret = pret || import("mermaid").then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false, securityLevel: "strict", theme: "dark",
      themeVariables: { background: "#0B1220", primaryColor: "#132433", primaryBorderColor: "#60A5FA",
        primaryTextColor: "#F2F6F8", lineColor: "#7C93A8", fontSize: "13px" },
    });
    return mermaid;
  });
  return pret;
}

export default function SchemaMermaid({ code, complet = true }) {
  const id = `schema-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [etat, setEtat] = useState({ svg: null, erreur: false });
  useEffect(() => {
    if (!complet) return undefined;
    let actif = true;
    charger()
      .then((mermaid) => mermaid.render(id, code))
      .then(({ svg }) => actif && setEtat({ svg, erreur: false }))
      .catch(() => actif && setEtat({ svg: null, erreur: true }));
    return () => { actif = false; };
  }, [code, complet, id]);

  const cadre = "my-2 overflow-x-auto rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1220] p-3";
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
  // svg produit par mermaid en mode strict (libellés échappés, aucun gestionnaire d'événement).
  return <div className={cadre} data-testid="schema-mermaid" role="img" aria-label="Schéma"
    dangerouslySetInnerHTML={{ __html: etat.svg }} />;
}
