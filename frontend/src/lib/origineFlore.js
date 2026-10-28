// D'où vient une réponse de Flore (plan de remédiation L0.5) : une réponse écrite d'avance ne se présente jamais
// comme une réponse calculée. Le serveur pose `origine` sur chaque réponse ; « modele » est la seule origine qui
// n'a rien à signaler, puisqu'elle est celle que l'utilisateur croit toujours avoir.
const ORIGINES = {
  scenario: { texte: "scénario de démonstration", teinte: "#F2B84B", testid: "flore-origine-scenario" },
  registre: { texte: "registre", teinte: "#7C93A8", testid: "flore-origine-registre" },
  recherche: { texte: "recherche plein texte", teinte: "#7C93A8", testid: "flore-origine-recherche" },
  repli: { texte: "aucune réponse calculée", teinte: "#F2B84B", testid: "flore-origine-repli" },
  refus: { texte: "question hors périmètre", teinte: "#7C93A8", testid: "flore-origine-refus" },
};

export function badgeOrigine(data) {
  const origine = data?.origine;
  if (!origine || origine === "modele") return null;
  return ORIGINES[origine] || { texte: origine, teinte: "#7C93A8", testid: "flore-origine" };
}
