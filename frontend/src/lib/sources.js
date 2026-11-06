export const STATUTS_SOURCE = {
  ajoutee: { label: "Ajoutée", couleur: "#7C93A8" },
  a_configurer: { label: "À configurer", couleur: "#F2B84B" },
  prete_a_tester: { label: "Prête à tester", couleur: "#60A5FA" },
  test_en_cours: { label: "Test en cours…", couleur: "#60A5FA" },
  prete: { label: "Prête", couleur: "#34D399" },
  erreur_connexion: { label: "Erreur de connexion", couleur: "#F87171" },
  autorisation_insuffisante: { label: "Autorisation insuffisante", couleur: "#F87171" },
  secret_expire: { label: "Secret expiré", couleur: "#F87171" },
  perimetre_vide: { label: "Périmètre vide", couleur: "#F2B84B" },
  configuration_incomplete: { label: "Configuration incomplète", couleur: "#F2B84B" },
  non_branche: { label: "Non branché", couleur: "#F2B84B" },
};

export const CLES_ERREUR = ["erreur_connexion", "autorisation_insuffisante", "secret_expire", "perimetre_vide", "configuration_incomplete"];
export const estErreurSource = (s) => CLES_ERREUR.includes(s);
export const estPreteSource = (s) => s === "prete";

export const ENVIRONNEMENTS = ["production", "préproduction", "recette", "développement"];

export const APPLICATION_ID = /^[a-z0-9][a-z0-9._-]{1,127}$/;

export const TYPES_TWIN = ["APPLICATION", "TEAM", "RESOURCE", "SUPPLIER", "ECOSYSTEM"];

export const LIBELLES_TYPE_TWIN = {
  APPLICATION: "Application",
  TEAM: "Équipe",
  RESOURCE: "Ressource tierce",
  SUPPLIER: "Fournisseur",
  ECOSYSTEM: "Écosystème",
};

export const AIDES_TYPE_TWIN = {
  APPLICATION: "Application avec App ID, ou application candidate explicitement déclarée sans App ID.",
  TEAM: "Équipe interne identifiée par son nom, son propriétaire et son périmètre.",
  RESOURCE: "Ressource fournie par un tiers : identifiant externe, ou twin_id généré.",
  SUPPLIER: "Fournisseur ou opérateur : code fournisseur, ou twin_id généré.",
  ECOSYSTEM: "Périmètre d'équipe regroupant ressources, applications et responsabilités.",
};

export const IDENTIFIANT_TYPE_TWIN = {
  APPLICATION: "application_id",
  TEAM: "team_id",
  RESOURCE: "resource_id",
  SUPPLIER: "supplier_id",
};

export const LIBELLES_IDENTIFIANT_TWIN = {
  application_id: "App ID",
  team_id: "Team ID",
  resource_id: "Resource ID",
  supplier_id: "Supplier ID",
};

const PREFIXES_TWIN = { APPLICATION: "app", TEAM: "team", RESOURCE: "res", SUPPLIER: "sup", ECOSYSTEM: "eco" };
const texte = (valeur) => String(valeur ?? "").trim();

export function typeTwin(jumeau = {}) {
  return TYPES_TWIN.includes(jumeau?.type) ? jumeau.type : "APPLICATION";
}

export function estApplication(jumeau = {}) {
  return typeTwin(jumeau) === "APPLICATION";
}

export function applicationIdDe(jumeau = {}) {
  return texte(jumeau?.application_id || jumeau?.app_id);
}

export function candidatDe(jumeau = {}) {
  return Boolean(jumeau?.candidat || jumeau?.application_candidate || jumeau?.mode_candidat);
}

export function genererTwinId(type = "APPLICATION") {
  const prefixe = PREFIXES_TWIN[typeTwin({ type })] || "twin";
  return `${prefixe}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function twinIdDe(jumeau = {}) {
  const explicite = texte(jumeau.twin_id);
  if (explicite) return explicite;
  return estApplication(jumeau) ? applicationIdDe(jumeau) : "";
}

export function identifiantsDe(jumeau = {}) {
  const valeur = jumeau?.identifiants;
  if (!valeur) return {};
  if (typeof valeur === "string") {
    try {
      const parse = JSON.parse(valeur);
      return parse && typeof parse === "object" && !Array.isArray(parse) ? parse : {};
    } catch {
      return {};
    }
  }
  return typeof valeur === "object" && !Array.isArray(valeur) ? valeur : {};
}

export function identifiantMetier(jumeau = {}) {
  const type = typeTwin(jumeau);
  const cle = IDENTIFIANT_TYPE_TWIN[type];
  if (!cle) return null;
  return { cle, label: LIBELLES_IDENTIFIANT_TWIN[cle], valeur: cle === "application_id" ? applicationIdDe(jumeau) : texte(jumeau[cle]) };
}

export function validerIdentite(jumeau = {}) {
  const type = typeTwin(jumeau);
  const nom = texte(jumeau.nom);
  const proprietaire = texte(jumeau.proprietaire);
  const perimetre = texte(jumeau.perimetre);
  const applicationId = applicationIdDe(jumeau);
  const candidat = candidatDe(jumeau);

  if (!nom) return { valide: false, code: "nom", message: "Le nom du Twin est requis." };
  if (!proprietaire) return { valide: false, code: "proprietaire", message: "Le propriétaire est requis." };

  if (type === "APPLICATION") {
    if (applicationId && !APPLICATION_ID.test(applicationId)) {
      return { valide: false, code: "application_id", message: "App ID invalide — minuscules, chiffres, point, tiret ou underscore." };
    }
    if (!applicationId && !candidat) {
      return { valide: false, code: "application_id", message: "App ID requis, ou mode candidat explicite." };
    }
  }

  if (type === "TEAM" || type === "ECOSYSTEM") {
    if (!perimetre) return { valide: false, code: "perimetre", message: "Le périmètre est requis pour un Twin TEAM ou ECOSYSTEM." };
  }

  if (type === "RESOURCE" && !texte(jumeau.resource_id) && !texte(jumeau.twin_id)) {
    return { valide: false, code: "resource_id", message: "Renseignez un Resource ID ou générez un twin_id." };
  }

  if (type === "SUPPLIER" && !texte(jumeau.supplier_id) && !texte(jumeau.twin_id)) {
    return { valide: false, code: "supplier_id", message: "Renseignez un Supplier ID ou générez un twin_id." };
  }

  if (jumeau.identifiants !== undefined && jumeau.identifiants !== null && jumeau.identifiants !== ""
    && (typeof jumeau.identifiants !== "object" || Array.isArray(jumeau.identifiants))) {
    return { valide: false, code: "identifiants", message: "Les identifiants externes doivent former un objet JSON." };
  }

  return { valide: true, code: null, message: "" };
}

export function normaliserJumeau(jumeau = {}) {
  const type = typeTwin(jumeau);
  const normalise = { ...jumeau, type, identifiants: identifiantsDe(jumeau), application_id: applicationIdDe(jumeau) };
  if (!texte(normalise.twin_id)) {
    normalise.twin_id = type === "APPLICATION" && APPLICATION_ID.test(normalise.application_id)
      ? normalise.application_id
      : genererTwinId(type);
  }
  normalise.candidat = type === "APPLICATION" ? candidatDe(normalise) : false;
  if (type !== "APPLICATION") {
    normalise.application_id = "";
    normalise.app_id = "";
  }
  return normalise;
}

export const ETAPES_COMMANDE = ["Identité", "Sources et connexions", "Plan de découverte", "Vérifier et lancer"];

// Une liste (couples dépôt/branche) n'est remplie que si une de ses lignes l'est.
export const champRempli = (v) => (Array.isArray(v) ? v.some((x) => x?.depot) : Boolean(v));

export function statutCalcule(source, connecteur) {
  if (source.statut === "test_en_cours" || source.statut === "prete" || estErreurSource(source.statut)) return source.statut;
  const manquants = (connecteur?.champs || []).filter((c) => c.requis && !champRempli(source.config?.[c.cle]));
  if (manquants.length === 0) return "prete_a_tester";
  return source.statut === "ajoutee" ? "a_configurer" : source.statut;
}

export function nouvelleInstance(connecteur, n) {
  const config = {};
  (connecteur.champs || []).forEach((c) => { if (c.defaut !== undefined) config[c.cle] = c.defaut; });
  return {
    id: `src-${Date.now().toString(36)}-${n}`,
    connecteur: connecteur.id,
    nom: `${connecteur.nom} — instance ${n}`,
    environnement: "production",
    perimetre: "",
    proprietaire: "",
    statut: "a_configurer",
    erreur: null,
    dernier_test: null,
    config,
  };
}
