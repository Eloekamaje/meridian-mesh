// MÉRIDIAN — Kiosque Polaris : fixtures locales (données fictives, jamais réseau).
// Tous les identifiants sont préfixés demo-polaris- (contrat §5.5).

export const APPLICATIONS = [
  { id: "demo-polaris-app-portail", nom: "Portail client", domaine: "Client", description: "Demandes et suivi côté client" },
  { id: "demo-polaris-app-conseiller", nom: "Poste conseiller", domaine: "Distribution", description: "Traitement en succursale" },
  { id: "demo-polaris-app-dossiers", nom: "Gestion des dossiers", domaine: "Opérations", description: "État et cycle de vie des dossiers" },
  { id: "demo-polaris-app-statuts", nom: "Diffusion des statuts", domaine: "Opérations", description: "Exposition des statuts aux canaux" },
];

export const ENTITES = [
  { id: "demo-polaris-ini-suivi", kind: "initiative", label: "Suivi des demandes clients", detail: "Informer le client tout au long de sa demande, sans appel ni relance", domaine: "Client", evidenceIds: ["demo-polaris-ev-g-initiatives"], fictional: true },
  { id: "demo-polaris-ini-poste", kind: "initiative", label: "Poste conseiller repensé", detail: "Dégager du temps de conseil en réduisant les tâches d'appoint", domaine: "Distribution", evidenceIds: ["demo-polaris-ev-g-initiatives"], fictional: true },
  { id: "demo-polaris-ini-reprises", kind: "initiative", label: "Réduction des reprises manuelles", detail: "Supprimer les corrections et ressaisies dans le traitement des dossiers", domaine: "Opérations", evidenceIds: ["demo-polaris-ev-g-initiatives"], fictional: true },
  { id: "demo-polaris-cap-etat-dossier", kind: "capability", label: "État fiable du dossier", detail: "Connaître l'état réel et à jour d'un dossier, partout où on en a besoin", evidenceIds: ["demo-polaris-ev-g-couverture"], fictional: true },
  { id: "demo-polaris-etape-demande", kind: "process_step", label: "Demande du client", domaine: "Client", fictional: true },
  { id: "demo-polaris-etape-conseil", kind: "process_step", label: "Échange en succursale", domaine: "Distribution", fictional: true },
  { id: "demo-polaris-etape-traitement", kind: "process_step", label: "Traitement du dossier", domaine: "Opérations", fictional: true },
];

export const RELATIONS = [
  { id: "demo-polaris-rel-suivi-demande", sourceId: "demo-polaris-ini-suivi", targetId: "demo-polaris-etape-demande", label: "vise à améliorer", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-poste-conseil", sourceId: "demo-polaris-ini-poste", targetId: "demo-polaris-etape-conseil", label: "vise à améliorer", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-reprises-traitement", sourceId: "demo-polaris-ini-reprises", targetId: "demo-polaris-etape-traitement", label: "vise à améliorer", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-demande-portail", sourceId: "demo-polaris-etape-demande", targetId: "demo-polaris-app-portail", label: "s'appuie sur", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-conseil-conseiller", sourceId: "demo-polaris-etape-conseil", targetId: "demo-polaris-app-conseiller", label: "s'appuie sur", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-traitement-dossiers", sourceId: "demo-polaris-etape-traitement", targetId: "demo-polaris-app-dossiers", label: "s'appuie sur", knowledgeStatus: "observe" },
  // Séquence 2 — besoin commun
  { id: "demo-polaris-rel-suivi-cap", sourceId: "demo-polaris-ini-suivi", targetId: "demo-polaris-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-polaris-rel-poste-cap", sourceId: "demo-polaris-ini-poste", targetId: "demo-polaris-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-polaris-rel-reprises-cap", sourceId: "demo-polaris-ini-reprises", targetId: "demo-polaris-cap-etat-dossier", label: "dépend de", knowledgeStatus: "a_etudier" },
  { id: "demo-polaris-rel-cap-dossiers", sourceId: "demo-polaris-cap-etat-dossier", targetId: "demo-polaris-app-dossiers", label: "existante — couverture partielle", knowledgeStatus: "observe", evidenceIds: ["demo-polaris-ev-g-couverture"] },
  { id: "demo-polaris-rel-dossiers-statuts", sourceId: "demo-polaris-app-dossiers", targetId: "demo-polaris-app-statuts", label: "alimente", knowledgeStatus: "observe" },
  { id: "demo-polaris-rel-statuts-portail", sourceId: "demo-polaris-app-statuts", targetId: "demo-polaris-app-portail", label: "raccordement envisagé", knowledgeStatus: "a_etudier" },
  { id: "demo-polaris-rel-statuts-conseiller", sourceId: "demo-polaris-app-statuts", targetId: "demo-polaris-app-conseiller", label: "raccordement envisagé", knowledgeStatus: "a_etudier" },
];

export const PREUVES = {
  "demo-polaris-ev-g-initiatives": {
    id: "demo-polaris-ev-g-initiatives",
    title: "Trois fiches d'initiative Polaris",
    sourceType: "Fiches préparées pour la démonstration",
    periodLabel: "Cycle de planification 2026",
    excerpt:
      "Fiche 1 — Suivi des demandes clients : tenir le client informé sans relance. Fiche 2 — Poste conseiller repensé : dégager du temps de conseil. Fiche 3 — Réduction des reprises manuelles : supprimer corrections et ressaisies dans les dossiers.",
    supports: "Les trois fiches citent le même besoin : disposer de l'état réel du dossier.",
    limits: "Fiches rédigées pour la démonstration ; le périmètre exact reste à confirmer avec les porteurs.",
    fictional: true,
  },
  "demo-polaris-ev-g-couverture": {
    id: "demo-polaris-ev-g-couverture",
    title: "Matrice de couverture du suivi des dossiers",
    sourceType: "Relevé de démonstration",
    periodLabel: "État au 18 septembre 2026",
    excerpt:
      "La Gestion des dossiers connaît l'état des dossiers qu'elle traite. La Diffusion des statuts expose une partie de ces états aux canaux. Couverture relevée : états principaux disponibles ; états détaillés et historique non exposés.",
    supports: "Une partie du suivi existe déjà et pourrait être partagée entre les trois initiatives.",
    limits: "Couverture partielle : elle ne répond pas encore à tous les besoins ; capacité de la Diffusion des statuts à confirmer.",
    fictional: true,
  },
};

export const TRAVAIL_G = {
  id: "demo-polaris-work-g",
  // Le travail naît avec un titre issu de la demande, puis prend celui de son livrable
  titreNaissance: "Trois pistes d'initiatives : ce qui se recoupe",
  titre: "Dossier d'arbitrage : mutualisation du suivi des dossiers",
  role: "Gestionnaire",
  objectifNaissance: "Comprendre ce que recoupent les trois pistes d'initiatives.",
  objectif: "Arbitrer entre trois projets en silos (6,6 M€ cumulés) et une mutualisation sur le socle existant.",
  resumeDiagnostic:
    "Les trois pistes visent le même besoin : connaître l'état réel, fiable et horodaté d'un dossier. Chaque direction a budgété sa propre solution, soit 6,6 M€ cumulés.",
  synthese:
    "Les trois pistes dépendent d'une même capacité — l'état fiable du dossier — déjà couverte à environ 80 % par la Gestion des dossiers et la Diffusion des statuts. Une mutualisation sur ce socle, avec deux connecteurs, est recommandée ; couverture et effort restent à confirmer avec les équipes.",
  aValider: [
    "Couverture réelle de la Gestion des dossiers face aux besoins des trois initiatives",
    "Capacité de la Diffusion des statuts à exposer les états détaillés",
    "Effort de raccordement des trois initiatives au socle commun",
  ],
  prochainesActions: [
    "Faire valider l'arbitrage en séance du comité",
    "Confirmer la couverture avec l'équipe Gestion des dossiers",
    "Confirmer les responsables de chaque connecteur",
  ],
  hypotheses: [
    "80 % du socle existe en production ; deux connecteurs suffiraient pour alimenter le portail client et le poste conseiller. À confirmer avec l'équipe Gestion des dossiers.",
  ],
  // Deux trajectoires comparées dans la conversation ; la recommandation n'est pas une décision
  options: [
    {
      id: "demo-polaris-opt-socle",
      titre: "Socle mutualisé et deux connecteurs",
      description: "S'appuyer sur la Gestion des dossiers et la Diffusion des statuts ; brancher le portail client et le poste conseiller.",
      impacts: ["Gestion des dossiers — socle renforcé", "Portail client — connecteur", "Poste conseiller — connecteur"],
      risque: "faible",
      statut: "recommandee",
    },
    {
      id: "demo-polaris-opt-silos",
      titre: "Trois développements en silos",
      description: "Chaque direction développe sa propre solution de suivi de l'état du dossier.",
      impacts: ["Trois architectures distinctes", "Divergence des états entre canaux"],
      risque: "moyen",
      statut: "a_evaluer",
    },
  ],
  preuves: ["demo-polaris-ev-g-initiatives", "demo-polaris-ev-g-couverture"],
};


const NOEUDS_BASE = [
  { id: "demo-polaris-ini-suivi", type: "initiative", position: { x: 40, y: 30 } },
  { id: "demo-polaris-ini-poste", type: "initiative", position: { x: 40, y: 250 } },
  { id: "demo-polaris-ini-reprises", type: "initiative", position: { x: 40, y: 470 } },
  { id: "demo-polaris-etape-demande", type: "etape", position: { x: 520, y: 60 } },
  { id: "demo-polaris-etape-conseil", type: "etape", position: { x: 520, y: 280 } },
  { id: "demo-polaris-etape-traitement", type: "etape", position: { x: 520, y: 500 } },
  { id: "demo-polaris-app-portail", type: "appli", position: { x: 960, y: 40 } },
  { id: "demo-polaris-app-conseiller", type: "appli", position: { x: 960, y: 260 } },
  { id: "demo-polaris-app-dossiers", type: "appli", position: { x: 960, y: 480 } },
  { id: "demo-polaris-app-statuts", type: "appli", position: { x: 1180, y: 480 } },
  { id: "demo-polaris-cap-etat-dossier", type: "capacite", position: { x: 520, y: 260 } },
];

export const SCENES = {
  "demo-polaris-scene-g-initiatives": {
    id: "demo-polaris-scene-g-initiatives",
    titre: "Polaris — lecture des initiatives",
    question: "Ce que les trois pistes impliquent et ce qui se recoupe",
    viewKind: "initiatives",
    noeuds: NOEUDS_BASE.map((n) =>
      n.type === "initiative"
        ? { ...n, accent: true }
        : n.type === "etape"
          ? { ...n }
          : { ...n, attenue: true, masque: n.type === "capacite" }
    ),
    liens: [
      { id: "demo-polaris-rel-suivi-demande", statut: "observee" },
      { id: "demo-polaris-rel-poste-conseil", statut: "observee" },
      { id: "demo-polaris-rel-reprises-traitement", statut: "observee" },
      { id: "demo-polaris-rel-demande-portail", statut: "observee", attenue: true },
      { id: "demo-polaris-rel-conseil-conseiller", statut: "observee", attenue: true },
      { id: "demo-polaris-rel-traitement-dossiers", statut: "observee", attenue: true },
    ],
  },
  "demo-polaris-scene-g-capacites": {
    id: "demo-polaris-scene-g-capacites",
    revele: true, // climax : la capacité commune et ses relations se matérialisent
    titre: "Polaris — capacités existantes",
    question: "Le besoin commun et ce qui existe déjà",
    viewKind: "dependencies",
    noeuds: NOEUDS_BASE.map((n) => {
      if (n.id === "demo-polaris-cap-etat-dossier") return { ...n, accent: true };
      if (n.id === "demo-polaris-app-dossiers") return { ...n, position: { x: 960, y: 480 }, accent: true };
      if (n.id === "demo-polaris-app-statuts") return { ...n, position: { x: 1180, y: 480 } };
      if (n.type === "initiative") return { ...n };
      return { ...n, attenue: true, masque: n.type === "etape" }; // étapes retirées : l'attention porte sur la capacité
    }),
    liens: [
      { id: "demo-polaris-rel-suivi-cap", statut: "a_etudier" },
      { id: "demo-polaris-rel-poste-cap", statut: "a_etudier" },
      { id: "demo-polaris-rel-reprises-cap", statut: "a_etudier" },
      { id: "demo-polaris-rel-cap-dossiers", statut: "observee" },
      { id: "demo-polaris-rel-dossiers-statuts", statut: "observee" },
      { id: "demo-polaris-rel-statuts-portail", statut: "a_etudier", attenue: true },
      { id: "demo-polaris-rel-statuts-conseiller", statut: "a_etudier", attenue: true },
    ],
  },
};

// Positions des jumeaux du récit : lobes adjacents aux territoires produit de leurs
// domaines (Client, Distribution, Opérations) — les membranes réelles s'étendent
// organiquement pour les accueillir, comme une découverte du Mesh.
export const POSITIONS_MESH = {
  "demo-polaris-ini-suivi": { x: -30, y: 250 },
  "demo-polaris-etape-demande": { x: -50, y: 370 },
  "demo-polaris-app-portail": { x: -10, y: 460 },
  "demo-polaris-ini-poste": { x: 540, y: -90 },
  "demo-polaris-etape-conseil": { x: 670, y: -120 },
  "demo-polaris-app-conseiller": { x: 790, y: -80 },
  "demo-polaris-ini-reprises": { x: 110, y: 880 },
  "demo-polaris-etape-traitement": { x: 230, y: 960 },
  "demo-polaris-app-dossiers": { x: 340, y: 890 },
  "demo-polaris-app-statuts": { x: 150, y: 1060 },
  "demo-polaris-cap-etat-dossier": { x: 290, y: 1100 },
};

export const FIXTURES_GESTIONNAIRE = {
  applications: APPLICATIONS,
  entites: ENTITES,
  relations: RELATIONS,
  preuves: PREUVES,
  scenes: SCENES,
  resultats: { "demo-polaris-work-g": TRAVAIL_G },
  positions: POSITIONS_MESH,
  sceneInitiale: "demo-polaris-scene-g-initiatives",
  // Monde connu à l'ouverture : tout, sauf la capacité à découvrir et ses relations,
  // qui se matérialisent au climax (scène portant `revele: true`)
  revelation: {
    noeuds: ["demo-polaris-cap-etat-dossier"],
    liens: ["demo-polaris-rel-suivi-cap", "demo-polaris-rel-poste-cap", "demo-polaris-rel-reprises-cap", "demo-polaris-rel-cap-dossiers"],
  },
};
