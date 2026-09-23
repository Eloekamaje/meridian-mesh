// Parcours VP Transformation — décider quelles initiatives Polaris financer, lesquelles arrêter.
// Joué dans les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil,
// résultats, canvas). Beats : message → activity → upsert_result / show_surface → observe. Même
// principe partout : Flore annonce en une phrase, une ligne d'activité évolue en place pendant le
// travail, puis UNE réponse porte le constat — jamais la même conclusion redite deux fois. Une
// question simple (clarification, chiffre déjà connu) reçoit une réponse directe, sans nouvelle
// activité : `terminer: true` marque alors la réponse comme complète sans fermer d'activité réelle.

const PRIORITE_3 = [
  { app_id: "suivi-demandes", jumeau: "Suivi des demandes clients", domaine: "Client", texte: "À privilégier — dépend de l'état fiable du dossier." },
  { app_id: "poste-conseiller", jumeau: "Simplification du poste conseiller", domaine: "Distribution", texte: "À privilégier — dépend de l'état fiable du dossier." },
  { app_id: "controles-dossier", jumeau: "Automatisation des contrôles de dossier", domaine: "Opérations", texte: "À privilégier — dépend de l'état fiable du dossier." },
];

const APERCU_12 = [
  { app_id: "portail-fournisseurs", jumeau: "Portail fournisseurs 2.0", domaine: "Achats", texte: "À réexaminer — chevauchement fonctionnel." },
  { app_id: "rapports-regionaux", jumeau: "Automatisation des rapports régionaux", domaine: "Finance", texte: "À réexaminer — faible contribution aux objectifs." },
  { app_id: "controle-qualite", jumeau: "Optimisation du contrôle qualité interne", domaine: "Opérations", texte: "À réexaminer — coût élevé pour le bénéfice attendu." },
];

const GROUPE_7 = [
  { app_id: "portail-fournisseurs", jumeau: "Portail fournisseurs 2.0", domaine: "Achats", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "rapports-regionaux", jumeau: "Automatisation des rapports régionaux", domaine: "Finance", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "intranet-rh", jumeau: "Refonte de l'intranet RH", domaine: "RH", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "suivi-budgets", jumeau: "Suivi interne des budgets de projet", domaine: "Finance", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "gestion-acces", jumeau: "Outil de gestion des accès internes", domaine: "TI", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "tableau-manager", jumeau: "Modernisation du tableau de bord managérial", domaine: "Opérations", texte: "Aucun impact client ni dépendance bloquante." },
  { app_id: "gestion-documentaire", jumeau: "Plateforme de gestion documentaire interne", domaine: "Opérations", texte: "Aucun impact client ni dépendance bloquante." },
];

const GROUPE_3 = [
  { app_id: "controle-qualite", jumeau: "Optimisation du contrôle qualité interne", domaine: "Opérations", texte: "Adaptation de processus internes nécessaire." },
  { app_id: "fournisseurs-strategiques", jumeau: "Système de gestion des fournisseurs stratégiques", domaine: "Achats", texte: "Adaptation de processus internes nécessaire." },
  { app_id: "approbation-budgetaire", jumeau: "Refonte du processus d'approbation budgétaire", domaine: "Finance", texte: "Adaptation de processus internes nécessaire." },
];

const GROUPE_2 = [
  { app_id: "facturation-legacy", jumeau: "Ancien système de facturation régionale", domaine: "Finance", texte: "Fournit une capacité attendue par d'autres projets — maintenir jusqu'au remplacement." },
  { app_id: "registre-contrats", jumeau: "Registre des contrats papier numérisé", domaine: "Opérations", texte: "Fournit une capacité attendue par d'autres projets — maintenir jusqu'au remplacement." },
];

export const SCENARIO_VP = {
  id: "demo-vp-scenario",
  version: 2,
  profileId: "vp",
  personaRole: "VP · Transformation Polaris",
  title: "Décider quelles initiatives Polaris financer",
  roleLabel: "VP Transformation",
  roleContext: "Vous devez arbitrer le portefeuille Polaris et concentrer les investissements sur les initiatives qui apportent le plus de valeur.",
  openingMode: "user_request",
  closingText:
    "Près de 400 initiatives deviennent une proposition d'arbitrage précise : 3 à privilégier en mutualisant leur besoin commun, 12 à réexaminer selon leur impact réel — jamais un simple chiffre d'économie déconnecté des conséquences.",
  discoveryStepId: "seq-4",
  steps: [
    {
      id: "seq-1",
      label: "Analyser le portefeuille",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Flore, nous avons près de 400 initiatives dans Polaris. On ne pourra pas tout financer. Lesquelles apporteraient le plus de valeur, et lesquelles devrait-on arrêter ?",
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais comparer leur contribution aux objectifs de Polaris, les bénéfices attendus et les investissements encore nécessaires. Je regarderai aussi les chevauchements et les dépendances entre initiatives.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Analyse du portefeuille Polaris…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Comparaison des bénéfices et des coûts…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Vérification des chevauchements et des dépendances…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "Trois initiatives ressortent en priorité : **le suivi des demandes clients, la simplification du poste conseiller et l'automatisation des contrôles de dossier**. Elles contribuent directement à réduire les délais et les tâches manuelles.\n\nElles partagent toutefois un besoin : disposer d'un état fiable et à jour du dossier. Une partie de leur investissement pourrait donc être mise en commun.\n\nJ'ai également repéré **12 initiatives à réexaminer en priorité**. Certaines contribuent peu aux objectifs actuels, d'autres présentent des coûts élevés par rapport aux bénéfices attendus, ou recoupent des travaux déjà financés.",
          evidenceIds: ["demo-vp-ev-portefeuille"],
          contenu: { comportement: "diagnostiquer", contributions: [...PRIORITE_3, ...APERCU_12] },
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Clarifier le regroupement",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Donc, pour les trois premières, tu recommandes de les regrouper ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je recommande de financer ensemble ce qu'elles ont en commun, tout en conservant leurs objectifs propres.\n\nLe client veut suivre sa demande, le conseiller veut pouvoir lui répondre et les opérations veulent éviter les reprises manuelles. Les usages sont différents, mais ils peuvent s'appuyer sur la même information de suivi.\n\nCela permettrait d'éviter que trois équipes reconstruisent séparément cette capacité.",
          evidenceIds: ["demo-vp-ev-capacite-commune"],
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-3",
      label: "Chiffrer l'arrêt des 12 initiatives",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Et pour les 12 à réexaminer, combien pourrait-on économiser en les arrêtant ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Leur arrêt pourrait éviter jusqu'à **18 M$ de dépenses prévues d'ici fin 2028**.\n\nIl faut encore déduire les engagements contractuels, les frais d'arrêt et les éventuels remplacements pour obtenir une économie nette.\n\nVeux-tu que je vérifie les conséquences de leur arrêt avant qu'on retienne cette piste ?",
          evidenceIds: ["demo-vp-ev-portefeuille"],
          contenu: { comportement: "diagnostiquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-4",
      label: "Vérifier les conséquences de l'arrêt",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Je ne veux pas qu'on économise sur un projet pour créer un problème ailleurs.",
        },
        { type: "activity_start", id: "act-seq-4" },
        {
          type: "activity_step",
          activityId: "act-seq-4",
          label: "Vérification des impacts clients…",
          sources: ["Cartographie d'impact client et de dépendances des initiatives à réexaminer"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-4",
          label: "Analyse des processus concernés…",
          sources: ["Cartographie d'impact client et de dépendances des initiatives à réexaminer"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-4",
          label: "Contrôle des dépendances entre projets…",
          sources: ["Cartographie d'impact client et de dépendances des initiatives à réexaminer"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-vp-work", phase: "enrichissement" },
        {
          type: "message",
          speaker: "flore",
          text: "Les 12 initiatives se répartissent en trois groupes :\n\n- **7 initiatives** : je n'ai identifié aucun impact direct sur les services clients ni dépendance bloquante dans les sources consultées. Ce sont les premières candidates à une revue d'arrêt.\n- **3 initiatives** : leur arrêt nécessiterait une adaptation des processus internes. Il faut préparer cette transition avec les équipes concernées.\n- **2 initiatives** : elles fournissent une capacité attendue par d'autres projets. Je recommande de les maintenir jusqu'à ce qu'un remplacement soit prêt.",
          evidenceIds: ["demo-vp-ev-impact-client"],
          contenu: { comportement: "recommander", contributions: [...GROUPE_7, ...GROUPE_3, ...GROUPE_2] },
          terminer: "act-seq-4",
        },
        { type: "observe", duree: 3000 },
      ],
    },
    {
      id: "seq-5",
      label: "Confirmer le plan d'action",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Tu commencerais donc par les sept premières ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Oui. Je ferais confirmer les impacts et les engagements par leurs responsables avant de soumettre leur arrêt au comité.\n\nEn parallèle, je préparerais la transition des trois initiatives qui touchent les processus internes. Pour les deux dernières, je conditionnerais toute décision d'arrêt à la disponibilité du remplacement.\n\nEt je protégerais le financement de la capacité commune aux trois initiatives prioritaires : elle contribue aux bénéfices attendus des trois projets.",
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-6",
      label: "Proposer la note d'arbitrage",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "D'accord. Il faut qu'on puisse présenter ces choix clairement au comité.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Veux-tu que je prépare une **note d'arbitrage pour le comité Polaris** ?\n\nElle présentera les initiatives à financer, à coordonner ou à arrêter, avec les bénéfices attendus, les économies potentielles et les risques associés.",
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 1500 },
      ],
    },
    {
      id: "seq-7",
      label: "Préparer la note pour le comité",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Fais bien ressortir les décisions qu'on peut prendre maintenant et celles qui demandent encore une validation.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je prépare la note avec cette distinction. Chaque recommandation sera accompagnée de sa justification, de ses sources et des points à confirmer.",
        },
        { type: "activity_start", id: "act-seq-7" },
        {
          type: "activity_step",
          activityId: "act-seq-7",
          label: "Préparation de la note d'arbitrage…",
          sources: ["Analyse du portefeuille des 400 initiatives Polaris"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-7",
          label: "Consolidation des recommandations et des sources…",
          sources: ["Cartographie d'impact client et de dépendances des initiatives à réexaminer"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-7",
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
          text: "La note est prête. Tu trouveras d'abord les arbitrages proposés, puis les impacts financiers, les risques et les validations nécessaires avant décision.",
          evidenceIds: ["demo-vp-ev-portefeuille", "demo-vp-ev-impact-client"],
          terminer: "act-seq-7",
          contenu: {
            comportement: "conclure",
            documentCanvas: "Polaris — Proposition d'arbitrage du portefeuille",
            contributions: [...PRIORITE_3, ...GROUPE_7.slice(0, 2)],
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
