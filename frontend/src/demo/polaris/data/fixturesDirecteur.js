// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours Directeur Polaris (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-directeur- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène : le scénario ne joue aucun beat apply_scene —
// construireMesh() dans mockApi.js a des replis sûrs pour ces champs absents.

// 13 candidats au décommissionnement en 2028 : les 10 premiers (score composite le plus favorable —
// coût, dépendances, risque, dette technique) sont montrés au directeur ; les 3 derniers concentrent
// trop de dépendances critiques pour être traités dans ce cycle (jamais mentionnés dans le tableau
// des 10, mais présents dans le Mesh comme le reste du parc applicatif réel).
export const APPLICATIONS = [
  { id: "demo-directeur-app-vision", nom: "Application Vision", domaine: "Ventes", description: "Ancien outil de reporting commercial" },
  { id: "demo-directeur-app-money-manager", nom: "Application Money Manager", domaine: "Finance", description: "Gestion budgétaire historique" },
  { id: "demo-directeur-app-archive-client", nom: "Application Archive Client", domaine: "Client", description: "Archivage des dossiers clients clos" },
  { id: "demo-directeur-app-payroll-light", nom: "Application Legacy Payroll Light", domaine: "RH", description: "Ancien module de paie allégé" },
  { id: "demo-directeur-app-crm-lite", nom: "Application Old CRM Lite", domaine: "Ventes", description: "Ancien CRM simplifié" },
  { id: "demo-directeur-app-rapports-v1", nom: "Application Rapports Régionaux V1", domaine: "Finance", description: "Première version des rapports régionaux" },
  { id: "demo-directeur-app-fournisseurs-legacy", nom: "Application Suivi Fournisseurs Legacy", domaine: "Achats", description: "Ancien suivi des fournisseurs" },
  { id: "demo-directeur-app-rh-historique", nom: "Application Portail RH Historique", domaine: "RH", description: "Ancien portail des ressources humaines" },
  { id: "demo-directeur-app-facturation-v1", nom: "Application Facturation Régionale V1", domaine: "Finance", description: "Première version de la facturation régionale" },
  { id: "demo-directeur-app-registre-contrats", nom: "Application Registre Contrats Papier", domaine: "Opérations", description: "Numérisation historique des contrats papier" },
  { id: "demo-directeur-app-batch-scheduler", nom: "Application Batch Scheduler V1", domaine: "TI", description: "Ordonnanceur de traitements par lots" },
  { id: "demo-directeur-app-middleware-v2", nom: "Application Middleware Interne V2", domaine: "TI", description: "Bus d'intégration interne historique" },
  { id: "demo-directeur-app-data-warehouse", nom: "Application Data Warehouse Legacy", domaine: "TI", description: "Entrepôt de données historique" },
];

export const ENTITES = [];

export const RELATIONS = [
  { id: "demo-directeur-rel-money-manager-dwh", sourceId: "demo-directeur-app-money-manager", targetId: "demo-directeur-app-data-warehouse", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-rapports-dwh", sourceId: "demo-directeur-app-rapports-v1", targetId: "demo-directeur-app-data-warehouse", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-facturation-middleware", sourceId: "demo-directeur-app-facturation-v1", targetId: "demo-directeur-app-middleware-v2", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-rh-middleware", sourceId: "demo-directeur-app-rh-historique", targetId: "demo-directeur-app-middleware-v2", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-directeur-rel-batch-middleware", sourceId: "demo-directeur-app-batch-scheduler", targetId: "demo-directeur-app-middleware-v2", label: "dépend de", knowledgeStatus: "observe" },
  { id: "demo-directeur-rel-dwh-middleware", sourceId: "demo-directeur-app-data-warehouse", targetId: "demo-directeur-app-middleware-v2", label: "interconnecté avec", knowledgeStatus: "observe" },
];

export const PREUVES = {
  "demo-directeur-ev-inventaire": {
    id: "demo-directeur-ev-inventaire",
    title: "Inventaire applicatif Polaris 2028",
    sourceType: "Relevé préparé pour la démonstration",
    periodLabel: "État au 1er janvier 2028",
    excerpt: "Recensement du parc applicatif Polaris avec, pour chaque application, le coût annuel de possession, le nombre de dépendances critiques, le nombre d'utilisateurs actifs et la dette technologique estimée.",
    supports: "13 applications sont candidates au retrait en 2028 selon le coût de possession, les dépendances, le risque opérationnel et la dette technologique.",
    limits: "Relevé préparé pour la démonstration ; les coûts et dépendances exacts restent à confirmer avec les équipes propriétaires.",
    fictional: true,
  },
  "demo-directeur-ev-scoring": {
    id: "demo-directeur-ev-scoring",
    title: "Méthodologie de scoring de décommissionnement",
    sourceType: "Relevé de démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Score composite combinant coût de possession, nombre de dépendances critiques, risque opérationnel et dette technologique, utilisé pour classer les 13 candidats au retrait.",
    supports: "10 des 13 candidats obtiennent un score favorable au retrait ou à la migration ; 3 concentrent trop de dépendances critiques pour ce cycle.",
    limits: "Méthodologie préparée pour la démonstration ; les pondérations restent à valider avec l'équipe architecture.",
    fictional: true,
  },
};

export const TRAVAIL_DIRECTEUR = {
  id: "demo-directeur-work",
  titreNaissance: "Candidats au retrait applicatif en 2028",
  titre: "Plan de décommissionnement 2028 : 10 applications prioritaires",
  role: "Directeur Polaris",
  objectifNaissance: "Identifier les applications du parc Polaris candidates au retrait en 2028.",
  objectif: "Prioriser les applications à décommissionner en 2028 selon leur coût, leurs dépendances, leur risque opérationnel et leur dette technologique.",
  resumeDiagnostic: "13 applications sont candidates au retrait en 2028, évaluées sur le coût de possession, les dépendances, le risque opérationnel et la dette technologique.",
  synthese: "10 des 13 candidats peuvent être décommissionnés ou migrés sans dépendance critique bloquante ; les 3 restants (Middleware Interne V2, Data Warehouse Legacy, Batch Scheduler V1) concentrent trop de dépendances critiques pour ce cycle.",
  aValider: [
    "Confirmer le calendrier de décommissionnement T1 à T3 2028 avec les équipes propriétaires",
    "Valider les migrations préalables requises pour 3 des 10 applications",
    "Réévaluer séparément les 3 applications à forte dépendance critique",
  ],
  prochainesActions: [
    "Lancer le décommissionnement T1 2028 pour les applications sans dépendance critique",
    "Engager les migrations préalables requises avant fermeture",
    "Réévaluer les 3 applications à forte dépendance au cycle suivant",
  ],
  hypotheses: [
    "Le score composite (coût, dépendances, risque, dette technologique) reflète fidèlement la priorité de retrait. À confirmer avec l'équipe architecture.",
  ],
  options: [
    {
      id: "demo-directeur-opt-phase",
      titre: "Décommissionnement en 3 phases (T1 à T3 2028)",
      description: "Retirer les applications sans dépendance dès T1, puis celles nécessitant une migration préalable sur T2-T3.",
      impacts: ["Risque opérationnel limité à chaque phase", "Charge de migration étalée dans le temps"],
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
  preuves: ["demo-directeur-ev-inventaire", "demo-directeur-ev-scoring"],
};

export const POSITIONS_MESH = {
  "demo-directeur-app-vision": { x: -60, y: 120 },
  "demo-directeur-app-money-manager": { x: 180, y: -40 },
  "demo-directeur-app-archive-client": { x: -220, y: 280 },
  "demo-directeur-app-payroll-light": { x: 420, y: -140 },
  "demo-directeur-app-crm-lite": { x: 60, y: 340 },
  "demo-directeur-app-rapports-v1": { x: 360, y: 60 },
  "demo-directeur-app-fournisseurs-legacy": { x: -380, y: 60 },
  "demo-directeur-app-rh-historique": { x: 600, y: -220 },
  "demo-directeur-app-facturation-v1": { x: 260, y: 220 },
  "demo-directeur-app-registre-contrats": { x: -140, y: 480 },
  "demo-directeur-app-batch-scheduler": { x: 520, y: 380 },
  "demo-directeur-app-middleware-v2": { x: 340, y: 500 },
  "demo-directeur-app-data-warehouse": { x: 100, y: -220 },
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
