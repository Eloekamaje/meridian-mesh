// Parcours VP Transformation — décider quelles initiatives Polaris financer, lesquelles arrêter.
// Joué dans les vraies pages : Nouveau travail (demande + première réponse) puis page Travail (fil,
// résultats, canvas). Beats : message → activity → upsert_result / show_surface → observe. Même
// principe partout : Flore annonce en une phrase, une ligne d'activité évolue en place pendant le
// travail, puis UNE réponse porte le constat — jamais la même conclusion redite deux fois. Une
// question simple (clarification, chiffre déjà connu) reçoit une réponse directe, sans nouvelle
// activité : `terminer: true` marque alors la réponse comme complète sans fermer d'activité réelle.

const A_PRIVILEGIER = [
  { nom: "Suivi des demandes clients", domaine: "Client" },
  { nom: "Simplification du poste conseiller", domaine: "Distribution" },
  { nom: "Automatisation des contrôles de dossier", domaine: "Opérations" },
];

const A_REEXAMINER_APERCU = [
  { nom: "Portail fournisseurs 2.0", domaine: "Achats" },
  { nom: "Automatisation des rapports régionaux", domaine: "Finance" },
  { nom: "Optimisation du contrôle qualité interne", domaine: "Opérations" },
  { nom: "+ 9 autres initiatives", domaine: "Opérations" },
];

const GROUPE_SANS_IMPACT = [
  { nom: "Portail fournisseurs 2.0", domaine: "Achats" },
  { nom: "Automatisation des rapports régionaux", domaine: "Finance" },
  { nom: "Refonte de l'intranet RH", domaine: "RH" },
  { nom: "Suivi interne des budgets de projet", domaine: "Finance" },
  { nom: "Outil de gestion des accès internes", domaine: "TI" },
  { nom: "Modernisation du tableau de bord managérial", domaine: "Opérations" },
  { nom: "Plateforme de gestion documentaire interne", domaine: "Opérations" },
];

const GROUPE_PROCESSUS_INTERNE = [
  { nom: "Optimisation du contrôle qualité interne", domaine: "Opérations" },
  { nom: "Système de gestion des fournisseurs stratégiques", domaine: "Achats" },
  { nom: "Refonte du processus d'approbation budgétaire", domaine: "Finance" },
];

const GROUPE_CAPACITE_ATTENDUE = [
  { nom: "Ancien système de facturation régionale", domaine: "Finance" },
  { nom: "Registre des contrats papier numérisé", domaine: "Opérations" },
];

const DOCUMENT_ARBITRAGE = `# Polaris — Proposition d'arbitrage du portefeuille
**Préparé par Flore · VP Transformation Polaris**

---

## 1. Contexte

Le portefeuille Polaris compte près de 400 initiatives. Cette note propose un arbitrage : les initiatives à privilégier, celles à réexaminer, et les décisions qui peuvent être prises dès maintenant.

---

## 2. Initiatives à privilégier

Trois initiatives ressortent directement des objectifs de Polaris et partagent un même besoin sous-jacent — un état fiable et à jour du dossier :

- **Suivi des demandes clients**
- **Simplification du poste conseiller**
- **Automatisation des contrôles de dossier**

**Décision proposée (peut être prise maintenant) :** financer ensemble ce que ces trois initiatives ont en commun, sans changer leurs objectifs propres. Cela évite que trois équipes reconstruisent séparément la même capacité.

---

## 3. Initiatives à réexaminer

12 initiatives contribuent peu aux objectifs actuels, présentent des coûts élevés par rapport aux bénéfices attendus, ou recoupent des travaux déjà financés. Leur arrêt éviterait jusqu'à **18 M$ de dépenses prévues d'ici fin 2028** — un montant brut, avant déduction des engagements contractuels, des frais d'arrêt et des remplacements éventuels.

| Groupe | Nombre | Situation | Recommandation |
| --- | --- | --- | --- |
| A | 7 | Aucun impact client ni dépendance bloquante | Soumettre l'arrêt au comité dès que les impacts sont confirmés |
| B | 3 | Adaptation de processus internes nécessaire | Préparer la transition avec les équipes concernées |
| C | 2 | Fournissent une capacité attendue par d'autres projets | Maintenir jusqu'à la disponibilité du remplacement |

---

## 4. Ce qui reste à valider

- Confirmer les impacts et les engagements des 7 initiatives du groupe A avec leurs responsables
- Préparer la transition des 3 initiatives du groupe B
- Suivre la disponibilité des remplacements avant d'arrêter les 2 initiatives du groupe C
- Chiffrer l'économie nette après déduction des engagements contractuels et des frais d'arrêt

---

## 5. Prochaines actions

1. Soumettre l'arrêt du groupe A au comité, une fois les impacts confirmés
2. Engager la transition du groupe B avec ses équipes
3. Conditionner l'arrêt du groupe C à la disponibilité de son remplacement
4. Protéger le financement de la capacité commune aux 3 initiatives prioritaires
`;

export const SCENARIO_VP = {
  id: "demo-vp-scenario",
  version: 3,
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
          contenu: {
            comportement: "diagnostiquer",
            selections: [
              { titre: "À privilégier", items: A_PRIVILEGIER },
              { titre: "À réexaminer (12 au total)", items: A_REEXAMINER_APERCU },
            ],
            atlasScene: {
              titre: "Capacité partagée entre les trois initiatives",
              cibles: ["demo-vp-ini-suivi-demandes", "demo-vp-ini-poste-conseiller", "demo-vp-ini-controles-dossier", "demo-vp-cap-etat-dossier"],
            },
          },
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
          contenu: {
            comportement: "recommander",
            selections: [
              { titre: "7 — Aucun impact ni dépendance", items: GROUPE_SANS_IMPACT },
              { titre: "3 — Adaptation de processus", items: GROUPE_PROCESSUS_INTERNE },
              { titre: "2 — Capacité attendue ailleurs", items: GROUPE_CAPACITE_ATTENDUE },
            ],
          },
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
        { type: "upsert_result", resultId: "demo-vp-work", phase: "final" },
        {
          type: "message",
          speaker: "flore",
          text: "La note est prête. Tu trouveras d'abord les arbitrages proposés, puis les impacts financiers, les risques et les validations nécessaires avant décision.",
          evidenceIds: ["demo-vp-ev-portefeuille", "demo-vp-ev-impact-client"],
          terminer: "act-seq-7",
          contenu: {
            comportement: "conclure",
            documentCanvas: "Polaris — Proposition d'arbitrage du portefeuille",
            documentTexte: DOCUMENT_ARBITRAGE,
          },
        },
        { type: "observe", duree: 5000 },
      ],
    },
  ],
};
