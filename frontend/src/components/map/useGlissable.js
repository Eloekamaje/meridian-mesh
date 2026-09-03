import { useCallback, useRef, useState } from "react";

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

  return { ref, decal, surPoigneeDown, reinitialiser };
}
