// Parcours Gestionnaire — ordre et questions de l'annexe A.1 de la spécification Polaris, joués dans
// les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil, résultats, canvas).
// Beats : message → activity → upsert_result / show_surface → observe.

// Contenus riches des réponses de Flore (cartes KPI, tableau comparatif, jumeaux, document) :
// ceux de la page Travail réelle — mêmes formes que les réponses du backend.
const JUMEAUX_4 = [
  { app_id: "app-portail", jumeau: "Portail client", domaine: "Client", texte: "Données de parcours client et auto-suivi en ligne." },
  { app_id: "app-conseiller", jumeau: "Poste conseiller", domaine: "Distribution", texte: "Charge de traitement des conseillers en succursale." },
  { app_id: "app-dossiers", jumeau: "Gestion des dossiers", domaine: "Opérations", texte: "Machine à états officielle et cycle de vie complet du dossier." },
  { app_id: "app-statuts", jumeau: "Diffusion des statuts", domaine: "Opérations", texte: "Exposition temps réel des événements d'état." },
];

export const SCENARIO_GESTIONNAIRE = {
  id: "demo-polaris-scenario-gestionnaire",
  version: 2,
  profileId: "gestionnaire",
  title: "Faire avancer la réunion sur les initiatives",
  roleLabel: "Gestionnaire",
  roleContext: "Vous réunissez architectes de domaine, architectes de solution, concepteurs et tech leads autour de pistes d'initiatives Polaris.",
  openingMode: "user_request",
  closingText:
    "Trois discussions dispersées deviennent une question collective précise : ce qui pourrait être partagé, ce qui reste spécifique, et les validations nécessaires pour comparer les options.",
  discoveryStepId: "seq-2",
  // Une ligne d'activité par traitement : activity_start → activity_step (libellé + sources) →
  // messages de découverte intercalés → `terminer` sur la réponse finale. Le libellé remplace le précédent sur place.
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
        // L'envoi de la première demande fait naître le travail (il apparaît dans les Récentes) et
        // ouvre la conversation : comme dans ChatGPT ou Claude, tout se déroule ensuite dans ce même fil
        { type: "upsert_result", resultId: "demo-polaris-work-g", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais rapprocher leurs objectifs des processus et capacités concernés.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Lecture des trois fiches d'initiative…",
          sources: ["Fiche — Suivi des demandes clients", "Fiche — Poste conseiller repensé", "Fiche — Réduction des reprises manuelles"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Consultation des jumeaux concernés…",
          sources: ["Portail client", "Poste conseiller", "Gestion des dossiers"],
          duree: 1500,
        },
        // Découverte importante : un message de Flore, la ligne se poursuit en dessous
        {
          type: "message",
          speaker: "flore",
          text: "Les trois pistes reposent sur le même besoin : connaître l'état réel du dossier. Je mesure ce que cela représente en budget.",
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Recherche des recoupements et du budget cumulé…",
          sources: ["Trois fiches d'initiative Polaris"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-polaris-work-g", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai rapproché les objectifs déclarés dans les trois fiches d'initiative avec les flux réels observés sur les jumeaux numériques de votre système d'information.\n\nLe constat est net : **les 3 directions cherchent en réalité à résoudre exactement le même problème métier**, à savoir connaître l'état réel, fiable et horodaté d'un dossier (parcours client web, poste conseiller en agence, et chaîne opérationnelle de traitement).\n\n⚠️ **Risque de triple redondance financière :** en l'absence de concertation, chaque direction a budgété sa propre solution en silo, pour un total cumulé de **6,6 M€** afin de reconstruire 3 fois la même capacité.",
          evidenceIds: ["demo-polaris-ev-g-initiatives"],
          contenu: { comportement: "diagnostiquer", contributions: JUMEAUX_4 },
          // Le traitement s'arrête quand la réponse est complète — pas après son temps de lecture
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Révéler le point commun",
      decouverte: true,
      beats: [
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
        { type: "activity_start", id: "act-seq-2" },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Examen de la Gestion des dossiers…",
          sources: ["Gestion des dossiers", "Matrice de couverture du suivi des dossiers"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Vérification des interfaces et de leurs usages…",
          sources: ["Diffusion des statuts"],
          duree: 1500,
        },
        {
          type: "message",
          speaker: "flore",
          text: "Une grande partie du besoin est déjà couverte en production. Je vérifie ce qu'il reste à raccorder.",
        },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Estimation des raccordements restants…",
          sources: ["Portail client", "Poste conseiller"],
          duree: 1500,
        },
        {
          type: "message",
          speaker: "flore",
          text: "Absolument pas. Le SI possède déjà **80 % de la solution en production** dans l'application « Gestion des dossiers » (`app-dossiers`) et son module d'exposition « Diffusion des statuts » (`app-statuts`).\n\nPlutôt que de financer 3 développements spécifiques à 6,6 M€, il suffit de construire 2 connecteurs d'API légers branchés directement sur ce socle existant.\n\nCe choix permet une mise en service en **4 mois** au lieu de 18 mois, pour un investissement mutualisé de **1,5 M€**, dégageant un **gain net de +5,1 M€ (-77%)** et garantissant une source unique de vérité sur les dossiers.\n\nCes chiffres reposent sur la matrice de couverture : la couverture réelle et l'effort de raccordement restent à confirmer avec l'équipe Gestion des dossiers avant l'arbitrage.",
          evidenceIds: ["demo-polaris-ev-g-couverture"],
          terminer: "act-seq-2",
          contenu: {
            comportement: "arbitrer",
            kpis: {
              gain: "+5,1 M€",
              gainSousTitre: "1,5 M€ vs 6,6 M€ (-77%)",
              delai: "4 mois",
              delaiSousTitre: "Au lieu de 12 à 18 mois en silos",
              socle: "80 %",
              socleSousTitre: "En production dans le SI",
            },
            tableauComparatif: [
              { critere: "Budget global", silos: "6,6 M€", socle: "1,5 M€ (-77%)" },
              { critere: "Délai de mise en service", silos: "12 à 18 mois", socle: "4 mois (-8 à -14 mois)" },
              { critere: "Architecture SI", silos: "3 développements spécifiques", socle: "2 connecteurs API légers sur socle" },
              { critere: "Dette technique", silos: "Élevée (divergence des états)", socle: "Faible (source unique de vérité)" },
            ],
            contributions: [
              { app_id: "app-dossiers", jumeau: "Gestion des dossiers", domaine: "Opérations", texte: "Socle métier central 80% existant en production." },
              { app_id: "app-statuts", jumeau: "Diffusion des statuts", domaine: "Opérations", texte: "Concentrateur d'événements prêt pour exposition." },
            ],
          },
        },
        // Première synthèse et hypothèse de couverture : le travail s'enrichit
        { type: "upsert_result", resultId: "demo-polaris-work-g", phase: "enrichissement" },
        { type: "observe", duree: 5000 },
      ],
    },
    {
      id: "seq-3",
      label: "Donner une suite à la réunion",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Prépare le dossier d'arbitrage pour le comité.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je rassemble le périmètre commun, les différences et les points à faire valider.",
        },
        { type: "activity_start", id: "act-seq-3" },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Regroupement des besoins communs…",
          sources: ["Trois fiches d'initiative Polaris"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation des décisions soumises au comité…",
          sources: ["Matrice de couverture du suivi des dossiers"],
          duree: 1400,
        },
        // Flore annonce la représentation ; l'espace concerné affiche sa préparation, l'ancien contenu reste stable
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation de la synthèse…",
          sources: [],
          duree: 300,
        },
        { type: "prepare", surface: "travail", titre: "Préparation de la synthèse…", duree: 2200 },
        { type: "upsert_result", resultId: "demo-polaris-work-g", phase: "final" },
        { type: "prepare_end" },
        {
          type: "message",
          speaker: "flore",
          text: "Le dossier exécutif **CASE_101_ARBITRAGE_CONVERGENCE.md** est prêt et archivé dans votre espace Travail.\n\nIl propose le gel des 3 développements redondants en silos, l'allocation du socle commun et les connecteurs d'interface à déployer. Ces décisions restent soumises au vote du comité.",
          evidenceIds: ["demo-polaris-ev-g-couverture"],
          terminer: "act-seq-3",
          // Le message porte le document : le canvas s'ouvre à sa publication, comme dans le produit
          contenu: {
            comportement: "conclure",
            documentCanvas: "CASE_101_ARBITRAGE_CONVERGENCE.md",
            contributions: JUMEAUX_4.map((j) => ({ ...j, texte: `${j.jumeau} : raccordement prêt à être branché.` })),
          },
        },
        // Temps d'observation du résultat avant la fin de la démonstration
        { type: "observe", duree: 5000 },
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
