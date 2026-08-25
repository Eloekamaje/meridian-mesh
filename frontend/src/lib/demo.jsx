import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";

const DemoCtx = createContext(null);

export function DemoProvider({ children }) {
  const [actes, setActes] = useState([]);
  const [courant, setCourant] = useState(-1);

  useEffect(() => {
    api.get("/demo/actes").then((r) => setActes(r.data)).catch(() => {});
  }, []);

  const demarrer = useCallback(() => setCourant(0), []);
  const quitter = useCallback(() => setCourant(-1), []);
  const suivant = useCallback(() => {
    setCourant((c) => (c >= actes.length - 1 ? -1 : c + 1));
  }, [actes.length]);
  const precedent = useCallback(() => setCourant((c) => Math.max(0, c - 1)), []);

  return (
    <DemoCtx.Provider value={{ actes, courant, demarrer, quitter, suivant, precedent }}>
      {children}
    </DemoCtx.Provider>
  );
}

export const useDemo = () => useContext(DemoCtx);
