// Logique pure du panneau d'actions de la boucle canonique : quelles transitions sont
// proposées selon le type et le statut, quels champs saisir, et quel corps envoyer.
// Aucun composant ni appel réseau ici : les mêmes règles sont testables sans DOM.

const STATUTS_DECISION_TRANCHEE = new Set([
  "DECIDED", "DECIDEE", "TRANCHEE", "APPROVED", "APPROUVEE",
]);
const STATUTS_DECISION_REJETEE = new Set([
  "REJECTED", "REJETEE", "REFUSEE", "ABANDONNEE",
]);
const STATUTS_INVESTIGATION_FERMES = new Set([
  "CLOSED", "CLOSE", "CLOTUREE", "FERMEE", "ARCHIVED", "ARCHIVEE",
]);
const STATUTS_INITIATIVE_ANNULEE = new Set([
  "CANCELLED", "ANNULEE", "ABANDONED", "ABANDONNEE",
]);
const STATUTS_EXPRESSION_QUALIFIABLES = new Set(["PROPOSED", "CONFIRMED"]);

export const TRANSITIONS_OPPORTUNITE = Object.freeze({
  DETECTED: Object.freeze(["MATURING", "QUALIFIED", "REJECTED", "DORMANT"]),
  MATURING: Object.freeze(["QUALIFIED", "REJECTED", "DORMANT"]),
  QUALIFIED: Object.freeze(["INVESTIGATING", "SCENARIOS_AVAILABLE", "REJECTED", "DORMANT"]),
  INVESTIGATING: Object.freeze(["SCENARIOS_AVAILABLE", "DECIDED", "REJECTED", "DORMANT"]),
  SCENARIOS_AVAILABLE: Object.freeze(["DECIDED", "REJECTED", "DORMANT"]),
  DECIDED: Object.freeze(["INITIATED", "REJECTED", "DORMANT"]),
  INITIATED: Object.freeze(["MEASURED", "REJECTED"]),
  MEASURED: Object.freeze(["LEARNED"]),
  LEARNED: Object.freeze([]),
  REJECTED: Object.freeze([]),
  DORMANT: Object.freeze(["MATURING", "REJECTED"]),
});
export const TRANSITIONS_RISQUE = TRANSITIONS_OPPORTUNITE;

export function statutsSuivants(type, statut) {
  const typeNormalise = texte(type).trim().toUpperCase();
  const transitions = typeNormalise === "RISK"
    ? TRANSITIONS_RISQUE
    : typeNormalise === "OPPORTUNITY" ? TRANSITIONS_OPPORTUNITE : null;
  if (!transitions) return [];
  return [...(transitions[statutObjet({ statut })] || [])];
}

const TYPES_EXPRESSION = [
  "OPPORTUNITE", "RISQUE", "PLAINTE", "BESOIN", "IDEE", "ANOMALIE", "DERIVE",
  "CONTRADICTION", "CHANGEMENT", "SIMPLIFICATION", "DUPLICATION", "COMPORTEMENT",
];

const CHAMPS_CREER_EXPRESSION = [
  {
    nom: "formulation",
    label: "Formulation",
    type: "textarea",
    requis: true,
    rows: 3,
    maxLength: 10000,
    placeholder: "Ce que nous formulons de ce phénomène, avec nos mots et nos doutes…",
    aide: "La lecture datée d'une situation, distincte d'une hypothèse ou d'une décision.",
  },
  {
    nom: "type_expression",
    label: "Type d'expression",
    type: "select",
    options: TYPES_EXPRESSION,
  },
  {
    nom: "canal",
    label: "Canal (optionnel)",
    type: "text",
    maxLength: 200,
    placeholder: "entretien, atelier, observation terrain…",
  },
  {
    nom: "auteur",
    label: "Auteur (optionnel)",
    type: "text",
    maxLength: 200,
    placeholder: "Alice Martin",
  },
  {
    nom: "inconnues",
    label: "Inconnues (une par ligne ou séparées par une virgule, optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "volume réel\ncharge de fin de mois",
  },
  {
    nom: "confiance",
    label: "Confiance (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.7",
  },
];

const CHAMPS_QUALIFIER_OBJET = [
  {
    nom: "titre",
    label: "Titre",
    type: "text",
    requis: true,
    maxLength: 500,
    placeholder: "Automatiser la ressaisie",
    aide: "Un titre qui rend l'objet reconnaissable dans la boucle.",
  },
  {
    nom: "description",
    label: "Description (optionnel)",
    type: "textarea",
    rows: 2,
    maxLength: 10000,
    placeholder: "Ce que cela change, pour qui et à quelles conditions…",
  },
  {
    nom: "valeur_potentielle",
    label: "Valeur potentielle (optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "12000",
  },
  {
    nom: "probabilite",
    label: "Probabilité (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.7",
  },
  {
    nom: "impact",
    label: "Impact (optionnel)",
    type: "textarea",
    rows: 2,
    maxLength: 2000,
    placeholder: "Deux ETP libérés, arrêt des paiements…",
  },
  {
    nom: "horizon",
    label: "Horizon (optionnel)",
    type: "text",
    maxLength: 200,
    placeholder: "90 jours, 6 mois…",
  },
  {
    nom: "criteres",
    label: "Critères (un par ligne ou séparés par une virgule, optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "faisable\nmesurable",
  },
  {
    nom: "preuves",
    label: "Preuves (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "preuve-1, preuve-2",
  },
  {
    nom: "confiance",
    label: "Confiance (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.6",
  },
];

const CHAMPS_QUALIFIER_OPPORTUNITE = CHAMPS_QUALIFIER_OBJET;
const CHAMPS_QUALIFIER_RISQUE = CHAMPS_QUALIFIER_OBJET;

const CHAMPS_CHANGER_STATUT = [
  {
    nom: "statut",
    label: "Nouveau statut",
    type: "select",
    requis: true,
    options: [],
  },
  {
    nom: "motif",
    label: "Motif (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Pourquoi ce changement, et à quelles conditions il tient…",
  },
  {
    nom: "preuves",
    label: "Preuves (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "preuve-1, preuve-2",
  },
];

const CHAMPS_CREER_SCENARIO = [
  {
    nom: "titre",
    label: "Titre du scénario",
    type: "text",
    requis: true,
    maxLength: 500,
    placeholder: "Automatiser la pièce",
    aide: "Une option d'action comparable, rattachée à l'investigation ou à la décision.",
  },
  {
    nom: "description",
    label: "Description (optionnel)",
    type: "textarea",
    rows: 2,
    maxLength: 10000,
    placeholder: "Ce que ce scénario change, pour qui et à quelles conditions…",
  },
  {
    nom: "hypothesis_ids",
    label: "Hypothèses liées (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "hyp-1, hyp-2",
  },
  {
    nom: "actions",
    label: "Actions (une par ligne ou séparées par une virgule, optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Automatiser\nContrôler",
  },
  {
    nom: "valeur_estimee",
    label: "Valeur estimée (optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "12000",
  },
  {
    nom: "cout_estime",
    label: "Coût estimé (optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "4500",
  },
  {
    nom: "delai_jours",
    label: "Délai en jours (optionnel)",
    type: "text",
    inputMode: "numeric",
    placeholder: "30",
  },
  {
    nom: "risque",
    label: "Risque (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.2",
  },
  {
    nom: "complexite",
    label: "Complexité (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.4",
  },
  {
    nom: "confiance",
    label: "Confiance (0 à 1, optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "0.7",
  },
  {
    nom: "dependances",
    label: "Dépendances (séparées par une virgule, optionnel)",
    type: "text",
    placeholder: "api-paiement, equipe-cartes",
  },
  {
    nom: "impacts",
    label: "Impacts clé=valeur (séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "client=baisse, risque=mitige",
  },
  {
    nom: "preuves",
    label: "Preuves (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "preuve-1, preuve-2",
  },
  {
    nom: "reversibilite",
    label: "Réversibilité (optionnel)",
    type: "select",
    options: ["REVERSIBLE", "PARTIELLE", "IRREVERSIBLE"],
  },
  {
    nom: "statut",
    label: "Statut (optionnel)",
    type: "select",
    options: ["DRAFT", "PROPOSED", "EVALUATED", "SELECTED", "REJECTED", "ARCHIVED"],
  },
];

const CHAMPS_CREER_SITUATION = [
  {
    nom: "titre",
    label: "Titre de la situation",
    type: "text",
    maxLength: 500,
    placeholder: "Latence des paiements sur les cartes",
    aide: "Un titre, une description ou un résumé est obligatoire.",
  },
  {
    nom: "description",
    label: "Description (optionnel)",
    type: "textarea",
    rows: 3,
    maxLength: 10000,
    placeholder: "Ce qui est observé, où et depuis quand…",
  },
  {
    nom: "resume",
    label: "Résumé (optionnel)",
    type: "textarea",
    rows: 2,
    maxLength: 5000,
    placeholder: "La lecture courte qui rend la situation reconnaissable.",
  },
  {
    nom: "priorite",
    label: "Priorité (optionnel)",
    type: "text",
    maxLength: 64,
    placeholder: "haute, P1, à qualifier…",
  },
  {
    nom: "twin_ids",
    label: "Twins liés (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "app-paiement, process-controle",
  },
  {
    nom: "mode",
    label: "Mode de connaissance (optionnel)",
    type: "select",
    options: [
      { value: "DECLARED", label: "Déclaré" },
      { value: "OBSERVED", label: "Observé" },
      { value: "INFERRED", label: "Inféré" },
      { value: "PROPOSED", label: "Proposé" },
      { value: "CONFIRMED", label: "Confirmé" },
    ],
  },
];

const CHAMPS_OUVRIR_INVESTIGATION = [
  {
    nom: "titre",
    label: "Titre de l'investigation",
    type: "text",
    requis: true,
    maxLength: 200,
    placeholder: "Comprendre la latence des paiements",
    aide: "Un titre court qui rend l'enquête reconnaissable dans la boucle.",
  },
  {
    nom: "question",
    label: "Question à instruire",
    type: "textarea",
    requis: true,
    rows: 3,
    placeholder: "Pourquoi les paiements ralentissent-ils depuis la règle R-118 ?",
    aide: "Une question à laquelle des preuves pourront répondre.",
  },
  {
    nom: "perimetre",
    label: "Périmètre (optionnel)",
    type: "text",
    placeholder: "paiements, cartes, trois flux",
  },
];

const CHAMPS_PROPOSER_DECISION = [
  {
    nom: "titre",
    label: "Titre de la décision",
    type: "text",
    requis: true,
    maxLength: 200,
    placeholder: "Rendre le contrôle R-118 asynchrone",
  },
  {
    nom: "options",
    label: "Options évaluées",
    type: "textarea",
    requis: true,
    rows: 3,
    placeholder: "Automatiser\nRéorganiser\nNe rien changer",
    aide: "Une option par ligne. La décision devra choisir l'une d'elles.",
  },
  {
    nom: "criteres",
    label: "Critères de choix (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "coût\ndélai\nréversibilité",
    aide: "Un critère par ligne.",
  },
  {
    nom: "incertitudes",
    label: "Incertitudes (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "volume de fin de mois",
    aide: "Une incertitude par ligne.",
  },
  {
    nom: "resume",
    label: "Contexte de la décision (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Ce que l'investigation établit et ce qui reste à arbitrer…",
  },
];

const CHAMPS_TRANCHER_DECISION = [
  {
    nom: "choix",
    label: "Choix retenu",
    type: "text",
    requis: true,
    placeholder: "Automatiser",
  },
  {
    nom: "motif",
    label: "Motif (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Pourquoi ce choix, et à quelles conditions il tient…",
  },
];

const CHAMPS_LANCER_INITIATIVE = [
  {
    nom: "titre",
    label: "Titre de l'initiative",
    type: "text",
    requis: true,
    maxLength: 200,
    placeholder: "Déployer le contrôle asynchrone",
  },
  {
    nom: "resume",
    label: "Description (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Déploiement progressif sur les trois flux de paiement…",
  },
  {
    nom: "proprietaire",
    label: "Propriétaire (optionnel)",
    type: "text",
    maxLength: 200,
    placeholder: "Alice Martin",
  },
  {
    nom: "perimetre",
    label: "Périmètre (optionnel)",
    type: "text",
    placeholder: "paiements",
  },
  {
    nom: "outcome_attendu_ids",
    label: "Outcomes attendus (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "out-attendu-1, out-attendu-2",
  },
];

const CHAMPS_MESURER_OUTCOME = [
  {
    nom: "metrique",
    label: "Métrique",
    type: "text",
    requis: true,
    placeholder: "p95, délai moyen, taux d'erreur…",
  },
  {
    nom: "valeur",
    label: "Valeur mesurée",
    type: "text",
    requis: true,
    inputMode: "decimal",
    placeholder: "180",
  },
  {
    nom: "unite",
    label: "Unité (optionnel)",
    type: "text",
    placeholder: "ms, %, €…",
  },
  {
    nom: "source",
    label: "Source de la mesure (optionnel)",
    type: "text",
    placeholder: "suivi-cartes",
  },
  {
    nom: "cible",
    label: "Cible (optionnel)",
    type: "text",
    inputMode: "decimal",
    placeholder: "200",
  },
  {
    nom: "periode",
    label: "Période (optionnel)",
    type: "text",
    placeholder: "2026-10",
  },
  {
    nom: "interpretation",
    label: "Interprétation (optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "Ce que la mesure établit, sans conclure au-delà…",
  },
  {
    nom: "preuves",
    label: "Preuves (IDs séparés par une virgule, optionnel)",
    type: "text",
    placeholder: "preuve-1, preuve-2",
  },
];

const CHAMPS_CAPITALISER_LEARNING = [
  {
    nom: "enonce",
    label: "Énoncé du learning",
    type: "textarea",
    requis: true,
    rows: 3,
    placeholder: "Un contrôle synchrone sur un flux critique amplifie tout ralentissement.",
    aide: "Une leçon réutilisable, formulée indépendamment du cas particulier.",
  },
  {
    nom: "scope",
    label: "Portée (optionnel)",
    type: "text",
    placeholder: "paiements, cartes…",
  },
  {
    nom: "conditions_applicabilite",
    label: "Conditions de réutilisation (une par ligne, optionnel)",
    type: "textarea",
    rows: 2,
    placeholder: "volume stable\ncharge nominale",
  },
];

export const ACTIONS_BOUCLE = Object.freeze({
  creer_situation: Object.freeze({
    id: "creer_situation",
    titre: "Créer une situation racine",
    description: "Formuler un phénomène observé qui ouvre une nouvelle chaîne canonique.",
    api: "creerSituation",
    champs: CHAMPS_CREER_SITUATION,
  }),
  creer_expression: Object.freeze({
    id: "creer_expression",
    libelle: "Exprimer la situation",
    titre: "Exprimer la situation",
    description: "Formuler la lecture datée du phénomène, avec son type, ses inconnues et sa confiance.",
    testid: "boucle-action-creer-expression",
    api: "creerExpression",
    icone: "expression",
    champs: CHAMPS_CREER_EXPRESSION,
  }),
  qualifier_opportunite: Object.freeze({
    id: "qualifier_opportunite",
    libelle: "Qualifier une opportunité",
    titre: "Qualifier une opportunité",
    description: "Transformer la lecture en opportunité canonique, avec sa valeur, son impact et ses critères.",
    testid: "boucle-action-qualifier-opportunite",
    api: "creerOpportunite",
    icone: "opportunite",
    champs: CHAMPS_QUALIFIER_OPPORTUNITE,
  }),
  qualifier_risque: Object.freeze({
    id: "qualifier_risque",
    libelle: "Qualifier un risque",
    titre: "Qualifier un risque",
    description: "Transformer la lecture en risque canonique, avec sa probabilité, son impact et son horizon.",
    testid: "boucle-action-qualifier-risque",
    api: "creerRisque",
    icone: "risque",
    champs: CHAMPS_QUALIFIER_RISQUE,
  }),
  changer_statut_opportunite: Object.freeze({
    id: "changer_statut_opportunite",
    libelle: "Changer le statut",
    titre: "Changer le statut de l'opportunité",
    description: "Faire évoluer l'opportunité selon son cycle de maturation canonique.",
    testid: "boucle-action-statut-opportunite",
    api: "changerStatutOpportunite",
    icone: "statut",
    champs: CHAMPS_CHANGER_STATUT,
  }),
  changer_statut_risque: Object.freeze({
    id: "changer_statut_risque",
    libelle: "Changer le statut",
    titre: "Changer le statut du risque",
    description: "Faire évoluer le risque selon son cycle de maturation canonique.",
    testid: "boucle-action-statut-risque",
    api: "changerStatutRisque",
    icone: "statut",
    champs: CHAMPS_CHANGER_STATUT,
  }),
  creer_scenario: Object.freeze({
    id: "creer_scenario",
    libelle: "Créer un scénario",
    titre: "Créer un scénario",
    description: "Décrire une option d'action comparable, avec ses métriques et sa réversibilité.",
    testid: "boucle-action-creer-scenario",
    api: "creerScenario",
    icone: "scenario",
    champs: CHAMPS_CREER_SCENARIO,
  }),
  ouvrir_investigation: Object.freeze({
    id: "ouvrir_investigation",
    libelle: "Ouvrir une investigation",
    titre: "Ouvrir une investigation",
    description: "Transformer la situation en question instruisible, avec son périmètre.",
    testid: "boucle-action-investigation",
    api: "ouvrirInvestigation",
    icone: "investigation",
    champs: CHAMPS_OUVRIR_INVESTIGATION,
  }),
  proposer_decision: Object.freeze({
    id: "proposer_decision",
    libelle: "Proposer une décision",
    titre: "Proposer une décision",
    description: "Exposer les options et les critères avant qu'un acteur tranche.",
    testid: "boucle-action-proposer-decision",
    api: "proposerDecision",
    icone: "decision",
    champs: CHAMPS_PROPOSER_DECISION,
  }),
  trancher_decision: Object.freeze({
    id: "trancher_decision",
    libelle: "Trancher la décision",
    titre: "Trancher la décision",
    description: "Enregistrer le choix retenu et son motif. L'acteur est l'utilisateur authentifié.",
    testid: "boucle-action-trancher",
    api: "trancherDecision",
    icone: "trancher",
    champs: CHAMPS_TRANCHER_DECISION,
  }),
  lancer_initiative: Object.freeze({
    id: "lancer_initiative",
    libelle: "Lancer une initiative",
    titre: "Lancer une initiative",
    description: "Traduire la décision en action suivie, avec un propriétaire et un périmètre.",
    testid: "boucle-action-initiative",
    api: "lancerInitiative",
    icone: "initiative",
    champs: CHAMPS_LANCER_INITIATIVE,
  }),
  mesurer_outcome: Object.freeze({
    id: "mesurer_outcome",
    libelle: "Mesurer un outcome",
    titre: "Mesurer un outcome",
    description: "Relier une mesure observée à l'initiative, avec sa cible et ses preuves.",
    testid: "boucle-action-outcome",
    api: "mesurerOutcome",
    icone: "outcome",
    champs: CHAMPS_MESURER_OUTCOME,
  }),
  capitaliser_learning: Object.freeze({
    id: "capitaliser_learning",
    libelle: "Capitaliser un learning",
    titre: "Capitaliser un learning",
    description: "Formuler la leçon réutilisable issue de l'outcome ou de l'investigation.",
    testid: "boucle-action-learning",
    api: "capitaliserLearningDepuisOutcome",
    icone: "learning",
    champs: CHAMPS_CAPITALISER_LEARNING,
  }),
});

export function texte(valeur) {
  return valeur == null ? "" : String(valeur);
}

export function sansAccents(valeur) {
  return texte(valeur).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function texteAffichable(valeur) {
  if (valeur == null) return "";
  if (Array.isArray(valeur)) {
    return valeur
      .filter((element) => element == null || typeof element !== "object")
      .map((element) => texte(element))
      .filter(Boolean)
      .join(", ");
  }
  if (typeof valeur === "object") return "";
  return texte(valeur);
}

export function valeurDe(objet, ...cles) {
  if (!objet || typeof objet !== "object") return null;
  for (const cle of cles) {
    const directe = objet[cle];
    if (directe !== undefined && directe !== null && directe !== "") return directe;
    const donnee = objet.donnees?.[cle];
    if (donnee !== undefined && donnee !== null && donnee !== "") return donnee;
  }
  return null;
}

export function idObjet(objet) {
  if (typeof objet === "string") {
    const identifiant = objet.trim();
    return identifiant || null;
  }
  if (!objet || typeof objet !== "object") return null;
  const identifiant = objet.id ?? objet._id;
  if (identifiant == null || String(identifiant).trim() === "") return null;
  return texte(identifiant);
}

export function typeObjet(objet) {
  return texte(valeurDe(objet, "type")).trim().toUpperCase();
}

export function titreObjet(objet) {
  if (typeof objet === "string") return objet.trim() || "Objet sans titre";
  return texteAffichable(valeurDe(objet, "titre")) || idObjet(objet) || "Objet sans titre";
}

export function statutObjet(objet) {
  const brut = texte(valeurDe(objet, "statut"));
  return brut
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function decisionEstTranchee(objet) {
  const statut = statutObjet(objet);
  if (STATUTS_DECISION_TRANCHEE.has(statut)) return true;
  if (STATUTS_DECISION_REJETEE.has(statut)) return false;
  return Boolean(texte(valeurDe(objet, "acteur")) && texte(valeurDe(objet, "choix")));
}

export function decisionEstRejetee(objet) {
  return STATUTS_DECISION_REJETEE.has(statutObjet(objet));
}

export function listeOptions(objet) {
  const brut = valeurDe(objet, "options");
  if (!Array.isArray(brut)) return [];
  return brut.map((option) => texte(option).trim()).filter(Boolean);
}

export function actionsPourObjet(objet) {
  const type = typeObjet(objet);
  const statut = statutObjet(objet);

  if (type === "SITUATION") {
    const actions = [ACTIONS_BOUCLE.ouvrir_investigation];
    if (!texte(valeurDe(objet, "expression_id", "expression")).trim()) {
      actions.push(ACTIONS_BOUCLE.creer_expression);
    }
    return actions;
  }

  if (type === "EXPRESSION") {
    return STATUTS_EXPRESSION_QUALIFIABLES.has(statut)
      ? [ACTIONS_BOUCLE.qualifier_opportunite, ACTIONS_BOUCLE.qualifier_risque]
      : [];
  }

  if (type === "OPPORTUNITY") {
    return statutsSuivants(type, statut).length > 0
      ? [ACTIONS_BOUCLE.changer_statut_opportunite]
      : [];
  }

  if (type === "RISK") {
    return statutsSuivants(type, statut).length > 0
      ? [ACTIONS_BOUCLE.changer_statut_risque]
      : [];
  }

  if (type === "INVESTIGATION") {
    const actions = [];
    if (!STATUTS_INVESTIGATION_FERMES.has(statut)) actions.push(ACTIONS_BOUCLE.proposer_decision);
    actions.push(ACTIONS_BOUCLE.creer_scenario);
    actions.push(ACTIONS_BOUCLE.capitaliser_learning);
    return actions;
  }

  if (type === "DECISION") {
    if (decisionEstRejetee(objet)) return [];
    if (decisionEstTranchee(objet)) {
      const actions = idObjet(valeurDe(objet, "initiative_id"))
        ? []
        : [ACTIONS_BOUCLE.lancer_initiative];
      actions.push(ACTIONS_BOUCLE.creer_scenario);
      return actions;
    }
    return [ACTIONS_BOUCLE.trancher_decision, ACTIONS_BOUCLE.creer_scenario];
  }

  if (type === "INITIATIVE") {
    return STATUTS_INITIATIVE_ANNULEE.has(statut) ? [] : [ACTIONS_BOUCLE.mesurer_outcome];
  }

  if (type === "OUTCOME") return [ACTIONS_BOUCLE.capitaliser_learning];

  return [];
}

export function configurationAction(actionId, objet) {
  const base = ACTIONS_BOUCLE[actionId];
  if (!base) return null;

  const typeSource = typeObjet(objet);
  const options = listeOptions(objet);
  let champs = base.champs.map((champ) => (
    champ.nom === "choix" && options.length > 0
      ? { ...champ, type: "select", options }
      : champ
  ));

  let api = base.api;
  if (actionId === "changer_statut_opportunite" || actionId === "changer_statut_risque") {
    const suivants = statutsSuivants(typeSource, statutObjet(objet));
    champs = champs.map((champ) => (
      champ.nom === "statut" ? { ...champ, options: suivants } : champ
    ));
    if (suivants.length === 0) api = null;
  }
  if (actionId === "capitaliser_learning") {
    if (typeSource === "OUTCOME") api = "capitaliserLearningDepuisOutcome";
    else if (typeSource === "INVESTIGATION") api = "capitaliserLearningDepuisInvestigation";
    else api = null;
  }

  return { ...base, champs, api, typeSource };
}

function valeurNette(valeurs, nom) {
  return texte(valeurs?.[nom]).trim();
}

function listeLignes(valeurs, nom) {
  return valeurNette(valeurs, nom)
    .split(/\r?\n/)
    .map((element) => element.trim())
    .filter(Boolean);
}

function listeVirgules(valeurs, nom) {
  return valeurNette(valeurs, nom)
    .split(",")
    .map((element) => element.trim())
    .filter(Boolean);
}

function listeLignesOuVirgules(valeurs, nom) {
  return valeurNette(valeurs, nom)
    .split(/[\r\n,]+/)
    .map((element) => element.trim())
    .filter(Boolean);
}

function nombreOptionnel(valeurs, nom, libelle, { entier = false, maximum = null } = {}) {
  const brut = valeurNette(valeurs, nom).replace(",", ".");
  if (!brut) return { valeur: null };
  if (!Number.isFinite(Number(brut))) {
    return { erreur: `${libelle} doit être un nombre positif.` };
  }
  const nombre = Number(brut);
  if (entier && !Number.isInteger(nombre)) {
    return { erreur: `${libelle} doit être un entier positif.` };
  }
  if (nombre < 0) {
    return { erreur: `${libelle} doit être un nombre positif.` };
  }
  if (maximum !== null && nombre > maximum) {
    return { erreur: `${libelle} doit être un nombre entre 0 et 1.` };
  }
  return { valeur: nombre };
}

function echec(message) {
  return { corps: null, erreur: message };
}

function avecOptions(corps, valeurs, champs) {
  const resultat = { ...corps };
  for (const champ of champs) {
    const valeur = valeurNette(valeurs, champ);
    if (valeur) resultat[champ] = valeur;
  }
  return resultat;
}

function corpsQualification(valeurs, libelle) {
  const titre = valeurNette(valeurs, "titre");
  if (!titre) {
    return echec(`Le titre ${libelle === "opportunité" ? "de l'opportunité" : "du risque"} est obligatoire.`);
  }
  const corps = { titre };
  for (const nom of ["description", "impact", "horizon"]) {
    const valeur = valeurNette(valeurs, nom);
    if (valeur) corps[nom] = valeur;
  }
  for (const [nom, libelleChamp, options] of [
    ["valeur_potentielle", "La valeur potentielle", {}],
    ["probabilite", "La probabilité", { maximum: 1 }],
    ["confiance", "La confiance", { maximum: 1 }],
  ]) {
    const resultat = nombreOptionnel(valeurs, nom, libelleChamp, options);
    if (resultat.erreur) return echec(resultat.erreur);
    if (resultat.valeur !== null) corps[nom] = resultat.valeur;
  }
  const criteres = listeLignesOuVirgules(valeurs, "criteres");
  if (criteres.length > 0) corps.criteres = criteres;
  const preuves = listeVirgules(valeurs, "preuves");
  if (preuves.length > 0) corps.preuves = preuves;
  const mode = valeurNette(valeurs, "mode").toUpperCase();
  if (mode) corps.mode = mode;
  return { corps };
}

function corpsChangementStatut(type, valeurs, objet) {
  const statut = valeurNette(valeurs, "statut").toUpperCase();
  if (!statut) return echec("Le statut cible est obligatoire.");
  const autorises = statutsSuivants(type, statutObjet(objet));
  if (!autorises.includes(statut)) {
    return echec(`transition de statut refusée : ${statutObjet(objet) || "?"} → ${statut}.`);
  }
  const corps = { statut };
  const motif = valeurNette(valeurs, "motif");
  if (motif) corps.motif = motif;
  const preuves = listeVirgules(valeurs, "preuves");
  if (preuves.length > 0) corps.preuves = preuves;
  return { corps };
}

export function construireCorps(actionId, valeurs = {}, objet = {}) {
  switch (actionId) {
    case "creer_situation": {
      const titre = valeurNette(valeurs, "titre");
      const description = valeurNette(valeurs, "description");
      const resume = valeurNette(valeurs, "resume");
      if (!titre && !description && !resume) {
        return echec("Un titre, une description ou un résumé est obligatoire.");
      }
      const corps = {};
      if (titre) corps.titre = titre;
      if (description) corps.description = description;
      if (resume) corps.resume = resume;
      const priorite = valeurNette(valeurs, "priorite");
      if (priorite) corps.priorite = priorite;
      const twinIds = listeVirgules(valeurs, "twin_ids");
      if (twinIds.length > 0) corps.twin_ids = twinIds;
      const mode = valeurNette(valeurs, "mode").toUpperCase();
      if (mode) corps.mode = mode;
      return { corps };
    }

    case "creer_expression": {
      const formulation = valeurNette(valeurs, "formulation");
      if (!formulation) return echec("La formulation est obligatoire.");
      const corps = { formulation };
      const typeExpression = valeurNette(valeurs, "type_expression").toUpperCase();
      if (typeExpression) {
        if (!TYPES_EXPRESSION.includes(typeExpression)) {
          return echec("Le type d'expression est inconnu.");
        }
        corps.type_expression = typeExpression;
      }
      const canal = valeurNette(valeurs, "canal");
      if (canal) corps.canal = canal;
      const auteur = valeurNette(valeurs, "auteur");
      if (auteur) corps.auteur = auteur;
      const inconnues = listeLignesOuVirgules(valeurs, "inconnues");
      if (inconnues.length > 0) corps.inconnues = inconnues;
      const confiance = nombreOptionnel(valeurs, "confiance", "La confiance", { maximum: 1 });
      if (confiance.erreur) return echec(confiance.erreur);
      if (confiance.valeur !== null) corps.confiance = confiance.valeur;
      return { corps };
    }

    case "qualifier_opportunite":
      return corpsQualification(valeurs, "opportunité");

    case "qualifier_risque":
      return corpsQualification(valeurs, "risque");

    case "changer_statut_opportunite":
      return corpsChangementStatut("OPPORTUNITY", valeurs, objet);

    case "changer_statut_risque":
      return corpsChangementStatut("RISK", valeurs, objet);

    case "creer_scenario": {
      const titre = valeurNette(valeurs, "titre");
      if (!titre) return echec("Le titre du scénario est obligatoire.");
      const typeSource = typeObjet(objet);
      const identifiantSource = idObjet(objet);
      const investigationId = typeSource === "INVESTIGATION"
        ? (identifiantSource || valeurNette(valeurs, "investigation_id"))
        : valeurNette(valeurs, "investigation_id");
      const decisionId = typeSource === "DECISION"
        ? (identifiantSource || valeurNette(valeurs, "decision_id"))
        : valeurNette(valeurs, "decision_id");
      if (!investigationId && !decisionId) {
        return echec("Un scénario doit être rattaché à une investigation ou une décision.");
      }

      const corps = { titre };
      const description = valeurNette(valeurs, "description");
      if (description) corps.description = description;
      if (investigationId) corps.investigation_id = investigationId;
      if (decisionId) corps.decision_id = decisionId;
      const hypotheses = listeLignesOuVirgules(valeurs, "hypothesis_ids");
      if (hypotheses.length > 0) corps.hypothesis_ids = hypotheses;
      const actions = listeLignesOuVirgules(valeurs, "actions");
      if (actions.length > 0) corps.actions = actions;
      const dependances = listeVirgules(valeurs, "dependances");
      if (dependances.length > 0) corps.dependances = dependances;
      const preuves = listeVirgules(valeurs, "preuves");
      if (preuves.length > 0) corps.preuves = preuves;

      const impacts = {};
      for (const element of listeVirgules(valeurs, "impacts")) {
        const separateur = element.indexOf("=");
        if (separateur <= 0 || separateur === element.length - 1) {
          return echec("Un impact doit être au format clé=valeur.");
        }
        const cleImpact = element.slice(0, separateur).trim();
        const valeurImpact = element.slice(separateur + 1).trim();
        if (!cleImpact || !valeurImpact) {
          return echec("Un impact doit être au format clé=valeur.");
        }
        impacts[cleImpact] = valeurImpact;
      }
      if (Object.keys(impacts).length > 0) corps.impacts = impacts;

      for (const [nom, libelle, options] of [
        ["valeur_estimee", "La valeur estimée", {}],
        ["cout_estime", "Le coût estimé", {}],
        ["delai_jours", "Le délai", { entier: true }],
        ["risque", "Le risque", { maximum: 1 }],
        ["complexite", "La complexité", { maximum: 1 }],
        ["confiance", "La confiance", { maximum: 1 }],
      ]) {
        const resultat = nombreOptionnel(valeurs, nom, libelle, options);
        if (resultat.erreur) return echec(resultat.erreur);
        if (resultat.valeur !== null) corps[nom] = resultat.valeur;
      }

      const reversibilite = valeurNette(valeurs, "reversibilite").toUpperCase();
      if (reversibilite) {
        if (!["REVERSIBLE", "PARTIELLE", "IRREVERSIBLE"].includes(reversibilite)) {
          return echec("La réversibilité doit être REVERSIBLE, PARTIELLE ou IRREVERSIBLE.");
        }
        corps.reversibilite = reversibilite;
      }
      const statut = valeurNette(valeurs, "statut").toUpperCase();
      if (statut) {
        if (!["DRAFT", "PROPOSED", "EVALUATED", "SELECTED", "REJECTED", "ARCHIVED"].includes(statut)) {
          return echec("Le statut du scénario est inconnu.");
        }
        corps.statut = statut;
      }
      return { corps };
    }

    case "ouvrir_investigation": {
      const titre = valeurNette(valeurs, "titre");
      const question = valeurNette(valeurs, "question");
      if (!titre) return echec("Le titre de l'investigation est obligatoire.");
      if (!question) return echec("La question à instruire est obligatoire.");
      return { corps: avecOptions({ titre, question }, valeurs, ["perimetre"]) };
    }

    case "proposer_decision": {
      const titre = valeurNette(valeurs, "titre");
      const options = listeLignes(valeurs, "options");
      if (!titre) return echec("Le titre de la décision est obligatoire.");
      if (options.length === 0) return echec("Au moins une option est obligatoire.");
      const corps = { titre, options };
      const criteres = listeLignes(valeurs, "criteres");
      const incertitudes = listeLignes(valeurs, "incertitudes");
      if (criteres.length > 0) corps.criteres = criteres;
      if (incertitudes.length > 0) corps.incertitudes = incertitudes;
      return { corps: avecOptions(corps, valeurs, ["resume"]) };
    }

    case "trancher_decision": {
      const choix = valeurNette(valeurs, "choix");
      if (!choix) return echec("Le choix retenu est obligatoire.");
      const options = listeOptions(objet);
      if (options.length > 0 && !options.some((option) => option.toLowerCase() === choix.toLowerCase())) {
        return echec("Le choix doit être l'une des options proposées.");
      }
      return { corps: avecOptions({ choix }, valeurs, ["motif"]) };
    }

    case "lancer_initiative": {
      const titre = valeurNette(valeurs, "titre");
      if (!titre) return echec("Le titre de l'initiative est obligatoire.");
      const corps = avecOptions({ titre }, valeurs, ["resume", "proprietaire", "perimetre"]);
      const attendus = listeVirgules(valeurs, "outcome_attendu_ids");
      if (attendus.length > 0) corps.outcome_attendu_ids = attendus;
      return { corps };
    }

    case "mesurer_outcome": {
      const metrique = valeurNette(valeurs, "metrique");
      const valeurBrute = valeurNette(valeurs, "valeur").replace(",", ".");
      if (!metrique) return echec("La métrique est obligatoire.");
      if (!valeurBrute) return echec("La valeur mesurée est obligatoire.");
      if (!Number.isFinite(Number(valeurBrute))) return echec("La valeur mesurée doit être un nombre.");
      const mesure = { metrique, valeur: Number(valeurBrute) };
      const unite = valeurNette(valeurs, "unite");
      const source = valeurNette(valeurs, "source");
      if (unite) mesure.unite = unite;
      if (source) mesure.source = source;
      const corps = { mesure };
      const cibleBrute = valeurNette(valeurs, "cible").replace(",", ".");
      if (cibleBrute) {
        if (!Number.isFinite(Number(cibleBrute))) return echec("La cible doit être un nombre.");
        corps.valeur_attendue = Number(cibleBrute);
      }
      const periode = valeurNette(valeurs, "periode");
      if (periode) corps.periode = periode;
      const interpretation = valeurNette(valeurs, "interpretation");
      if (interpretation) corps.interpretation = interpretation;
      const preuves = listeVirgules(valeurs, "preuves");
      if (preuves.length > 0) corps.preuves = preuves;
      return { corps };
    }

    case "capitaliser_learning": {
      const enonce = valeurNette(valeurs, "enonce");
      if (!enonce) return echec("L'énoncé du learning est obligatoire.");
      const corps = avecOptions({ enonce }, valeurs, ["scope"]);
      const conditions = listeLignes(valeurs, "conditions_applicabilite");
      if (conditions.length > 0) corps.conditions_applicabilite = conditions;
      return { corps };
    }

    default:
      return echec("Action de boucle inconnue.");
  }
}

export function messageErreurTransition(erreur, defaut = "La transition n'a pas pu être enregistrée.") {
  const reponse = erreur?.response;
  const detail = reponse?.data?.detail;

  if (Array.isArray(detail)) {
    const messages = detail.map((element) => {
      if (typeof element === "string") return element;
      const champ = Array.isArray(element?.loc)
        ? element.loc.filter((partie) => !["body", "query", "path"].includes(partie)).join(".")
        : "";
      const message = element?.msg || element?.message || "";
      return champ && message ? `${champ} : ${message}` : message;
    }).filter(Boolean);
    if (messages.length > 0) return messages.join(" · ");
  }

  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (reponse?.status === 400) {
    return "Les données envoyées sont invalides. Vérifiez le formulaire.";
  }
  if (reponse?.status === 404) {
    return "L'objet source est introuvable. Rechargez la boucle puis réessayez.";
  }
  if (reponse?.status === 409) {
    return "Conflit : l'objet existe peut-être déjà ou a changé d'état. Rechargez la boucle.";
  }
  if (reponse?.status === 422) {
    return "Certaines valeurs sont invalides. Vérifiez le formulaire.";
  }
  if (reponse?.status === 403) {
    return "Vous n'avez pas le droit d'effectuer cette transition.";
  }
  if (reponse?.status === 503) {
    return "La boucle est momentanément indisponible. Réessayez dans un instant.";
  }
  return defaut;
}

export function fusionnerObjet(objets, objet) {
  const identifiant = idObjet(objet);
  if (!identifiant) return objets;
  const index = objets.findIndex((element) => idObjet(element) === identifiant);
  if (index === -1) return [...objets, objet];
  const copie = [...objets];
  copie[index] = objet;
  return copie;
}

// Réponse A : la chaîne va de la racine jusqu'à l'enfant créé, et l'historique
// est celui de l'objet retourné. Pour la source, on coupe la chaîne à son index
// et on ne reprend l'historique de la réponse que si c'est le même objet.
// Une chaîne vide, absente ou sans la source ne doit jamais effacer l'ancienne.
export function detailSourceApresTransition({
  identifiant,
  nouvelObjet,
  nouvelleChaine,
  nouvelHistorique,
  ancienDetail,
}) {
  const chaine = Array.isArray(nouvelleChaine) ? nouvelleChaine : null;
  const indexSource = chaine
    ? chaine.findIndex((etape) => idObjet(etape) === identifiant)
    : -1;
  const memeObjet = idObjet(nouvelObjet) === identifiant;
  const source = indexSource >= 0
    ? chaine[indexSource]
    : (memeObjet ? nouvelObjet : null);
  const chaineSource = indexSource >= 0
    ? (memeObjet ? chaine : chaine.slice(0, indexSource + 1))
    : null;

  return {
    source,
    chaine: chaineSource ?? ancienDetail?.chaine ?? [],
    historique: (memeObjet ? nouvelHistorique : null) ?? ancienDetail?.historique ?? [],
  };
}

let compteurIdempotence = 0;

export function cleIdempotence() {
  compteurIdempotence += 1;
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  return `boucle-${Date.now().toString(36)}-${compteurIdempotence}-${Math.random().toString(36).slice(2, 10)}`;
}

// Trace canonique portée par un Travail legacy, si le backend en expose une.
// Contrat C2 attendu : cas.boucle = { id, statut, chaine }. Les formes plates
// (boucle_id, boucle_statut, boucle_chaine) restent acceptées comme repli.
// Plusieurs formes sont acceptées pour ne pas dépendre d'un seul contrat de sérialisation.
export function traceCanoniqueDeTravail(cas) {
  if (!cas || typeof cas !== "object") return null;

  const brut = cas.boucle
    ?? cas.boucle_canonique
    ?? cas.trace_canonique
    ?? cas.trace_boucle
    ?? cas.objet_boucle
    ?? null;
  if (brut) {
    if (typeof brut === "string") return { id: brut, statut: "", chaine: [] };
    if (Array.isArray(brut)) {
      if (brut.length === 0) return null;
      const dernier = brut[brut.length - 1];
      return {
        id: texte(cas.boucle_id ?? (typeof dernier === "object" ? dernier?.id ?? dernier?.objet_id : dernier) ?? ""),
        statut: texte(cas.boucle_statut ?? (typeof dernier === "object" ? dernier?.statut : "") ?? ""),
        chaine: brut,
      };
    }
    if (typeof brut !== "object") return null;
    const objet = brut.objet && typeof brut.objet === "object" ? brut.objet : brut;
    const id = objet.id ?? objet.objet_id ?? brut.objet_id ?? brut.id ?? null;
    const statut = objet.statut ?? objet.donnees?.statut ?? brut.statut ?? "";
    const chaine = Array.isArray(brut.chaine)
      ? brut.chaine
      : Array.isArray(brut.objets)
        ? brut.objets
        : Array.isArray(objet.chaine)
          ? objet.chaine
          : [];
    if (!id && chaine.length === 0) return null;
    return { id: id == null ? "" : texte(id), statut: texte(statut), chaine };
  }

  const id = cas.boucle_id ?? cas.objet_boucle_id ?? cas.id_boucle ?? cas.boucle_objet_id ?? null;
  if (!id) return null;
  return {
    id: texte(id),
    statut: texte(cas.boucle_statut ?? cas.statut_boucle ?? ""),
    chaine: Array.isArray(cas.boucle_chaine)
      ? cas.boucle_chaine
      : Array.isArray(cas.chaine_canonique)
        ? cas.chaine_canonique
        : Array.isArray(cas.chaine_boucle)
          ? cas.chaine_boucle
          : [],
  };
}
