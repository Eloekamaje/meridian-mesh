import { renderToStaticMarkup } from "react-dom/server";
import LigneActiviteFlore from "./LigneActiviteFlore";

const outil = (etat, extra = {}) => ({ label: "Je lis le code concerné…", status: etat === "en_cours" ? "running" : "done",
  outil: { id: "u1", nom: "lire_code", etat, arguments: { chemin: "articles.py" }, duree: 0.12, ...extra } });

test("en cours avec des outils : une ligne par outil, dépliée, avec nom et argument", () => {
  const html = renderToStaticMarkup(<LigneActiviteFlore activite={{ id: "a", status: "running", ops: [outil("en_cours")] }} />);
  expect(html).toContain("lire_code");
  expect(html).toContain("articles.py");
  expect(html).toContain("en cours…");
});

test("terminée : repliée, « Analyse terminée », les outils ne s'affichent qu'au clic", () => {
  const html = renderToStaticMarkup(<LigneActiviteFlore activite={{ id: "a", status: "done", ops: [outil("fait")] }} />);
  expect(html).toContain("Analyse terminée");
  expect(html).not.toContain("lire_code");
});
