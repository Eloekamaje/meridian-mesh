import { useId } from "react";

// Rendu SVG déterministe des schémas de Flore, sans dépendance ni HTML injecté. Le Mermaid reste écrit dans
// la réponse comme repli/export ; ici, on ne dessine que la structure vérifiée fournie par le backend.
export const COULEURS = {
  fond: "#0A131C",
  texte: "#F2F6F8",
  muted: "#7C93A8",
  regle: "rgba(255,255,255,0.12)",
  accent: "#60A5FA",
};

// Même contrat visuel que le harness (état de la flèche = état de la preuve qui la fonde).
export const ETATS_FLECHES = {
  code: { couleur: "#60A5FA", largeur: 1.5, pointille: null },
  valide: { couleur: "#4ADE80", largeur: 3, pointille: null },
  verifie: { couleur: "#34D399", largeur: 2, pointille: null },
  recoupe: { couleur: "#22D3EE", largeur: 2, pointille: null },
  selon: { couleur: "#93C5FD", largeur: 1.5, pointille: null },
  propose: { couleur: "#F2B84B", largeur: 1.5, pointille: "3 3" },
  conteste: { couleur: "#F2B84B", largeur: 1.5, pointille: "6 3" },
  inconnu: { couleur: "#7C93A8", largeur: 1, pointille: "3 3" },
};

const GRILLE = 4;
const MARGE = 24;
const HAUTEUR_NOEUD = 40;
const ECART_COLONNE = 64;
const ECART_VERTICAL = 24;
const LARGEUR_MIN = 88;
const LARGEUR_MAX = 280;
const CARACTERES_MAX = 34;
const CARACTERES_FLECHE = 64;
const LARGEUR_CARACTERE = 7;
const POLICE = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const POLICE_CODE = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

const grille = (valeur) => Math.max(0, Math.round(valeur / GRILLE) * GRILLE);
const grilleSup = (valeur) => Math.max(0, Math.ceil(valeur / GRILLE) * GRILLE);

export function tronquerLibelle(libelle, max = CARACTERES_MAX) {
  const texte = String(libelle ?? "").replace(/\s+/g, " ").trim();
  if (!texte) return "";
  const points = Array.from(texte);
  if (points.length <= max) return texte;
  return `${points.slice(0, Math.max(1, max - 1)).join("").trimEnd()}…`;
}

export function largeurNoeud(libelle) {
  const visible = tronquerLibelle(libelle) || "?";
  return Math.min(LARGEUR_MAX, Math.max(LARGEUR_MIN, grilleSup(32 + Array.from(visible).length * LARGEUR_CARACTERE)));
}

function normaliserBoites(boites) {
  const vues = new Set();
  const sortie = [];
  for (const boite of Array.isArray(boites) ? boites : []) {
    const id = boite?.id == null ? "" : String(boite.id);
    if (!id || vues.has(id)) continue;
    vues.add(id);
    sortie.push({ id, libelle: tronquerLibelle(boite.libelle ?? boite.id) || id });
  }
  return sortie;
}

function normaliserFleches(fleches, ids) {
  const sortie = [];
  for (const fleche of Array.isArray(fleches) ? fleches : []) {
    const de = fleche?.de == null ? "" : String(fleche.de);
    const vers = fleche?.vers == null ? "" : String(fleche.vers);
    if (!ids.has(de) || !ids.has(vers)) continue;
    const etat = ETATS_FLECHES[fleche?.etat] ? fleche.etat : "inconnu";
    sortie.push({ de, vers, etat, libelle: tronquerLibelle(fleche.libelle, CARACTERES_FLECHE) });
  }
  return sortie;
}

export function schemaValide(schema) {
  if (!schema || typeof schema !== "object") return false;
  if (!["architecture", "flux", "sequence"].includes(schema.type)) return false;
  const boites = normaliserBoites(schema.boites);
  if (!boites.length || !Array.isArray(schema.fleches) || !schema.fleches.length) return false;
  const ids = new Set(boites.map((b) => b.id));
  return normaliserFleches(schema.fleches, ids).length > 0;
}

// Rangs topologiques en coupant les arêtes de retour d'un parcours DFS : un cycle ne doit pas écraser tout
// le schéma dans une seule colonne. L'arête de retour reste dessinée plus bas, comme un retour explicite.
export function calculerRangs(boites, fleches) {
  const ids = (Array.isArray(boites) ? boites : []).map((b) => (typeof b === "string" ? b : String(b?.id ?? ""))).filter(Boolean);
  const ordre = new Map(ids.map((id, i) => [id, i]));
  const adjacence = new Map(ids.map((id) => [id, new Set()]));
  for (const fleche of Array.isArray(fleches) ? fleches : []) {
    const de = String(fleche?.de ?? "");
    const vers = String(fleche?.vers ?? "");
    if (adjacence.has(de) && adjacence.has(vers)) adjacence.get(de).add(vers);
  }

  // DFS : une arête vers un sommet encore gris ferme un cycle, on la retire du graphe de rangs.
  const etat = new Map();
  const retours = new Set();
  const visiter = (sommet) => {
    etat.set(sommet, 1);
    for (const voisin of adjacence.get(sommet) || []) {
      if (etat.get(voisin) === 1) retours.add(`${sommet}\u0000${voisin}`);
      else if (!etat.has(voisin)) visiter(voisin);
    }
    etat.set(sommet, 2);
  };
  for (const id of ids) if (!etat.has(id)) visiter(id);

  // Kahn sur le graphe sans arêtes de retour ; les arêtes parallèles ne comptent qu'une fois.
  const dag = new Map(ids.map((id) => [id, []]));
  const degreEntrant = new Map(ids.map((id) => [id, 0]));
  for (const [de, voisins] of adjacence) {
    for (const vers of voisins) {
      if (retours.has(`${de}\u0000${vers}`)) continue;
      dag.get(de).push(vers);
      degreEntrant.set(vers, degreEntrant.get(vers) + 1);
    }
  }
  const rangs = new Map(ids.map((id) => [id, 0]));
  const file = ids.filter((id) => degreEntrant.get(id) === 0);
  const traites = new Set();
  for (let i = 0; i < file.length; i += 1) {
    const courant = file[i];
    traites.add(courant);
    for (const suivante of dag.get(courant)) {
      rangs.set(suivante, Math.max(rangs.get(suivante), rangs.get(courant) + 1));
      degreEntrant.set(suivante, degreEntrant.get(suivante) - 1);
      if (degreEntrant.get(suivante) === 0) file.push(suivante);
    }
  }
  // Filet de sécurité : si un cycle croisé subsiste, on range les sommets restants après leurs prédécesseurs.
  for (const id of ids.slice().sort((a, b) => ordre.get(a) - ordre.get(b))) {
    if (traites.has(id)) continue;
    const predecesseurs = ids.filter((autre) => dag.get(autre)?.includes(id));
    rangs.set(id, Math.max(0, ...predecesseurs.map((autre) => (rangs.get(autre) ?? 0) + 1)));
    traites.add(id);
  }
  return Object.fromEntries(ids.map((id) => [id, rangs.get(id) ?? 0]));
}

function etiquetteFleche(x, y, libelle) {
  if (!libelle) return null;
  const largeur = grilleSup(Math.max(24, Array.from(libelle).length * 6.2 + 12));
  const hauteur = 18;
  return { x, y, largeur, hauteur, libelle };
}

function bornesEtiquette(etiquette) {
  if (!etiquette) return null;
  return {
    minX: etiquette.x - etiquette.largeur / 2,
    maxX: etiquette.x + etiquette.largeur / 2,
    minY: etiquette.y - etiquette.hauteur / 2,
    maxY: etiquette.y + etiquette.hauteur / 2,
  };
}

function descriptionArchitecture(schema, boites, fleches) {
  const morceaux = fleches.map((f) => `${boites.find((b) => b.id === f.de)?.libelle || f.de} vers ${boites.find((b) => b.id === f.vers)?.libelle || f.vers} (${f.etat})`);
  const debut = schema.titre ? `Schéma « ${schema.titre} »` : `Schéma ${schema.type}`;
  return `${debut} : ${boites.length} boîte(s), ${fleches.length} flèche(s). ${morceaux.join(" ; ")}`.slice(0, 1000);
}

function textesDe(valeur) {
  return (Array.isArray(valeur) ? valeur : valeur == null ? [] : [valeur])
    .map((item) => (typeof item === "object" && item !== null
      ? item.texte ?? item.libelle ?? item.label ?? item.description ?? ""
      : item))
    .map((texte) => String(texte ?? "").trim())
    .filter(Boolean);
}

export function descriptionProposition(schema) {
  const hypotheses = textesDe(schema?.hypotheses);
  const horsScope = textesDe(schema?.hors_scope ?? schema?.horsScope);
  return [
    hypotheses.length ? `Hypothèses : ${hypotheses.join(" ; ")}.` : "",
    horsScope.length ? `Hors scope : ${horsScope.join(" ; ")}.` : "",
  ].filter(Boolean).join(" ");
}

export function disposerArchitecture(schema) {
  if (!schema || !Array.isArray(schema.boites) || !schema.boites.length
    || !Array.isArray(schema.fleches) || !schema.fleches.length) return null;
  const boites = normaliserBoites(schema.boites);
  if (!boites.length) return null;
  const ids = new Set(boites.map((b) => b.id));
  const fleches = normaliserFleches(schema.fleches, ids);
  const rangs = calculerRangs(boites, fleches);
  const titre = tronquerLibelle(schema.titre, 80);
  // L'écart entre colonnes suit le libellé le plus long : une étiquette de flèche tient dans la gouttière,
  // sans être recouverte par les nœuds voisins.
  const largeurEtiquettes = Math.max(0, ...fleches.filter((f) => f.libelle).map((f) => Array.from(f.libelle).length * 6.2 + 12));
  const ecartColonne = Math.max(ECART_COLONNE, grilleSup(largeurEtiquettes + 24));

  const parRang = new Map();
  for (const boite of boites) {
    const rang = rangs[boite.id] ?? 0;
    if (!parRang.has(rang)) parRang.set(rang, []);
    parRang.get(rang).push(boite);
  }
  const rangsTries = [...parRang.keys()].sort((a, b) => a - b);
  const colonnes = rangsTries.map((rang) => ({
    rang,
    boites: parRang.get(rang),
    largeur: Math.max(...parRang.get(rang).map((b) => largeurNoeud(b.libelle))),
  }));

  const hauteurColonne = (n) => n * HAUTEUR_NOEUD + Math.max(0, n - 1) * ECART_VERTICAL;
  const hauteurContenu = Math.max(...colonnes.map((c) => hauteurColonne(c.boites.length)));
  const hautContenu = titre ? 64 : 40;
  const noeuds = [];
  const parId = new Map();
  let x = MARGE + 16;

  for (const colonne of colonnes) {
    const depart = hautContenu + grille((hauteurContenu - hauteurColonne(colonne.boites.length)) / 2);
    let y = depart;
    for (const boite of colonne.boites) {
      const largeur = largeurNoeud(boite.libelle);
      const nx = grille(x + (colonne.largeur - largeur) / 2);
      const noeud = {
        id: boite.id,
        libelle: boite.libelle,
        rang: colonne.rang,
        x: nx,
        y: grille(y),
        largeur,
        hauteur: HAUTEUR_NOEUD,
        cx: nx + largeur / 2,
        cy: grille(y) + HAUTEUR_NOEUD / 2,
      };
      noeuds.push(noeud);
      parId.set(boite.id, noeud);
      y += HAUTEUR_NOEUD + ECART_VERTICAL;
    }
    x += colonne.largeur + ecartColonne;
  }

  const groupes = (Array.isArray(schema.groupes) ? schema.groupes : []).map((groupe) => {
    const idsGroupe = [...new Set((Array.isArray(groupe?.ids) ? groupe.ids : []).map((id) => String(id)))].filter((id) => parId.has(id));
    if (!idsGroupe.length) return null;
    const membres = idsGroupe.map((id) => parId.get(id));
    const libelle = tronquerLibelle(groupe.libelle, 40);
    const gauche = grille(Math.min(...membres.map((n) => n.x)) - 16);
    const haut = grille(Math.min(...membres.map((n) => n.y)) - 16);
    const droite = grilleSup(Math.max(...membres.map((n) => n.x + n.largeur)) + 16);
    const bas = grilleSup(Math.max(...membres.map((n) => n.y + n.hauteur)) + 16);
    const largeurLibelle = libelle ? grilleSup(20 + Array.from(libelle).length * 6.2) : 0;
    return {
      libelle,
      x: gauche,
      y: haut,
      largeur: Math.max(droite - gauche, largeurLibelle),
      hauteur: bas - haut,
    };
  }).filter(Boolean);

  const gaucheColonne = new Map();
  const droiteColonne = new Map();
  for (const noeud of noeuds) {
    gaucheColonne.set(noeud.rang, Math.min(gaucheColonne.get(noeud.rang) ?? Infinity, noeud.x));
    droiteColonne.set(noeud.rang, Math.max(droiteColonne.get(noeud.rang) ?? -Infinity, noeud.x + noeud.largeur));
  }
  const basNoeuds = Math.max(...noeuds.map((n) => n.y + n.hauteur));
  let canal = 0;
  const compteurSameRang = new Map();
  const chemins = [];

  fleches.forEach((fleche) => {
    const de = parId.get(fleche.de);
    const vers = parId.get(fleche.vers);
    if (!de || !vers) return;
    const style = ETATS_FLECHES[fleche.etat];
    let points;
    let etiquette = null;

    if (de.id === vers.id) {
      // Boucle : un petit retour à droite du nœud, sans traverser la colonne.
      const droite = de.x + de.largeur;
      const milieu = de.cy;
      const bus = droite + 20;
      points = [[droite, milieu - 8], [bus, milieu - 8], [bus, milieu + 8], [droite, milieu + 8]];
      etiquette = etiquetteFleche(droite + 16, milieu - 20, fleche.libelle);
    } else if (de.rang === vers.rang) {
      // Même colonne : un bus à droite de la colonne, décalé si plusieurs arêtes s'y croisent.
      const rang = de.rang;
      const compteur = compteurSameRang.get(rang) || 0;
      compteurSameRang.set(rang, compteur + 1);
      const bus = grilleSup(droiteColonne.get(rang) + ecartColonne / 2 + (compteur % 3) * 12);
      points = [[de.x + de.largeur, de.cy], [bus, de.cy], [bus, vers.cy], [vers.x + vers.largeur, vers.cy]];
      etiquette = etiquetteFleche(bus, (de.cy + vers.cy) / 2, fleche.libelle);
    } else if (vers.rang === de.rang + 1) {
      // Deux colonnes voisines : le couloir entre elles suffit, sans traverser de nœud.
      const bus = grille((droiteColonne.get(de.rang) + gaucheColonne.get(vers.rang)) / 2);
      points = [[de.x + de.largeur, de.cy], [bus, de.cy], [bus, vers.cy], [vers.x, vers.cy]];
      etiquette = etiquetteFleche(bus, (de.cy + vers.cy) / 2, fleche.libelle);
    } else {
      // Saut de plusieurs colonnes ou retour : on passe sous le schéma, dans un canal réservé,
      // puis on remonte dans le couloir juste avant la cible. Aucune arête ne traverse un nœud.
      const sourceBus = grilleSup(droiteColonne.get(de.rang) + 16);
      const cibleBus = grille(gaucheColonne.get(vers.rang) - 16);
      const y = grilleSup(basNoeuds + 32 + canal * 24);
      canal += 1;
      points = [
        [de.x + de.largeur, de.cy], [sourceBus, de.cy], [sourceBus, y],
        [cibleBus, y], [cibleBus, vers.cy], [vers.x, vers.cy],
      ];
      etiquette = etiquetteFleche((sourceBus + cibleBus) / 2, y, fleche.libelle);
    }

    const bornes = bornesEtiquette(etiquette);
    chemins.push({
      de: fleche.de,
      vers: fleche.vers,
      etat: fleche.etat,
      style,
      points,
      etiquette,
      minX: Math.min(...points.map((p) => p[0]), bornes?.minX ?? Infinity),
      maxX: Math.max(...points.map((p) => p[0]), bornes?.maxX ?? -Infinity),
      minY: Math.min(...points.map((p) => p[1]), bornes?.minY ?? Infinity),
      maxY: Math.max(...points.map((p) => p[1]), bornes?.maxY ?? -Infinity),
    });
  });

  const minX = Math.min(
    ...noeuds.map((n) => n.x),
    ...groupes.map((g) => g.x),
    ...chemins.map((c) => c.minX),
  );
  const maxX = Math.max(
    ...noeuds.map((n) => n.x + n.largeur),
    ...groupes.map((g) => g.x + g.largeur),
    ...chemins.map((c) => c.maxX),
  );
  const minY = Math.min(
    ...noeuds.map((n) => n.y),
    ...groupes.map((g) => g.y),
    ...chemins.map((c) => c.minY),
  );
  const maxY = Math.max(
    ...noeuds.map((n) => n.y + n.hauteur),
    ...groupes.map((g) => g.y + g.hauteur),
    ...chemins.map((c) => c.maxY),
  );
  const largeurTitre = titre ? MARGE + Array.from(titre).length * 7 + MARGE : 0;
  const decalageX = Math.max(0, MARGE - minX);
  const decalageY = Math.max(0, MARGE - minY);

  return {
    type: schema.type,
    titre,
    noeuds: noeuds.map((n) => ({ ...n, x: n.x + decalageX, y: n.y + decalageY, cx: n.cx + decalageX, cy: n.cy + decalageY })),
    groupes: groupes.map((g) => ({ ...g, x: g.x + decalageX, y: g.y + decalageY })),
    fleches: chemins.map((c) => {
      const points = c.points.map(([px, py]) => [px + decalageX, py + decalageY]);
      return {
        ...c,
        points,
        d: points.map((point, i) => `${i === 0 ? "M" : "L"} ${point[0]} ${point[1]}`).join(" "),
        etiquette: c.etiquette ? { ...c.etiquette, x: c.etiquette.x + decalageX, y: c.etiquette.y + decalageY } : null,
      };
    }),
    largeur: grilleSup(Math.max(maxX + decalageX + MARGE, largeurTitre)),
    hauteur: grilleSup(maxY + decalageY + MARGE),
    description: descriptionArchitecture(schema, boites, fleches),
  };
}

export function disposerSequence(schema) {
  if (!schema || !Array.isArray(schema.boites) || !schema.boites.length
    || !Array.isArray(schema.fleches) || !schema.fleches.length) return null;
  const boites = normaliserBoites(schema.boites);
  if (!boites.length) return null;
  const ids = new Set(boites.map((b) => b.id));
  const fleches = normaliserFleches(schema.fleches, ids);
  const titre = tronquerLibelle(schema.titre, 80);
  const haut = titre ? 64 : 32;
  const ecartActeur = 56;
  const pasMessage = 44;
  const acteurs = [];
  let x = MARGE + 16;

  for (const boite of boites) {
    const largeur = largeurNoeud(boite.libelle);
    const acteur = {
      id: boite.id,
      libelle: boite.libelle,
      x: grille(x),
      y: haut,
      largeur,
      hauteur: HAUTEUR_NOEUD,
      cx: grille(x) + largeur / 2,
    };
    acteurs.push(acteur);
    x += largeur + ecartActeur;
  }

  const parId = new Map(acteurs.map((a) => [a.id, a]));
  const departMessages = haut + HAUTEUR_NOEUD + 28;
  const messages = fleches.map((fleche, i) => {
    const de = parId.get(fleche.de);
    const vers = parId.get(fleche.vers);
    const y = departMessages + i * pasMessage;
    let points;
    let etiquette;
    if (de.id === vers.id) {
      points = [[de.cx, y], [de.cx + 32, y], [de.cx + 32, y + 18], [de.cx, y + 18]];
      etiquette = etiquetteFleche(de.cx + 36 + Math.max(24, Array.from(fleche.libelle).length * 6.2 + 12) / 2, y + 9, fleche.libelle);
    } else {
      points = [[de.cx, y], [vers.cx, y]];
      etiquette = etiquetteFleche((de.cx + vers.cx) / 2, y - 9, fleche.libelle);
    }
    const bornes = bornesEtiquette(etiquette);
    return {
      ...fleche,
      style: ETATS_FLECHES[fleche.etat],
      y,
      d: points.map((point, j) => `${j === 0 ? "M" : "L"} ${point[0]} ${point[1]}`).join(" "),
      etiquette,
      minX: Math.min(...points.map((p) => p[0]), bornes?.minX ?? Infinity),
      maxX: Math.max(...points.map((p) => p[0]), bornes?.maxX ?? -Infinity),
      minY: Math.min(...points.map((p) => p[1]), bornes?.minY ?? Infinity),
      maxY: Math.max(...points.map((p) => p[1]), bornes?.maxY ?? -Infinity),
    };
  });

  const dernierMessage = messages.length ? messages[messages.length - 1] : null;
  const basLigne = dernierMessage ? Math.max(dernierMessage.maxY, dernierMessage.y + 18) + 24 : haut + HAUTEUR_NOEUD + 48;
  const minX = Math.min(...acteurs.map((a) => a.x), ...messages.map((m) => m.minX));
  const maxX = Math.max(...acteurs.map((a) => a.x + a.largeur), ...messages.map((m) => m.maxX));
  const decalageX = Math.max(0, MARGE - minX);
  const largeurTitre = titre ? MARGE + Array.from(titre).length * 7 + MARGE : 0;
  const morceaux = messages.map((m) => `${parId.get(m.de)?.libelle || m.de} vers ${parId.get(m.vers)?.libelle || m.vers} (${m.etat})`);
  const description = `${titre ? `Schéma « ${titre} »` : "Schéma de séquence"} : ${acteurs.length} acteur(s), ${messages.length} message(s). ${morceaux.join(" ; ")}`.slice(0, 1000);

  return {
    type: "sequence",
    titre,
    acteurs: acteurs.map((a) => ({ ...a, x: a.x + decalageX, cx: a.cx + decalageX })),
    messages: messages.map((m) => ({
      ...m,
      d: m.d.replace(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g, (_v, px, py) => `${Number(px) + decalageX} ${py}`),
      etiquette: m.etiquette ? { ...m.etiquette, x: m.etiquette.x + decalageX } : null,
      minX: m.minX + decalageX,
      maxX: m.maxX + decalageX,
    })),
    haut,
    basLigne,
    largeur: grilleSup(Math.max(maxX + decalageX + MARGE, largeurTitre)),
    hauteur: grilleSup(basLigne + MARGE),
    description,
  };
}

function DefinitionFleches({ prefixe, etats }) {
  return (
    <defs>
      {[...etats].sort().map((etat) => {
        const style = ETATS_FLECHES[etat] || ETATS_FLECHES.inconnu;
        return (
          <marker
            key={etat}
            id={`${prefixe}-${etat}`}
            viewBox="0 0 8 8"
            markerWidth="8"
            markerHeight="8"
            refX="8"
            refY="4"
            orient="auto"
            markerUnits="userSpaceOnUse"
          >
            <path d="M 0 0 L 8 4 L 0 8 Z" fill={style.couleur} />
          </marker>
        );
      })}
    </defs>
  );
}

function TitreSchema({ titre }) {
  if (!titre) return null;
  return (
    <text x={MARGE} y={32} fill={COULEURS.texte} fontSize={13} fontWeight={600} fontFamily={POLICE}>
      {titre}
    </text>
  );
}

function Fleche({ fleche, prefixe }) {
  const style = fleche.style;
  return (
    <g data-testid="schema-fleche" data-etat={fleche.etat}>
      <path
        d={fleche.d}
        fill="none"
        stroke={style.couleur}
        strokeWidth={style.largeur}
        strokeDasharray={style.pointille || undefined}
        strokeLinecap="round"
        strokeLinejoin="round"
        markerEnd={`url(#${prefixe}-${fleche.etat})`}
      />
    </g>
  );
}

function Etiquette({ etiquette }) {
  if (!etiquette) return null;
  return (
    <g data-testid="schema-etiquette">
      <rect
        x={etiquette.x - etiquette.largeur / 2}
        y={etiquette.y - etiquette.hauteur / 2}
        width={etiquette.largeur}
        height={etiquette.hauteur}
        rx={3}
        fill={COULEURS.fond}
      />
      <text
        x={etiquette.x}
        y={etiquette.y + 3.5}
        textAnchor="middle"
        fill={COULEURS.muted}
        fontSize={10.5}
        fontFamily={POLICE}
      >
        {etiquette.libelle}
      </text>
    </g>
  );
}

function Noeud({ noeud }) {
  return (
    <g data-testid="schema-noeud" data-id={noeud.id}>
      <rect x={noeud.x} y={noeud.y} width={noeud.largeur} height={noeud.hauteur} rx={6} fill={COULEURS.fond} stroke={COULEURS.regle} />
      <rect x={noeud.x} y={noeud.y + 12} width={3} height={16} rx={1.5} fill={COULEURS.accent} />
      <text
        x={noeud.x + 14}
        y={noeud.cy}
        dominantBaseline="middle"
        fill={COULEURS.texte}
        fontSize={12}
        fontFamily={POLICE}
      >
        {noeud.libelle}
      </text>
    </g>
  );
}

function Groupe({ groupe }) {
  return (
    <g data-testid="schema-groupe">
      <rect
        x={groupe.x}
        y={groupe.y}
        width={groupe.largeur}
        height={groupe.hauteur}
        rx={6}
        fill="rgba(255,255,255,0.02)"
        stroke={COULEURS.regle}
        strokeDasharray="4 4"
      />
      {groupe.libelle && (
        <text x={groupe.x + 10} y={groupe.y + 14} fill={COULEURS.muted} fontSize={10.5} fontFamily={POLICE_CODE}>
          {groupe.libelle}
        </text>
      )}
    </g>
  );
}

export default function SchemaSvg({ schema }) {
  const prefixe = `schema-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  if (!schemaValide(schema)) return null;
  const proposition = schema.mode === "proposition";
  const sequence = schema.type === "sequence";
  const disposition = sequence ? disposerSequence(schema) : disposerArchitecture(schema);
  if (!disposition) return null;
  const etats = new Set((sequence ? disposition.messages : disposition.fleches).map((f) => f.etat));
  const titreA11y = proposition
    ? `Proposition : ${disposition.titre || `schéma ${schema.type}`}`
    : (disposition.titre ? `Schéma : ${disposition.titre}` : `Schéma ${schema.type}`);
  const description = [disposition.description, descriptionProposition(schema)].filter(Boolean).join(" ").slice(0, 4000);
  const idTitre = `${prefixe}-titre`;
  const idDescription = `${prefixe}-description`;

  return (
    <div
      className="my-2 w-full overflow-x-auto"
      data-testid="schema-svg-cadre"
      data-mode={proposition ? "proposition" : undefined}
      role={proposition ? "group" : undefined}
      aria-label={proposition ? "Schéma de proposition : hypothèses et hors-scope à valider" : undefined}
    >
    {proposition && (
      <div className="mb-1 flex" data-testid="schema-proposition">
        <span
          className="inline-flex items-center rounded-full border border-[#F2B84B]/40 bg-[#F2B84B]/10 px-2 py-0.5 font-code text-[10px] font-semibold tracking-wide text-[#F2B84B]"
          data-testid="schema-badge-proposition"
        >
          Proposition
        </span>
      </div>
    )}
    <svg
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-labelledby={proposition ? undefined : `${idTitre} ${idDescription}`}
      aria-describedby={proposition ? idDescription : undefined}
      aria-label={proposition ? titreA11y : undefined}
      viewBox={`0 0 ${disposition.largeur} ${disposition.hauteur}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      data-testid="schema-svg"
      data-type={schema.type}
      data-mode={proposition ? "proposition" : undefined}
      className="block"
      style={{ width: "100%", minWidth: `${disposition.largeur}px`, height: "auto" }}
    >
      <title id={idTitre}>{titreA11y}</title>
      <desc id={idDescription}>{description}</desc>
      <DefinitionFleches prefixe={prefixe} etats={etats} />
      <rect x={0} y={0} width={disposition.largeur} height={disposition.hauteur} rx={6} fill={COULEURS.fond} />
      <rect x={0.5} y={0.5} width={disposition.largeur - 1} height={disposition.hauteur - 1} rx={6} fill="none" stroke={COULEURS.regle} />
      <TitreSchema titre={disposition.titre} />
      {sequence ? (
        <>
          {disposition.acteurs.map((acteur) => (
            <line
              key={`ligne-${acteur.id}`}
              x1={acteur.cx}
              y1={acteur.y + acteur.hauteur}
              x2={acteur.cx}
              y2={disposition.basLigne}
              stroke={COULEURS.regle}
              strokeDasharray="3 4"
            />
          ))}
          {disposition.messages.map((message, i) => <Fleche key={`message-${i}`} fleche={message} prefixe={prefixe} />)}
          {disposition.messages.map((message, i) => <Etiquette key={`etiquette-message-${i}`} etiquette={message.etiquette} />)}
          {disposition.acteurs.map((acteur) => (
            <g key={`acteur-${acteur.id}`} data-testid="schema-acteur" data-id={acteur.id}>
              <rect x={acteur.x} y={acteur.y} width={acteur.largeur} height={acteur.hauteur} rx={6} fill={COULEURS.fond} stroke={COULEURS.regle} />
              <rect x={acteur.x} y={acteur.y + 12} width={3} height={16} rx={1.5} fill={COULEURS.accent} />
              <text x={acteur.x + 14} y={acteur.y + acteur.hauteur / 2} dominantBaseline="middle" fill={COULEURS.texte} fontSize={12} fontFamily={POLICE}>
                {acteur.libelle}
              </text>
            </g>
          ))}
        </>
      ) : (
        <>
          {disposition.groupes.map((groupe, i) => <Groupe key={`groupe-${i}`} groupe={groupe} />)}
          {disposition.fleches.map((fleche, i) => <Fleche key={`fleche-${i}`} fleche={fleche} prefixe={prefixe} />)}
          {disposition.fleches.map((fleche, i) => <Etiquette key={`etiquette-${i}`} etiquette={fleche.etiquette} />)}
          {disposition.noeuds.map((noeud) => <Noeud key={noeud.id} noeud={noeud} />)}
        </>
      )}
    </svg>
    </div>
  );
}
