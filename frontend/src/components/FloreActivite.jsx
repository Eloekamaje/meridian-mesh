import LigneActiviteFlore from "./LigneActiviteFlore";

// Attente d'une réponse de Flore tant qu'aucune étape réelle n'est connue : une seule ligne indéterminée,
// sans étapes nommées. L'ancienne version inventait trois libellés et les révélait un par un comme si le travail
// avançait (plan de remédiation L0.4). Dès que le flux donne une vraie étape, c'est elle qui s'affiche.
const ATTENTE = { id: "attente-flore", status: "running", ops: [] };

const etapesDe = () => [];  // plus aucun libellé inventé ; conservé pour ne pas casser les appelants

// Laisse aux étapes le temps de se dérouler même si la réponse arrive vite
export function delaiMin(promesse, ms = 2400) {
  return Promise.all([promesse, new Promise((r) => setTimeout(r, ms))]).then(([res]) => res);
}

// Activité d'une réponse dont aucune étape n'a été enregistrée : la ligne le dit, elle ne fabrique rien.
export function activiteTerminee(genre = "defaut") {
  return { id: `fin-${genre}`, status: "done", ops: etapesDe(genre) };
}

export default function FloreActivite({ testid = "flore-activite" }) {
  return <LigneActiviteFlore activite={ATTENTE} testid={testid} />;
}
