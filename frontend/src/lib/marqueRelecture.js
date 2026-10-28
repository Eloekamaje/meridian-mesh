// Ce que l'étiquette de relecture a le droit de dire (plan de remédiation L0.1 et L0.3).
// `relue` seul autorise « relu » : une correction n'est jamais relue (une seule révision au plus), une panne du
// relecteur ne s'affiche pas comme une relecture, et un verdict illisible ne vaut pas approbation.
const BADGES = {
  relue: { texte: "relu", testid: "flore-relu", teinte: "#34D399" },
  corrigee_non_relue: { texte: "corrigé — non relu", testid: "flore-corrige", teinte: "#93C5FD" },
  objection_sans_effet: { texte: "relecture non appliquée", testid: "flore-relecture-non-appliquee", teinte: "#F2B84B" },
  indisponible: { texte: "non relu", testid: "flore-non-relu", teinte: "#7C93A8" },
  verdict_illisible: { texte: "non relu", testid: "flore-non-relu", teinte: "#7C93A8" },
};

export function badgeRelecture(data) {
  if (!data) return null;
  const etat = data.relecture_etat;
  if (etat) return BADGES[etat] || null;
  // Réponse d'un serveur antérieur à L0.1 : `relu` y était posé sans condition, on ne peut donc rien en dire.
  return null;
}
