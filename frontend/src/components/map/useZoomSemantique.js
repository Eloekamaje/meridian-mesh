import { useCallback, useState } from "react";

// Zoom sémantique GLOBAL : le niveau de détail dépend uniquement du zoom,
// jamais du domaine traversé — la même grammaire visuelle partout dans le Mesh.
// 1 Capacités → 2 Domaines → 3 Applications & flux → 4 Composants & preuves
export default function useZoomSemantique() {
  const [zoomNiveau, setZoomNiveau] = useState(2);

  const onMove = useCallback((_, vp) => {
    const z = vp.zoom;
    setZoomNiveau(z < 0.6 ? 1 : z > 1.9 ? 4 : z > 1.15 ? 3 : 2);
  }, []);

  return { zoomNiveau, onMove };
}
