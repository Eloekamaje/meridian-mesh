import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";
import { usePerimetre } from "./perimetre";

const MeshCtx = createContext({ mesh: null, recharger: () => {}, jumeauPar: () => null });

export function MeshProvider({ children }) {
  const [mesh, setMesh] = useState(null);
  const { version } = usePerimetre();
  const recharger = useCallback(async () => {
    const { data } = await api.get("/mesh");
    setMesh(data);
    return data;
  }, []);
  useEffect(() => {
    recharger().catch(() => {});
  }, [recharger, version]);
  const jumeauPar = useCallback((id) => mesh?.jumeaux.find((j) => j.id === id) || null, [mesh]);
  return <MeshCtx.Provider value={{ mesh, recharger, jumeauPar }}>{children}</MeshCtx.Provider>;
}

export const useMesh = () => useContext(MeshCtx);
