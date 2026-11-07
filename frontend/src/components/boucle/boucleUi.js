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
    nom: "acteur",
    label: "Acteur qui tranche",
    type: "text",
    requis: true,
    maxLength: 200,
    placeholder: "comité-cartes",
    aide: "La personne ou l'instance qui assume la décision.",
  },
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
    nom: "preuve_ids",
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
    description: "Enregistrer l'acteur, le choix retenu et son motif.",
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
  if (typeof objet === "string") return objet;
  if (!objet || typeof objet !== "object") return null;
  const identifiant = objet.id ?? objet._id;
  return identifiant == null ? null : texte(identifiant);
}

export function typeObjet(objet) {
  return texte(valeurDe(objet, "type")).trim().toUpperCase();
}

export function titreObjet(objet) {
  if (typeof objet === "string") return objet;
  return texte(valeurDe(objet, "titre")) || idObjet(objet) || "Objet sans titre";
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

  if (type === "SITUATION") return [ACTIONS_BOUCLE.ouvrir_investigation];

  if (type === "INVESTIGATION") {
    const actions = [];
    if (!STATUTS_INVESTIGATION_FERMES.has(statut)) actions.push(ACTIONS_BOUCLE.proposer_decision);
    actions.push(ACTIONS_BOUCLE.capitaliser_learning);
    return actions;
  }

  if (type === "DECISION") {
    if (decisionEstRejetee(objet)) return [];
    return decisionEstTranchee(objet)
      ? [ACTIONS_BOUCLE.lancer_initiative]
      : [ACTIONS_BOUCLE.trancher_decision];
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
  const champs = base.champs.map((champ) => (
    champ.nom === "choix" && options.length > 0
      ? { ...champ, type: "select", options }
      : champ
  ));

  let api = base.api;
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

export function construireCorps(actionId, valeurs = {}, objet = {}) {
  switch (actionId) {
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
      const acteur = valeurNette(valeurs, "acteur");
      const choix = valeurNette(valeurs, "choix");
      if (!acteur) return echec("L'acteur qui tranche est obligatoire.");
      if (!choix) return echec("Le choix retenu est obligatoire.");
      const options = listeOptions(objet);
      if (options.length > 0 && !options.some((option) => option.toLowerCase() === choix.toLowerCase())) {
        return echec("Le choix doit être l'une des options proposées.");
      }
      return { corps: avecOptions({ acteur, choix }, valeurs, ["motif"]) };
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
      const preuves = listeVirgules(valeurs, "preuve_ids");
      if (preuves.length > 0) corps.preuve_ids = preuves;
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
  if (reponse?.status === 404) {
    return "L'objet source est introuvable. Rechargez la boucle puis réessayez.";
  }
  if (reponse?.status === 409) {
    return "Transition invalide : l'objet a peut-être déjà changé d'état. Rechargez la boucle.";
  }
  if (reponse?.status === 422) {
    return "Certaines valeurs sont invalides. Vérifiez le formulaire.";
  }
  if (reponse?.status === 403) {
    return "Vous n'avez pas le droit d'effectuer cette transition.";
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

let compteurIdempotence = 0;

export function cleIdempotence() {
  compteurIdempotence += 1;
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return uuid;
  return `boucle-${Date.now().toString(36)}-${compteurIdempotence}-${Math.random().toString(36).slice(2, 10)}`;
}

// Trace canonique portée par un Travail legacy, si le backend en expose une.
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
