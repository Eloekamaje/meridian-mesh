// Parcours VP Transformation — décider quelles initiatives Polaris financer, lesquelles arrêter.
// Joué dans les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil,
// résultats, canvas). Beats : message → activity → upsert_result / show_surface → observe. Même
// principe partout : Flore annonce en une phrase, une ligne d'activité évolue en place pendant le
// travail, puis UNE réponse porte le constat — jamais la même conclusion redite deux fois.

const INITIATIVES_SANS_IMPACT = [
  { app_id: "portail-fournisseurs", jumeau: "Portail fournisseurs 2.0", domaine: "Achats", texte: "Aucun impact client — arrêt recommandé." },
  { app_id: "rapports-regionaux", jumeau: "Automatisation des rapports régionaux", domaine: "Finance", texte: "Aucun impact client — arrêt recommandé." },
  { app_id: "intranet-rh", jumeau: "Refonte de l'intranet RH", domaine: "RH", texte: "Aucun impact client — arrêt recommandé." },
  { app_id: "suivi-budgets", jumeau: "Suivi interne des budgets de projet", domaine: "Finance", texte: "Aucun impact client — arrêt recommandé." },
];

export const SCENARIO_VP = {
  id: "demo-vp-scenario",
  version: 1,
  profileId: "vp",
  title: "Décider quelles initiatives Polaris financer",
  roleLabel: "VP Transformation",
  personaRole: "VP · Transformation Polaris",
  roleContext: "Vous devez décider, parmi 400 initiatives Polaris, lesquelles financer et lesquelles arrêter.",
  openingMode: "user_request",
  closingText:
    "400 initiatives deviennent une décision de portefeuille précise : 12 à arrêter, 18 M$ à réorienter, un ordre de priorité fondé sur l'impact client réel.",
  discoveryStepId: "seq-2",
  steps: [
    {
      id: "seq-1",
      label: "Évaluer le portefeuille",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Nous avons 400 initiatives Polaris. Lesquelles selon toi produisent le plus de valeur, et lesquelles devrions-nous arrêter ?",
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais croiser les 400 initiatives avec leur alignement stratégique, leurs coûts et leurs chevauchements fonctionnels.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Lecture des 400 fiches d'initiative…",
          sources: ["Portefeuille Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Évaluation de l'alignement stratégique…",
          sources: ["Feuille de route Polaris"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Croisement des coûts et des chevauchements fonctionnels…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai identifié **12 initiatives à faible valeur** : elles combinent un faible alignement stratégique, des coûts élevés et un chevauchement fonctionnel avec d'autres initiatives déjà financées.\n\nLes économies potentielles sont estimées à **18 M$**.\n\nSouhaitez-vous voir les risques d'abandon ?",
          evidenceIds: ["demo-vp-ev-portefeuille"],
          contenu: { comportement: "diagnostiquer", contributions: INITIATIVES_SANS_IMPACT.slice(0, 3) },
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Évaluer les risques d'abandon",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je vérifie l'impact client, le processus concerné et les dépendances de ces 12 initiatives avant de recommander un arrêt.",
        },
        { type: "activity_start", id: "act-seq-2" },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Vérification de l'impact client…",
          sources: ["Cartographie d'impact client des initiatives Polaris"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Repérage des remplacements nécessaires avant fermeture…",
          sources: ["Ancien système de facturation régionale", "Registre des contrats papier numérisé"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "enrichissement" },
        {
          type: "message",
          speaker: "flore",
          text: "Parmi les 12 initiatives :\n\n- **7 n'ont aucun impact client**\n- **3 touchent un processus interne**\n- **2 nécessitent un remplacement avant fermeture**\n\nJe recommande de commencer par les 7 initiatives sans impact client : le risque relationnel est nul et l'économie est immédiate.",
          evidenceIds: ["demo-vp-ev-impact-client"],
          contenu: { comportement: "recommander", contributions: INITIATIVES_SANS_IMPACT },
          terminer: "act-seq-2",
        },
        { type: "observe", duree: 3000 },
      ],
    },
    {
      id: "seq-3",
      label: "Donner une suite au comité",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Prépare une note de recommandation pour le comité d'investissement.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je rassemble le diagnostic, les économies attendues et le calendrier d'arrêt en une note pour le comité.",
        },
        { type: "activity_start", id: "act-seq-3" },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Regroupement des 12 initiatives par priorité d'arrêt…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation des décisions soumises au comité…",
          sources: ["Cartographie d'impact client des initiatives Polaris"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation de la note…",
          sources: [],
          duree: 300,
        },
        { type: "prepare", surface: "travail", titre: "Préparation de la note…", duree: 2200 },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "final" },
        { type: "prepare_end" },
        {
          type: "message",
          speaker: "flore",
          text: "La note **POLARIS-PORTFOLIO-2028.md** est prête et archivée dans votre espace Travail.\n\nElle recommande l'arrêt immédiat des 7 initiatives sans impact client, un remplacement préalable pour les 2 dernières, et une économie nette de **18 M$** réorientée vers les initiatives à plus forte valeur. Ces décisions restent soumises au vote du comité.",
          evidenceIds: ["demo-vp-ev-impact-client"],
          terminer: "act-seq-3",
          contenu: {
            comportement: "conclure",
            documentCanvas: "POLARIS-PORTFOLIO-2028.md",
            contributions: INITIATIVES_SANS_IMPACT.map((j) => ({ ...j, texte: "Arrêt recommandé — note soumise au comité." })),
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
