import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";
import { usePerimetre } from "./perimetre";

const MeshCtx = createContext({ mesh: null, recharger: () => {}, jumeauPar: () => null });

// Même précaution que dans le périmètre : un 200 au corps inattendu (backend absent,
// page HTML renvoyée par un serveur statique) ne doit pas entrer dans l'état. Un Mesh
// mal formé vaut « pas encore de Mesh » — les consommateurs gèrent déjà ce cas.
const meshValide = (d) => (d && typeof d === "object" && Array.isArray(d.jumeaux) && Array.isArray(d.relations) ? d : null);

export function MeshProvider({ children }) {
  const [mesh, setMesh] = useState(null);
  const { version } = usePerimetre();
  const recharger = useCallback(async () => {
    const { data } = await api.get("/mesh");
    const valide = meshValide(data);
    // Rejet explicite : le produit l'ignore (le Mesh reste « pas encore chargé »),
    // la démonstration le traite comme un échec de scène plutôt qu'un faux succès.
    if (!valide) throw new Error("Mesh illisible");
    setMesh(valide);
    return valide;
  }, []);
  useEffect(() => {
    recharger().catch(() => {});
  }, [recharger, version]);
  const jumeauPar = useCallback((id) => mesh?.jumeaux?.find((j) => j.id === id) || null, [mesh]);
  return <MeshCtx.Provider value={{ mesh, recharger, jumeauPar }}>{children}</MeshCtx.Provider>;
}

export const useMesh = () => useContext(MeshCtx);
