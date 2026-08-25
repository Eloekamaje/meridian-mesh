import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./api";

const PerimetreCtx = createContext(null);

const LS_PERSONA = "meridian.persona";
const LS_CIBLE = "meridian.perimetre";
const LS_ESPACE = "meridian.perimetre.espace";

export function PerimetreProvider({ children }) {
  const [persona, setPersona] = useState(() => localStorage.getItem(LS_PERSONA) || "architecte");
  const [cible, setCible] = useState(() => localStorage.getItem(LS_CIBLE) || "mesh-global");
  const [personas, setPersonas] = useState([]);
  const [espaces, setEspaces] = useState([]);
  const [vues, setVues] = useState([]);
  const [info, setInfo] = useState(null);
  const [version, setVersion] = useState(0);

  const espaceId = cible.startsWith("vue:") ? localStorage.getItem(LS_ESPACE) || "mesh-global" : cible;
  const vueActive = cible.startsWith("vue:") ? vues.find((v) => `vue:${v.id}` === cible) || null : null;

  useEffect(() => {
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
  }, []);

  const rafraichir = useCallback(async () => {
    try {
      const [es, vs, inf] = await Promise.all([
        api.get("/espaces"),
        api.get("/vues"),
        api.get("/perimetre"),
      ]);
      setEspaces(es.data);
      setVues(vs.data);
      setInfo(inf.data);
    } catch {}
  }, [version]);

  useEffect(() => { rafraichir(); }, [rafraichir]);

  const changerPersona = useCallback(async (p) => {
    localStorage.setItem(LS_PERSONA, p);
    setPersona(p);
    let defaut = "mesh-global";
    try {
      const { data } = await api.get("/espaces", { headers: { "X-Persona": p } });
      defaut = data.find((e) => !e.global)?.id || data[0]?.id || "mesh-global";
    } catch {}
    localStorage.setItem(LS_CIBLE, defaut);
    localStorage.setItem(LS_ESPACE, defaut);
    setCible(defaut);
    setVersion((v) => v + 1);
    api.post("/journal", { action: "changement d'identité", detail: `persona ${p}` }, { headers: { "X-Persona": p, "X-Espace": defaut } }).catch(() => {});
  }, []);

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
      setVues(data);
    } catch {}
  }, []);

  return (
    <PerimetreCtx.Provider
      value={{ persona, cible, espaceId, vueActive, personas, espaces, vues, info, version, changerPersona, changerCible, rechargerVues }}
    >
      {children}
    </PerimetreCtx.Provider>
  );
}

export const usePerimetre = () => useContext(PerimetreCtx);
