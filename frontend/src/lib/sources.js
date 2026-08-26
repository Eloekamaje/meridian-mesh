export const STATUTS_SOURCE = {
  ajoutee: { label: "Ajoutée", couleur: "#64748B" },
  a_configurer: { label: "À configurer", couleur: "#B45309" },
  prete_a_tester: { label: "Prête à tester", couleur: "#3730A3" },
  test_en_cours: { label: "Test en cours…", couleur: "#3730A3" },
  prete: { label: "Prête", couleur: "#047857" },
  erreur_connexion: { label: "Erreur de connexion", couleur: "#B91C1C" },
  autorisation_insuffisante: { label: "Autorisation insuffisante", couleur: "#B91C1C" },
  secret_expire: { label: "Secret expiré", couleur: "#B91C1C" },
  perimetre_vide: { label: "Périmètre vide", couleur: "#B45309" },
  configuration_incomplete: { label: "Configuration incomplète", couleur: "#B45309" },
};

export const CLES_ERREUR = ["erreur_connexion", "autorisation_insuffisante", "secret_expire", "perimetre_vide", "configuration_incomplete"];
export const estErreurSource = (s) => CLES_ERREUR.includes(s);
export const estPreteSource = (s) => s === "prete";

export const ENVIRONNEMENTS = ["production", "préproduction", "recette", "développement"];

export const ETAPES_COMMANDE = ["Identité", "Sources et connexions", "Plan de découverte", "Vérifier et lancer"];

export function statutCalcule(source, connecteur) {
  if (source.statut === "test_en_cours" || source.statut === "prete" || estErreurSource(source.statut)) return source.statut;
  const manquants = (connecteur?.champs || []).filter((c) => c.requis && !source.config?.[c.cle]);
  if (manquants.length === 0 && source.perimetre) return "prete_a_tester";
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
