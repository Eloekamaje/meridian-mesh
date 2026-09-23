// Parcours Directeur Polaris — piloter le décommissionnement du parc applicatif en 2028. Joué dans
// les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil, résultats,
// canvas). Beats : message → activity → upsert_result / show_surface → observe. Même principe partout :
// Flore annonce en une phrase, une ligne d'activité évolue en place pendant le travail, puis UNE
// réponse porte le constat — jamais la même conclusion redite deux fois.

// Les 10 meilleurs candidats (sur 13), classés par score composite : coût de possession, dépendances
// critiques, risque opérationnel, dette technologique. `contenu.tableau` : nouveau bloc générique de
// CorpsMessageFlore, pour des colonnes hétérogènes qu'aucun bloc existant ne rend correctement.
const TABLEAU_CANDIDATS = {
  colonnes: ["Application", "Coût annuel", "Dépendances critiques", "Utilisateurs actifs", "Recommandation"],
  lignes: [
    ["Application Vision", "320 k$", "Aucune", "17", "Décommissionnement T2 2028"],
    ["Application Registre Contrats Papier", "220 k$", "Aucune", "12", "Décommissionnement T1 2028"],
    ["Application Archive Client", "190 k$", "Aucune", "8", "Décommissionnement T1 2028"],
    ["Application Old CRM Lite", "275 k$", "1", "25", "Décommissionnement T2 2028"],
    ["Application Suivi Fournisseurs Legacy", "260 k$", "2", "19", "Décommissionnement T3 2028"],
    ["Application Legacy Payroll Light", "280 k$", "1", "42", "Décommissionnement T3 2028"],
    ["Application Money Manager", "450 k$", "2", "34", "Migration préalable requise"],
    ["Application Rapports Régionaux V1", "310 k$", "3", "51", "Migration préalable requise"],
    ["Application Portail RH Historique", "340 k$", "1", "63", "Migration préalable requise"],
    ["Application Facturation Régionale V1", "410 k$", "3", "77", "Migration préalable requise"],
  ],
};

export const SCENARIO_DIRECTEUR = {
  id: "demo-directeur-scenario",
  version: 1,
  profileId: "directeur",
  title: "Piloter le décommissionnement du parc applicatif",
  roleLabel: "Directeur Polaris",
  personaRole: "Directeur · Polaris",
  roleContext: "Vous pilotez le décommissionnement du parc applicatif Polaris et devez planifier les retraits pour 2028.",
  openingMode: "user_request",
  closingText:
    "Un parc de 13 candidats devient un calendrier de retrait précis : 10 applications priorisées par coût, dépendances, risque et dette technologique, 3 mises de côté pour un cycle ultérieur.",
  discoveryStepId: "seq-2",
  steps: [
    {
      id: "seq-1",
      label: "Identifier les candidats",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Flore, quelles applications pouvons-nous retirer en 2028 ?",
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais identifier les applications candidates au retrait, classées par coût de possession, dépendances, risque opérationnel et dette technologique.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Recensement du parc applicatif Polaris…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Calcul du coût de possession…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Analyse des dépendances et du risque opérationnel…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Évaluation de la dette technologique…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai trouvé **13 candidats** au retrait en 2028, classés selon leur coût de possession, leurs dépendances, leur risque opérationnel et leur dette technologique.\n\nMontrez-moi les 10 meilleurs candidats pour voir le détail ?",
          evidenceIds: ["demo-directeur-ev-inventaire"],
          contenu: { comportement: "diagnostiquer" },
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Classer les meilleurs candidats",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Montre-moi les 10 meilleurs candidats.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je classe les 13 candidats par score composite et j'isole les 10 premiers.",
        },
        { type: "activity_start", id: "act-seq-2" },
        {
          type: "activity_step",
          activityId: "act-seq-2",
          label: "Tri des 13 candidats par score composite…",
          sources: ["Méthodologie de scoring de décommissionnement"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "enrichissement" },
        {
          type: "message",
          speaker: "flore",
          text: "Voici les 10 meilleurs candidats au retrait, classés par score composite (coût, dépendances, risque, dette technologique).\n\nLes 3 applications restantes (Middleware Interne V2, Data Warehouse Legacy, Batch Scheduler V1) concentrent trop de dépendances critiques pour ce cycle — elles seront réévaluées séparément.",
          evidenceIds: ["demo-directeur-ev-scoring"],
          contenu: { comportement: "recommander", tableau: TABLEAU_CANDIDATS },
          terminer: "act-seq-2",
        },
        { type: "observe", duree: 3500 },
      ],
    },
    {
      id: "seq-3",
      label: "Donner une suite au comité technique",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Prépare le calendrier de décommissionnement pour le comité technique.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je transforme le classement en calendrier de décommissionnement par trimestre.",
        },
        { type: "activity_start", id: "act-seq-3" },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Répartition des 10 applications par trimestre…",
          sources: ["Méthodologie de scoring de décommissionnement"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation des décisions soumises au comité technique…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Préparation du calendrier…",
          sources: [],
          duree: 300,
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "final" },
        {
          type: "message",
          speaker: "flore",
          text: "Le calendrier **POLARIS-DECOM-2028.md** est prêt et archivé dans votre espace Travail.\n\nIl planifie le décommissionnement des 10 applications sur 3 trimestres (T1 à T3 2028) et laisse les 3 applications à forte dépendance critique pour un cycle ultérieur. Ces décisions restent soumises au comité technique.",
          evidenceIds: ["demo-directeur-ev-scoring"],
          terminer: "act-seq-3",
          contenu: {
            comportement: "conclure",
            documentCanvas: "POLARIS-DECOM-2028.md",
            tableau: TABLEAU_CANDIDATS,
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
