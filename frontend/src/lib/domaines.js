export const DOMAINES = {
  Paiement: "#3B82F6",
  Client: "#34D399",
  Risque: "#F87171",
  Support: "#FBBF24",
  "Opérations": "#38BDF8",
  Distribution: "#F0ABFC",
  "Non classé": "#9CA3AF",
};

export const couleurDomaine = (d) => DOMAINES[d] || "#9CA3AF";

export const PRIORITES = {
  critique: { label: "Critique", couleur: "#EF4444" },
  haute: { label: "Haute", couleur: "#F59E0B" },
  moyenne: { label: "Moyenne", couleur: "#3B82F6" },
  basse: { label: "Basse", couleur: "#6B7280" },
};

export const TYPES_SITUATION = {
  incident: { label: "Incident", couleur: "#EF4444" },
  decouverte: { label: "Découverte", couleur: "#34D399" },
  changement: { label: "Changement", couleur: "#3B82F6" },
  anomalie: { label: "Anomalie", couleur: "#F59E0B" },
  connaissance: { label: "Connaissance", couleur: "#9CA3AF" },
  optimisation: { label: "Optimisation", couleur: "#38BDF8" },
};

export const NATURES_EVENEMENT = {
  signal: "#3B82F6",
  preuve: "#34D399",
  alerte: "#EF4444",
  decouverte: "#F59E0B",
  trace: "#6B7280",
};

export const couleurConfiance = (v) => (v >= 70 ? "#10B981" : v >= 40 ? "#F59E0B" : "#EF4444");
