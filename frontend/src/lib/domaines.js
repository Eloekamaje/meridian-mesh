export const DOMAINES = {
  Paiement: "#3B82F6",
  Client: "#34D399",
  Risque: "#F87171",
  Support: "#FB923C",
  "Opérations": "#38BDF8",
  Distribution: "#F0ABFC",
  "Non classé": "#9CA3AF",
};

export const couleurDomaine = (d) => DOMAINES[d] || "#9CA3AF";

export const VERBES = {
  decouvert: { label: "Découvert", verbe: "Découvrir", couleur: "#22D3EE", accroche: "Nouvelles connaissances candidates" },
  a_comprendre: { label: "À comprendre", verbe: "Comprendre", couleur: "#A78BFA", accroche: "Confiance insuffisante, validation requise" },
  a_decider: { label: "À décider", verbe: "Décider", couleur: "#FBBF24", accroche: "Conclusions et actions en attente d'approbation" },
};

export const NATURES = {
  relation: { label: "Relation", couleur: "#22D3EE" },
  comportement: { label: "Comportement", couleur: "#A78BFA" },
  connaissance: { label: "Connaissance", couleur: "#38BDF8" },
  contradiction: { label: "Contradiction", couleur: "#F87171" },
  incident: { label: "Incident", couleur: "#EF4444" },
  changement: { label: "Changement", couleur: "#FBBF24" },
};

export const ETATS_RELATION = {
  observee: { label: "Observée", couleur: "rgba(255,255,255,0.35)" },
  supposee: { label: "Supposée", couleur: "#22D3EE" },
  validation: { label: "Validation A2A", couleur: "#A78BFA" },
  confirmee: { label: "Confirmée", couleur: "rgba(255,255,255,0.6)" },
  contestee: { label: "Contestée", couleur: "#F87171" },
  obsolete: { label: "Obsolète", couleur: "rgba(255,255,255,0.25)" },
};

export const MATURITES = {
  "bien connu": "#10B981",
  "partiellement découvert": "#22D3EE",
  "instable": "#F59E0B",
  "en transformation": "#3B82F6",
  "insuffisamment couvert": "#F87171",
};

export const PRIORITES = {
  critique: { label: "Critique", couleur: "#EF4444" },
  haute: { label: "Haute", couleur: "#F59E0B" },
  moyenne: { label: "Moyenne", couleur: "#3B82F6" },
  basse: { label: "Basse", couleur: "#6B7280" },
};

export const NATURES_EVENEMENT = {
  signal: "#3B82F6",
  preuve: "#34D399",
  alerte: "#EF4444",
  decouverte: "#22D3EE",
  trace: "#6B7280",
};

export const couleurConfiance = (v) => (v >= 70 ? "#10B981" : v >= 40 ? "#F59E0B" : "#EF4444");
