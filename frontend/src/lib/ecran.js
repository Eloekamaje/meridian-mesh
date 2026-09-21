import { useEffect, useState } from "react";

// Taille d'écran de l'application : « mobile » (< 768 px), « tablette » (768–1023 px), « bureau » (≥ 1024 px).
// La coquille s'y adapte (barre latérale : tiroir, rail d'icônes, ou colonne) ; les pages, elles, ne changent que leur mise en page.
export const SEUILS = { tablette: 768, bureau: 1024 };

const lire = () => {
  if (typeof window === "undefined") return "bureau";
  const l = window.innerWidth;
  return l < SEUILS.tablette ? "mobile" : l < SEUILS.bureau ? "tablette" : "bureau";
};

export function useEcran() {
  const [ecran, setEcran] = useState(lire);
  useEffect(() => {
    const maj = () => setEcran(lire());
    const mm = [SEUILS.tablette, SEUILS.bureau].map((w) => window.matchMedia(`(min-width: ${w}px)`));
    mm.forEach((m) => m.addEventListener("change", maj));
    maj();
    return () => mm.forEach((m) => m.removeEventListener("change", maj));
  }, []);
  return ecran;
}
