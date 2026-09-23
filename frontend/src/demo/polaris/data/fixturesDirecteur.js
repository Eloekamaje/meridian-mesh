// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours Directeur Polaris (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-directeur- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène à l'ancienne (scenes: {}) : la mise en évidence de
// Money Manager passe par le mécanisme réel de l'Atlas (commanderCarte / focusCarte de type
// « scene »), déclenché depuis un bouton dans le message — jamais un changement de surface forcé.

// 13 candidats au décommissionnement en 2028 : les 10 premiers (score composite le plus favorable —
// économies, dette technologique, faisabilité du retrait) sont montrés au directeur ; les 3 derniers
// concentrent trop de dépendances critiques entre eux pour être traités dans ce cycle (jamais
// mentionnés dans le tableau des 10, mais présents dans le Mesh comme le reste du parc applicatif).
export const APPLICATIONS = [
  { id: "demo-directeur-app-vision", nom: "Vision", domaine: "Ventes", description: "Ancien outil de reporting commercial" },
  { id: "demo-directeur-app-reportplus", nom: "ReportPlus", domaine: "Finance", description: "Génération de rapports financiers historiques" },
  { id: "demo-directeur-app-docbridge", nom: "DocBridge", domaine: "Opérations", description: "Passerelle d'échange de documents entre systèmes" },
  { id: "demo-directeur-app-suivi-agence", nom: "Suivi Agence", domaine: "Distribution", description: "Suivi d'activité des agences" },
  { id: "demo-directeur-app-planifpro", nom: "PlanifPro", domaine: "Opérations", description: "Planification des interventions et des plannings d'équipe" },
  { id: "demo-directeur-app-money-manager", nom: "Money Manager", domaine: "Finance", description: "Gestion budgétaire historique" },
  { id: "demo-directeur-app-batchlink", nom: "BatchLink", domaine: "TI", description: "Orchestration de traitements par lots" },
  { id: "demo-directeur-app-referentiel-contact", nom: "Référentiel Contact", domaine: "Client", description: "Référentiel historique des contacts clients" },
  { id: "demo-directeur-app-dossier-express", nom: "Dossier Express", domaine: "Client", description: "Traitement accéléré de dossiers clients" },
  { id: "demo-directeur-app-archive-services", nom: "Archive Services", domaine: "Opérations", description: "Service de consultation des archives" },
  { id: "demo-directeur-app-middleware-v2", nom: "Middleware Interne V2", domaine: "TI", description: "Bus d'intégration interne historique" },
  { id: "demo-directeur-app-data-warehouse", nom: "Data Warehouse Legacy", domaine: "TI", description: "Entrepôt de données historique" },
  { id: "demo-directeur-app-ordonnanceur", nom: "Ordonnanceur Central", domaine: "TI", description: "Ordonnancement des traitements batch globaux" },
];

// Les deux flux critiques de Money Manager : des capacités, pas des applications — exactement comme
// la capacité partagée du parcours VP. Ce sont eux que l'Atlas met en évidence au tour 3.
export const ENTITES = [
  { id: "demo-directeur-flux-facturation", label: "Flux de facturation client", domaine: "Finance", detail: "Flux critique fourni par Money Manager, utilisé par Dossier Express" },
  { id: "demo-directeur-flux-rapprochement", label: "Flux de rapprochement comptable", domaine: "Finance", detail: "Flux critique fourni par Money Manager, utilisé par Référentiel Contact" },
];

export const RELATIONS = [
  // Les deux flux critiques dépendent de Money Manager, et deux applications dépendent d'eux —
  // c'est exactement le chemin que l'Atlas met en évidence (« Money Manager, ses deux flux
  // critiques et les applications qui les utilisent »)
  { id: "demo-directeur-rel-facturation-mm", sourceId: "demo-directeur-flux-facturation", targetId: "demo-directeur-app-money-manager", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-dossier-facturation", sourceId: "demo-directeur-app-dossier-express", targetId: "demo-directeur-flux-facturation", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-rapprochement-mm", sourceId: "demo-directeur-flux-rapprochement", targetId: "demo-directeur-app-money-manager", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-contact-rapprochement", sourceId: "demo-directeur-app-referentiel-contact", targetId: "demo-directeur-flux-rapprochement", label: "dépend de", knowledgeStatus: "observe" },
  // Les 3 applications tenues à l'écart de ce cycle : trop interdépendantes entre elles
  { id: "demo-directeur-rel-dwh-middleware", sourceId: "demo-directeur-app-data-warehouse", targetId: "demo-directeur-app-middleware-v2", label: "interconnecté avec", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-ordonnanceur-middleware", sourceId: "demo-directeur-app-ordonnanceur", targetId: "demo-directeur-app-middleware-v2", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-ordonnanceur-dwh", sourceId: "demo-directeur-app-ordonnanceur", targetId: "demo-directeur-app-data-warehouse", label: "dépend de", knowledgeStatus: "a_etudier" },
];

export const PREUVES = {
  "demo-directeur-ev-inventaire": {
    id: "demo-directeur-ev-inventaire",
    title: "Inventaire applicatif Polaris 2028",
    sourceType: "Relevé préparé pour la démonstration",
    periodLabel: "État au 1er janvier 2028",
    excerpt: "Recensement du parc applicatif Polaris avec, pour chaque application, le coût annuel de possession, le nombre d'utilisateurs actifs, les dépendances critiques identifiées et la dette technologique estimée.",
    supports: "13 applications sont candidates au retrait en 2028 selon leur coût, leurs dépendances, leur risque opérationnel et leur dette technologique.",
    limits: "Relevé préparé pour la démonstration ; les coûts et dépendances exacts restent à confirmer avec les équipes propriétaires.",
    fictional: true,
  },
  "demo-directeur-ev-scoring": {
    id: "demo-directeur-ev-scoring",
    title: "Méthodologie de scoring de décommissionnement",
    sourceType: "Relevé de démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Score composite combinant économies possibles, dette technologique et faisabilité du retrait, utilisé pour classer les 13 candidats et prioriser les 10 premiers.",
    supports: "10 des 13 candidats obtiennent un score favorable au retrait pour ce cycle ; 3 concentrent trop de dépendances critiques entre eux.",
    limits: "Méthodologie préparée pour la démonstration ; les pondérations restent à valider avec l'équipe architecture.",
    fictional: true,
  },
  "demo-directeur-ev-flux-money-manager": {
    id: "demo-directeur-ev-flux-money-manager",
    title: "Cartographie des flux critiques de Money Manager",
    sourceType: "Relevé de démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Deux flux critiques fournis par Money Manager restent utilisés : le flux de facturation client (Dossier Express) et le flux de rapprochement comptable (Référentiel Contact).",
    supports: "Le retrait de Money Manager nécessite de migrer ces deux flux avant d'être envisagé.",
    limits: "Cartographie préparée pour la démonstration ; les propriétaires exacts des flux restent à confirmer.",
    fictional: true,
  },
};

export const TRAVAIL_DIRECTEUR = {
  id: "demo-directeur-work",
  titreNaissance: "Candidats au retrait applicatif en 2028",
  titre: "Polaris — Plan de décommissionnement 2028",
  role: "Directeur Polaris",
  objectifNaissance: "Identifier les applications du parc Polaris candidates à un retrait en 2028.",
  objectif: "Prioriser et planifier le décommissionnement des applications Polaris pour 2028, selon les économies possibles, les dépendances critiques et la faisabilité du retrait.",
  resumeDiagnostic: "13 applications sont candidates à un retrait en 2028. 10 d'entre elles sont priorisées selon les économies possibles, la dette technologique et la faisabilité du retrait ; les 3 autres concentrent trop de dépendances critiques entre elles pour ce cycle.",
  synthese: "La première vague retient Vision, ReportPlus et DocBridge, avec un objectif de retrait au T2 2028 (710 k$ de coûts annuels). Money Manager présente un potentiel d'économie plus élevé, mais deux flux critiques en dépendent encore (utilisés par Dossier Express et Référentiel Contact) : sa migration est préparée en parallèle.",
  aValider: [
    "Confirmer avec les utilisateurs de Vision que la plateforme cible couvre bien leurs deux fonctions de reporting",
    "Valider la migration des deux flux critiques de Money Manager avant d'envisager son retrait",
    "Confirmer les responsables et les dates de chaque retrait avec les équipes propriétaires",
  ],
  prochainesActions: [
    "Lancer le retrait de Vision, ReportPlus et DocBridge au T2 2028",
    "Engager la migration des deux flux critiques de Money Manager",
    "Confirmer la trajectoire prévisionnelle des 7 autres applications (T3-T4 2028)",
  ],
  hypotheses: [
    "Le score composite (économies possibles, dette technologique, faisabilité du retrait) reflète fidèlement l'ordre de priorité proposé. À confirmer avec l'équipe architecture.",
  ],
  options: [
    {
      id: "demo-directeur-opt-phase",
      titre: "Décommissionnement en 3 vagues (T2 à T4 2028)",
      description: "Retirer d'abord les 3 applications sans dépendance (T2), puis celles nécessitant une migration de flux ou de traitements (T3), enfin celles à synchronisation ou parcours critiques (T4).",
      impacts: ["Risque opérationnel limité à chaque vague", "Charge de migration étalée dans le temps"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-directeur-opt-groupe",
      titre: "Décommissionnement groupé fin 2028",
      description: "Retirer les 10 applications en une seule fenêtre de fin d'année.",
      impacts: ["Fenêtre de bascule unique", "Charge de migration concentrée, risque de contention des équipes"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-directeur-ev-inventaire", "demo-directeur-ev-scoring", "demo-directeur-ev-flux-money-manager"],
};

export const POSITIONS_MESH = {
  "demo-directeur-app-vision": { x: -60, y: 120 },
  "demo-directeur-app-reportplus": { x: -260, y: 40 },
  "demo-directeur-app-docbridge": { x: -320, y: 220 },
  "demo-directeur-app-suivi-agence": { x: -140, y: 320 },
  "demo-directeur-app-planifpro": { x: 80, y: 340 },
  "demo-directeur-app-money-manager": { x: 220, y: -40 },
  "demo-directeur-app-batchlink": { x: 460, y: 260 },
  "demo-directeur-app-referentiel-contact": { x: 420, y: -120 },
  "demo-directeur-app-dossier-express": { x: 40, y: -180 },
  "demo-directeur-app-archive-services": { x: -420, y: -60 },
  "demo-directeur-flux-facturation": { x: 140, y: -220 },
  "demo-directeur-flux-rapprochement": { x: 340, y: -220 },
  "demo-directeur-app-middleware-v2": { x: 340, y: 480 },
  "demo-directeur-app-data-warehouse": { x: 560, y: 400 },
  "demo-directeur-app-ordonnanceur": { x: 560, y: 560 },
};

export const FIXTURES_DIRECTEUR = {
  applications: APPLICATIONS,
  entites: ENTITES,
  relations: RELATIONS,
  preuves: PREUVES,
  scenes: {},
  resultats: { "demo-directeur-work": TRAVAIL_DIRECTEUR },
  positions: POSITIONS_MESH,
};
