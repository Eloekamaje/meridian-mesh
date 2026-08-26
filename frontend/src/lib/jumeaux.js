export const STATUTS = {
  actif: ["Actif", "#047857"],
  "en construction": ["Construction", "#B45309"],
  observation: ["Observation", "#3730A3"],
};

export const STRATE_LABELS = { identite: "Identité", comportement: "Comportement normal", relations: "Relations", trajectoire: "Trajectoire", memoire: "Mémoire interprétée" };

export const FRAICHEUR_ETATS = {
  a_jour: ["À jour", "#047857"],
  partiel: ["Partiellement à jour", "#B45309"],
  sync: ["Synchronisation en cours", "#3730A3"],
  retard: ["Source en retard", "#B91C1C"],
  obsolete: ["Connaissance obsolète", "#B91C1C"],
};

export const AUTONOMIE = {
  aucune: ["Désactivé", "observation seulement", "#64748B"],
  restreint: ["Conseiller", "recommandations uniquement", "#0E7490"],
  supervisé: ["Supervisé", "prépare des actions avec approbation", "#B45309"],
  contrôlé: ["Contrôlé", "actions réversibles autorisées", "#6D28D9"],
};

export const STATUTS_SOURCES = {
  prete: ["prête", "#047857"],
  secret_expire: ["secret expiré", "#B91C1C"],
  en_retard: ["en retard", "#B91C1C"],
  a_configurer: ["à configurer", "#B45309"],
};

export const ACTION_LIGNE = {
  actif: "Ouvrir",
  "en construction": "Reprendre la construction",
  observation: "Revoir l'admission",
};

export const qualifConnaissance = (c) => (c >= 80 ? "Bonne" : c >= 60 ? "Correcte" : c >= 40 ? "Faible" : "Insuffisante");

export function resumeStrates(j) {
  const s = j.strates || {};
  const completes = Object.entries(s).filter(([, v]) => v >= 95).map(([k]) => `${STRATE_LABELS[k]} complète`);
  const plusFaible = Object.entries(s).sort((a, b) => a[1] - b[1])[0];
  const parts = [...completes.slice(0, 1)];
  if (plusFaible && plusFaible[1] < 70) parts.push(`${STRATE_LABELS[plusFaible[0]]} à compléter`);
  return parts.join(" · ") || "Strates équilibrées";
}

export function estEnAttention(j) {
  return (
    j.statut !== "actif" ||
    (j.couverture ?? 100) < 60 ||
    (j.sources_detail || []).some((s) => s.statut !== "prete") ||
    ["retard", "obsolete"].includes(j.fraicheur_etat)
  );
}
