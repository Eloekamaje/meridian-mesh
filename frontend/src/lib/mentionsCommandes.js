// Mentions @jumeau et commandes / du compositeur. Aucune commande n'exécute une action serveur cachée :
// elle remplit le message avec une consigne explicite, que l'humain peut relire et modifier avant l'envoi.
export const COMMANDES = [
  {
    nom: "resumer",
    titre: "Résumer le travail",
    aide: "Ce qui est établi, ce qui reste ouvert, la prochaine étape.",
    prompt: "Résume ce travail : ce qui est établi, ce qui reste ouvert, ce qui a changé, et la prochaine étape.",
  },
  {
    nom: "investiguer",
    titre: "Mener l'investigation",
    aide: "Hypothèses concurrentes, mise à l'épreuve, preuves manquantes.",
    prompt: "Mène l'investigation sur le sujet de ce travail : formule les hypothèses concurrentes, mets-les à l'épreuve avec tes outils, puis dis ce qui est établi et ce qui manque.",
  },
  {
    nom: "decision",
    titre: "Préparer une décision",
    aide: "Options, impacts, risques, recommandation argumentée.",
    prompt: "Prépare une décision : options, impacts, preuves, risques et une recommandation argumentée.",
  },
  {
    nom: "preuves",
    titre: "Lister les preuves",
    aide: "Ce qui fonde les affirmations, avec leurs sources.",
    prompt: "Liste les preuves qui fondent les affirmations de ce travail, avec leurs sources et leur état de vérification.",
  },
  {
    nom: "pieces",
    titre: "Interroger les pièces",
    aide: "Les pièces jointes pertinentes et ce qu'elles disent.",
    prompt: "Quelles pièces jointes de ce travail sont pertinentes, et que disent-elles ?",
  },
  {
    nom: "aide",
    titre: "Afficher les commandes",
    aide: "La liste des commandes disponibles.",
    local: "Commandes : /resumer, /investiguer, /decision, /preuves, /pieces, /aide",
  },
];

const SANS_ACCENT = /[\u0300-\u036f]/g;

export function normaliser(texte) {
  return String(texte || "").normalize("NFD").replace(SANS_ACCENT, "").toLowerCase();
}

export function requeteMention(texte) {
  const trouve = /(?:^|\s)@([^\s@]*)$/.exec(String(texte || ""));
  return trouve ? trouve[1] : null;
}

export function requeteCommande(texte) {
  const trouve = /(?:^|\s)\/([a-z-]*)$/i.exec(String(texte || ""));
  return trouve ? trouve[1] : null;
}

export function appliquerMention(texte, nom) {
  return String(texte || "").replace(/@([^\s@]*)$/, `@${nom} `);
}

export function appliquerCommande(texte, commande) {
  return String(texte || "").replace(/\/([a-z-]*)$/i, commande.prompt);
}

export function commandesFiltrees(requete) {
  const q = normaliser(requete);
  if (!q) return COMMANDES;
  return COMMANDES.filter((c) => normaliser(`${c.nom} ${c.titre} ${c.aide}`).includes(q));
}

export function resoudreCommande(texte) {
  const trouve = /^\s*\/([a-z-]+)\s*$/i.exec(String(texte || ""));
  if (!trouve) return null;
  return COMMANDES.find((c) => c.nom === trouve[1].toLowerCase()) || null;
}
