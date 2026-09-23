// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours Analyste support TI (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-supportti- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène à l'ancienne (scenes: {}) : les deux mises en évidence
// de ce parcours passent par le mécanisme réel de l'Atlas (commanderCarte / focusCarte de type
// « scene »), déclenchées depuis un bouton dans le message — jamais un changement de surface forcé.

export const APPLICATIONS = [
  { id: "demo-supportti-app-portail-ouverture", nom: "Portail Ouverture de compte", domaine: "Client", description: "Point d'entrée des demandes d'ouverture de compte" },
  { id: "demo-supportti-app-service-identite", nom: "Service Identité", domaine: "Risque", description: "Validation d'identité appelée par la chaîne d'ouverture" },
  { id: "demo-supportti-app-gestion-client", nom: "Gestion client", domaine: "Client", description: "Reçoit les informations issues d'une ouverture de compte" },
  { id: "demo-supportti-app-prevention-fraude", nom: "Prévention de la fraude", domaine: "Risque", description: "Reçoit les informations issues d'une ouverture de compte pour contrôle" },
];

// La chaîne événementielle elle-même : une capacité, pas une application — c'est elle, et non une
// application isolée, où la dégradation est observée.
export const ENTITES = [
  { id: "demo-supportti-chaine-ouverture", kind: "chaine", label: "Chaîne événementielle d'ouverture de compte", domaine: "Client", detail: "Chaîne suivie dans Polaris ; dégradation progressive observée depuis 3 jours" },
];

export const RELATIONS = [
  { id: "demo-supportti-rel-chaine-portail", sourceId: "demo-supportti-app-portail-ouverture", targetId: "demo-supportti-chaine-ouverture", label: "alimente", knowledgeStatus: "observe" },
  { id: "demo-supportti-rel-chaine-identite", sourceId: "demo-supportti-chaine-ouverture", targetId: "demo-supportti-app-service-identite", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-supportti-rel-chaine-gestion-client", sourceId: "demo-supportti-chaine-ouverture", targetId: "demo-supportti-app-gestion-client", label: "transmet à", knowledgeStatus: "observe" },
  { id: "demo-supportti-rel-chaine-prevention-fraude", sourceId: "demo-supportti-chaine-ouverture", targetId: "demo-supportti-app-prevention-fraude", label: "transmet à", knowledgeStatus: "observe" },
];

export const PREUVES = {
  "demo-supportti-ev-metriques": {
    id: "demo-supportti-ev-metriques",
    title: "Métriques de traitement de la chaîne d'ouverture de compte",
    sourceType: "Relevé de démonstration",
    periodLabel: "3 derniers jours",
    excerpt: "Délai de traitement des événements, taille de la file de messages et débit des traitements nocturnes sur la chaîne d'ouverture de compte.",
    supports: "Les trois indicateurs évoluent simultanément depuis 3 jours : délai en hausse, file en croissance, débit nocturne en baisse.",
    limits: "Relevé préparé pour la démonstration ; la cause de l'évolution reste à confirmer.",
    fictional: true,
  },
  "demo-supportti-ev-alertes": {
    id: "demo-supportti-ev-alertes",
    title: "Seuils d'alerte configurés sur la chaîne d'ouverture de compte",
    sourceType: "Relevé de démonstration",
    periodLabel: "Configuration actuelle",
    excerpt: "Seuils d'alerte configurés individuellement sur le délai de traitement, la file d'attente et le débit nocturne.",
    supports: "Aucune des alertes configurées sur ces indicateurs ne s'est déclenchée : chaque indicateur reste sous son propre seuil.",
    limits: "Relevé préparé pour la démonstration ; les seuils eux-mêmes restent à revoir séparément.",
    fictional: true,
  },
  "demo-supportti-ev-deploiement": {
    id: "demo-supportti-ev-deploiement",
    title: "Journal des déploiements Polaris",
    sourceType: "Relevé de démonstration",
    periodLabel: "7 derniers jours",
    excerpt: "Une évolution Polaris a été déployée juste avant le début de la dégradation observée, modifiant les flux événementiels de la chaîne d'ouverture.",
    supports: "Le rapprochement temporel entre le déploiement et le début de la dégradation est cohérent.",
    limits: "Le rapprochement temporel ne prouve pas la cause ; une confirmation par comparaison des traces reste nécessaire.",
    fictional: true,
  },
  "demo-supportti-ev-services-appeles": {
    id: "demo-supportti-ev-services-appeles",
    title: "Services appelés par la chaîne d'ouverture de compte",
    sourceType: "Relevé de démonstration",
    periodLabel: "3 derniers jours",
    excerpt: "Services et traitements appelés par la chaîne d'ouverture de compte, avec leurs temps de réponse et leurs tentatives de reprise.",
    supports: "Un éventuel ralentissement d'un service appelé et une hausse des tentatives de reprise restent à vérifier.",
    limits: "Relevé préparé pour la démonstration ; l'analyse détaillée des services reste à mener.",
    fictional: true,
  },
};

export const TRAVAIL_SUPPORTTI = {
  id: "demo-supportti-work",
  titreNaissance: "Dégradation progressive sur la chaîne d'ouverture de compte",
  titre: "Polaris — Investigation préventive de la chaîne d'ouverture de compte",
  role: "Analyste support TI Polaris",
  objectifNaissance: "Comprendre une dégradation progressive détectée sur la chaîne d'ouverture de compte avant qu'elle n'ait d'impact utilisateur confirmé.",
  objectif: "Documenter les signaux observés, évaluer l'hypothèse d'origine et préparer les vérifications nécessaires avant une éventuelle escalade.",
  resumeDiagnostic: "Depuis 3 jours, le délai de traitement augmente, la file de messages grossit et le débit nocturne de rattrapage diminue sur la chaîne d'ouverture de compte. Aucune alerte configurée ne s'est déclenchée ; aucun impact utilisateur n'est confirmé.",
  synthese: "L'hypothèse principale relie la dégradation à une évolution Polaris déployée juste avant son apparition. Le constat de dégradation est établi avec une confiance élevée ; le lien avec le déploiement reste à confirmer.",
  aValider: [
    "Comparer les traces de traitement avant et après le déploiement Polaris",
    "Vérifier un éventuel ralentissement d'un service appelé par la chaîne et une hausse des tentatives de reprise",
    "Confirmer qu'aucun impact utilisateur n'est survenu avant toute escalade",
  ],
  prochainesActions: [
    "Comparer les traitements avant et après le déploiement",
    "Examiner les messages en attente et les reprises",
    "Vérifier les services appelés et la capacité de traitement",
  ],
  hypotheses: [
    "L'évolution Polaris déployée juste avant la dégradation en est la cause. Confiance modérée — à confirmer par comparaison des traces avant/après déploiement.",
  ],
  options: [
    {
      id: "demo-supportti-opt-verifications",
      titre: "Mener les trois vérifications avant toute action",
      description: "Comparer les traces, examiner les messages en attente et vérifier les services appelés avant d'envisager une augmentation de capacité.",
      impacts: ["Aucune action technique tant que la cause n'est pas confirmée", "Délai de résolution dépendant du temps de vérification"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-supportti-opt-capacite",
      titre: "Augmenter temporairement la capacité de traitement",
      description: "Absorber le retard en augmentant la capacité, sans attendre la confirmation de la cause.",
      impacts: ["Résorption plus rapide du retard si le blocage n'est pas en aval", "Risque d'agir sans traiter la cause réelle"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-supportti-ev-metriques", "demo-supportti-ev-alertes", "demo-supportti-ev-deploiement", "demo-supportti-ev-services-appeles"],
};

export const POSITIONS_MESH = {
  "demo-supportti-chaine-ouverture": { x: 0, y: 0 },
  "demo-supportti-app-portail-ouverture": { x: -220, y: -80 },
  "demo-supportti-app-service-identite": { x: 220, y: -80 },
  "demo-supportti-app-gestion-client": { x: -160, y: 220 },
  "demo-supportti-app-prevention-fraude": { x: 160, y: 220 },
};

export const FIXTURES_SUPPORTTI = {
  applications: APPLICATIONS,
  entites: ENTITES,
  relations: RELATIONS,
  preuves: PREUVES,
  scenes: {},
  resultats: { "demo-supportti-work": TRAVAIL_SUPPORTTI },
  positions: POSITIONS_MESH,
};
