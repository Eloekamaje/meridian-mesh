import { brouillonLisible } from "./fluxFlore";

test("le brouillon s'affiche sans citations ni schéma à la main", () => {
  expect(brouillonLisible("Elle publie (`app/routes.py#L64-L64`) un article `a.py#L3`.")).toBe("Elle publie un article.");
  expect(brouillonLisible("Voici\n```mermaid\nflowchart LR\na --> b")).toBe("Voici\n");
});
