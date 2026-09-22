export const DOMAINES = {
  Paiement: "#818CF8",
  Client: "#4ADE80",
  Risque: "#F87171",
  Support: "#FB923C",
  "Opérations": "#A3E635",
  Distribution: "#EC4899",
  "Non classé": "#94A3B8",
};

export const couleurDomaine = (d) => DOMAINES[d] || "#94A3B8";

export const VERBES = {
  decouvert: { label: "Découvert", verbe: "Découvrir", couleur: "#60A5FA", accroche: "Nouvelles connaissances candidates" },
  a_comprendre: { label: "À comprendre", verbe: "Comprendre", couleur: "#93C5FD", accroche: "Confiance insuffisante, validation requise" },
  a_decider: { label: "À décider", verbe: "Décider", couleur: "#F59E0B", accroche: "Conclusions et actions en attente d'approbation" },
};

export const NATURES = {
  relation: { label: "Relation", couleur: "#60A5FA" },
  comportement: { label: "Comportement", couleur: "#93C5FD" },
  connaissance: { label: "Connaissance", couleur: "#BFDBFE" },
  contradiction: { label: "Contradiction", couleur: "#F87171" },
  incident: { label: "Incident", couleur: "#F87171" },
  changement: { label: "Changement", couleur: "#F59E0B" },
  trajectoire: { label: "Trajectoire", couleur: "#60A5FA" },
  opportunite: { label: "Opportunité", couleur: "#4ADE80" },
};

export const ETATS_RELATION = {
  observee: { label: "Observée", couleur: "#60A5FA" },
  supposee: { label: "Supposée", couleur: "#F59E0B" },
  validation: { label: "Validation A2A", couleur: "#93C5FD" },
  confirmee: { label: "Confirmée", couleur: "rgba(226,232,240,0.85)" },
  contestee: { label: "Contestée", couleur: "#F87171" },
  obsolete: { label: "Obsolète", couleur: "rgba(148,163,184,0.35)" },
};

export const MATURITES = {
  "bien connu": "#34D399",
  "partiellement découvert": "#60A5FA",
  "instable": "#F2B84B",
  "en transformation": "#60A5FA",
  "insuffisamment couvert": "#F87171",
};

export const PRIORITES = {
  critique: { label: "Critique", couleur: "#F87171" },
  haute: { label: "Haute", couleur: "#F2B84B" },
  moyenne: { label: "Moyenne", couleur: "#60A5FA" },
  basse: { label: "Basse", couleur: "#7C93A8" },
};

export const NATURES_EVENEMENT = {
  signal: "#60A5FA",
  preuve: "#34D399",
  alerte: "#F87171",
  decouverte: "#60A5FA",
  trace: "#7C93A8",
};

export const couleurConfiance = (v) => (v >= 70 ? "#34D399" : v >= 40 ? "#F2B84B" : "#F87171");
