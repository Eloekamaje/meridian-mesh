import { decouperMermaid } from "./segmentsMermaid";

test("texte, schéma complet, texte", () => {
  expect(decouperMermaid("Avant\n```mermaid\nflowchart LR\na --> b\n```\nAprès")).toEqual([
    { type: "texte", texte: "Avant\n" },
    { type: "mermaid", code: "flowchart LR\na --> b", complet: true },
    { type: "texte", texte: "\nAprès" },
  ]);
});

test("schéma en train de s'écrire, ou aucun schéma", () => {
  expect(decouperMermaid("A\n```mermaid\nflowchart LR\na -")).toEqual([
    { type: "texte", texte: "A\n" }, { type: "mermaid", code: "flowchart LR\na -", complet: false }]);
  expect(decouperMermaid("Rien")).toEqual([{ type: "texte", texte: "Rien" }]);
});
