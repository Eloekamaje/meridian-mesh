import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";

const PerimetreCtx = createContext(null);

const LS_CIBLE = "meridian.perimetre";
const LS_ESPACE = "meridian.perimetre.espace";

// Un 200 au corps inattendu (backend absent, proxy ou page d'erreur HTML renvoyée par
// le serveur statique) n'est PAS une erreur réseau : les .catch ci-dessous ne le voient
// pas et la chaîne finirait dans l'état. Sans ce filtre, `espaces.some(...)` dans le
// Topbar — monté sur toutes les pages — fait tomber l'application entière.
const liste = (d) => (Array.isArray(d) ? d : []);
const objet = (d) => (d && typeof d === "object" && !Array.isArray(d) ? d : null);

export function PerimetreProvider({ children }) {
  const [authMode, setAuthMode] = useState("demo");
  const [utilisateur, setUtilisateur] = useState(null);
  const [acteur, setActeur] = useState("demo");
  const [cible, setCible] = useState(() => localStorage.getItem(LS_CIBLE) || "mesh-global");
  const [espaces, setEspaces] = useState([]);
  const [vues, setVues] = useState([]);
  const [info, setInfo] = useState(null);
  const [version, setVersion] = useState(0);

  const espaceId = cible.startsWith("vue:") ? localStorage.getItem(LS_ESPACE) || "mesh-global" : cible;
  const vueActive = cible.startsWith("vue:") ? vues.find((v) => `vue:${v.id}` === cible) || null : null;

  useEffect(() => {
    api.get("/moi").then((r) => {
      const d = objet(r.data);
      if (!d) return;
      if (d.auth_mode) setAuthMode(d.auth_mode);
      if (d.utilisateur) setUtilisateur(d.utilisateur);
      if (d.acteur) setActeur(d.acteur);
    }).catch(() => {});
  }, []);

  const rafraichir = useCallback(async () => {
    try {
      const [es, vs, inf] = await Promise.all([
        api.get("/espaces"),
        api.get("/vues"),
        api.get("/perimetre"),
      ]);
      setEspaces(liste(es.data));
      setVues(liste(vs.data));
      setInfo(objet(inf.data));
    } catch {}
  }, [version]);

  useEffect(() => { rafraichir(); }, [rafraichir]);

  const changerCible = useCallback((c) => {
    localStorage.setItem(LS_CIBLE, c);
    if (!c.startsWith("vue:")) localStorage.setItem(LS_ESPACE, c);
    setCible(c);
    setVersion((v) => v + 1);
    api.post("/journal", { action: "changement de périmètre", detail: c }).catch(() => {});
  }, []);

  const rechargerVues = useCallback(async () => {
    try {
      const { data } = await api.get("/vues");
      setVues(liste(data));
    } catch {}
  }, []);

  return (
    <PerimetreCtx.Provider
      value={{ acteur, cible, espaceId, vueActive, espaces, vues, info, version, authMode, utilisateur, changerCible, rechargerVues }}
    >
      {children}
    </PerimetreCtx.Provider>
  );
}

export const usePerimetre = () => useContext(PerimetreCtx);
