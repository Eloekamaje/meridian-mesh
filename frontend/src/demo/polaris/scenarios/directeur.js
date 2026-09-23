// Parcours Directeur Polaris — planifier le décommissionnement du parc applicatif en 2028. Joué dans
// les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil, résultats,
// canvas). Beats : message → activity → upsert_result / show_surface → observe. Même principe partout :
// Flore annonce en une phrase, une ligne d'activité évolue en place pendant le travail, puis UNE
// réponse porte le constat — jamais la même conclusion redite deux fois.

// Les 10 candidats à traiter en priorité (sur 13), avec les conditions de leur retrait. Bloc générique
// `contenu.tableau` de CorpsMessageFlore, pour des colonnes hétérogènes qu'aucun bloc existant ne rend
// correctement — les cellules acceptent le gras (**...**), comme le reste des messages de Flore.
const TABLEAU_10_CANDIDATS = {
  colonnes: ["Application", "Coût annuel", "Utilisateurs actifs¹", "Dépendances critiques identifiées", "Retrait envisagé et conditions"],
  lignes: [
    ["**Vision**", "320 k$", "17", "Aucune", "**T2 2028** — transférer les usages et archiver les historiques"],
    ["**ReportPlus**", "210 k$", "24", "Aucune", "**T2 2028** — valider la reprise des rapports"],
    ["**DocBridge**", "180 k$", "9", "Aucune", "**T2 2028** — transférer les archives et vérifier leur accès"],
    ["**Suivi Agence**", "260 k$", "38", "Aucune", "**T3 2028** — accompagner l'adoption de l'outil de remplacement"],
    ["**PlanifPro**", "150 k$", "12", "Aucune", "**T3 2028** — reprendre les plannings et les historiques"],
    ["**Money Manager**", "450 k$", "86", "2 flux critiques", "**T3 2028** — migrer et valider les deux flux"],
    ["**BatchLink**", "390 k$", "6", "3 traitements critiques", "**T3 2028** — migrer les traitements et valider leur fonctionnement"],
    ["**Référentiel Contact**", "280 k$", "43", "1 synchronisation critique", "**T4 2028** — basculer vers le référentiel cible"],
    ["**Dossier Express**", "520 k$", "124", "2 parcours critiques", "**T4 2028** — migrer progressivement les parcours"],
    ["**Archive Services**", "240 k$", "15", "1 service de consultation critique", "**T4 2028** — garantir la conservation et la consultation des données"],
  ],
};
const NOTE_UTILISATEURS = "¹ Utilisateurs humains actifs sur les 90 derniers jours. Les usages automatisés sont examinés séparément.";

// Ce que l'Atlas met en évidence au tour 3 : Money Manager, ses deux flux critiques, et les deux
// applications qui en dépendent encore (voir fixturesDirecteur.js::RELATIONS)
const ATLAS_MONEY_MANAGER = {
  titre: "Money Manager et ses flux critiques",
  cibles: [
    "demo-directeur-app-money-manager",
    "demo-directeur-flux-facturation",
    "demo-directeur-flux-rapprochement",
    "demo-directeur-app-dossier-express",
    "demo-directeur-app-referentiel-contact",
  ],
};

const DOCUMENT_DECOM_2028 = `# Polaris — Plan de décommissionnement 2028

## Contexte

13 applications du parc Polaris sont candidates à un retrait en 2028. 10 d'entre elles sont priorisées selon les économies possibles, la dette technologique et la faisabilité du retrait ; les 3 autres restent hors de ce cycle en raison de leurs dépendances critiques entre elles.

## Première vague — T2 2028

| Application | Coût annuel | Conditions |
|---|---|---|
| Vision | 320 k$ | Transférer les usages et archiver les historiques |
| ReportPlus | 210 k$ | Valider la reprise des rapports |
| DocBridge | 180 k$ | Transférer les archives et vérifier leur accès |

Ces trois applications représentent **710 k$ de coûts annuels**. Pour estimer les économies réelles, il faut isoler les coûts qui disparaîtraient effectivement, puis déduire les frais de transition.

Quatre conditions s'appliquent à chaque retrait : les usages sont repris, les données nécessaires sont conservées, les dépendances sont vérifiées et le responsable a validé la bascule.

## Préparation en parallèle — Money Manager

Money Manager (450 k$ de coûts annuels, 86 utilisateurs actifs) dépend encore de deux flux critiques :

- Flux de facturation client, utilisé par Dossier Express
- Flux de rapprochement comptable, utilisé par Référentiel Contact

Ces deux flux doivent être migrés et validés avant d'envisager le retrait de Money Manager.

## Équipes à mobiliser

- Reporting commercial — Vision
- Finance — ReportPlus
- Opérations — gestion documentaire — DocBridge
- Finance — flux critiques — Money Manager, Dossier Express, Référentiel Contact

## Points pouvant retarder chaque retrait

- **Vision** — confirmer avec les utilisateurs que la plateforme cible couvre bien leurs deux fonctions de reporting
- **ReportPlus** — validation de la reprise des rapports par les équipes finance
- **DocBridge** — vérification de l'accès aux archives transférées
- **Money Manager** — migration des deux flux critiques pas encore engagée

## Trajectoire prévisionnelle (à confirmer)

| Application | Période envisagée | Dépendances critiques identifiées |
|---|---|---|
| Suivi Agence | T3 2028 | Aucune |
| PlanifPro | T3 2028 | Aucune |
| Money Manager | T3 2028 | 2 flux critiques |
| BatchLink | T3 2028 | 3 traitements critiques |
| Référentiel Contact | T4 2028 | 1 synchronisation critique |
| Dossier Express | T4 2028 | 2 parcours critiques |
| Archive Services | T4 2028 | 1 service de consultation critique |

## Prochaines actions

- Lancer le retrait de Vision, ReportPlus et DocBridge au T2 2028
- Engager la migration des deux flux critiques de Money Manager
- Confirmer les responsables et les dates de chaque retrait avec les équipes propriétaires
`;

export const SCENARIO_DIRECTEUR = {
  id: "demo-directeur-scenario",
  version: 2,
  profileId: "directeur",
  title: "Planifier le décommissionnement des applications",
  roleLabel: "Directeur Polaris",
  personaRole: "Directeur · Polaris",
  roleContext: "Le directeur doit établir une trajectoire réaliste de retrait des applications pour 2028.",
  openingMode: "user_request",
  closingText:
    "Un parc de 13 candidats devient un plan précis : une première vague de 3 retraits, la migration de Money Manager préparée en parallèle, et une trajectoire prévisionnelle pour le reste du parc.",
  discoveryStepId: "seq-3",
  steps: [
    {
      id: "seq-1",
      label: "Identifier les candidats au retrait",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Flore, je prépare notre plan de décommissionnement pour 2028. Quelles applications pourrait-on retirer ?",
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais examiner leurs coûts, leur utilisation et leur dette technologique. Je vérifierai surtout ce qui dépend encore d'elles et si leurs fonctions peuvent être reprises ailleurs.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Analyse des coûts et des usages…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Vérification des dépendances…",
          sources: ["Inventaire applicatif Polaris 2028"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Recherche des solutions de remplacement…",
          sources: ["Méthodologie de scoring de décommissionnement"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai identifié **13 applications candidates à un retrait en 2028**.\n\nCertaines semblent relativement simples à retirer. D'autres demandent d'abord de migrer des données, des traitements ou des usages.",
          evidenceIds: ["demo-directeur-ev-inventaire"],
          contenu: { comportement: "diagnostiquer" },
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Prioriser les dix premiers",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Montre-moi les dix à traiter en priorité, avec les conditions à remplir.",
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "enrichissement" },
        {
          type: "message",
          speaker: "flore",
          text: "Voici l'ordre que je propose. Il tient compte des économies possibles, de la dette technologique et de la faisabilité du retrait.\n\nLes périodes restent à confirmer avec les équipes. Les montants représentent les coûts annuels actuels, pas encore les économies nettes.",
          evidenceIds: ["demo-directeur-ev-scoring"],
          contenu: { comportement: "recommander", tableau: TABLEAU_10_CANDIDATS, tableauNote: NOTE_UTILISATEURS },
          terminer: true,
        },
        { type: "observe", duree: 3000 },
      ],
    },
    {
      id: "seq-3",
      label: "Pourquoi Vision avant Money Manager",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Pourquoi Vision arrive en premier, alors que Money Manager nous coûte plus cher ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Parce que son retrait semble plus simple à réaliser. Vision a peu d'utilisateurs, une solution de remplacement est identifiée et je n'ai trouvé aucune dépendance critique dans les sources consultées.\n\nMoney Manager présente un potentiel d'économie plus élevé, mais deux flux critiques en dépendent encore. Il faut les migrer avant de retirer l'application.\n\nJe propose donc d'avancer sur Vision tout en préparant la migration de Money Manager.",
          evidenceIds: ["demo-directeur-ev-flux-money-manager"],
          contenu: { comportement: "expliquer", atlasScene: ATLAS_MONEY_MANAGER },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-4",
      label: "Les utilisateurs de Vision",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Et les 17 utilisateurs de Vision ? Est-ce qu'on sait ce qu'ils utilisent encore ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Les usages observés portent sur deux fonctions de reporting, également disponibles dans la plateforme cible.\n\nIl faut confirmer avec ces utilisateurs que la reprise couvre bien leurs besoins, transférer leurs accès et conserver les historiques nécessaires. Le faible nombre d'utilisateurs facilite la transition, mais ne suffit pas à justifier l'arrêt.",
          evidenceIds: ["demo-directeur-ev-inventaire"],
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-5",
      label: "La première vague",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "D'accord. Quelle première vague tu me proposes ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "**Vision, ReportPlus et DocBridge**, avec un objectif de retrait au deuxième trimestre 2028.\n\nCes trois applications représentent **710 k$ de coûts annuels**. Pour estimer les économies réelles, il faut isoler les coûts qui disparaîtraient effectivement, puis déduire les frais de transition.\n\nPour chaque retrait, je retiendrais quatre conditions : les usages sont repris, les données nécessaires sont conservées, les dépendances sont vérifiées et le responsable a validé la bascule.",
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-6",
      label: "Proposer le plan",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Ça me va. On prépare ces trois retraits et on lance en parallèle les travaux nécessaires pour Money Manager.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Veux-tu que je génère un **plan de décommissionnement 2028** sur cette base ?\n\nIl détaillera la première vague et la préparation de Money Manager, avec les prérequis, les jalons et les coûts potentiellement évitables. Les autres applications resteront dans une trajectoire prévisionnelle à confirmer.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-7",
      label: "Générer le plan de décommissionnement",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Ajoute les équipes à mobiliser et les points qui pourraient retarder chaque retrait.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je les intègre, avec les validations nécessaires avant chaque arrêt. Les dates proposées et les responsables encore à confirmer seront clairement indiqués.",
        },
        { type: "activity_start", id: "act-seq-7" },
        {
          type: "activity_step",
          activityId: "act-seq-7",
          label: "Construction du plan de décommissionnement…",
          sources: ["Méthodologie de scoring de décommissionnement"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-7",
          label: "Ajout des dépendances, des jalons et des validations…",
          sources: ["Cartographie des flux critiques de Money Manager"],
          duree: 1400,
        },
        { type: "upsert_result", resultId: "demo-directeur-work", phase: "final" },
        {
          type: "message",
          speaker: "flore",
          text: "Le plan est prêt. Il présente les trois premiers retraits et la préparation de Money Manager en parallèle, puis la trajectoire envisagée pour les autres applications.\n\nTu peux l'utiliser avec les équipes pour confirmer les responsabilités, les dates et les conditions de chaque arrêt.",
          evidenceIds: ["demo-directeur-ev-inventaire", "demo-directeur-ev-scoring", "demo-directeur-ev-flux-money-manager"],
          terminer: "act-seq-7",
          contenu: {
            comportement: "conclure",
            documentCanvas: "Polaris — Plan de décommissionnement 2028",
            documentTexte: DOCUMENT_DECOM_2028,
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
