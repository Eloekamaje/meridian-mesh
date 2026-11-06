// Rendu structuré des outils de Flore, emprunté à l'idée de « tool renderers » de CopilotKit :
// le même flux AG-UI, mais chaque outil connu a une lecture humaine (champs, référence, action)
// au lieu d'un bloc JSON brut. Aucun outil n'est inventé : un nom inconnu retombe sur le
// premier argument.

const texte = (valeur) => (valeur == null || valeur === "" ? "" : String(valeur));
const tronquer = (valeur, maximum = 240) => {
  const contenu = texte(valeur);
  return contenu.length > maximum ? `${contenu.slice(0, maximum)}…` : contenu;
};
const liste = (valeur) => (Array.isArray(valeur) ? valeur : valeur ? [valeur] : []).map(String).filter(Boolean);

export function premierArgument(args) {
  const valeur = args && typeof args === "object"
    ? Object.values(args).find((x) => typeof x === "string" || typeof x === "number")
    : null;
  return valeur == null ? "" : String(valeur).slice(0, 60);
}

export function resumeOutil(outil) {
  const nom = outil?.nom || "";
  const args = outil?.arguments && typeof outil.arguments === "object" ? outil.arguments : {};
  const base = { nom, titre: outil?.libelle || nom, detail: "", champs: [], actions: [], masquerExtrait: false };

  switch (nom) {
    case "mobiliser_jumeaux": {
      const jumeaux = liste(args.jumeaux);
      return {
        ...base,
        titre: "Mobilisation de jumeaux",
        detail: tronquer(args.question || args.mission, 300),
        champs: [{ label: "Jumeaux", valeur: jumeaux.join(", ") || "—" }],
        actions: jumeaux.map((id) => ({ type: "jumeau", id, label: `Ouvrir ${id}` })),
      };
    }
    case "lire_code": {
      const chemin = texte(args.chemin);
      const lignes = args.debut ? `#L${args.debut}${args.fin ? `-L${args.fin}` : ""}` : "";
      const reference = `${chemin}${lignes}`;
      return {
        ...base,
        titre: "Lecture de code",
        detail: reference || "fichier inconnu",
        champs: [
          ...(args.depot ? [{ label: "Dépôt", valeur: texte(args.depot) }] : []),
          ...(args.debut ? [{ label: "Lignes", valeur: `${args.debut}${args.fin ? `–${args.fin}` : ""}` }] : []),
        ],
        actions: reference ? [{ type: "copier", texte: reference, label: "Copier la référence" }] : [],
        masquerExtrait: true,
      };
    }
    case "chercher_texte":
    case "chercher_symbole": {
      const terme = texte(args.texte || args.symbole);
      return {
        ...base,
        titre: nom === "chercher_symbole" ? "Recherche de symbole" : "Recherche dans le code",
        detail: terme || "terme inconnu",
        champs: args.depot ? [{ label: "Dépôt", valeur: texte(args.depot) }] : [],
        actions: terme ? [{ type: "copier", texte: terme, label: "Copier le terme" }] : [],
        masquerExtrait: true,
      };
    }
    case "lire_piece": {
      const piece = texte(args.piece_id);
      const section = texte(args.section_id);
      return {
        ...base,
        titre: "Lecture d'une pièce",
        detail: [piece, section].filter(Boolean).join(" · ") || "pièce inconnue",
        champs: section ? [{ label: "Section", valeur: section }] : [],
        actions: piece ? [{ type: "piece", id: piece, label: "Ouvrir la pièce" }] : [],
      };
    }
    case "chercher_pieces":
      return { ...base, titre: "Recherche dans les pièces", detail: tronquer(args.question, 300) };
    case "lire_table":
      return {
        ...base,
        titre: "Lecture d'un tableau",
        detail: [texte(args.piece_id), texte(args.feuille)].filter(Boolean).join(" · ") || "tableau inconnu",
        actions: args.piece_id ? [{ type: "piece", id: texte(args.piece_id), label: "Ouvrir la pièce" }] : [],
      };
    case "chercher_dans": {
      const terme = texte(args.texte);
      return {
        ...base,
        titre: "Recherche dans une source",
        detail: terme || "terme inconnu",
        champs: args.source ? [{ label: "Source", valeur: texte(args.source) }] : [],
        actions: terme ? [{ type: "copier", texte: terme, label: "Copier le terme" }] : [],
      };
    }
    case "lire_dans": {
      const reference = texte(args.ref);
      return {
        ...base,
        titre: "Lecture d'une source",
        detail: reference || "référence inconnue",
        actions: reference ? [{ type: "copier", texte: reference, label: "Copier la référence" }] : [],
      };
    }
    case "architecture":
      return { ...base, titre: "Architecture du dépôt", detail: texte(args.depot) || "dépôt inconnu", masquerExtrait: true };
    case "tracer_appels":
    case "suivre_appels":
      return { ...base, titre: "Traçage d'appels", detail: texte(args.fonction) || "fonction inconnue", masquerExtrait: true };
    case "historique_du_code":
      return { ...base, titre: "Historique du code", detail: texte(args.chemin) || "fichier inconnu", masquerExtrait: true };
    case "ce_qui_a_change":
      return { ...base, titre: "Ce qui a changé", detail: texte(args.depuis) || "depuis le dernier commit", masquerExtrait: true };
    case "rechercher_web": {
      const requete = texte(args.requete);
      return {
        ...base,
        titre: "Recherche web",
        detail: requete || "requête inconnue",
        actions: requete ? [{ type: "copier", texte: requete, label: "Copier la requête" }] : [],
      };
    }
    case "lire_page": {
      const url = texte(args.url);
      return {
        ...base,
        titre: "Lecture d'une page",
        detail: url || "URL inconnue",
        actions: url ? [{ type: "copier", texte: url, label: "Copier l'URL" }] : [],
      };
    }
    case "planifier": {
      const etapes = liste(args.etapes);
      return {
        ...base,
        titre: "Plan du Travail",
        detail: tronquer(args.prochaine_etape, 300),
        champs: etapes.length ? [{ label: "Étapes", valeur: String(etapes.length) }] : [],
      };
    }
    case "proposer_hypothese":
      return { ...base, titre: "Hypothèse proposée", detail: tronquer(args.texte, 400) };
    case "proposer_option":
      return {
        ...base,
        titre: "Option proposée",
        detail: tronquer(args.titre, 240),
        champs: args.risque ? [{ label: "Risque", valeur: texte(args.risque) }] : [],
      };
    case "deposer_livrable":
      return { ...base, titre: "Livrable déposé", detail: tronquer(args.titre, 240) };
    case "demander_precision":
      return { ...base, titre: "Précision demandée", detail: tronquer(args.question, 400) };
    default:
      return { ...base, detail: premierArgument(args) };
  }
}
