export const DOMAINES = {
  Paiement: "#3730A3",
  Client: "#047857",
  Risque: "#B91C1C",
  Support: "#C2410C",
  "Opérations": "#0369A1",
  Distribution: "#A21CAF",
  "Non classé": "#71716D",
};

export const couleurDomaine = (d) => DOMAINES[d] || "#71716D";

export const VERBES = {
  decouvert: { label: "Découvert", verbe: "Découvrir", couleur: "#0E7490", accroche: "Nouvelles connaissances candidates" },
  a_comprendre: { label: "À comprendre", verbe: "Comprendre", couleur: "#6D28D9", accroche: "Confiance insuffisante, validation requise" },
  a_decider: { label: "À décider", verbe: "Décider", couleur: "#B45309", accroche: "Conclusions et actions en attente d'approbation" },
};

export const NATURES = {
  relation: { label: "Relation", couleur: "#0E7490" },
  comportement: { label: "Comportement", couleur: "#6D28D9" },
  connaissance: { label: "Connaissance", couleur: "#0369A1" },
  contradiction: { label: "Contradiction", couleur: "#B91C1C" },
  incident: { label: "Incident", couleur: "#B91C1C" },
  changement: { label: "Changement", couleur: "#B45309" },
};

export const ETATS_RELATION = {
  observee: { label: "Observée", couleur: "#0E7490" },
  supposee: { label: "Supposée", couleur: "#D97706" },
  validation: { label: "Validation A2A", couleur: "#6D28D9" },
  confirmee: { label: "Confirmée", couleur: "rgba(17,17,16,0.7)" },
  contestee: { label: "Contestée", couleur: "#B91C1C" },
  obsolete: { label: "Obsolète", couleur: "rgba(17,17,16,0.35)" },
};

export const MATURITES = {
  "bien connu": "#047857",
  "partiellement découvert": "#0E7490",
  "instable": "#B45309",
  "en transformation": "#3730A3",
  "insuffisamment couvert": "#B91C1C",
};

export const PRIORITES = {
  critique: { label: "Critique", couleur: "#B91C1C" },
  haute: { label: "Haute", couleur: "#B45309" },
  moyenne: { label: "Moyenne", couleur: "#3730A3" },
  basse: { label: "Basse", couleur: "#71716D" },
};

export const NATURES_EVENEMENT = {
  signal: "#3730A3",
  preuve: "#047857",
  alerte: "#B91C1C",
  decouverte: "#0E7490",
  trace: "#71716D",
};

export const couleurConfiance = (v) => (v >= 70 ? "#047857" : v >= 40 ? "#B45309" : "#B91C1C");
