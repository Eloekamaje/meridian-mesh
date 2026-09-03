import { useCallback, useEffect, useRef, useState } from "react";

const CLE = "atlas.chrome.decals";

const lireTout = () => {
  try {
    return JSON.parse(localStorage.getItem(CLE) || "{}");
  } catch {
    return {};
  }
};

// Élément de chrome « glissable » : décalage persisté (localStorage) par rapport à son
// ancrage par défaut. Poignée : glisser pour déplacer (borné au conteneur), double-clic pour revenir.
export default function useGlissable(cle, conteneurRef) {
  const ref = useRef(null);
  const [decal, setDecal] = useState(() => {
    const d = lireTout()[cle];
    return d && Number.isFinite(d.x) && Number.isFinite(d.y) ? d : { x: 0, y: 0 };
  });
  const decalRef = useRef(decal);

  const appliquer = useCallback(
    (d, persister = true) => {
      decalRef.current = d;
      setDecal(d);
      if (persister) {
        try {
          localStorage.setItem(CLE, JSON.stringify({ ...lireTout(), [cle]: d }));
        } catch {
          /* stockage indisponible */
        }
      }
    },
    [cle]
  );

  const reinitialiser = useCallback(() => appliquer({ x: 0, y: 0 }), [appliquer]);

  const surPoigneeDown = useCallback(
    (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const el = ref.current;
      if (!el) return;
      const base = decalRef.current;
      const rect = el.getBoundingClientRect();
      const cr = conteneurRef?.current?.getBoundingClientRect();
      // Position ancrée (sans le décalage courant) relative au conteneur — sert au bornage
      const ancX = cr ? rect.left - base.x - cr.left : 0;
      const ancY = cr ? rect.top - base.y - cr.top : 0;
      const px = e.clientX;
      const py = e.clientY;
      const bouger = (ev) => {
        let nx = base.x + ev.clientX - px;
        let ny = base.y + ev.clientY - py;
        if (cr) {
          nx = Math.min(Math.max(nx, -ancX + 6), cr.width - ancX - rect.width - 6);
          ny = Math.min(Math.max(ny, -ancY + 6), cr.height - ancY - rect.height - 6);
        }
        appliquer({ x: Math.round(nx), y: Math.round(ny) }, false);
      };
      const lacher = () => {
        window.removeEventListener("pointermove", bouger);
        window.removeEventListener("pointerup", lacher);
        appliquer(decalRef.current, true);
      };
      window.addEventListener("pointermove", bouger);
      window.addEventListener("pointerup", lacher);
    },
    [appliquer, conteneurRef]
  );

  // Re-bornage automatique : si le conteneur ou l'élément change de taille (colonnes de
  // layout, redimensionnement, dépliage du tiroir), l'offset persisté est re-clampé —
  // un élément déplacé ne peut jamais sortir du champ ni passer sous une colonne.
  useEffect(() => {
    const c = conteneurRef?.current;
    const el = ref.current;
    if (!c || !el || typeof ResizeObserver === "undefined") return undefined;
    let t;
    const reborner = () => {
      // Délai > transition d'ancrage (300 ms) : le bornage mesure la position finale
      clearTimeout(t);
      t = setTimeout(() => {
        const d = decalRef.current;
        if (!d.x && !d.y) return;
        const cr = c.getBoundingClientRect();
        const r = el.getBoundingClientRect();
        const ancX = r.left - d.x - cr.left;
        const ancY = r.top - d.y - cr.top;
        const nx = Math.min(Math.max(d.x, -ancX + 6), cr.width - ancX - r.width - 6);
        const ny = Math.min(Math.max(d.y, -ancY + 6), cr.height - ancY - r.height - 6);
        if (Math.round(nx) !== d.x || Math.round(ny) !== d.y) appliquer({ x: Math.round(nx), y: Math.round(ny) });
      }, 350);
    };
    const ro = new ResizeObserver(reborner);
    ro.observe(c);
    return () => { ro.disconnect(); clearTimeout(t); };
  }, [conteneurRef, appliquer]);

  return { ref, decal, surPoigneeDown, reinitialiser };
}
