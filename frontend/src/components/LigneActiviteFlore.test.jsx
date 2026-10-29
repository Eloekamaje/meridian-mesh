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

const consultation = (jumeau, extra = {}) => ({ label: "Je consulte l'application concernée…", status: "running",
  outil: { id: `c-${jumeau}`, nom: "consulter_jumeau", etat: "en_cours", debut: Date.now() - 14000, arguments: { jumeau, mission: "Si Conduit tombe ?" }, ...extra } });

test("jumeaux consultés en parallèle : une ligne par jumeau, ses outils dessous, le bilan quand il a fini", () => {
  const ops = [
    consultation("conduit", { etat: "fait", duree: 16, mission: { etat: "fait", confiance: "elevee", preuves: 3, constat: "Tout repose sur une base." } }),
    consultation("gestion-des-articles"),
    { label: "Je lis le code concerné…", status: "running", outil: { id: "u1", nom: "lire_code", etat: "en_cours", parent: "gestion-des-articles", arguments: { chemin: "app/utils.py" }, debut: Date.now() } },
  ];
  const html = renderToStaticMarkup(<LigneActiviteFlore activite={{ id: "a", status: "running", ops }} />);
  expect(html).toContain("2 jumeaux consultés · 1 terminé");
  expect(html).toContain("conduit");
  expect(html).toContain("confiance élevée · 3 preuves");
  expect(html).toContain("app/utils.py");
  expect(html.match(/data-testid="flore-activite-consultation-/g)).toHaveLength(2);
});
