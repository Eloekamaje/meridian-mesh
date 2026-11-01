import { useEffect, useRef, useState } from "react";
import { entetesPerimetre } from "./api";
import { usePerimetre } from "./perimetre";

// Un seul canal SSE par onglet, partagé par la barre latérale et les notifications. Le serveur envoie d'abord
// un instantané (« pret »), puis les changements du périmètre. Une reconnexion rejoue l'instantané : les
// événements manqués pendant une coupure sont ainsi rattrapés sans polling.
const abonnes = new Set();
let etat = { controller: null, cible: null };

const API = () => `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function entetes(cible) {
  const espace = cible?.startsWith("vue:")
    ? localStorage.getItem("meridian.perimetre.espace") || "mesh-global"
    : cible || "mesh-global";
  return { ...entetesPerimetre(), "X-Espace": espace };
}

function diffuser(evenement) {
  for (const abonne of [...abonnes]) {
    try { abonne(evenement); } catch { /* un abonné qui casse ne coupe pas les autres */ }
  }
}

async function boucle(controller, cible) {
  let essai = 0;
  while (!controller.signal.aborted) {
    try {
      const reponse = await fetch(`${API()}/evenements`, {
        headers: { Accept: "text/event-stream", ...entetes(cible) },
        signal: controller.signal,
        cache: "no-store",
      });
      if (!reponse.ok || !reponse.body) throw new Error(`canal indisponible (${reponse.status})`);
      essai = 0;
      const lecteur = reponse.body.getReader();
      const decodeur = new TextDecoder();
      let tampon = "";
      for (;;) {
        const { value, done } = await lecteur.read();
        if (done) break;
        tampon += decodeur.decode(value, { stream: true });
        const blocs = tampon.split(/\r?\n\r?\n/);
        tampon = blocs.pop();
        for (const bloc of blocs) {
          const ligne = bloc.split(/\r?\n/).find((l) => l.startsWith("data: "));
          if (!ligne) continue;
          try { diffuser(JSON.parse(ligne.slice(6))); } catch { /* trame illisible : on ignore */ }
        }
      }
      throw new Error("canal fermé");
    } catch {
      // Une coupure réseau peut aussi remonter en AbortError : seul notre propre AbortController arrête la boucle.
      if (controller.signal.aborted) return;
      await new Promise((ok) => setTimeout(ok, Math.min(1000 * 2 ** essai, 15000)));
      essai += 1;
    }
  }
}

function demarrer(cible) {
  etat.controller?.abort();
  const controller = new AbortController();
  etat = { controller, cible };
  boucle(controller, cible).catch(() => {});
  return () => {
    if (etat.controller === controller) {
      etat.controller = null;
      controller.abort();
    }
  };
}

export function EvenementsProvider({ children }) {
  const { cible } = usePerimetre();
  const [relance, setRelance] = useState(0);

  useEffect(() => {
    if (!cible) return undefined;
    return demarrer(cible);
  }, [cible, relance]);

  // Au retour d'un onglet ou après une coupure réseau : on rouvre le canal et le serveur renvoie l'instantané.
  useEffect(() => {
    const relancer = () => {
      if (document.visibilityState === "visible") setRelance((v) => v + 1);
    };
    document.addEventListener("visibilitychange", relancer);
    window.addEventListener("online", relancer);
    return () => {
      document.removeEventListener("visibilitychange", relancer);
      window.removeEventListener("online", relancer);
    };
  }, []);

  return children;
}

// Abonne un composant aux événements du canal. Le hook garde toujours le dernier handler sans se réabonner.
export function useEvenements(handler) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const abonne = (evenement) => ref.current?.(evenement);
    abonnes.add(abonne);
    return () => abonnes.delete(abonne);
  }, []);
}
