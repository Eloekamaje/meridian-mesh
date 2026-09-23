// Parcours Analyste support TI — anticiper une dégradation avant les premiers impacts utilisateurs.
// Joué dans les vraies pages : Travail (fil, résultats, canvas). Beats : message → activity →
// upsert_result / show_surface → observe. Particularité de ce parcours : c'est FLORE qui ouvre la
// conversation, sans question préalable du visiteur (openingMode différent de "user_request" —
// le premier beat n'est donc pas une demande tapée dans le composer, mais un message qui s'écrit
// tout seul). Chaque réplique du visiteur (Support TI) se mérite toujours un clic, comme partout
// ailleurs — seule l'ouverture change.

// Ce que l'Atlas met en évidence au tour 2 : la chaîne et ses applications directement liées
// (« leurs liens avec les applications concernées »)
const ATLAS_CHAINE_APPLICATIONS = {
  titre: "La chaîne d'ouverture et ses applications",
  cibles: [
    "demo-supportti-chaine-ouverture",
    "demo-supportti-app-portail-ouverture",
    "demo-supportti-app-service-identite",
  ],
};

// Ce que l'Atlas met en évidence au tour 6 : la zone où la dégradation est OBSERVÉE (accentuée) se
// distingue des systèmes en aval SUSCEPTIBLES d'être affectés (présents dans la scène, mais pas
// accentués — exactement la distinction demandée)
const ATLAS_ZONE_VS_AVAL = {
  titre: "Zone observée et systèmes exposés en aval",
  cibles: [
    "demo-supportti-chaine-ouverture",
    "demo-supportti-app-portail-ouverture",
    "demo-supportti-app-service-identite",
    "demo-supportti-app-gestion-client",
    "demo-supportti-app-prevention-fraude",
  ],
  accents: [
    "demo-supportti-chaine-ouverture",
    "demo-supportti-app-portail-ouverture",
    "demo-supportti-app-service-identite",
  ],
};

const TENDANCES_CHAINE = [
  { libelle: "Délai de traitement", valeur: "En hausse", direction: "hausse", detail: "Depuis 3 jours", alerte: true },
  { libelle: "File de messages en attente", valeur: "En croissance", direction: "hausse", detail: "Depuis 3 jours", alerte: true },
  { libelle: "Débit nocturne de rattrapage", valeur: "En baisse", direction: "baisse", detail: "Depuis 3 jours", alerte: true },
];

const DOCUMENT_INVESTIGATION = `# Polaris — Investigation préventive de la chaîne d'ouverture de compte

## Avertissement

Aucun impact utilisateur n'est confirmé à ce stade. Le lien avec le déploiement Polaris reste à vérifier. Ce document sépare les faits observés, les projections et les hypothèses.

## Chronologie

- Il y a 3 jours — début de la dégradation progressive des trois indicateurs suivis
- Peu avant — déploiement d'une évolution Polaris modifiant les flux événementiels
- Aujourd'hui, 8 h 13 — Flore signale la situation, sans alerte ni appel utilisateur préalable

## Signaux observés (faits)

- Délai de traitement des événements : en hausse depuis 3 jours
- File de messages en attente : en croissance depuis 3 jours
- Débit des traitements nocturnes : en baisse depuis 3 jours
- Aucune des alertes configurées sur ces indicateurs ne s'est déclenchée

## Applications concernées

- Chaîne événementielle d'ouverture de compte — zone où la dégradation est observée
- Portail Ouverture de compte et Service Identité — chaîne et dépendances directes
- Gestion client et Prévention de la fraude — systèmes en aval, exposés à un retard de réception, sans impact confirmé

## Projection — à surveiller, pas un incident confirmé

Si la tendance et les volumes se maintiennent, le retard pourrait ne plus être résorbé la nuit et les premières conséquences pourraient apparaître demain matin, retardant la disponibilité des informations après une ouverture de compte et leur transmission aux systèmes en aval.

## Hypothèses

- **Principale** — une évolution Polaris déployée juste avant le début de la dégradation a modifié les flux événementiels et pourrait avoir augmenté le travail effectué pour chaque ouverture. Le rapprochement temporel est cohérent mais ne prouve pas la cause.
- **À vérifier en parallèle** — un éventuel ralentissement d'un service appelé par les traitements, et une hausse des tentatives de reprise.

## Niveau de confiance

- Constat de dégradation : **élevé** — plusieurs signaux indépendants convergent sur trois jours.
- Lien avec le déploiement : **modéré** — à confirmer par comparaison des traces avant et après déploiement.

## Vérifications recommandées

1. Comparer les traitements avant et après le déploiement, pour repérer une hausse du nombre d'événements ou du temps de traitement.
2. Examiner les messages en attente et les reprises, pour voir si certains événements concentrent le retard.
3. Vérifier les services appelés et la capacité de traitement, pour localiser le ralentissement.

## Critères d'escalade

- Le rythme d'accumulation du retard s'accélère
- Une augmentation temporaire de capacité est envisagée, à condition que le blocage ne soit pas en aval
- L'évolution Polaris est confirmée comme cause : à examiner avec son responsable pour une correction ou un retour arrière

## Équipes concernées

Ouverture de compte, Gestion client, Prévention de la fraude.
`;

export const SCENARIO_SUPPORTTI = {
  id: "demo-supportti-scenario",
  version: 1,
  profileId: "support-ti",
  title: "Anticiper une dégradation avant les premiers impacts utilisateurs",
  roleLabel: "Analyste support TI",
  personaRole: "Analyste support TI · Polaris",
  roleContext: "Il est 8 h 13. L'Atlas Méridian est calme : aucun incident n'est déclaré et aucun appel utilisateur n'a été reçu. Flore prend l'initiative de signaler une situation à examiner.",
  // Ouverture par notification : le visiteur est sur Actualités, en train de lire, quand le signal
  // apparaît soudainement en haut à droite — il clique « Voir » pour ouvrir le nouveau travail, où
  // Flore commence alors à écrire (voir BarreKiosque.jsx::SurcouchesKiosque)
  openingMode: "notification",
  notification: {
    titre: "Flore · Nouveau signal",
    texte: "Une évolution inhabituelle a été repérée sur la chaîne d'ouverture de compte.",
  },
  closingText:
    "Une dégradation invisible aux seuils d'alerte devient une fiche d'investigation claire : les signaux observés, une hypothèse à confirmer, et les vérifications à mener avant toute escalade.",
  discoveryStepId: "seq-2",
  steps: [
    {
      id: "seq-1",
      label: "Flore signale une dégradation progressive",
      beats: [
        { type: "upsert_result", resultId: "demo-supportti-work", phase: "naissance" },
        { type: "show_surface", surface: "travail" },
        {
          type: "message",
          speaker: "flore",
          text: "Bonjour. J'ai repéré une évolution inhabituelle sur la chaîne d'ouverture de compte suivie dans Polaris. Aucun impact utilisateur n'est confirmé, mais plusieurs signaux indiquent une dégradation progressive.",
        },
        {
          type: "message",
          speaker: "persona",
          text: "Pourtant, nous n'avons aucune alerte et aucun appel. Qu'est-ce que tu as détecté ?",
        },
        { type: "upsert_result", resultId: "demo-supportti-work", phase: "diagnostic" },
        {
          type: "message",
          speaker: "flore",
          text: "Depuis trois jours, les événements prennent plus de temps à être traités, la file de messages grossit et les traitements nocturnes absorbent moins de retard.\n\nPris séparément, ces indicateurs restent sous les seuils d'alerte configurés. Ensemble, ils montrent que la chaîne perd progressivement sa capacité à rattraper les événements en attente.",
          evidenceIds: ["demo-supportti-ev-metriques"],
          contenu: { comportement: "diagnostiquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-2",
      label: "Aucune alerte ne s'est déclenchée",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Donc les outils de surveillance ne déclenchent rien ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Aucune des alertes configurées sur ces indicateurs ne s'est déclenchée.\n\nCe qui attire mon attention, c'est leur évolution simultanée et le fait qu'ils concernent la même chaîne de traitement.",
          evidenceIds: ["demo-supportti-ev-alertes"],
          contenu: { comportement: "diagnostiquer", tendances: TENDANCES_CHAINE, atlasScene: ATLAS_CHAINE_APPLICATIONS },
          terminer: true,
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-3",
      label: "Ce qui pourrait se passer",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Qu'est-ce qui pourrait se passer si ça continue ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Le retard pourrait s'accumuler pendant la journée et ne plus être résorbé cette nuit. Si la tendance et les volumes se maintiennent, les premières conséquences pourraient apparaître demain matin.\n\nCela pourrait retarder la disponibilité des informations après une ouverture de compte et leur transmission aux systèmes en aval. C'est une projection à surveiller, pas un incident confirmé.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-4",
      label: "Une hypothèse sur l'origine",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Tu as une hypothèse sur l'origine ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "L'hypothèse principale concerne une évolution Polaris déployée juste avant le début de la dégradation. Elle a modifié les flux événementiels et pourrait avoir augmenté le travail effectué pour chaque ouverture.\n\nLe rapprochement temporel est cohérent, mais ne prouve pas la cause. Il faut aussi vérifier un éventuel ralentissement d'un service appelé par les traitements et une hausse des tentatives de reprise.",
          evidenceIds: ["demo-supportti-ev-deploiement"],
          contenu: { comportement: "diagnostiquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-5",
      label: "Niveau de confiance",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Quel est ton niveau de confiance ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "J'ai une confiance élevée dans le constat de dégradation : plusieurs signaux indépendants convergent sur trois jours.\n\nMa confiance est plus modérée sur le lien avec le déploiement. Pour le confirmer, il faut comparer les traces avant et après la mise en production et examiner les traitements qui ralentissent.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-6",
      label: "Équipes concernées",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Quelles équipes seraient concernées ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "**Ouverture de compte, Gestion client et Prévention de la fraude.**\n\nLa dégradation est observée sur la chaîne événementielle d'ouverture. Les autres systèmes sont exposés à un retard de réception des informations, sans impact confirmé pour le moment.",
          evidenceIds: ["demo-supportti-ev-services-appeles"],
          contenu: { comportement: "recommander", atlasScene: ATLAS_ZONE_VS_AVAL },
          terminer: true,
        },
        {
          type: "message",
          speaker: "flore",
          text: "Veux-tu que je te propose les premières vérifications et les mesures à envisager selon les résultats ?",
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-7",
      label: "Les premières vérifications",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Par quoi commencerais-tu ?",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je commencerais par trois vérifications :\n\n1. **Comparer les traitements avant et après le déploiement**, pour repérer une hausse du nombre d'événements ou du temps de traitement.\n2. **Examiner les messages en attente et les reprises**, pour voir si certains événements concentrent le retard.\n3. **Vérifier les services appelés et la capacité de traitement**, pour localiser le ralentissement.\n\nEn parallèle, je recommande de suivre le rythme d'accumulation du retard. S'il s'accélère, l'équipe pourra évaluer une augmentation temporaire de capacité, à condition que le blocage ne soit pas en aval.\n\nSi l'évolution Polaris est confirmée comme cause, il faudra examiner avec son responsable les possibilités de correction ou de retour arrière.",
          contenu: { comportement: "recommander" },
          terminer: true,
        },
        { type: "observe", duree: 2500 },
      ],
    },
    {
      id: "seq-8",
      label: "Proposer la fiche d'investigation",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "D'accord. Il faut qu'on lance l'investigation avec les équipes concernées.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Veux-tu que je génère une **fiche d'investigation préventive** ? Elle réunira la chronologie, les signaux observés, les applications concernées, les hypothèses et les vérifications recommandées.",
          contenu: { comportement: "expliquer" },
          terminer: true,
        },
        { type: "observe", duree: 2000 },
      ],
    },
    {
      id: "seq-9",
      label: "Générer la fiche d'investigation",
      beats: [
        {
          type: "message",
          speaker: "persona",
          text: "Oui. Précise bien qu'aucun impact utilisateur n'est confirmé et que le lien avec le déploiement reste à vérifier.",
        },
        {
          type: "message",
          speaker: "flore",
          text: "Je l'indique explicitement. Je séparerai les faits observés, les projections et les hypothèses.",
        },
        { type: "activity_start", id: "act-seq-9" },
        {
          type: "activity_step",
          activityId: "act-seq-9",
          label: "Consolidation de la chronologie et des signaux…",
          sources: ["Métriques de traitement de la chaîne d'ouverture de compte"],
          duree: 1400,
        },
        {
          type: "activity_step",
          activityId: "act-seq-9",
          label: "Préparation de la fiche d'investigation…",
          sources: [],
          duree: 1400,
        },
        { type: "upsert_result", resultId: "demo-supportti-work", phase: "final" },
        {
          type: "message",
          speaker: "flore",
          text: "La fiche est prête. Elle contient les éléments nécessaires pour démarrer l'investigation, ainsi que les critères qui justifieraient une escalade.",
          evidenceIds: ["demo-supportti-ev-metriques", "demo-supportti-ev-alertes", "demo-supportti-ev-deploiement", "demo-supportti-ev-services-appeles"],
          terminer: "act-seq-9",
          contenu: {
            comportement: "conclure",
            documentCanvas: "Polaris — Investigation préventive de la chaîne d'ouverture de compte",
            documentTexte: DOCUMENT_INVESTIGATION,
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
