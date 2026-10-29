import { useEffect, useRef, useState } from "react";
import { usePerimetre } from "./perimetre";
import { usePilotage } from "./pilotage";

// Un seul canal SSE par onglet, partagé par la barre latérale et les notifications. Le serveur envoie d'abord
// un instantané (« pret »), puis les changements de la persona. Une reconnexion rejoue l'instantané : les
// événements manqués pendant une coupure sont ainsi rattrapés sans polling.
const abonnes = new Set();
let etat = { controller: null, persona: null, cible: null };

const API = () => `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function entetes(persona, cible) {
  const espace = cible?.startsWith("vue:")
    ? localStorage.getItem("meridian.perimetre.espace") || "mesh-global"
    : cible || "mesh-global";
  return { "X-Persona": persona, "X-Espace": espace };
}

function diffuser(evenement) {
  for (const abonne of [...abonnes]) {
    try { abonne(evenement); } catch { /* un abonné qui casse ne coupe pas les autres */ }
  }
}

async function boucle(controller, persona, cible) {
  let essai = 0;
  while (!controller.signal.aborted) {
    try {
      const reponse = await fetch(`${API()}/evenements`, {
        headers: { Accept: "text/event-stream", ...entetes(persona, cible) },
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

function demarrer(persona, cible) {
  etat.controller?.abort();
  const controller = new AbortController();
  etat = { controller, persona, cible };
  boucle(controller, persona, cible).catch(() => {});
  return () => {
    if (etat.controller === controller) {
      etat.controller = null;
      controller.abort();
    }
  };
}

export function EvenementsProvider({ children }) {
  const { persona, cible } = usePerimetre();
  const pilote = usePilotage();
  const demo = !!pilote;
  const [relance, setRelance] = useState(0);

  useEffect(() => {
    if (demo || !persona) return undefined;
    return demarrer(persona, cible);
  }, [persona, cible, demo, relance]);

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
