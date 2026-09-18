// Parcours Gestionnaire — textes et ordre issus de l'annexe A.1 de la spécification Polaris.
// Beats : message → activity → apply_scene/upsert_result/show_surface → observe.

export const SCENARIO_GESTIONNAIRE = {
  id: "demo-polaris-scenario-gestionnaire",
  version: 1,
  profileId: "gestionnaire",
  title: "Faire avancer la réunion sur les initiatives",
  roleLabel: "Gestionnaire",
  roleContext: "Vous réunissez architectes de domaine, architectes de solution, concepteurs et tech leads autour de pistes d'initiatives Polaris.",
  openingMode: "user_request",
  closingText:
    "Trois discussions dispersées deviennent une question collective précise : ce qui pourrait être partagé, ce qui reste spécifique, et les validations nécessaires pour comparer les options.",
  discoveryStepId: "seq-2",
  steps: [
    {
      id: "seq-1",
      label: "Poser les pistes",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Nous avons trois pistes : le suivi des demandes clients, le poste conseiller et la réduction des reprises manuelles. Nous avons du mal à voir ce qu'elles impliquent et ce qui se recoupe.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais rapprocher leurs objectifs des processus et capacités concernés.",
        },
        {
          type: "activity",
          label: "Rapprochement des initiatives",
          ops: [
            "Lit les trois fiches d'initiative…",
            "Consulte les connaissances des jumeaux concernés…",
            "Recherche les points communs…",
          ],
        },
        { type: "apply_scene", sceneId: "demo-polaris-scene-g-initiatives" },
        {
          type: "message",
          speaker: "flore",
          text: "Voici les trois pistes reliées aux parties du parcours qu'elles veulent améliorer. Les applications restent au second plan pour l'instant.",
          evidenceIds: ["demo-polaris-ev-g-initiatives"],
        },
        { type: "observe", duree: 5000 },
      ],
    },
    {
      id: "seq-2",
      label: "Révéler le point commun",
      decouverte: true,
      beats: [
        {
          type: "message",
          speaker: "flore",
          text: "Les trois pistes ont un besoin commun : connaître l'état réel du dossier. Aujourd'hui, le client, le conseiller et les opérations n'en disposent pas de la même façon.",
        },
        {
          type: "message",
          speaker: "persona",
          text: "Devons-nous tout construire pour partager cette information ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je vérifie les capacités déjà disponibles et leurs limites.",
        },
        {
          type: "activity",
          label: "Vérification des capacités",
          ops: [
            "Examine la gestion des dossiers…",
            "Vérifie les interfaces et leurs usages…",
            "Rapproche avec les besoins des trois initiatives…",
          ],
        },
        { type: "apply_scene", sceneId: "demo-polaris-scene-g-capacites" },
        {
          type: "message",
          speaker: "flore",
          text: "Une partie du suivi existe déjà. Sa couverture ne répond pas encore à tous les besoins des trois initiatives. Nous pouvons examiner un socle commun et les adaptations propres à chacune.",
          evidenceIds: ["demo-polaris-ev-g-couverture"],
        },
        { type: "observe", duree: 6000 },
      ],
    },
    {
      id: "seq-3",
      label: "Donner une suite à la réunion",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Prépare ce qu'il nous faut pour évaluer cette piste ensemble.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je rassemble le périmètre commun, les différences et les points à faire valider.",
        },
        {
          type: "activity",
          label: "Préparation de la base commune",
          ops: [
            "Regroupe les besoins communs…",
            "Identifie les responsables…",
            "Prépare les questions d'effort, de couverture et de capacité…",
          ],
        },
        { type: "upsert_result", resultId: "demo-polaris-work-g" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Voici une base commune pour votre réunion : ce qui pourrait être partagé, ce qui reste spécifique et les validations nécessaires pour comparer les options.",
        },
        { type: "observe", duree: 6000 },
      ],
    },
  ],
};

export const PROFILS = [
  {
    id: "gestionnaire",
    titre: "Directeur / Gestionnaire",
    phrase: "Éclairer les initiatives à évaluer ensemble.",
    disponible: true,
  },
  {
    id: "ligne-affaires",
    titre: "Ligne d'affaires",
    phrase: "Réduire le délai d'émission d'une traite en succursale.",
    disponible: false,
  },
  {
    id: "architecte",
    titre: "Architecte",
    phrase: "Décommissionner ou réécrire MD2 : comprendre les impacts.",
    disponible: false,
  },
  {
    id: "support-ti",
    titre: "Support TI",
    phrase: "Relier les alertes et orienter le diagnostic.",
    disponible: false,
  },
  {
    id: "developpeur",
    titre: "Développeur",
    phrase: "Comprendre un changement et les usages à préserver.",
    disponible: false,
  },
];

export const SCENARIOS = {
  gestionnaire: SCENARIO_GESTIONNAIRE,
};
