export const STATUTS = {
  actif: ["Actif", "#10B981"],
  "en construction": ["Construction", "#FBBF24"],
  observation: ["Observation", "#3B82F6"],
};

export const STRATE_LABELS = { identite: "Identité", comportement: "Comportement normal", relations: "Relations", trajectoire: "Trajectoire", memoire: "Mémoire interprétée" };

export const FRAICHEUR_ETATS = {
  a_jour: ["À jour", "#10B981"],
  partiel: ["Partiellement à jour", "#FBBF24"],
  sync: ["Synchronisation en cours", "#3B82F6"],
  retard: ["Source en retard", "#F87171"],
  obsolete: ["Connaissance obsolète", "#F87171"],
};

export const AUTONOMIE = {
  aucune: ["Désactivé", "observation seulement", "#94A3B8"],
  restreint: ["Conseiller", "recommandations uniquement", "#22D3EE"],
  supervisé: ["Supervisé", "prépare des actions avec approbation", "#FBBF24"],
  contrôlé: ["Contrôlé", "actions réversibles autorisées", "#A78BFA"],
};

export const STATUTS_SOURCES = {
  prete: ["prête", "#10B981"],
  secret_expire: ["secret expiré", "#F87171"],
  en_retard: ["en retard", "#F87171"],
  a_configurer: ["à configurer", "#FBBF24"],
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
