// Parcours Analyste d'affaires — comprendre ChequeFlow avant de la remplacer. Joué dans les vraies
// pages : Nouveau travail (demande + première réponse) puis page Travail (fil, résultats, canvas).
// Beats : message → activity → upsert_result / show_surface → observe. Même principe partout : Flore
// annonce en une phrase, une ligne d'activité évolue en place pendant le travail, puis UNE réponse
// porte le constat — jamais la même conclusion redite deux fois.

const TABLEAU_UTILISATEURS = {
  colonnes: ["Secteur", "Utilisateurs actifs", "Usage principal"],
  lignes: [
    ["**Opérations de paiements**", "8", "Traiter les écarts et les exceptions"],
    ["**Soutien aux succursales**", "4", "Rechercher les opérations et suivre leur résolution"],
    ["**Contrôle et conformité**", "2", "Vérifier les traitements et retrouver les justificatifs"],
  ],
};

// Ce que l'Atlas met en évidence au tour 3 : ChequeFlow relié aux 3 secteurs et aux 2 chaînes de
// production des rapports (voir fixturesAnalyste.js::RELATIONS)
const ATLAS_CHEQUEFLOW = {
  titre: "ChequeFlow, ses secteurs et ses rapports",
  cibles: [
    "demo-analyste-app-chequeflow",
    "demo-analyste-secteur-operations-paiements",
    "demo-analyste-secteur-soutien-succursales",
    "demo-analyste-secteur-controle-conformite",
    "demo-analyste-rapport-conformite",
    "demo-analyste-rapport-ecarts",
  ],
};

const DOCUMENT_CADRAGE = `# Polaris — Cadrage du remplacement de ChequeFlow

## Contexte

ChequeFlow a été créée en 2012 pour automatiser le traitement des chèques et réduire les rapprochements manuels. Elle assure trois fonctions, mais les usages observés se concentrent aujourd'hui sur une seule d'entre elles.

## Périmètre à préserver

- Le rapprochement des opérations et le traitement des écarts
- La gestion des exceptions
- L'historique des décisions prises sur chaque écart
- Les données utilisées par les deux rapports réglementaires
- Les droits d'accès et la traçabilité (qui a traité un écart, et sur quelle base)

## Fonctions candidates au retrait

| Fonction | Constat | Condition avant retrait |
|---|---|---|
| Préparation des lots de traitement | Progressivement reprise par la plateforme de paiements | Confirmer que la plateforme couvre les derniers cas particuliers |
| Production d'états de suivi locaux | Largement remplacée par des rapports centralisés | Vérifier qu'aucun état local n'est encore nécessaire à une équipe |

## Utilisateurs concernés

| Secteur | Utilisateurs actifs | Usage principal |
|---|---|---|
| Opérations de paiements | 8 | Traiter les écarts et les exceptions |
| Soutien aux succursales | 4 | Rechercher les opérations et suivre leur résolution |
| Contrôle et conformité | 2 | Vérifier les traitements et retrouver les justificatifs |

## Dépendances à reprendre

Le rapprochement des opérations alimente deux rapports réglementaires par extraction automatisée : le rapport de conformité des chèques et le rapport de suivi des écarts réglementaires. Son importance dépasse donc les seuls utilisateurs qui se connectent à l'application.

## Questions à valider en atelier

- **Opérations de paiements** — le remplacement couvre-t-il tous les cas d'écarts et d'exceptions actuels ?
- **Soutien aux succursales** — la recherche d'opérations et le suivi de résolution restent-ils aussi rapides ?
- **Contrôle et conformité** — la traçabilité des justificatifs est-elle intégralement préservée ?

## Sources

Ce cadrage s'appuie sur l'historique et les décisions d'architecture de ChequeFlow, l'analyse des demandes d'évolution, des incidents et du code, l'étude des usages actuels, et le rapprochement des accès et des traitements automatisés.
`;

export const SCENARIO_ANALYSTE = {
  id: "demo-analyste-scenario",
  version: 1,
  profileId: "analyste",
  title: "Comprendre une application avant de la remplacer",
  roleLabel: "Analyste d'affaires",
  personaRole: "Analyste d'affaires · Polaris",
  roleContext: "L'analyste doit déterminer quels besoins de ChequeFlow restent à couvrir avant de définir le périmètre de son remplacement.",
  openingMode: "user_request",
  closingText:
    "Une application historique devient un périmètre clair : ce qu'il faut reprendre, ce qui est candidat au retrait, et les questions encore à valider avec chaque secteur.",
  discoveryStepId: "seq-3",
  steps: [
    {
      id: "seq-1",
      label: "Comprendre l'origine et l'usage de ChequeFlow",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Flore, Polaris prévoit de remplacer ChequeFlow. Avant de définir le périmètre, j'aimerais comprendre pourquoi cette application a été créée et à quoi elle sert encore aujourd'hui.",
        },
        { type: "upsert_result", resultId: "demo-analyste-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Je vais rapprocher son historique, les demandes d'évolution et les usages actuels. Cela permettra de distinguer sa mission d'origine des fonctions encore nécessaires.",
        },
        { type: "activity_start", id: "act-seq-1" },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Lecture des documents et des décisions d'architecture…",
          sources: ["Historique et décisions d'architecture de ChequeFlow"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Analyse des demandes, des incidents et du code…",
          sources: ["Demandes d'évolution, incidents et code de ChequeFlow"],
          duree: 1500,
        },
        {
          type: "activity_step",
          activityId: "act-seq-1",
          label: "Vérification des usages récents…",
          sources: ["Usages actuels de ChequeFlow"],
          duree: 1500,
        },
        { type: "upsert_result", resultId: "demo-analyste-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "ChequeFlow a été créée en **2012** pour automatiser le traitement des chèques et réduire les rapprochements manuels.\n\nElle assure principalement trois fonctions :\n\n1. **Rapprocher les opérations et traiter les écarts**, pour repérer les chèques qui nécessitent une intervention.\n2. **Préparer les lots de traitement**, une fonction progressivement reprise par la plateforme de paiements.\n3. **Produire des états de suivi locaux**, désormais largement remplacés par des rapports centralisés.\n\nLes usages observés se concentrent aujourd'hui sur la première fonction. Les deux autres sont très peu utilisées sur la période consultée.",
          evidenceIds: ["demo-analyste-ev-historique", "demo-analyste-ev-demandes-incidents", "demo-analyste-ev-usages"],
          contenu: { comportement: "diagnostiquer" },
          terminer: "act-seq-1",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-2",
      label: "Les fonctions 2 et 3 sont-elles abandonnables ?",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Est-ce que ça veut dire qu'on peut abandonner les fonctions 2 et 3 dans le remplacement ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Elles semblent candidates à un retrait, mais je vérifierais d'abord les usages ponctuels, notamment ceux liés aux clôtures ou aux traitements exceptionnels.\n\nPour la fonction 2, il faut confirmer que la plateforme de paiements couvre les derniers cas particuliers. Pour la fonction 3, il faut vérifier qu'aucun état local n'est encore nécessaire à une équipe.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-3",
      label: "Qui utilise encore la première fonction",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Et la première fonction, qui l'utilise encore ?",
        },
        { type: "activity_start", id: "act-seq-3" },
        {
          type: "activity_step",
          activityId: "act-seq-3",
          label: "Rapprochement des accès, des activités et des traitements automatisés…",
          sources: ["Rapprochement des accès, des activités et des traitements automatisés"],
          duree: 1600,
        },
        { type: "upsert_result", resultId: "demo-analyste-work", phase: "enrichissement" },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai identifié **14 utilisateurs actifs dans trois secteurs**, détaillés ci-dessous.\n\nLa fonction alimente aussi **deux rapports réglementaires** par des extractions automatisées. Son importance dépasse donc les seuls utilisateurs qui se connectent à l'application.",
          evidenceIds: ["demo-analyste-ev-acces"],
          contenu: { comportement: "recommander", tableau: TABLEAU_UTILISATEURS, atlasScene: ATLAS_CHEQUEFLOW },
          terminer: "act-seq-3",
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-4",
      label: "Ce qu'il faut absolument reprendre",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "C'est justement ce que je voulais éviter : remplacer l'écran et découvrir ensuite qu'on a oublié des traitements derrière. Qu'est-ce qu'il faut absolument reprendre ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Le rapprochement des opérations, la gestion des exceptions, l'historique des décisions et les données utilisées par les deux rapports.\n\nIl faudra aussi préserver les droits d'accès et la traçabilité permettant de retrouver qui a traité un écart et sur quelle base.\n\nJe recommande donc un remplacement centré sur cette fonction, puis une validation explicite du retrait des deux autres.",
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-5",
      label: "Proposer le dossier de cadrage",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Ça nous donnerait un périmètre plus ciblé. Il faut que je puisse le faire valider par les secteurs.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Veux-tu que je prépare un **dossier de cadrage du remplacement de ChequeFlow** ?\n\nIl présentera les besoins à conserver, les fonctions candidates au retrait, les utilisateurs concernés et les dépendances à reprendre. J'ajouterai les questions à valider avec chaque secteur.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-6",
      label: "Générer le dossier de cadrage",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Mets aussi les éléments qui justifient chaque conclusion, pour qu'on puisse les discuter en atelier.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je prépare le dossier avec les sources associées et une liste des validations attendues.",
        },
        { type: "activity_start", id: "act-seq-6" },
        {
          type: "activity_step",
          activityId: "act-seq-6",
          label: "Consolidation des besoins encore actifs…",
          sources: ["Usages actuels de ChequeFlow"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-6",
          label: "Identification des dépendances à reprendre…",
          sources: ["Rapprochement des accès, des activités et des traitements automatisés"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-6",
          label: "Préparation du dossier de cadrage…",
          sources: [],
          duree: 300,
        },
        { type: "upsert_result", resultId: "demo-analyste-work", phase: "final" },
        {
          type: "message",
          speaker: "flore",
          text: "Le dossier est prêt. Il distingue le périmètre à préserver, les retraits possibles et les points à confirmer en atelier.",
          evidenceIds: ["demo-analyste-ev-historique", "demo-analyste-ev-demandes-incidents", "demo-analyste-ev-usages", "demo-analyste-ev-acces"],
          terminer: "act-seq-6",
          contenu: {
            comportement: "conclure",
            documentCanvas: "Polaris — Cadrage du remplacement de ChequeFlow",
            documentTexte: DOCUMENT_CADRAGE,
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
