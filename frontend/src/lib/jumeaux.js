export const STATUTS = {
  actif: ["Actif", "#34D399"],
  "en construction": ["Construction", "#F2B84B"],
  observation: ["Observation", "#60A5FA"],
};

export const STRATE_LABELS = { identite: "Identité", comportement: "Comportement normal", relations: "Relations", trajectoire: "Trajectoire", memoire: "Mémoire interprétée" };

export const FRAICHEUR_ETATS = {
  a_jour: ["À jour", "#34D399"],
  partiel: ["Partiellement à jour", "#F2B84B"],
  sync: ["Synchronisation en cours", "#60A5FA"],
  retard: ["Source en retard", "#F87171"],
  obsolete: ["Connaissance obsolète", "#F87171"],
};

export const AUTONOMIE = {
  aucune: ["Désactivé", "observation seulement", "#7C93A8"],
  restreint: ["Conseiller", "recommandations uniquement", "#60A5FA"],
  supervisé: ["Supervisé", "prépare des actions avec approbation", "#F2B84B"],
  contrôlé: ["Contrôlé", "actions réversibles autorisées", "#60A5FA"],
};

export const STATUTS_SOURCES = {
  prete: ["prête", "#34D399"],
  secret_expire: ["secret expiré", "#F87171"],
  en_retard: ["en retard", "#F87171"],
  a_configurer: ["à configurer", "#F2B84B"],
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
