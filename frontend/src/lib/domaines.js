export const DOMAINES = {
  Paiement: "#9B87F5",
  Client: "#34D399",
  Risque: "#F87171",
  Support: "#FB923C",
  "Opérations": "#58A6FF",
  Distribution: "#F472B6",
  "Non classé": "#7C93A8",
};

export const couleurDomaine = (d) => DOMAINES[d] || "#7C93A8";

export const VERBES = {
  decouvert: { label: "Découvert", verbe: "Découvrir", couleur: "#25D0C8", accroche: "Nouvelles connaissances candidates" },
  a_comprendre: { label: "À comprendre", verbe: "Comprendre", couleur: "#9B87F5", accroche: "Confiance insuffisante, validation requise" },
  a_decider: { label: "À décider", verbe: "Décider", couleur: "#F2B84B", accroche: "Conclusions et actions en attente d'approbation" },
};

export const NATURES = {
  relation: { label: "Relation", couleur: "#25D0C8" },
  comportement: { label: "Comportement", couleur: "#9B87F5" },
  connaissance: { label: "Connaissance", couleur: "#58A6FF" },
  contradiction: { label: "Contradiction", couleur: "#F87171" },
  incident: { label: "Incident", couleur: "#F87171" },
  changement: { label: "Changement", couleur: "#F2B84B" },
};

export const ETATS_RELATION = {
  observee: { label: "Observée", couleur: "#25D0C8" },
  supposee: { label: "Supposée", couleur: "#F2B84B" },
  validation: { label: "Validation A2A", couleur: "#9B87F5" },
  confirmee: { label: "Confirmée", couleur: "rgba(216,226,234,0.78)" },
  contestee: { label: "Contestée", couleur: "#F87171" },
  obsolete: { label: "Obsolète", couleur: "rgba(148,163,184,0.35)" },
};

export const MATURITES = {
  "bien connu": "#34D399",
  "partiellement découvert": "#25D0C8",
  "instable": "#F2B84B",
  "en transformation": "#9B87F5",
  "insuffisamment couvert": "#F87171",
};

export const PRIORITES = {
  critique: { label: "Critique", couleur: "#F87171" },
  haute: { label: "Haute", couleur: "#F2B84B" },
  moyenne: { label: "Moyenne", couleur: "#9B87F5" },
  basse: { label: "Basse", couleur: "#7C93A8" },
};

export const NATURES_EVENEMENT = {
  signal: "#9B87F5",
  preuve: "#34D399",
  alerte: "#F87171",
  decouverte: "#25D0C8",
  trace: "#7C93A8",
};

export const couleurConfiance = (v) => (v >= 70 ? "#34D399" : v >= 40 ? "#F2B84B" : "#F87171");
