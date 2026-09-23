// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours Analyste d'affaires (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-analyste- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène à l'ancienne (scenes: {}) : la mise en évidence de
// ChequeFlow passe par le mécanisme réel de l'Atlas (commanderCarte / focusCarte de type « scene »),
// déclenchée depuis un bouton dans le message — jamais un changement de surface forcé.

export const APPLICATIONS = [
  { id: "demo-analyste-app-chequeflow", nom: "ChequeFlow", domaine: "Paiement", description: "Application historique de traitement des chèques, créée en 2012" },
];

// Les trois secteurs utilisateurs et les deux rapports réglementaires : des capacités, pas des
// applications — ce que l'Atlas relie à ChequeFlow au tour 3.
export const ENTITES = [
  { id: "demo-analyste-secteur-operations-paiements", kind: "secteur", label: "Opérations de paiements", domaine: "Paiement", detail: "Traite les écarts et les exceptions" },
  { id: "demo-analyste-secteur-soutien-succursales", kind: "secteur", label: "Soutien aux succursales", domaine: "Distribution", detail: "Recherche les opérations et suit leur résolution" },
  { id: "demo-analyste-secteur-controle-conformite", kind: "secteur", label: "Contrôle et conformité", domaine: "Risque", detail: "Vérifie les traitements et retrouve les justificatifs" },
  { id: "demo-analyste-rapport-conformite", kind: "rapport", label: "Rapport de conformité des chèques", domaine: "Risque", detail: "Extraction automatisée alimentée par ChequeFlow" },
  { id: "demo-analyste-rapport-ecarts", kind: "rapport", label: "Rapport de suivi des écarts réglementaires", domaine: "Risque", detail: "Extraction automatisée alimentée par ChequeFlow" },
];

export const RELATIONS = [
  { id: "demo-analyste-rel-chequeflow-operations", sourceId: "demo-analyste-app-chequeflow", targetId: "demo-analyste-secteur-operations-paiements", label: "utilisé par", knowledgeStatus: "observe" },
  { id: "demo-analyste-rel-chequeflow-succursales", sourceId: "demo-analyste-app-chequeflow", targetId: "demo-analyste-secteur-soutien-succursales", label: "utilisé par", knowledgeStatus: "observe" },
  { id: "demo-analyste-rel-chequeflow-conformite", sourceId: "demo-analyste-app-chequeflow", targetId: "demo-analyste-secteur-controle-conformite", label: "utilisé par", knowledgeStatus: "observe" },
  { id: "demo-analyste-rel-chequeflow-rapport-conformite", sourceId: "demo-analyste-app-chequeflow", targetId: "demo-analyste-rapport-conformite", label: "alimente", knowledgeStatus: "observe" },
  { id: "demo-analyste-rel-chequeflow-rapport-ecarts", sourceId: "demo-analyste-app-chequeflow", targetId: "demo-analyste-rapport-ecarts", label: "alimente", knowledgeStatus: "observe" },
];

export const PREUVES = {
  "demo-analyste-ev-historique": {
    id: "demo-analyste-ev-historique",
    title: "Historique et décisions d'architecture de ChequeFlow",
    sourceType: "Relevé préparé pour la démonstration",
    periodLabel: "2012 à aujourd'hui",
    excerpt: "Documents de conception et décisions d'architecture retraçant la création de ChequeFlow en 2012, pour automatiser le traitement des chèques et réduire les rapprochements manuels.",
    supports: "ChequeFlow a été créée pour automatiser le traitement des chèques et réduire les rapprochements manuels.",
    limits: "Relevé préparé pour la démonstration ; certains documents d'origine restent à localiser.",
    fictional: true,
  },
  "demo-analyste-ev-demandes-incidents": {
    id: "demo-analyste-ev-demandes-incidents",
    title: "Demandes d'évolution, incidents et code de ChequeFlow",
    sourceType: "Relevé de démonstration",
    periodLabel: "5 dernières années",
    excerpt: "Analyse des demandes d'évolution, des incidents déclarés et du code source, distinguant les trois fonctions assurées par ChequeFlow.",
    supports: "ChequeFlow assure trois fonctions : rapprochement des opérations, préparation des lots de traitement, production d'états de suivi locaux.",
    limits: "Relevé préparé pour la démonstration ; l'historique des incidents antérieurs à 5 ans n'est pas couvert.",
    fictional: true,
  },
  "demo-analyste-ev-usages": {
    id: "demo-analyste-ev-usages",
    title: "Usages actuels de ChequeFlow",
    sourceType: "Relevé de démonstration",
    periodLabel: "90 derniers jours",
    excerpt: "Analyse des usages récents des trois fonctions de ChequeFlow.",
    supports: "Les usages observés se concentrent sur le rapprochement des opérations ; les deux autres fonctions sont très peu utilisées.",
    limits: "Relevé préparé pour la démonstration ; les usages ponctuels (clôtures, traitements exceptionnels) restent à vérifier séparément.",
    fictional: true,
  },
  "demo-analyste-ev-acces": {
    id: "demo-analyste-ev-acces",
    title: "Rapprochement des accès, des activités et des traitements automatisés",
    sourceType: "Relevé de démonstration",
    periodLabel: "90 derniers jours",
    excerpt: "Rapprochement des accès utilisateurs, des activités et des extractions automatisées liées au rapprochement des opérations dans ChequeFlow.",
    supports: "14 utilisateurs actifs dans 3 secteurs, et 2 rapports réglementaires alimentés par extraction automatisée.",
    limits: "Relevé préparé pour la démonstration ; les comptes de service restent à confirmer séparément des utilisateurs humains.",
    fictional: true,
  },
};

export const TRAVAIL_ANALYSTE = {
  id: "demo-analyste-work",
  titreNaissance: "Comprendre ChequeFlow avant son remplacement",
  titre: "Polaris — Cadrage du remplacement de ChequeFlow",
  role: "Analyste d'affaires Polaris",
  objectifNaissance: "Comprendre pourquoi ChequeFlow a été créée et à quoi elle sert encore aujourd'hui.",
  objectif: "Définir le périmètre du remplacement de ChequeFlow en distinguant les besoins encore actifs des fonctions candidates au retrait.",
  resumeDiagnostic: "ChequeFlow (2012) assure trois fonctions. Les usages observés se concentrent sur le rapprochement des opérations ; les deux autres fonctions sont très peu utilisées sur la période consultée.",
  synthese: "14 utilisateurs actifs dans 3 secteurs dépendent du rapprochement des opérations, qui alimente aussi 2 rapports réglementaires. Le remplacement doit se concentrer sur cette fonction ; les deux autres sont candidates au retrait, sous réserve de validation des usages ponctuels.",
  aValider: [
    "Confirmer que la plateforme de paiements couvre les derniers cas particuliers de préparation des lots (fonction 2)",
    "Vérifier qu'aucun état de suivi local n'est encore nécessaire à une équipe (fonction 3)",
    "Faire valider le périmètre ciblé par chacun des trois secteurs utilisateurs",
  ],
  prochainesActions: [
    "Centrer le remplacement sur le rapprochement des opérations et la gestion des exceptions",
    "Vérifier les usages ponctuels des fonctions 2 et 3 avant leur retrait",
    "Organiser les ateliers de validation avec les trois secteurs concernés",
  ],
  hypotheses: [
    "Les usages observés sur les 90 derniers jours reflètent fidèlement les besoins réels, y compris les cas de clôture. À confirmer avec les secteurs.",
  ],
  options: [
    {
      id: "demo-analyste-opt-cible",
      titre: "Remplacement ciblé sur le rapprochement des opérations",
      description: "Reprendre uniquement la fonction encore largement utilisée, avec retrait validé des deux autres après vérification des cas particuliers.",
      impacts: ["Périmètre de remplacement réduit et plus rapide à livrer", "Risque limité aux usages ponctuels restant à vérifier"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-analyste-opt-complet",
      titre: "Remplacement complet des trois fonctions",
      description: "Reprendre l'intégralité de ChequeFlow, y compris les fonctions très peu utilisées.",
      impacts: ["Aucun risque de perte de fonction", "Effort de remplacement plus important pour un usage marginal"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-analyste-ev-historique", "demo-analyste-ev-demandes-incidents", "demo-analyste-ev-usages", "demo-analyste-ev-acces"],
};

export const POSITIONS_MESH = {
  "demo-analyste-app-chequeflow": { x: 0, y: 0 },
  "demo-analyste-secteur-operations-paiements": { x: -220, y: -100 },
  "demo-analyste-secteur-soutien-succursales": { x: 220, y: -100 },
  "demo-analyste-secteur-controle-conformite": { x: 0, y: -240 },
  "demo-analyste-rapport-conformite": { x: -180, y: 180 },
  "demo-analyste-rapport-ecarts": { x: 180, y: 180 },
};

export const FIXTURES_ANALYSTE = {
  applications: APPLICATIONS,
  entites: ENTITES,
  relations: RELATIONS,
  preuves: PREUVES,
  scenes: {},
  resultats: { "demo-analyste-work": TRAVAIL_ANALYSTE },
  positions: POSITIONS_MESH,
};
