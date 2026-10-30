// Une citation de pièce (`pièce:<id>#<section>`) devient un lien interne qui ouvre la section source,
// jamais une navigation vers une URL inventée ni un bouton décoratif.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";
import { ciblePiece, ImageFlore, lierCitations, LienPiece } from "../components/MarkdownFlore";
import PanneauPiece from "../components/case/PanneauPiece";
import api from "../lib/api";

jest.mock("react-markdown", () => ({ __esModule: true, default: () => null, defaultUrlTransform: (url) => url }));
jest.mock("remark-gfm", () => () => {});
jest.mock("remark-math", () => () => {});
jest.mock("rehype-katex", () => () => {});
jest.mock("rehype-highlight", () => () => {});
jest.mock("sonner", () => ({ toast: { success: jest.fn() } }));
jest.mock("../components/SchemaMermaid", () => () => null);
jest.mock("../lib/api", () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

const lire = (f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8");

test("les citations entre accents graves ou nues deviennent des liens internes, sans casser le Markdown", () => {
  expect(lierCitations("D'après `pièce:p1#s2`, la règle s'applique."))
    .toBe("D'après [§](meridian-piece:p1#s2), la règle s'applique.");
  expect(lierCitations("Voir pièce:p1#document.")).toBe("Voir [§](meridian-piece:p1#document).");
  // Un lien normal et un bloc de code restent intacts ; une citation hors bloc est convertie.
  expect(lierCitations("[doc](https://exemple.test) et pièce:p1#s2"))
    .toBe("[doc](https://exemple.test) et [§](meridian-piece:p1#s2)");
  expect(lierCitations("```\npièce:p1#s2\n```\npièce:p1#s2"))
    .toBe("```\npièce:p1#s2\n```\n[§](meridian-piece:p1#s2)");
  // Une citation de tableau n'est pas une section : elle reste du texte, avec ou sans accents graves.
  expect(lierCitations("Voir pièce:p1#table:t2 pour le détail.")).toBe("Voir pièce:p1#table:t2 pour le détail.");
  expect(lierCitations("Voir `pièce:p1#table:t2`.")).toBe("Voir `pièce:p1#table:t2`.");
  // Une section ordinaire suivie de deux-points reste bien un lien.
  expect(lierCitations("Pièce:p1#s2: la règle s'applique.")).toBe("[§](meridian-piece:p1#s2): la règle s'applique.");
});

test("LienPiece empêche la navigation et appelle onOuvrirPiece avec la pièce et la section", async () => {
  const appels = [];
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<LienPiece href="meridian-piece:p1#s2" onOuvrirPiece={(cible) => appels.push(cible)}>§</LienPiece>);
  });
  const lien = hote.querySelector('[data-testid="lien-piece"]');
  expect(lien).not.toBeNull();
  expect(lien.getAttribute("data-piece-id")).toBe("p1");
  expect(lien.getAttribute("data-section-id")).toBe("s2");
  await act(async () => {
    lien.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  expect(appels).toEqual([{ pieceId: "p1", sectionId: "s2" }]);
  await act(async () => { racine.unmount(); });
});

test("LienPiece sans geste d'ouverture reste un texte, jamais un faux lien", () => {
  const html = renderToStaticMarkup(<LienPiece href="meridian-piece:p1#s2">§</LienPiece>);
  expect(html).not.toContain("<a");
  expect(html).toContain('data-testid="lien-piece-inactif"');
  expect(html).toContain("§");
  // Le texte fourni (et non « § ») est conservé pour un lien mort.
  const personnalise = renderToStaticMarkup(<LienPiece href="meridian-piece:p1#s2">section 2</LienPiece>);
  expect(personnalise).not.toContain("<a");
  expect(personnalise).toContain("section 2");
});

test("une URL interne incomplète ou un identifiant invalide n'ouvre aucune section", () => {
  expect(ciblePiece("meridian-piece:p1#s2")).toEqual({ pieceId: "p1", sectionId: "s2" });
  expect(ciblePiece("meridian-piece:p_1-2#section_3")).toEqual({ pieceId: "p_1-2", sectionId: "section_3" });
  expect(ciblePiece("meridian-piece:p1")).toBeNull();
  expect(ciblePiece("meridian-piece:#s2")).toBeNull();
  expect(ciblePiece("https://exemple.test")).toBeNull();
  // Le décodage précède la validation : un identifiant encodé ne contourne jamais la liste blanche.
  expect(ciblePiece("meridian-piece:%3Cscript%3E#s2")).toBeNull();
  expect(ciblePiece("meridian-piece:p1#a%20b")).toBeNull();
  expect(ciblePiece("meridian-piece:p1#s2%2F..%2Fadmin")).toBeNull();
  expect(ciblePiece("meridian-piece:p1%00#s2")).toBeNull();
});

test("MarkdownFlore branche le rendu des liens et passe le geste à ses liens de pièce", () => {
  const source = lire("components/MarkdownFlore.jsx");
  expect(source).toContain("export function lierCitations");
  expect(source).toContain("export function LienPiece");
  expect(source).toContain("const propre = lierCitations(couperPastille(texte))");
  expect(source).toContain("a: (p) => <LienMarkdown {...p} onOuvrirPiece={onOuvrirPiece} />");
  // Le schéma interne doit être autorisé par react-markdown, qui bloque par défaut les protocoles inconnus.
  expect(source).toContain("defaultUrlTransform");
  expect(source).toContain("urlTransform={transformerUrl}");
  expect(source).toContain('rel: "noopener noreferrer"');
  expect(source).not.toContain("dangerouslySetInnerHTML");
  expect(source).not.toContain('from "rehype-raw"');
  expect(source).toContain("img: (p) => <ImageFlore {...p} />");
});

test("aucune image distante n'est chargée automatiquement depuis une réponse", () => {
  const distante = renderToStaticMarkup(<ImageFlore src="https://exemple.test/schema.png" alt="Schéma" />);
  expect(distante).not.toContain("<img");
  expect(distante.replace(/<[^>]+>/g, "")).toContain("Image : Schéma");
  expect(distante).toContain('target="_blank"');
  expect(distante).toContain('rel="noopener noreferrer"');
  expect(distante).toContain("non chargée automatiquement");

  // Une URL protocol-relative est distante elle aussi : aucun chargement, seulement un lien manuel.
  const protocoleRelatif = renderToStaticMarkup(<ImageFlore src="//cdn.exemple.test/logo.png" alt="Logo" />);
  expect(protocoleRelatif).not.toContain("<img");
  expect(protocoleRelatif.replace(/<[^>]+>/g, "")).toContain("Image : Logo");

  // Les images embarquées en data: (raster et base64) restent affichables, sans requête réseau.
  const data = renderToStaticMarkup(<ImageFlore src="data:image/png;base64,iVBORw0KGgo=" alt="pixel" />);
  expect(data).toContain("<img");
  expect(data).toContain("data:image/png;base64");

  // Un data: SVG peut référencer des ressources : il reste du texte.
  const svg = renderToStaticMarkup(<ImageFlore src="data:image/svg+xml;base64,PHN2Zz4=" alt="svg" />);
  expect(svg).not.toContain("<img");

  const source = lire("components/MarkdownFlore.jsx");
  expect(source).toContain("RE_IMAGE_DISTANTE");
  expect(source).toContain("RE_IMAGE_DATA");
});

test("MessageFlore transmet onOuvrirPiece au Markdown du corps et à ses enfants", () => {
  const source = lire("components/MessageFlore.jsx");
  expect(source).toContain("onOuvrirPiece");
  expect(source).toContain("cloneElement(corps, { onOuvrirPiece");
  expect(source).toContain("<MarkdownFlore texte={message.texte} onOuvrirPiece={onOuvrirPiece} />");
});

test("le panneau de pièce charge la section par l'API encodée, affiche le texte et se ferme pour de vrai", () => {
  const source = lire("components/case/PanneauPiece.jsx");
  expect(source).toContain("api.get(`/cases/${encodeURIComponent(casId)}/pieces/${encodeURIComponent(pieceId)}/sections/${encodeURIComponent(sectionId)}`)");
  expect(source).toContain('data-testid="panneau-piece"');
  expect(source).toContain('data-testid="panneau-piece-fermer"');
  expect(source).toContain('data-testid="panneau-piece-texte"');
  expect(source).toContain("section.tronque");
  expect(source).toContain("onFermer");
  expect(source).toContain('aria-modal="true"');
  // Aucun bouton factice : en chargement, la seule action est la fermeture.
  const html = renderToStaticMarkup(<PanneauPiece casId="c1" pieceId="p1" sectionId="s2" onFermer={() => {}} />);
  expect(html).toContain('data-testid="panneau-piece"');
  expect(html).toContain('data-testid="panneau-piece-fermer"');
  expect(html.match(/<button/g)).toHaveLength(1);
});

test("le panneau piège le focus puis le rend au déclencheur à la fermeture", async () => {
  api.get.mockResolvedValue({ data: { nom: "Pièce", titre: "Section", texte: "Le texte." } });
  const declencheur = document.createElement("button");
  declencheur.textContent = "ouvrir la citation";
  document.body.appendChild(declencheur);
  declencheur.focus();

  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<PanneauPiece casId="c1" pieceId="p1" sectionId="s2" onFermer={() => {}} />);
  });

  const panneau = document.querySelector('[data-testid="panneau-piece"]');
  const fermer = document.querySelector('[data-testid="panneau-piece-fermer"]');
  expect(panneau.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(fermer);

  // Tab et Shift+Tab restent dans le panneau, même quand la fermeture est le seul élément focusable.
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  await act(async () => { fermer.dispatchEvent(tab); });
  expect(tab.defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(fermer);
  const shiftTab = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
  await act(async () => { fermer.dispatchEvent(shiftTab); });
  expect(shiftTab.defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(fermer);

  await act(async () => { racine.unmount(); });
  expect(document.activeElement).toBe(declencheur);

  hote.remove();
  declencheur.remove();
});

test("le Travail ouvre le panneau depuis une citation et le referme au changement de travail", () => {
  const source = lire("components/case/OngletTravail.jsx");
  expect(source).toContain("PanneauPiece");
  expect(source).toContain("const [pieceInspectee, setPieceInspectee] = useState(null)");
  expect(source).toContain("useEffect(() => { setPieceInspectee(null); }, [cas?.id])");
  expect(source).toContain("onOuvrirPiece={setPieceInspectee}");
  expect(source).toContain("<PanneauPiece");
  expect(source).toContain("onOuvrirPiece={onOuvrirPiece}");
});
