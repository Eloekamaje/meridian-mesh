import { useCallback, useState } from "react";

// Zoom sémantique GLOBAL : le niveau de détail dépend uniquement du zoom,
// jamais du domaine traversé — la même grammaire visuelle partout dans le Mesh.
// 1 Global → 2 Domaine (constellation) → 3 Jumeau (robots) → 4 Composants & preuves
// Hystérésis de ±0.06 sur chaque borne : un micro-mouvement de molette autour d'un
// seuil ne fait jamais vaciller le niveau (convention map UI : stabilité des couches).
const BORNES = { 1: [0, 0.6], 2: [0.6, 1.15], 3: [1.15, 1.9], 4: [1.9, 99] };
const MARGE = 0.06;

export default function useZoomSemantique() {
  const [zoomNiveau, setZoomNiveau] = useState(2);

  const onMove = useCallback((_, vp) => {
    const z = vp.zoom;
    setZoomNiveau((n) => {
      const [lo, hi] = BORNES[n];
      if (z >= lo - MARGE && z <= hi + MARGE) return n;
      return z < 0.6 ? 1 : z > 1.9 ? 4 : z > 1.15 ? 3 : 2;
    });
  }, []);

  return { zoomNiveau, onMove };
}
