import { createContext, useCallback, useContext, useState } from "react";

const ContexteCtx = createContext(null);

export function ContexteProvider({ children }) {
  const [selection, setSelection] = useState([]);
  const [domaineSel, setDomaineSel] = useState(null);
  const [focusCarte, setFocusCarte] = useState(null);
  const [focusVisuel, setFocusVisuel] = useState(null);
  const [lot, setLot] = useState(null);
  const [floreOuverte, setFloreOuverte] = useState(false);
  // Instantané contextuel de l'Atlas transmis à Flore (surface, sélection, couches, zoom)
  const [atlasCtx, setAtlasCtx] = useState(null);
  // État de navigation de l'Atlas (viewport, sélection, couches) — mémorisé à la sortie
  // de la page pour être restauré exactement au retour (jamais de fitView au retour)
  const [atlasEtat, setAtlasEtat] = useState(null);

  const ajouterJumeau = useCallback((id) => setSelection((s) => (s.includes(id) ? s : [...s, id])), []);
  const retirerJumeau = useCallback((id) => setSelection((s) => s.filter((x) => x !== id)), []);
  const commanderCarte = useCallback((cmd) => setFocusCarte(cmd ? { ...cmd, ts: Date.now() } : null), []);
  const ouvrirFlore = useCallback(() => setFloreOuverte(true), []);
  const fermerFlore = useCallback(() => setFloreOuverte(false), []);
  const basculerFlore = useCallback(() => setFloreOuverte((o) => !o), []);

  return (
    <ContexteCtx.Provider
      value={{ selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, ajouterJumeau, retirerJumeau, focusVisuel, setFocusVisuel, lot, setLot, floreOuverte, ouvrirFlore, fermerFlore, basculerFlore, atlasCtx, setAtlasCtx, atlasEtat, setAtlasEtat }}
    >
      {children}
    </ContexteCtx.Provider>
  );
}

export const useContexte = () => useContext(ContexteCtx);
