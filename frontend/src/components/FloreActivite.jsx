import { useEffect, useMemo, useState } from "react";
import LigneActiviteFlore from "./LigneActiviteFlore";

// Activité de Flore quand la réponse vient du vrai backend : les libellés se remplacent sur place,
// dans la ligne d'activité commune. (En démonstration, c'est le scénario qui pilote la ligne.)
const ETAPES = {
  defaut: ["S'informe dans le Mesh…", "Croise les sources concernées…", "Comprend la situation…"],
  rapport: ["Se saisit de la situation…", "Rassemble les preuves et les jumeaux concernés…", "Rédige son rapport…"],
  incident: ["Analyse la dérive en cours…", "Croise traces, incidents passés et règles récentes…", "Évalue la propagation…"],
  relation: ["Examine les signaux entre les jumeaux…", "Vérifie les preuves concordantes…", "Mesure la confiance…"],
  phenomene: ["Examine les signaux entre les jumeaux…", "Vérifie les preuves concordantes…", "Mesure la confiance…"],
  changement: ["Rejoue le scénario de changement…", "Mesure la propagation sur les dépendants…", "Évalue les options…"],
  travail: ["Relit la mémoire du travail…", "Repère où vous vous étiez arrêté…", "Rassemble le contexte…"],
};

const etapesDe = (genre) => ETAPES[genre] || ETAPES.defaut;

// Laisse aux étapes le temps de se dérouler même si la réponse arrive vite
export function delaiMin(promesse, ms = 2400) {
  return Promise.all([promesse, new Promise((r) => setTimeout(r, ms))]).then(([res]) => res);
}

// Activité terminée, à attacher à une réponse : « Analyse terminée · Voir l'activité »
export function activiteTerminee(genre = "defaut") {
  return { id: `fin-${genre}`, status: "done", ops: etapesDe(genre).map((label) => ({ label, status: "done" })) };
}

export default function FloreActivite({ genre = "defaut", testid = "flore-activite" }) {
  const etapes = useMemo(() => etapesDe(genre), [genre]);
  const [courant, setCourant] = useState(0);

  useEffect(() => {
    if (courant >= etapes.length - 1) return undefined;
    const t = setTimeout(() => setCourant((c) => c + 1), 850);
    return () => clearTimeout(t);
  }, [courant, etapes.length]);

  const activite = {
    id: `en-cours-${genre}`,
    status: "running",
    ops: etapes.slice(0, courant + 1).map((label, i) => ({ label, status: i < courant ? "done" : "running" })),
  };
  return <LigneActiviteFlore activite={activite} testid={testid} />;
}
