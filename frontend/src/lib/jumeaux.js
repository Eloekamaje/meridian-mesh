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

// Vérification d'une connaissance (Harness v3 §2), comme un journaliste montre ses sources : jamais « vrai ».
export const ETATS_VERIFICATION = {
  verifie: ["vérifié", "#34D399", "la ligne citée dit bien cela (contrôle automatique)"],
  recoupe: ["recoupé", "#22D3EE", "deux sources indépendantes concordent"],
  selon: ["selon une source", "#93C5FD", "une seule source l'appuie"],
  conteste: ["contesté", "#F2B84B", "deux sources se contredisent"],
  en_partie: ["en partie", "#FB923C", "un détail n'est pas appuyé"],
  incertain: ["incertain", "#9CA3AF", "le juge se contredit sur les mêmes preuves : ni l'un ni l'autre ne fait foi"],
  non_appuye: ["non appuyé", "#F87171", "sa preuve ne dit pas cela"],
};
const SYSTEMES = { git: "le code", documentation: "la documentation", confluence: "Confluence", jira: "Jira",
  servicenow: "ServiceNow", datadog: "Datadog" };

// Libellé d'un état : « selon le code », « selon Confluence »… ; null si pas encore vérifiée.
export function libelleVerification(v) {
  const e = v && ETATS_VERIFICATION[v.etat];
  if (!e) return null;
  return v.etat === "selon" && v.systemes?.length === 1 ? `selon ${SYSTEMES[v.systemes[0]] || v.systemes[0]}` : e[0];
}
