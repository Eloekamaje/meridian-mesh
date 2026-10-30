// Schémas de Flore : disposition déterministe, sélection SVG prioritaire et repli Mermaid conservé.
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import SchemaSvg, {
  calculerRangs,
  disposerArchitecture,
  disposerSequence,
  largeurNoeud,
  schemaValide,
  tronquerLibelle,
} from "./SchemaSvg";
import MarkdownFlore from "./MarkdownFlore";
import { MessageFlore } from "./MessageFlore";

jest.mock("react-markdown", () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
  defaultUrlTransform: (url) => url,
}));
jest.mock("remark-gfm", () => () => {});
jest.mock("remark-math", () => () => {});
jest.mock("rehype-katex", () => () => {});
jest.mock("rehype-highlight", () => () => {});
jest.mock("sonner", () => ({ toast: { success: jest.fn() } }));
jest.mock("./SchemaMermaid", () => () => <div data-testid="schema-mermaid" />);
jest.mock("@/lib/api", () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock("@/lib/useFluxAction", () => ({ __esModule: true, default: () => ({ flux: null, lancer: jest.fn(), arreter: jest.fn() }) }));

const lire = (fichier) => fs.readFileSync(path.join(__dirname, "..", fichier), "utf8");
const schemaSimple = {
  type: "architecture",
  titre: "Parcours client",
  boites: [
    { id: "a", libelle: "Portail client" },
    { id: "b", libelle: "Gestion des dossiers" },
    { id: "c", libelle: "Diffusion des statuts" },
  ],
  fleches: [
    { de: "a", vers: "b", libelle: "ouvre", etat: "valide" },
    { de: "b", vers: "c", libelle: "publie", etat: "code" },
  ],
  groupes: [{ libelle: "Socle", ids: ["b", "c"] }],
};

function segmentsOrthogonaux(d) {
  const points = [...d.matchAll(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g)].map((m) => [Number(m[1]), Number(m[2])]);
  return points.slice(1).every((point, i) => point[0] === points[i][0] || point[1] === points[i][1]);
}

function seChevauchent(a, b) {
  return a.x < b.x + b.largeur && b.x < a.x + a.largeur && a.y < b.y + b.hauteur && b.y < a.y + a.hauteur;
}

function pointsDe(d) {
  return [...d.matchAll(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g)].map((m) => [Number(m[1]), Number(m[2])]);
}

function segmentToucheRect([x1, y1], [x2, y2], rect) {
  const gauche = rect.x + 1;
  const droite = rect.x + rect.largeur - 1;
  const haut = rect.y + 1;
  const bas = rect.y + rect.hauteur - 1;
  if (y1 === y2) return y1 > haut && y1 < bas && Math.max(Math.min(x1, x2), gauche) < Math.min(Math.max(x1, x2), droite);
  if (x1 === x2) return x1 > gauche && x1 < droite && Math.max(Math.min(y1, y2), haut) < Math.min(Math.max(y1, y2), bas);
  return false;
}

test("les libellés sont tronqués autour de 34 caractères et les largeurs restent sur la grille", () => {
  const long = "Un libellé de nœud beaucoup trop long pour tenir sur une seule ligne lisible";
  const court = tronquerLibelle("Portail client");
  expect(court).toBe("Portail client");
  expect(Array.from(tronquerLibelle(long)).length).toBeLessThanOrEqual(34);
  expect(tronquerLibelle(long).endsWith("…")).toBe(true);
  expect(tronquerLibelle("").length).toBe(0);
  for (const libelle of ["a", "Portail client", long]) {
    expect(largeurNoeud(libelle) % 4).toBe(0);
    expect(largeurNoeud(libelle)).toBeGreaterThanOrEqual(88);
    expect(largeurNoeud(libelle)).toBeLessThanOrEqual(280);
  }
});

test("Kahn range une chaîne et coupe l'arête de retour d'un cycle", () => {
  const chaine = calculerRangs(
    [{ id: "a" }, { id: "b" }, { id: "c" }],
    [{ de: "a", vers: "b" }, { de: "b", vers: "c" }],
  );
  expect(chaine).toEqual({ a: 0, b: 1, c: 2 });

  const cycle = calculerRangs(
    [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }],
    [{ de: "a", vers: "b" }, { de: "b", vers: "a" }, { de: "b", vers: "c" }, { de: "c", vers: "d" }],
  );
  expect(cycle.a).toBe(0); // b -> a est l'arête de retour
  expect(cycle.b).toBe(1);
  expect(cycle.c).toBe(2);
  expect(cycle.d).toBe(3);
});

test("l'architecture se dispose par couches, sans chevauchement, avec des flèches orthogonales", () => {
  const disposition = disposerArchitecture(schemaSimple);
  const parId = Object.fromEntries(disposition.noeuds.map((n) => [n.id, n]));

  // Trois couches distinctes, de gauche à droite.
  expect(parId.a.rang).toBe(0);
  expect(parId.b.rang).toBe(1);
  expect(parId.c.rang).toBe(2);
  expect(parId.a.x).toBeLessThan(parId.b.x);
  expect(parId.b.x).toBeLessThan(parId.c.x);

  // Aucune paire de nœuds ne se superpose, et tout reste aligné sur la grille de 4 px.
  for (let i = 0; i < disposition.noeuds.length; i += 1) {
    const noeud = disposition.noeuds[i];
    expect(noeud.hauteur).toBe(40);
    for (const valeur of [noeud.x, noeud.y, noeud.largeur]) expect(valeur % 4).toBe(0);
    for (let j = i + 1; j < disposition.noeuds.length; j += 1) {
      expect(seChevauchent(noeud, disposition.noeuds[j])).toBe(false);
    }
  }

  // Les étiquettes de flèche ont un fond opaque et les tracés ne font que des pas horizontaux/verticaux.
  expect(disposition.fleches).toHaveLength(2);
  for (const fleche of disposition.fleches) {
    expect(segmentsOrthogonaux(fleche.d)).toBe(true);
    expect(fleche.etiquette).not.toBeNull();
    expect(fleche.etiquette.largeur).toBeGreaterThan(0);
  }
  expect(disposition.groupes).toHaveLength(1);
  expect(disposition.groupes[0].libelle).toBe("Socle");
});

test("une arête qui saute des colonnes passe sous les nœuds, jamais à travers", () => {
  const disposition = disposerArchitecture({
    type: "architecture",
    boites: [{ id: "a", libelle: "A" }, { id: "b", libelle: "B" }, { id: "c", libelle: "C" }, { id: "d", libelle: "D" }],
    fleches: [
      { de: "a", vers: "b" }, { de: "b", vers: "c" }, { de: "c", vers: "d" },
      { de: "a", vers: "d", libelle: "saute" },
    ],
  });
  const longue = disposition.fleches.find((f) => f.de === "a" && f.vers === "d");
  const points = pointsDe(longue.d);
  const traverses = disposition.noeuds.filter((n) => !["a", "d"].includes(n.id));
  for (let i = 1; i < points.length; i += 1) {
    for (const noeud of traverses) expect(segmentToucheRect(points[i - 1], points[i], noeud)).toBe(false);
  }
  expect(longue.etiquette.libelle).toBe("saute");
});

test("les groupes dessinent un cadre pointillé derrière les nœuds et les messages d'une séquence restent ordonnés", () => {
  const disposition = disposerSequence({
    type: "sequence",
    titre: "Consultation",
    boites: [{ id: "client", libelle: "Client" }, { id: "api", libelle: "API dossiers" }],
    fleches: [
      { de: "client", vers: "api", libelle: "demande", etat: "valide" },
      { de: "api", vers: "client", libelle: "statut", etat: "selon" },
    ],
    groupes: [{ libelle: "Ignoré", ids: ["client", "api"] }],
  });
  expect(disposition.acteurs.map((a) => a.id)).toEqual(["client", "api"]);
  expect(disposition.acteurs[0].cx).toBeLessThan(disposition.acteurs[1].cx);
  expect(disposition.messages).toHaveLength(2);
  expect(disposition.messages[0].etat).toBe("valide");
  expect(disposition.messages[1].y).toBeGreaterThan(disposition.messages[0].y);
  expect(disposition.messages[1].etiquette.libelle).toBe("statut");
  expect(disposition.groupes).toBeUndefined(); // les groupes ne s'appliquent pas aux séquences
});

test("un schéma vide ou de type inconnu ne rend rien", () => {
  expect(schemaValide(null)).toBe(false);
  expect(schemaValide({ type: "architecture", boites: [], fleches: [] })).toBe(false);
  expect(schemaValide({ type: "inconnu", boites: [{ id: "a" }], fleches: [{ de: "a", vers: "a" }] })).toBe(false);
  expect(renderToStaticMarkup(<SchemaSvg schema={{ type: "architecture", boites: [], fleches: [] }} />)).toBe("");
  expect(renderToStaticMarkup(<SchemaSvg schema={{ type: "inconnu", boites: [{ id: "a" }], fleches: [{ de: "a", vers: "a" }] }} />)).toBe("");
});

test("le SVG est accessible, responsive et reprend les couleurs d'état du contrat", () => {
  const html = renderToStaticMarkup(<SchemaSvg schema={schemaSimple} />);
  expect(html).toContain('data-testid="schema-svg"');
  expect(html).toContain('data-testid="schema-svg-cadre"');
  expect(html).toContain("overflow-x-auto");
  expect(html).toContain('role="img"');
  expect(html).toContain("aria-labelledby=");
  expect(html).toContain("Schéma : Parcours client");
  expect(html).toMatch(/<title id="[^"]+"[^>]*>Schéma : Parcours client<\/title>/);
  expect(html).toMatch(/<desc id="[^"]+"[^>]*>Schéma « Parcours client »/);
  expect(html).toContain('width="100%"');
  expect(html).toContain('viewBox="');
  expect(html).not.toContain("<foreignObject");
  expect(html).not.toContain("drop-shadow");
  expect(html).toContain('stroke="#4ADE80"'); // valide
  expect(html).toContain('stroke-width="3"');
  expect(html).toContain('stroke="#60A5FA"'); // code
  // Le libellé de flèche est masqué par un rectangle de fond avant le texte.
  expect(html.indexOf('data-testid="schema-etiquette"')).toBeGreaterThan(-1);
  expect(html).toContain('fill="#0A131C"');
  // Aucun HTML injecté dans le composant.
  const source = lire("components/SchemaSvg.jsx");
  expect(source).not.toContain("dangerouslySetInnerHTML");
  expect(source).not.toContain("foreignObject");
});

test("un flux suit la même disposition et chaque état garde sa couleur, son épaisseur et son pointillé", () => {
  const html = renderToStaticMarkup(<SchemaSvg schema={{
    type: "flux",
    boites: [{ id: "a", libelle: "Entrée" }, { id: "b", libelle: "Sortie" }],
    fleches: [
      { de: "a", vers: "b", libelle: "conteste", etat: "conteste" },
      { de: "b", vers: "a", libelle: "inconnu", etat: "inconnu" },
    ],
  }} />);
  expect(html).toContain('data-type="flux"');
  expect(html).toContain('stroke="#F2B84B"');
  expect(html).toContain('stroke-width="1.5"');
  expect(html).toContain('stroke-dasharray="6 3"');
  expect(html).toContain('stroke="#7C93A8"');
  expect(html).toContain('stroke-width="1"');
  expect(html).toContain('stroke-dasharray="3 3"');
});

test("MarkdownFlore préfère le SVG quand un schéma correspond, sinon garde Mermaid", () => {
  const texte = "Avant.\n```mermaid\nflowchart LR\na --> b\n```\nAprès.";
  const avecSchema = renderToStaticMarkup(<MarkdownFlore texte={texte} schemas={[schemaSimple]} />);
  expect(avecSchema).toContain('data-testid="schema-svg"');
  expect(avecSchema).not.toContain('data-testid="schema-mermaid"');

  const sansSchema = renderToStaticMarkup(<MarkdownFlore texte={texte} schemas={[]} />);
  expect(sansSchema).toContain('data-testid="schema-mermaid"');
  expect(sansSchema).not.toContain('data-testid="schema-svg"');
});

test("les schémas suivent l'ordre des blocs Mermaid, avec repli bloc par bloc", () => {
  const texte = [
    "```mermaid", "flowchart LR", "a --> b", "```",
    "```mermaid", "flowchart LR", "b --> c", "```",
  ].join("\n");
  const premier = { ...schemaSimple, titre: "Premier" };
  const second = { ...schemaSimple, titre: "Second" };
  const html = renderToStaticMarkup(<MarkdownFlore texte={texte} schemas={[premier, second]} />);
  expect(html.indexOf("Premier")).toBeGreaterThan(-1);
  expect(html.indexOf("Premier")).toBeLessThan(html.indexOf("Second"));

  // Un schéma invalide consomme quand même son rang : le bloc suivant reste associé au bon schéma.
  const mixte = renderToStaticMarkup(<MarkdownFlore texte={texte} schemas={[null, second]} />);
  expect(mixte).toContain('data-testid="schema-mermaid"');
  expect(mixte).toContain('data-testid="schema-svg"');
  expect(mixte).toContain("Second");
});

test("un message de Flore rend le SVG du schéma, pas le Mermaid", () => {
  const message = {
    role: "flore", texte: "Avant.\n```mermaid\nflowchart LR\na --> b\n```\nAprès.",
    schemas: [schemaSimple], versions: [{}], version: 0, preuves: [],
  };
  const html = renderToStaticMarkup(<MessageFlore message={message} index={0} prefixe="/cases/c1" />);
  expect(html).toContain('data-testid="schema-svg"');
  expect(html).toContain('data-testid="schema-svg-cadre"');
  expect(html).toContain("overflow-x-auto");
  expect(html).not.toContain('data-testid="schema-mermaid"');
});

test("MessageFlore et CorpsMessageFlore transmettent les schémas du message au Markdown", () => {
  const message = lire("components/MessageFlore.jsx");
  expect(message).toContain("schemas={message.schemas}");
  expect(message).toContain("<SchemasContexte.Provider value={message.schemas || []}>");
  const travail = lire("components/case/OngletTravail.jsx");
  expect(travail).toContain("schemas={message.schemas}");
});

const schemaProposition = {
  ...schemaSimple,
  mode: "proposition",
  hypotheses: ["Le portail reste stable", "Les statuts partent chaque nuit"],
  hors_scope: ["Application mobile", "Facturation"],
  fleches: [
    { de: "a", vers: "b", libelle: "ouvre", etat: "propose" },
    { de: "b", vers: "c", libelle: "publie", etat: "propose" },
  ],
};

test("l'état propose est orange, pointillé et fin", () => {
  const html = renderToStaticMarkup(<SchemaSvg schema={schemaProposition} />);
  expect(html).toContain('stroke="#F2B84B"');
  expect(html).toContain('stroke-width="1.5"');
  expect(html).toContain('stroke-dasharray="3 3"');
});

test("une proposition est étiquetée et expose hypothèses et hors-scope dans son accessibilité", () => {
  const html = renderToStaticMarkup(<SchemaSvg schema={schemaProposition} />);
  expect(html).toContain('data-mode="proposition"');
  expect(html).toMatch(/aria-label="[^"]*Proposition/);
  expect(html).toContain('data-testid="schema-badge-proposition"');
  expect(html).toContain(">Proposition</span>");
  expect(html).toMatch(/<desc[^>]*>[^<]*Hypothèses : Le portail reste stable ; Les statuts partent chaque nuit\./);
  expect(html).toMatch(/<desc[^>]*>[^<]*Hors scope : Application mobile ; Facturation\./);
});

test("une conception sans bloc Mermaid rend quand même son schéma", () => {
  const html = renderToStaticMarkup(<MarkdownFlore texte="Voici la conception proposée." schemas={[schemaProposition]} />);
  expect(html).toContain("Voici la conception proposée.");
  expect((html.match(/data-testid="schema-svg"/g) || [])).toHaveLength(1);
  expect(html).not.toContain('data-testid="schema-mermaid"');
  expect(html).toContain('data-testid="schema-badge-proposition"');
});

test("un message avec Mermaid ne rend pas le schéma une seconde fois", () => {
  const texte = "Avant.\n```mermaid\nflowchart LR\na --> b\n```\nAprès.";
  const html = renderToStaticMarkup(<MarkdownFlore texte={texte} schemas={[schemaSimple]} />);
  expect((html.match(/data-testid="schema-svg"/g) || [])).toHaveLength(1);
  expect(html).not.toContain('data-testid="schema-mermaid"');
});

test("MessageFlore signale une proposition par un badge discret, sans pastille de preuve", () => {
  const message = {
    role: "flore", texte: "Conception proposée.", schemas: [schemaProposition],
    proposition: { label: "Valider la conception" }, versions: [{}], version: 0, preuves: [],
  };
  const html = renderToStaticMarkup(<MessageFlore message={message} index={0} prefixe="/cases/c1" />);
  expect(html).toContain('data-testid="message-proposition"');
  expect(html).toContain("Proposition");
  expect(html).not.toContain('data-testid="pastille-');

  const sans = renderToStaticMarkup(<MessageFlore message={{ ...message, proposition: undefined }} index={0} prefixe="/cases/c1" />);
  expect(sans).not.toContain('data-testid="message-proposition"');
});
