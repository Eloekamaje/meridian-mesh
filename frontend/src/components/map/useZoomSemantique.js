import { useCallback, useRef, useState } from "react";

export default function useZoomSemantique({
  jumeauFocus, domaineInterne,
  sortirJumeau, sortirDomaine, entrerJumeau, entrerDomaine,
  jumeauPar, verrouNav, zoomEntree,
}) {
  const [zoomNiveau, setZoomNiveau] = useState(2);
  const survol = useRef(null);
  const dernierZ = useRef(null);

  const onMove = useCallback((_, vp) => {
    const z = vp.zoom;
    setZoomNiveau(z < 0.6 ? 1 : z > 1.15 ? 3 : 2);
    const prev = dernierZ.current;
    dernierZ.current = z;
    if (prev == null || Date.now() - verrouNav.current < 1000) return;
    const ze = zoomEntree.current;
    // Zoom arrière : remonter d'un niveau dans la hiérarchie (seuil bas pour tolérer un dézoom de confort)
    if (jumeauFocus && ze && z < prev && z < ze * 0.38) { sortirJumeau(); return; }
    if (!jumeauFocus && domaineInterne && ze && z < prev && z < ze * 0.45) { sortirDomaine(); return; }
    // Zoom avant sur l'élément sous le pointeur : entrée progressive
    if (!jumeauFocus && z > prev && prev < 2.3 && z >= 2.3 && survol.current) {
      if (survol.current.type === "twin") {
        const j = jumeauPar(survol.current.id);
        if (j && !j.anonyme) { entrerJumeau(j); return; }
      }
      if (survol.current.type === "region" && !domaineInterne) entrerDomaine(survol.current.label);
    }
  }, [jumeauFocus, domaineInterne, sortirJumeau, sortirDomaine, entrerJumeau, entrerDomaine, jumeauPar, verrouNav, zoomEntree]);

  const onNodeMouseEnter = useCallback((_, node) => {
    if (node.type === "region") survol.current = { type: "region", label: node.data.label };
    else if (node.type === "twin" && !node.data?.porte && !node.data?.voisinRel && !node.data?.jumeau?.anonyme) survol.current = { type: "twin", id: node.data.jumeau.id };
    else survol.current = null;
  }, []);

  const onNodeMouseLeave = useCallback(() => { survol.current = null; }, []);

  return { zoomNiveau, onMove, onNodeMouseEnter, onNodeMouseLeave };
}
