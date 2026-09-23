// MÉRIDIAN — Kiosque Polaris : fixtures locales du parcours VP Transformation (données fictives,
// jamais réseau). Tous les identifiants sont préfixés demo-vp- (contrat §5.5).
// Ni scènes ni révélation Atlas mises en scène : le scénario ne joue aucun beat apply_scene —
// construireMesh() dans mockApi.js a des replis sûrs pour ces champs absents, tout s'affiche
// simplement dès le départ.

export const APPLICATIONS = [
  { id: "demo-vp-app-facturation-centrale", nom: "Plateforme Facturation Centrale", domaine: "Finance", description: "Socle de facturation mutualisé" },
  { id: "demo-vp-app-documentaire", nom: "Système Documentaire Central", domaine: "Opérations", description: "Gestion documentaire mutualisée" },
  { id: "demo-vp-app-rh", nom: "Portail RH", domaine: "RH", description: "Portail des ressources humaines" },
];

export const ENTITES = [
  // Les 3 initiatives à privilégier — usages différents, même besoin sous-jacent
  { id: "demo-vp-ini-suivi-demandes", kind: "initiative", label: "Suivi des demandes clients", detail: "Permettre au client de suivre sa demande sans relance", domaine: "Client", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-poste-conseiller", kind: "initiative", label: "Simplification du poste conseiller", detail: "Donner au conseiller de quoi répondre au client sans délai", domaine: "Distribution", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-controles-dossier", kind: "initiative", label: "Automatisation des contrôles de dossier", detail: "Éviter les reprises manuelles dans le traitement du dossier", domaine: "Opérations", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-cap-etat-dossier", kind: "capability", label: "État fiable et à jour du dossier", detail: "Connaître l'état réel du dossier, partout où on en a besoin", evidenceIds: ["demo-vp-ev-capacite-commune"], fictional: true },

  // Les 12 initiatives à réexaminer
  { id: "demo-vp-ini-portail-fournisseurs", kind: "initiative", label: "Portail fournisseurs 2.0", detail: "Refonte du portail d'échange avec les fournisseurs", domaine: "Achats", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-rapports-regionaux", kind: "initiative", label: "Automatisation des rapports régionaux", detail: "Génération automatique des rapports de performance régionaux", domaine: "Finance", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-intranet-rh", kind: "initiative", label: "Refonte de l'intranet RH", detail: "Nouvelle interface pour l'intranet des ressources humaines", domaine: "RH", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-suivi-budgets", kind: "initiative", label: "Suivi interne des budgets de projet", detail: "Outil de suivi budgétaire pour les chefs de projet", domaine: "Finance", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-gestion-acces", kind: "initiative", label: "Outil de gestion des accès internes", detail: "Portail de demande d'accès aux systèmes internes", domaine: "TI", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-tableau-manager", kind: "initiative", label: "Modernisation du tableau de bord managérial", detail: "Nouveau tableau de bord pour les gestionnaires d'équipe", domaine: "Opérations", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-gestion-documentaire", kind: "initiative", label: "Plateforme de gestion documentaire interne", detail: "Nouvel outil de classement documentaire pour les équipes internes", domaine: "Opérations", evidenceIds: ["demo-vp-ev-portefeuille"], fictional: true },
  { id: "demo-vp-ini-controle-qualite", kind: "initiative", label: "Optimisation du contrôle qualité interne", detail: "Révision des processus de contrôle qualité internes — adaptation de processus nécessaire", domaine: "Opérations", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-fournisseurs-strategiques", kind: "initiative", label: "Système de gestion des fournisseurs stratégiques", detail: "Suivi des relations avec les fournisseurs stratégiques — adaptation de processus nécessaire", domaine: "Achats", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-approbation-budgetaire", kind: "initiative", label: "Refonte du processus d'approbation budgétaire", detail: "Simplification du circuit d'approbation des budgets internes — adaptation de processus nécessaire", domaine: "Finance", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-facturation-legacy", kind: "initiative", label: "Ancien système de facturation régionale", detail: "Fournit une capacité encore utilisée par d'autres projets, en attendant la Plateforme Facturation Centrale", domaine: "Finance", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
  { id: "demo-vp-ini-registre-contrats", kind: "initiative", label: "Registre des contrats papier numérisé", detail: "Fournit une capacité encore utilisée par d'autres projets, en attendant le Système Documentaire Central", domaine: "Opérations", evidenceIds: ["demo-vp-ev-impact-client"], fictional: true },
];

export const RELATIONS = [
  // Les 3 priorités dépendent toutes du même besoin — c'est ce qui permet de mutualiser une partie de l'investissement
  { id: "demo-vp-rel-suivi-cap", sourceId: "demo-vp-ini-suivi-demandes", targetId: "demo-vp-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-vp-rel-conseiller-cap", sourceId: "demo-vp-ini-poste-conseiller", targetId: "demo-vp-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-vp-rel-controles-cap", sourceId: "demo-vp-ini-controles-dossier", targetId: "demo-vp-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },

  { id: "demo-vp-rel-portail-fournisseurs-strategiques", sourceId: "demo-vp-ini-portail-fournisseurs", targetId: "demo-vp-ini-fournisseurs-strategiques", label: "chevauchement fonctionnel", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-portefeuille"] },
  { id: "demo-vp-rel-facturation-legacy-centrale", sourceId: "demo-vp-ini-facturation-legacy", targetId: "demo-vp-app-facturation-centrale", label: "capacité à transférer vers", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-impact-client"] },
  { id: "demo-vp-rel-registre-documentaire", sourceId: "demo-vp-ini-registre-contrats", targetId: "demo-vp-app-documentaire", label: "capacité à transférer vers", knowledgeStatus: "observe", evidenceIds: ["demo-vp-ev-impact-client"] },
  { id: "demo-vp-rel-intranet-rh-portail", sourceId: "demo-vp-ini-intranet-rh", targetId: "demo-vp-app-rh", label: "s'appuie sur", knowledgeStatus: "a_etudier" },
];

export const PREUVES = {
  "demo-vp-ev-portefeuille": {
    id: "demo-vp-ev-portefeuille",
    title: "Analyse du portefeuille des 400 initiatives Polaris",
    sourceType: "Relevé préparé pour la démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Comparaison de la contribution aux objectifs de Polaris, des bénéfices attendus et des investissements encore nécessaires pour les 400 initiatives, avec repérage des chevauchements et des dépendances.",
    supports: "3 initiatives ressortent en priorité et partagent un même besoin ; 12 autres sont à réexaminer (faible contribution, coûts élevés ou recoupement avec des travaux déjà financés).",
    limits: "Relevé préparé pour la démonstration ; le périmètre exact reste à confirmer avec les porteurs de chaque initiative.",
    fictional: true,
  },
  "demo-vp-ev-capacite-commune": {
    id: "demo-vp-ev-capacite-commune",
    title: "Besoin commun aux 3 initiatives prioritaires",
    sourceType: "Relevé de démonstration",
    periodLabel: "Cycle de planification 2028",
    excerpt: "Le suivi des demandes clients, la simplification du poste conseiller et l'automatisation des contrôles de dossier dépendent tous d'un état fiable et à jour du dossier, malgré des usages différents.",
    supports: "Une partie de l'investissement des 3 initiatives peut être mise en commun sans changer leurs objectifs propres.",
    limits: "Relevé préparé pour la démonstration ; l'effort de mutualisation reste à chiffrer avec les équipes concernées.",
    fictional: true,
  },
  "demo-vp-ev-impact-client": {
    id: "demo-vp-ev-impact-client",
    title: "Cartographie d'impact client et de dépendances des initiatives à réexaminer",
    sourceType: "Relevé de démonstration",
    periodLabel: "État au 15 mars 2028",
    excerpt: "Pour chacune des 12 initiatives à réexaminer, mesure de l'impact sur les services clients, du processus interne concerné et des dépendances envers d'autres projets.",
    supports: "7 initiatives sans impact direct ni dépendance bloquante ; 3 nécessitent une adaptation de processus internes ; 2 fournissent une capacité attendue par d'autres projets.",
    limits: "Cartographie préparée pour la démonstration ; la confirmation finale revient aux responsables de chaque initiative.",
    fictional: true,
  },
};

export const TRAVAIL_VP = {
  id: "demo-vp-work",
  titreNaissance: "400 initiatives Polaris : où concentrer l'investissement",
  titre: "Polaris — Proposition d'arbitrage du portefeuille",
  role: "VP Transformation",
  objectifNaissance: "Décider, parmi près de 400 initiatives Polaris, lesquelles financer et lesquelles arrêter.",
  objectif: "Concentrer l'investissement sur les initiatives à plus forte valeur et statuer sur les 12 initiatives à réexaminer.",
  resumeDiagnostic: "3 initiatives ressortent en priorité et partagent un même besoin — une partie de leur investissement peut être mise en commun. 12 autres initiatives sont à réexaminer : faible contribution, coûts élevés ou recoupement avec des travaux déjà financés.",
  synthese: "Les 12 initiatives à réexaminer se répartissent en trois groupes : 7 sans impact client ni dépendance bloquante (premières candidates à l'arrêt), 3 nécessitant une adaptation de processus internes, et 2 fournissant une capacité encore attendue par d'autres projets (à maintenir jusqu'à leur remplacement).",
  aValider: [
    "Faire confirmer par les responsables les impacts et les engagements des 7 initiatives sans impact client",
    "Préparer la transition des 3 initiatives touchant des processus internes",
    "Suivre la disponibilité des remplacements avant d'arrêter les 2 dernières initiatives",
  ],
  prochainesActions: [
    "Soumettre l'arrêt des 7 premières initiatives au comité, une fois les impacts confirmés",
    "Engager la transition des 3 initiatives concernées avec leurs équipes",
    "Conditionner l'arrêt des 2 dernières à la disponibilité de leur remplacement",
    "Protéger le financement de la capacité commune aux 3 initiatives prioritaires",
  ],
  hypotheses: [
    "Le regroupement du financement des 3 initiatives prioritaires sur leur besoin commun n'affecte pas leurs objectifs propres. À confirmer avec les équipes concernées.",
  ],
  options: [
    {
      id: "demo-vp-opt-phase",
      titre: "Arrêt progressif selon les 3 groupes identifiés",
      description: "Arrêter d'abord les 7 initiatives sans impact ni dépendance, préparer la transition des 3 suivantes, et conditionner l'arrêt des 2 dernières à leur remplacement.",
      impacts: ["Risque limité à chaque étape", "Aucune rupture de service pour les projets dépendants"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-vp-opt-groupe",
      titre: "Arrêt groupé des 12 initiatives",
      description: "Arrêter les 12 initiatives en même temps, sans attendre la transition ni les remplacements nécessaires.",
      impacts: ["Économie immédiate maximale", "Risque de rupture sur les processus internes et les projets dépendants"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-vp-ev-portefeuille", "demo-vp-ev-capacite-commune", "demo-vp-ev-impact-client"],
};

export const POSITIONS_MESH = {
  "demo-vp-ini-suivi-demandes": { x: -260, y: -40 },
  "demo-vp-ini-poste-conseiller": { x: -40, y: -220 },
  "demo-vp-ini-controles-dossier": { x: 180, y: -60 },
  "demo-vp-cap-etat-dossier": { x: -60, y: -60 },
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
