export const STATUTS_SOURCE = {
  ajoutee: { label: "Ajoutée", couleur: "#94A3B8" },
  a_configurer: { label: "À configurer", couleur: "#FBBF24" },
  prete_a_tester: { label: "Prête à tester", couleur: "#3B82F6" },
  test_en_cours: { label: "Test en cours…", couleur: "#3B82F6" },
  prete: { label: "Prête", couleur: "#10B981" },
  erreur_connexion: { label: "Erreur de connexion", couleur: "#F87171" },
  autorisation_insuffisante: { label: "Autorisation insuffisante", couleur: "#F87171" },
  secret_expire: { label: "Secret expiré", couleur: "#F87171" },
  perimetre_vide: { label: "Périmètre vide", couleur: "#F59E0B" },
  configuration_incomplete: { label: "Configuration incomplète", couleur: "#F59E0B" },
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
