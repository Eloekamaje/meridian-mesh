// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours VP Transformation (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-vp- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène : le scénario ne joue aucun beat apply_scene
// (comme l'ancien scénario Gestionnaire) — construireMesh() dans mockApi.js a des replis sûrs pour
// ces champs absents, tout s'affiche simplement dès le départ.

export const APPLICATIONS = [
  { id: "demo-vp-app-facturation-centrale", nom: "Plateforme Facturation Centrale", domaine: "Finance", description: "Socle de facturation mutualisé" },
  { id: "demo-vp-app-documentaire", nom: "Système Documentaire Central", domaine: "Opérations", description: "Gestion documentaire mutualisée" },
  { id: "demo-vp-app-rh", nom: "Portail RH", domaine: "RH", description: "Portail des ressources humaines" },
];

export const ENTITES = [
  { id: "demo-vp-ini-portail-fournisseurs", kind: "initiative", label: "Portail fournisseurs 2.0", detail: "Refonte du portail d'échange avec les fournisseurs", domaine: "Achats", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-rapports-regionaux", kind: "initiative", label: "Automatisation des rapports régionaux", detail: "Génération automatique des rapports de performance régionaux", domaine: "Finance", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-intranet-rh", kind: "initiative", label: "Refonte de l'intranet RH", detail: "Nouvelle interface pour l'intranet des ressources humaines", domaine: "RH", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-suivi-budgets", kind: "initiative", label: "Suivi interne des budgets de projet", detail: "Outil de suivi budgétaire pour les chefs de projet", domaine: "Finance", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-gestion-acces", kind: "initiative", label: "Outil de gestion des accès internes", detail: "Portail de demande d'accès aux systèmes internes", domaine: "TI", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-tableau-manager", kind: "initiative", label: "Modernisation du tableau de bord managérial", detail: "Nouveau tableau de bord pour les gestionnaires d'équipe", domaine: "Opérations", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-gestion-documentaire", kind: "initiative", label: "Plateforme de gestion documentaire interne", detail: "Nouvel outil de classement documentaire pour les équipes internes", domaine: "Opérations", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-controle-qualite", kind: "initiative", label: "Optimisation du contrôle qualité interne", detail: "Révision des processus de contrôle qualité internes", domaine: "Opérations", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-fournisseurs-strategiques", kind: "initiative", label: "Système de gestion des fournisseurs stratégiques", detail: "Suivi des relations avec les fournisseurs stratégiques", domaine: "Achats", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-approbation-budgetaire", kind: "initiative", label: "Refonte du processus d'approbation budgétaire", detail: "Simplification du circuit d'approbation des budgets internes", domaine: "Finance", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-facturation-legacy", kind: "initiative", label: "Ancien système de facturation régionale", detail: "Système à remplacer par la Plateforme Facturation Centrale avant fermeture", domaine: "Finance", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-registre-contrats", kind: "initiative", label: "Registre des contrats papier numérisé", detail: "À remplacer par le Système Documentaire Central avant fermeture", domaine: "Opérations", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
];

export const RELATIONS = [
  { id: "demo-vp-rel-portail-fournisseurs-strategiques", sourceId: "demo-vp-ini-portail-fournisseurs", targetId: "demo-vp-ini-fournisseurs-strategiques", label: "chevauchement fonctionnel", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-portefeuille"] },
  { id: "demo-vp-rel-facturation-legacy-centrale", sourceId: "demo-vp-ini-facturation-legacy", targetId: "demo-vp-app-facturation-centrale", label: "à remplacer par", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-impact-client"] },
  { id: "demo-vp-rel-registre-documentaire", sourceId: "demo-vp-ini-registre-contrats", targetId: "demo-vp-app-documentaire", label: "à remplacer par", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-impact-client"] },
  { id: "demo-vp-rel-intranet-rh-portail", sourceId: "demo-vp-ini-intranet-rh", targetId: "demo-vp-app-rh", label: "s'appuie sur", knowledgeStatus: "a_etudier" },
];

export const PREUVES = {
  "demo-vp-ev-portefeuille": {
    id: "demo-vp-ev-portefeuille",
    title: "Analyse du portefeuille des 400 initiatives Polaris",
    sourceType: "Relevé préparé pour la démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Croisement de l'alignement stratégique déclaré, du coût cumulé et des chevauchements fonctionnels entre les 400 initiatives du portefeuille Polaris.",
    supports: "12 initiatives combinent faible alignement stratégique, coûts élevés et chevauchement fonctionnel — 18 M$ d'économies potentielles.",
    limits: "Relevé préparé pour la démonstration ; le périmètre exact reste à confirmer avec les porteurs de chaque initiative.",
    fictional: true,
  },
  "demo-vp-ev-impact-client": {
    id: "demo-vp-ev-impact-client",
    title: "Cartographie d'impact client des initiatives Polaris",
    sourceType: "Relevé de démonstration",
    periodLabel: "État au 15 mars 2028",
    excerpt: "Pour chacune des 12 initiatives à faible valeur, mesure de l'impact sur le client final, du processus interne concerné et des dépendances à traiter avant fermeture.",
    supports: "7 initiatives n'ont aucun impact client ; 3 touchent un processus interne ; 2 nécessitent un remplacement avant fermeture.",
    limits: "Cartographie préparée pour la démonstration ; la confirmation finale revient aux équipes propriétaires de chaque initiative.",
    fictional: true,
  },
};

export const TRAVAIL_VP = {
  id: "demo-vp-work",
  titreNaissance: "400 initiatives Polaris : où concentrer l'investissement",
  titre: "Recommandation de portefeuille : 12 initiatives à arrêter, 18 M$ d'économies",
  role: "VP Transformation",
  objectifNaissance: "Identifier, parmi 400 initiatives Polaris, celles qui produisent le moins de valeur.",
  objectif: "Décider quelles initiatives arrêter en priorité pour dégager 18 M$ et concentrer l'investissement sur les initiatives à plus forte valeur.",
  resumeDiagnostic: "12 initiatives présentent un faible alignement stratégique, des coûts élevés et un chevauchement fonctionnel — 18 M$ d'économies potentielles.",
  synthese: "Parmi les 12 initiatives à faible valeur : 7 n'ont aucun impact client et peuvent être arrêtées sans risque relationnel, 3 touchent un processus interne, 2 nécessitent un remplacement avant fermeture.",
  aValider: [
    "Confirmer l'absence d'impact client sur les 7 initiatives concernées",
    "Valider les remplacements nécessaires avant la fermeture des 2 dernières",
    "Chiffrer précisément l'économie nette après coûts de transition",
  ],
  prochainesActions: [
    "Faire valider l'arrêt des 7 premières initiatives en comité d'investissement",
    "Engager le remplacement préalable pour les 2 initiatives concernées",
    "Réallouer les 18 M$ économisés vers les initiatives à plus forte valeur",
  ],
  hypotheses: [
    "Les 7 initiatives sans impact client peuvent être arrêtées dès le prochain trimestre sans risque relationnel. À confirmer avec les porteurs.",
  ],
  options: [
    {
      id: "demo-vp-opt-phase",
      titre: "Arrêt en 2 phases (7 puis 5 initiatives)",
      description: "Arrêter d'abord les 7 initiatives sans impact client, puis traiter les 5 restantes une fois les remplacements prêts.",
      impacts: ["Risque relationnel nul sur la première phase", "18 M$ d'économies étalées sur 2 trimestres"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-vp-opt-groupe",
      titre: "Arrêt groupé des 12 initiatives",
      description: "Arrêter les 12 initiatives en même temps, sans attendre les remplacements des 2 dernières.",
      impacts: ["Économie immédiate maximale", "Risque de rupture de service sur 2 processus internes"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-vp-ev-portefeuille", "demo-vp-ev-impact-client"],
};

export const POSITIONS_MESH = {
  "demo-vp-ini-portail-fournisseurs": { x: -40, y: 200 },
  "demo-vp-ini-fournisseurs-strategiques": { x: 120, y: 320 },
  "demo-vp-ini-rapports-regionaux": { x: 420, y: -80 },
  "demo-vp-ini-approbation-budgetaire": { x: 560, y: 40 },
  "demo-vp-ini-suivi-budgets": { x: 500, y: 180 },
  "demo-vp-ini-intranet-rh": { x: 780, y: -60 },
  "demo-vp-app-rh": { x: 900, y: -160 },
  "demo-vp-ini-gestion-acces": { x: 150, y: 640 },
  "demo-vp-ini-tableau-manager": { x: 320, y: 760 },
  "demo-vp-ini-gestion-documentaire": { x: 480, y: 820 },
  "demo-vp-ini-controle-qualite": { x: 640, y: 780 },
  "demo-vp-ini-facturation-legacy": { x: -120, y: 480 },
  "demo-vp-app-facturation-centrale": { x: -260, y: 560 },
  "demo-vp-ini-registre-contrats": { x: 20, y: 920 },
  "demo-vp-app-documentaire": { x: -60, y: 1040 },
};

export const FIXTURES_VP = {
  applications: APPLICATIONS,
  entites: ENTITES,
  relations: RELATIONS,
  preuves: PREUVES,
  scenes: {},
  resultats: { "demo-vp-work": TRAVAIL_VP },
  positions: POSITIONS_MESH,
};
