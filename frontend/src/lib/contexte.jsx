import { createContext, useCallback, useContext, useState } from "react";

const ContexteCtx = createContext(null);

export function ContexteProvider({ children }) {
  const [selection, setSelection] = useState([]);
  const [domaineSel, setDomaineSel] = useState(null);
  const [focusCarte, setFocusCarte] = useState(null);
  const [focusVisuel, setFocusVisuel] = useState(null);

  const ajouterJumeau = useCallback((id) => setSelection((s) => (s.includes(id) ? s : [...s, id])), []);
  const retirerJumeau = useCallback((id) => setSelection((s) => s.filter((x) => x !== id)), []);
  const commanderCarte = useCallback((cmd) => setFocusCarte(cmd ? { ...cmd, ts: Date.now() } : null), []);

  return (
    <ContexteCtx.Provider
      value={{ selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, ajouterJumeau, retirerJumeau, focusVisuel, setFocusVisuel }}
    >
      {children}
    </ContexteCtx.Provider>
  );
}

export const useContexte = () => useContext(ContexteCtx);
