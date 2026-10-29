import { useCallback, useEffect, useRef, useState } from "react";
import { demanderEnFlux, estArret, journalActivite } from "./fluxFlore";

// Une action de Flore qui s'écrit au fil de l'eau (régénérer, modifier) et qu'on peut arrêter.
// `flux` : étapes + brouillon à afficher ; `arreter` coupe la requête. À l'arrêt, `surArret(brouillon)` relit la
// conversation (le serveur a enregistré la réponse partielle) pendant que le brouillon reste affiché « interrompu ».
export default function useFluxAction() {
  const [flux, setFlux] = useState(null);
  const ctrl = useRef(null);
  useEffect(() => () => ctrl.current?.abort(), []);
  const arreter = useCallback(() => ctrl.current?.abort(), []);
  const lancer = useCallback(async (chemin, corps, surArret) => {
    const c = new AbortController();
    ctrl.current = c;
    const journal = journalActivite((ops) => setFlux((f) => f && { ...f, etapes: ops }));
    let brouillon = "";
    setFlux({ etapes: [], brouillon: "", relecture: false });
    try {
      return await demanderEnFlux(chemin, corps, {
        signal: c.signal,
        onEtape: journal.onEtape, onOutil: journal.onOutil, onMission: journal.onMission, onCoupure: (c) => setFlux((f) => f && { ...f, coupure: c }),
        onTexte: (d) => { brouillon += d; setFlux((f) => f && { ...f, brouillon }); },
        onRelecture: () => setFlux((f) => f && { ...f, relecture: true }),
      });
    } catch (err) {
      if (!estArret(err)) throw err;
      setFlux((f) => f && { ...f, interrompu: true });
      await surArret?.(brouillon);
      return null;
    } finally {
      ctrl.current = null;
      setFlux(null);
    }
  }, []);
  return { flux, lancer, arreter };
}
